"""Offline mocked tests for the independently gated Cloudflare-only capture runner."""
import copy
import json
import os
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from api.investigation_classifier import (
    _query_classifier, classification_system_prompt,
)
from api.management.commands.audit_investigation_classification import DEFAULT_CORPUS
from api.verification.classification_capture_plan import (
    build_capture_plan, write_private_capture_package,
)
from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
)
from api.verification.cloudflare_classification_capture import (
    CONFIRMATION, JOURNAL_NAME, LIVE_ENV, RAW_OUTPUT_NAME, SCORE_OUTPUT_NAME,
    execute_direct_cloudflare_capture, validate_cloudflare_packet,
)
from api.verification.cloudflare_evaluation import DEFAULT_MODEL


def valid_abstain():
    return json.dumps({"decision": "ABSTAIN", "domains": []})


@override_settings(APP_ENV="development", DEBUG=True)
class DirectCloudflareClassificationCaptureTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.approved = copy.deepcopy(load_classification_corpus(DEFAULT_CORPUS))
        for case in self.approved:
            case["review"] = {
                "status": "APPROVED",
                "reviewer": "Synthetic offline test reviewer",
                "notes": "Unit-test data only; not claimed as a real review.",
            }
        self.corpus = self.root / "approved.json"
        self.corpus.write_text(json.dumps({
            "schema_version": 1, "cases": self.approved,
        }), encoding="utf-8")
        self.plan = build_capture_plan(
            self.approved, provider="cloudflare",
            model_id=DEFAULT_MODEL, limit=4,
        )
        self.packet = write_private_capture_package(
            self.plan, self.root / "cloudflare-packet",
        )
        self.http = self.enterContext(patch(
            "api.verification.cloudflare_evaluation.requests.post",
        ))
        self.live_env = self.enterContext(patch.dict(os.environ, {
            LIVE_ENV: "1",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "offline-test-credential",
        }))

    def _http_content(self, value):
        self.http.return_value.status_code = 200
        self.http.return_value.json.return_value = {
            "choices": [{
                "message": {"content": value},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 185,
                "completion_tokens": 105,
                "total_tokens": 290,
            },
        }

    def _live(self):
        return execute_direct_cloudflare_capture(
            self.corpus, self.packet,
            execute_live=True, confirmation=CONFIRMATION,
        )

    def _read(self, filename):
        return json.loads((self.packet / filename).read_text(encoding="utf-8"))

    def test_default_cli_is_dry_run_and_never_calls_provider(self):
        output = StringIO()
        call_command(
            "capture_investigation_classification_cloudflare",
            "--corpus", str(self.corpus),
            "--packet-dir", str(self.packet),
            "--json-summary", stdout=output,
        )
        summary = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(summary["status"], "DRY_RUN_READY_NO_PROVIDER_CALLS")
        self.assertEqual(summary["planned_requests"], 4)
        self.assertEqual(summary["model_id"], DEFAULT_MODEL)
        self.assertTrue(summary["system_prompt_sha256"])
        self.assertFalse(summary["fallback_enabled"])
        self.assertFalse(summary["enforcement_approved"])
        self.assertFalse((self.packet / JOURNAL_NAME).exists())
        self.http.assert_not_called()

    def test_cli_live_without_exact_confirmation_fails_closed(self):
        with self.assertRaises(CommandError):
            call_command(
                "capture_investigation_classification_cloudflare",
                "--corpus", str(self.corpus),
                "--packet-dir", str(self.packet),
                "--execute-live", stdout=StringIO(),
            )
        self.http.assert_not_called()
        self.assertFalse((self.packet / "cloudflare_capture.lock").exists())

    def test_missing_dev_environment_opt_in_denies_live(self):
        with patch.dict(os.environ, {LIVE_ENV: "0"}):
            with self.assertRaises(ClassificationAuditError):
                self._live()
        self.http.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_production_setting_denies_live_even_with_confirmation(self):
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.http.assert_not_called()

    def test_pending_corpus_refused_even_for_dry_run(self):
        with self.assertRaises(ClassificationAuditError):
            validate_cloudflare_packet(DEFAULT_CORPUS, self.packet)
        self.http.assert_not_called()

    def test_manifest_tampering_refused_before_live_call(self):
        path = self.packet / "capture_inputs.json"
        for altered in (
            ("claim", lambda m: m["requests"][0].update(claim_text="A changed claim")),
            ("model", lambda m: m.update(model_id="NOT_SELECTED")),
            ("budget", lambda m: m.update(planned_requests=5)),
            ("order", lambda m: m["requests"].reverse()),
        ):
            with self.subTest(change=altered[0]):
                manifest = copy.deepcopy(self.plan)
                altered[1](manifest)
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ClassificationAuditError):
                    self._live()
                self.http.assert_not_called()
        path.write_text(json.dumps(self.plan), encoding="utf-8")

    def test_prompt_is_identical_to_live_classifier_prompt(self):
        with patch("api.services.call_llm_with_fallback",
                   return_value=valid_abstain()) as fallback:
            self.assertEqual(_query_classifier("A lengthy ambiguous sample claim."),
                             {"decision": "ABSTAIN", "domains": []})
        self.assertEqual(fallback.call_args.args[0], classification_system_prompt())
        summary = execute_direct_cloudflare_capture(self.corpus, self.packet)
        self.assertEqual(
            summary["system_prompt_sha256"],
            __import__("hashlib").sha256(
                fallback.call_args.args[0].encode("utf-8")
            ).hexdigest(),
        )
        self.http.assert_not_called()

    def test_four_valid_capture_attempts_are_single_provider_and_nonreplayable(self):
        # Real adapter request construction but locally mocked HTTP transport.
        self._http_content(valid_abstain())
        with patch("api.services.call_llm_with_fallback") as fallback:
            result = self._live()
        self.assertEqual(result["attempted_requests"], 4)
        self.assertEqual(result["valid_responses"], 4)
        self.assertEqual(result["captured_predictions"], 4)
        self.assertFalse(result["stopped_early"])
        self.assertEqual(self.http.call_count, 4)
        fallback.assert_not_called()
        for call, case in zip(self.http.call_args_list, self.plan["requests"]):
            kwargs = call.kwargs
            self.assertEqual(kwargs["json"]["model"], DEFAULT_MODEL)
            self.assertEqual(kwargs["json"]["messages"][0]["content"],
                             classification_system_prompt())
            self.assertEqual(kwargs["json"]["messages"][1]["content"],
                             case["claim_text"])
            self.assertEqual(kwargs["json"]["temperature"], 0.1)
            self.assertEqual(kwargs["json"]["max_tokens"], 1024)
            self.assertEqual(kwargs["json"]["response_format"],
                             {"type": "json_object"})
            self.assertEqual(kwargs["json"]["options"],
                             {"rejectIfBusy": True})
            self.assertIs(kwargs["json"]["stream"], False)
            self.assertEqual(kwargs["timeout"], (3, 30))
            self.assertNotIn("retry", kwargs["json"])
        raw = self._read(RAW_OUTPUT_NAME)
        score = self._read(SCORE_OUTPUT_NAME)
        self.assertEqual(len(raw["results"]), 4)
        self.assertEqual(len(score["predictions"]), 4)
        self.assertTrue(all(r["raw_response"] == valid_abstain()
                            for r in raw["results"]))
        self.assertTrue(all(a["status"] == "CAPTURED_VALID"
                            for a in self._read(JOURNAL_NAME)["attempts"]))
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.assertEqual(self.http.call_count, 4)

    def test_invalid_json_is_preserved_unmodified_and_stops_early(self):
        raw_invalid = "this is NOT JSON; preserve its exact bytes as text"
        self._http_content(raw_invalid)
        report = self._live()
        self.assertEqual(report["attempted_requests"], 1)
        self.assertTrue(report["stopped_early"])
        self.assertEqual(self._read(RAW_OUTPUT_NAME)["results"][0]["raw_response"],
                         raw_invalid)
        self.assertEqual(self._read(SCORE_OUTPUT_NAME)["predictions"][0]["raw_response"],
                         raw_invalid)
        attempts = self._read(JOURNAL_NAME)["attempts"]
        self.assertEqual(attempts[0]["status"], "CAPTURED_INVALID_CONTRACT")
        self.assertFalse(attempts[0]["valid_contract"])
        self.http.assert_called_once()

    def test_timeout_stops_without_groq_or_gemini_fallback(self):
        self.http.side_effect = requests.exceptions.ReadTimeout(
            "secret vendor details must not leak",
        )
        with patch("api.services.call_llm_with_fallback") as fallback:
            report = self._live()
        self.assertEqual(report["attempted_requests"], 1)
        self.assertEqual(report["captured_predictions"], 0)
        self.assertTrue(report["stopped_early"])
        record = self._read(JOURNAL_NAME)["attempts"][0]
        self.assertEqual(record["status"], "PROVIDER_FAILED")
        self.assertEqual(record["error_code"], "TRANSPORT_ReadTimeout")
        self.assertNotIn("secret vendor details",
                         (self.packet / JOURNAL_NAME).read_text())
        self.http.assert_called_once()
        fallback.assert_not_called()

    def test_too_long_raw_response_retained_but_not_accepted_by_scorer(self):
        long_invalid = "x" * 8001
        self._http_content(long_invalid)
        report = self._live()
        self.assertEqual(report["attempted_requests"], 1)
        self.assertEqual(report["captured_predictions"], 0)
        self.assertEqual(self._read(RAW_OUTPUT_NAME)["results"][0]["raw_response"],
                         long_invalid)
        self.assertEqual(self._read(SCORE_OUTPUT_NAME)["predictions"], [])
        self.assertEqual(
            self._read(JOURNAL_NAME)["attempts"][0]["status"],
            "CAPTURED_TOO_LARGE_TO_SCORE",
        )

    def test_packet_can_never_be_replayed_after_partial_capture(self):
        self.http.side_effect = requests.exceptions.ConnectionError("offline")
        self._live()
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.http.assert_called_once()
