"""Offline-only tests for the separate one-case Cloudflare-03 diagnostic."""
import copy
import hashlib
import json
import os
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from api.investigation_classifier import classification_system_prompt
from api.management.commands.audit_investigation_classification import DEFAULT_CORPUS
from api.verification.classification_capture_plan import (
    build_capture_plan, write_private_capture_package,
)
from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
    load_classification_predictions, score_classification_predictions,
)
from api.verification.cloudflare_classification_diagnostic import (
    CASE_ID, CONFIRMATION, DIAGNOSTIC_PROFILE, HTTP_TIMEOUT, JOURNAL_FILE,
    LIVE_ENV, LOCK_FILE, MAX_COMPLETION_TOKENS, PREDICTIONS_FILE, RAW_FILE,
    execute_diagnostic, prepare_private_diagnostic, validate_diagnostic_packet,
)
from api.verification.cloudflare_evaluation import DEFAULT_MODEL


VALID_CLASSIFICATION = json.dumps({
    "decision": "CLASSIFY",
    "domains": [
        {"code": "SCIENCE", "evidence": "scientists would analyze data"},
        {"code": "TECHNOLOGY", "evidence": "Falcon Heavy rocket launch"},
    ],
})


@override_settings(APP_ENV="development", DEBUG=True)
class Cloudflare4096DiagnosticTests(SimpleTestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(TemporaryDirectory()))
        self.cases = copy.deepcopy(load_classification_corpus(DEFAULT_CORPUS))
        for case in self.cases:
            case["review"] = {
                "status": "APPROVED", "reviewer": "Synthetic mocked test reviewer",
                "notes": "Only for mocked test data; not a real review signoff.",
            }
        self.corpus = self.temp / "approved.json"
        self.corpus.write_text(json.dumps({
            "schema_version": 1, "cases": self.cases,
        }), encoding="utf-8")
        self.packet = self.temp / "Cloudflare-03"
        self.plan_result = prepare_private_diagnostic(self.corpus, self.packet)
        self.post = self.enterContext(patch(
            "api.verification.cloudflare_evaluation.requests.post",
        ))
        self.enterContext(patch.dict(os.environ, {
            LIVE_ENV: "1",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "mock-only-not-real",
        }))

    def _mock_content(self, content, *, finish="stop", reasoning="mock private reasoning"):
        self.post.return_value.status_code = 200
        self.post.return_value.json.return_value = {
            "choices": [{
                "message": {
                    "content": content,
                    "reasoning_content": reasoning,
                },
                "finish_reason": finish,
            }],
            "usage": {
                "prompt_tokens": 176,
                "completion_tokens": 2048,
                "total_tokens": 2224,
            },
        }

    def _live(self):
        return execute_diagnostic(
            self.corpus, self.packet,
            execute_live=True, confirmation=CONFIRMATION,
        )

    def _read(self, name):
        return json.loads((self.packet / name).read_text(encoding="utf-8"))

    def test_prepare_creates_single_case_4096_without_network(self):
        self.assertEqual(self.plan_result["planned_requests"], 1)
        self.assertEqual(self.plan_result["max_completion_tokens"], 4096)
        self.assertEqual(self.plan_result["case_ids"], [CASE_ID])
        self.assertEqual(self.plan_result["provider_calls"], 0)
        plan = self._read("capture_inputs.json")
        self.assertEqual(plan["diagnostic_profile"], DIAGNOSTIC_PROFILE)
        self.assertEqual(plan["max_output_tokens"], MAX_COMPLETION_TOKENS)
        self.assertEqual(plan["http_timeout_read_inactivity_sec"], 45)
        self.assertEqual(len(plan["requests"]), 1)
        self.assertEqual(plan["requests"][0]["case_id"], CASE_ID)
        self.assertNotIn("draft_expected", json.dumps(plan))
        self.assertNotIn("review", json.dumps(plan))
        self.assertEqual(self._read("predictions.json")["predictions"], [])
        self.post.assert_not_called()

    def test_dry_run_is_read_only_and_fingerprints_real_prompt(self):
        result = execute_diagnostic(self.corpus, self.packet)
        self.assertEqual(result["status"], "DRY_RUN_READY_NO_PROVIDER_CALLS")
        self.assertEqual(result["planned_requests"], 1)
        self.assertEqual(result["max_completion_tokens"], 4096)
        self.assertEqual(result["http_timeout_read_inactivity_sec"], 45)
        self.assertEqual(
            result["system_prompt_sha256"],
            hashlib.sha256(classification_system_prompt().encode()).hexdigest(),
        )
        self.assertFalse(result["fallback_enabled"])
        self.assertFalse(result["retry_enabled"])
        self.assertFalse(result["enforcement_approved"])
        self.assertFalse((self.packet / LOCK_FILE).exists())
        self.assertFalse((self.packet / JOURNAL_FILE).exists())
        self.post.assert_not_called()

    def test_default_cli_summary_is_one_json_object(self):
        out = StringIO()
        call_command(
            "capture_cloudflare_classification_diagnostic",
            "--corpus", str(self.corpus),
            "--packet-dir", str(self.packet),
            "--json-summary", stdout=out,
        )
        value = json.loads(out.getvalue())
        self.assertEqual(value["provider_calls"], 0)
        self.assertEqual(value["case_ids"], [CASE_ID])
        self.assertNotIn("NASA", out.getvalue())
        self.post.assert_not_called()

    def test_prepare_cli_writes_new_folder_no_network(self):
        target = self.temp / "Cloudflare-04-prep"
        out = StringIO()
        call_command(
            "prepare_cloudflare_classification_diagnostic",
            "--corpus", str(self.corpus),
            "--export-dir", str(target),
            "--json-summary", stdout=out,
        )
        value = json.loads(out.getvalue())
        self.assertTrue(value["private_package_created"])
        self.assertEqual(value["planned_requests"], 1)
        self.assertEqual(value["provider_calls"], 0)
        self.assertTrue((target / "capture_inputs.json").is_file())
        self.post.assert_not_called()

    def test_pending_fixture_and_reexport_refused(self):
        with self.assertRaises(ClassificationAuditError):
            prepare_private_diagnostic(DEFAULT_CORPUS, self.temp / "pending")
        with self.assertRaises(ClassificationAuditError):
            prepare_private_diagnostic(self.corpus, self.packet)
        self.post.assert_not_called()

    def test_cloudflare_02_four_case_package_is_not_usable(self):
        original = build_capture_plan(
            self.cases, provider="cloudflare", model_id=DEFAULT_MODEL,
            limit=4,
        )
        four = write_private_capture_package(original, self.temp / "Cloudflare-02")
        with self.assertRaises(ClassificationAuditError):
            validate_diagnostic_packet(self.corpus, four)
        self.post.assert_not_called()

    def test_manifest_change_and_stale_template_refused_without_call(self):
        path = self.packet / "capture_inputs.json"
        good = self._read("capture_inputs.json")
        for change in (
            lambda p: p.update(max_output_tokens=1024),
            lambda p: p.update(diagnostic_profile="not_this_profile"),
            lambda p: p["requests"][0].update(claim_text="altered input"),
            lambda p: p.update(planned_requests=2),
        ):
            data = copy.deepcopy(good)
            change(data)
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ClassificationAuditError):
                self._live()
            self.post.assert_not_called()
        path.write_text(json.dumps(good), encoding="utf-8")
        pred = self.packet / "predictions.json"
        pred.write_text(json.dumps({
            "schema_version": 1, "predictions": [{"case_id": CASE_ID,
                                                  "raw_response": "{}"}],
        }), encoding="utf-8")
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_not_called()

    def test_no_live_without_all_gates(self):
        with self.assertRaises(ClassificationAuditError):
            execute_diagnostic(self.corpus, self.packet, execute_live=True)
        with patch.dict(os.environ, {LIVE_ENV: "0"}):
            with self.assertRaises(ClassificationAuditError):
                self._live()
        self.assertFalse((self.packet / LOCK_FILE).exists())
        self.post.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_not_available_in_production(self):
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_not_called()

    def test_live_cli_requires_exact_confirmation(self):
        with self.assertRaises(CommandError):
            call_command(
                "capture_cloudflare_classification_diagnostic",
                "--corpus", str(self.corpus),
                "--packet-dir", str(self.packet),
                "--execute-live", stdout=StringIO(),
            )
        self.post.assert_not_called()

    def test_one_success_uses_4096_and_exact_prompt_never_falls_back(self):
        self._mock_content(VALID_CLASSIFICATION)
        with patch("api.services.call_llm_with_fallback") as fallback:
            outcome = self._live()
        self.assertEqual(outcome["attempted_requests"], 1)
        self.assertEqual(outcome["valid_responses"], 1)
        self.assertEqual(outcome["captured_predictions"], 1)
        self.post.assert_called_once()
        fallback.assert_not_called()
        kw = self.post.call_args.kwargs
        self.assertEqual(kw["json"]["model"], DEFAULT_MODEL)
        self.assertEqual(kw["json"]["max_tokens"], 4096)
        self.assertEqual(kw["json"]["temperature"], 0.1)
        self.assertEqual(kw["json"]["response_format"], {"type": "json_object"})
        self.assertEqual(kw["json"]["options"], {"rejectIfBusy": True})
        self.assertFalse(kw["json"]["stream"])
        self.assertEqual(kw["timeout"], HTTP_TIMEOUT)
        self.assertEqual(kw["json"]["messages"][0]["content"],
                         classification_system_prompt())
        self.assertEqual(kw["json"]["messages"][1]["content"],
                         self._read("capture_inputs.json")["requests"][0]["claim_text"])
        self.assertEqual(self._read(RAW_FILE)["results"][0]["raw_response"],
                         VALID_CLASSIFICATION)
        self.assertEqual(self._read(PREDICTIONS_FILE)["predictions"][0]["raw_response"],
                         VALID_CLASSIFICATION)
        journal = self._read(JOURNAL_FILE)
        self.assertEqual(journal["request_config"]["max_tokens"], 4096)
        self.assertEqual(journal["request_config"]["timeout_read_inactivity_sec"], 45)
        self.assertTrue(journal["attempts"][0]["usage"]["reasoning_present"])
        self.assertNotIn("mock private reasoning", (self.packet / JOURNAL_FILE).read_text())
        self.assertTrue((self.packet / LOCK_FILE).is_file())
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_called_once()

    def test_one_case_real_scorer_reports_31_missing_without_accuracy_rate(self):
        self._mock_content(VALID_CLASSIFICATION)
        self._live()
        predictions = load_classification_predictions(
            self.packet / PREDICTIONS_FILE, {c["id"] for c in self.cases},
        )
        result = score_classification_predictions(self.cases, predictions)
        self.assertEqual(result["approved"], 32)
        self.assertEqual(result["predicted"], 1)
        self.assertEqual(result["missing"], 31)
        self.assertFalse(result["coverage_complete"])
        self.assertIsNone(result["exact_match_rate"])
        self.assertFalse(result["eligible_for_automatic_enforcement"])

    def test_length_exhaustion_with_reasoning_records_sanitized_failure(self):
        self._mock_content("", finish="length", reasoning="DO NOT PERSIST")
        self.post.return_value.json.return_value["usage"]["completion_tokens"] = 4096
        result = self._live()
        self.assertEqual(result["attempted_requests"], 1)
        self.assertEqual(result["captured_predictions"], 0)
        attempt = self._read(JOURNAL_FILE)["attempts"][0]
        self.assertEqual(attempt["status"], "PROVIDER_FAILED")
        self.assertEqual(attempt["error_code"], "EMPTY_PROVIDER_RESPONSE")
        self.assertEqual(attempt["usage"]["finish_reason"], "length")
        self.assertEqual(attempt["usage"]["completion_tokens"], 4096)
        self.assertTrue(attempt["usage"]["reasoning_present"])
        self.assertNotIn("DO NOT PERSIST", (self.packet / JOURNAL_FILE).read_text())
        self.assertTrue((self.packet / LOCK_FILE).exists())
        self.post.assert_called_once()

    def test_invalid_response_is_preserved_as_raw_and_scorable_diagnostic(self):
        bad = "Not valid classification JSON"
        self._mock_content(bad)
        self._live()
        self.assertEqual(self._read(RAW_FILE)["results"][0]["raw_response"], bad)
        self.assertEqual(self._read(PREDICTIONS_FILE)["predictions"][0]["raw_response"], bad)
        self.assertEqual(self._read(JOURNAL_FILE)["attempts"][0]["status"],
                         "CAPTURED_INVALID_CONTRACT")

    def test_timeout_is_sanitized_no_retry_no_groq(self):
        self.post.side_effect = requests.exceptions.ReadTimeout(
            "private vendor error that must never be logged",
        )
        with patch("api.services.call_llm_with_fallback") as fallback:
            result = self._live()
        self.assertEqual(result["captured_predictions"], 0)
        self.post.assert_called_once()
        fallback.assert_not_called()
        attempt = self._read(JOURNAL_FILE)["attempts"][0]
        self.assertEqual(attempt["status"], "PROVIDER_FAILED")
        self.assertEqual(attempt["error_code"], "TRANSPORT_ReadTimeout")
        self.assertNotIn("private vendor error", (self.packet / JOURNAL_FILE).read_text())
        with self.assertRaises(ClassificationAuditError):
            self._live()

    def test_large_invalid_response_is_retained_only_in_private_raw(self):
        self._mock_content("x" * 8001)
        result = self._live()
        self.assertEqual(result["captured_predictions"], 0)
        self.assertEqual(len(self._read(RAW_FILE)["results"][0]["raw_response"]), 8001)
        self.assertEqual(self._read(PREDICTIONS_FILE)["predictions"], [])
        self.assertEqual(self._read(JOURNAL_FILE)["attempts"][0]["status"],
                         "CAPTURED_TOO_LARGE_TO_SCORE")

    def test_stale_writing_file_prevents_replaying_packet(self):
        (self.packet / (JOURNAL_FILE + ".writing")).write_text("interrupted")
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_not_called()
