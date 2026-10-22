"""Mocked 32-case Cloudflare subject-accuracy capture: never real network."""
import copy
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

from api.management.commands.audit_investigation_classification import DEFAULT_CORPUS
from api.verification.classification_capture_plan import build_capture_plan
from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
    load_classification_predictions, score_classification_predictions,
)
from api.verification.cloudflare_classification_accuracy_capture import (
    COMPLETION_TOKENS, CONFIRMATION, EXPECTED_PROMPT_SHA256, HTTP_TIMEOUT,
    JOURNAL_FILE, LIVE_ENV, LOCK_FILE, MAX_ATTEMPTS, OUTPUT_FILES,
    PREDICTIONS_FILE, PROFILE, RAW_FILE, accuracy_dry_run_summary,
    build_accuracy_plan, execute_accuracy_capture, prepare_private_accuracy_packet,
    validate_accuracy_packet,
)
from api.verification.cloudflare_evaluation import DEFAULT_MODEL
from api.investigation_classifier import classification_system_prompt


ABSTAIN = '{"decision":"ABSTAIN","domains":[]}'
CROSS_VALID = json.dumps({
    "decision": "CLASSIFY", "domains": [
        {"code": "SCIENCE", "evidence": "scientists would analyze data"},
        {"code": "TECHNOLOGY", "evidence": "Falcon Heavy rocket launch"},
    ],
})


@override_settings(APP_ENV="development", DEBUG=True)
class Cloudflare32AccuracyTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        cases = copy.deepcopy(load_classification_corpus(DEFAULT_CORPUS))
        for c in cases:
            c["review"] = {
                "status": "APPROVED",
                "reviewer": "Unit test reviewer only",
                "notes": "Synthetic test-only approval; NOT human reference data.",
            }
        self.cases = cases
        self.corpus = self.root / "approved_mock.json"
        self.corpus.write_text(json.dumps({
            "schema_version": 1, "cases": cases,
        }), encoding="utf-8")
        fake_hash = build_capture_plan(
            cases, provider="cloudflare", model_id=DEFAULT_MODEL,
            limit=32, case_ids=[c["id"] for c in cases],
        )["corpus_sha256"]
        self.enterContext(patch(
            "api.verification.cloudflare_classification_accuracy_capture.EXPECTED_CORPUS_SHA256",
            fake_hash,
        ))
        self.packet = self.root / "private_accuracy_01"
        self.prepared = prepare_private_accuracy_packet(self.corpus, self.packet)
        self.post = self.enterContext(patch(
            "api.verification.cloudflare_evaluation.requests.post",
        ))
        self.fallback = self.enterContext(patch(
            "api.services.call_llm_with_fallback",
        ))
        self.enterContext(patch.dict(os.environ, {
            LIVE_ENV: "1",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "offline-test-only",
        }))
        self._mock_response(ABSTAIN)

    def _read(self, name):
        return json.loads((self.packet / name).read_text(encoding="utf-8"))

    def _mock_response(self, raw, *, finish_reason="stop"):
        self.post.return_value.status_code = 200
        self.post.return_value.json.return_value = {
            "choices": [{
                "message": {
                    "content": raw,
                    "reasoning_content": "synthetic reasoning, must not be logged",
                },
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": 176,
                "completion_tokens": 900,
                "total_tokens": 1076,
            },
        }

    def _live(self):
        return execute_accuracy_capture(
            self.corpus, self.packet,
            execute_live=True, confirmation=CONFIRMATION,
        )

    def test_plan_requires_32_approved_unique_cases(self):
        plan = build_accuracy_plan(self.cases)
        self.assertEqual(plan["planned_requests"], 32)
        self.assertEqual(plan["max_output_tokens"], 4096)
        self.assertEqual(plan["accuracy_profile"], PROFILE)
        self.assertEqual(plan["system_prompt_sha256"], EXPECTED_PROMPT_SHA256)
        self.assertEqual(
            [r["case_id"] for r in plan["requests"]],
            [c["id"] for c in self.cases],
        )
        self.assertNotIn("draft_expected", json.dumps(plan))
        self.assertNotIn("review", json.dumps(plan))
        self.assertTrue(plan["stop_on_first_nonvalid"])
        self.post.assert_not_called()

    def test_export_creates_brand_new_private_empty_packet(self):
        self.assertEqual(self.prepared["provider_calls"], 0)
        self.assertEqual(self.prepared["planned_requests"], 32)
        self.assertEqual(self.prepared["max_completion_tokens"], 4096)
        self.assertFalse(self.prepared["live_authorized"])
        self.assertEqual(self._read("predictions.json"), {
            "schema_version": 1, "predictions": [],
        })
        self.assertFalse(any((self.packet / n).exists() for n in OUTPUT_FILES))
        with self.assertRaises(ClassificationAuditError):
            prepare_private_accuracy_packet(self.corpus, self.packet)
        self.post.assert_not_called()

    def test_dry_run_only_reads_packet_and_checks_prompt_fingerprint(self):
        first = {p.name: p.read_bytes() for p in self.packet.iterdir()}
        summary = execute_accuracy_capture(self.corpus, self.packet)
        self.assertEqual(summary["status"], "DRY_RUN_READY_NO_PROVIDER_CALLS")
        self.assertEqual(summary["max_completion_tokens"], 4096)
        self.assertEqual(summary["planned_requests"], 32)
        self.assertEqual(summary["http_timeout_read_inactivity_sec"], 45)
        self.assertFalse(summary["live_authorized"])
        self.assertFalse(summary["enforcement_approved"])
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.packet.iterdir()},
            first,
        )
        self.post.assert_not_called()

    def test_cli_prepare_and_preflight_are_offline(self):
        target = self.root / "prepared_by_command"
        out = StringIO()
        call_command(
            "prepare_cloudflare_classification_accuracy",
            "--corpus", str(self.corpus), "--export-dir", str(target),
            "--json-summary", stdout=out,
        )
        prepared = json.loads(out.getvalue())
        self.assertEqual(prepared["planned_requests"], 32)
        self.assertFalse(prepared["live_authorized"])
        out = StringIO()
        call_command(
            "capture_cloudflare_classification_accuracy",
            "--corpus", str(self.corpus), "--packet-dir", str(target),
            "--json-summary", stdout=out,
        )
        dry = json.loads(out.getvalue())
        self.assertEqual(dry["provider_calls"], 0)
        self.assertNotIn("NASA announced", out.getvalue())
        self.post.assert_not_called()
        self.fallback.assert_not_called()

    def test_public_pending_fixture_is_rejected_before_export(self):
        with self.assertRaises(ClassificationAuditError):
            prepare_private_accuracy_packet(DEFAULT_CORPUS, self.root / "pending")
        self.post.assert_not_called()

    def test_changed_review_provenance_fails_before_network(self):
        changed = copy.deepcopy(self.cases)
        changed[0]["review"]["notes"] = "Changed untrusted attestation"
        self.corpus.write_text(json.dumps({
            "schema_version": 1, "cases": changed,
        }), encoding="utf-8")
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_not_called()

    def test_tampered_manifest_or_fake_prior_predictions_fail_closed(self):
        original = self._read("capture_inputs.json")
        manifest = self.packet / "capture_inputs.json"
        for mutate in (
            lambda v: v.update(max_output_tokens=1024),
            lambda v: v.update(accuracy_profile="cloudflare_02"),
            lambda v: v["requests"][0].update(claim_text="altered"),
            lambda v: v.update(planned_requests=33),
            lambda v: v.update(system_prompt_sha256="0" * 64),
        ):
            bad = copy.deepcopy(original)
            mutate(bad)
            manifest.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ClassificationAuditError):
                self._live()
            self.post.assert_not_called()
        manifest.write_text(json.dumps(original), encoding="utf-8")
        (self.packet / "predictions.json").write_text(json.dumps({
            "schema_version": 1,
            "predictions": [{"case_id": "cross_spacecraft", "raw_response": ABSTAIN}],
        }), encoding="utf-8")
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_not_called()

    def test_no_live_use_without_fresh_distinct_exact_gates(self):
        with self.assertRaises(ClassificationAuditError):
            execute_accuracy_capture(
                self.corpus, self.packet, execute_live=True,
            )
        with patch.dict(os.environ, {LIVE_ENV: "0"}):
            with self.assertRaises(ClassificationAuditError):
                self._live()
        with self.assertRaises(CommandError):
            call_command(
                "capture_cloudflare_classification_accuracy",
                "--corpus", str(self.corpus),
                "--packet-dir", str(self.packet),
                "--confirm-live", CONFIRMATION,
                stdout=StringIO(),
            )
        self.post.assert_not_called()
        self.assertFalse((self.packet / LOCK_FILE).exists())

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_production_never_enables_live_capture(self):
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_not_called()
        self.assertFalse((self.packet / LOCK_FILE).exists())

    def test_single_success_then_transport_failure_stops_without_retry(self):
        first = self.post.return_value
        self.post.side_effect = [
            first,
            requests.exceptions.ReadTimeout("vendor secret string"),
        ]
        # The first canonical case is CIVICS, so use a structurally
        # valid abstention (not an invented SCIENCE quotation).
        self._mock_response(ABSTAIN)
        with patch("api.services.call_llm_with_fallback") as routing:
            done = self._live()
        self.assertEqual(done["attempted_requests"], 2)
        self.assertEqual(done["captured_predictions"], 1)
        self.assertEqual(done["valid_responses"], 1)
        self.assertTrue(done["stopped_early"])
        self.assertEqual(self.post.call_count, 2)
        routing.assert_not_called()
        kw = self.post.call_args_list[0].kwargs
        self.assertEqual(kw["json"]["max_tokens"], COMPLETION_TOKENS)
        self.assertEqual(kw["timeout"], HTTP_TIMEOUT)
        self.assertEqual(kw["json"]["model"], DEFAULT_MODEL)
        self.assertEqual(kw["json"]["messages"][0]["content"],
                         classification_system_prompt())
        self.assertEqual(kw["json"]["messages"][1]["content"],
                         self.cases[0]["claim_text"])
        self.assertEqual(kw["json"]["options"], {"rejectIfBusy": True})
        journal = self._read(JOURNAL_FILE)
        self.assertEqual(journal["attempts"][0]["status"], "CAPTURED_VALID")
        self.assertEqual(journal["attempts"][1]["status"], "PROVIDER_FAILED")
        self.assertEqual(journal["attempts"][1]["error_code"],
                         "TRANSPORT_ReadTimeout")
        self.assertNotIn(
            "vendor secret string",
            (self.packet / JOURNAL_FILE).read_text(),
        )
        self.assertNotIn(
            "synthetic reasoning, must not be logged",
            (self.packet / JOURNAL_FILE).read_text(),
        )
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.assertEqual(self.post.call_count, 2)

    def test_invalid_response_stops_and_remains_unaltered(self):
        self._mock_response('{"decision":"CLASSIFY","domains":[]}')
        with patch("api.services.call_llm_with_fallback") as routing:
            result = self._live()
        self.assertEqual(result["attempted_requests"], 1)
        self.assertEqual(result["valid_responses"], 0)
        self.assertTrue(result["stopped_early"])
        self.assertEqual(self._read(RAW_FILE)["results"][0]["raw_response"],
                         '{"decision":"CLASSIFY","domains":[]}')
        self.assertEqual(
            self._read(PREDICTIONS_FILE)["predictions"][0]["raw_response"],
            '{"decision":"CLASSIFY","domains":[]}',
        )
        self.assertEqual(self._read(JOURNAL_FILE)["attempts"][0]["status"],
                         "CAPTURED_INVALID_CONTRACT")
        self.post.assert_called_once()
        routing.assert_not_called()

    def test_length_exhaustion_records_metadata_and_stops(self):
        self._mock_response("", finish_reason="length")
        self.post.return_value.json.return_value["usage"]["completion_tokens"] = 4096
        finished = self._live()
        self.assertEqual(finished["attempted_requests"], 1)
        self.assertEqual(finished["captured_predictions"], 0)
        attempt = self._read(JOURNAL_FILE)["attempts"][0]
        self.assertEqual(attempt["error_code"], "EMPTY_PROVIDER_RESPONSE")
        self.assertEqual(attempt["status"], "PROVIDER_FAILED")
        self.assertEqual(attempt["usage"]["finish_reason"], "length")
        self.assertTrue(attempt["usage"]["reasoning_present"])
        self.assertTrue((self.packet / LOCK_FILE).exists())
        self.post.assert_called_once()

    def test_all_32_valid_contracts_feed_real_offline_audit(self):
        # Structural compliance is not reference correctness. 32 real
        # provider-shaped responses, all ABSTAIN, are NOT high accuracy.
        self._mock_response(ABSTAIN)
        completed = self._live()
        self.assertEqual(completed["attempted_requests"], MAX_ATTEMPTS)
        self.assertEqual(completed["captured_predictions"], MAX_ATTEMPTS)
        self.assertEqual(completed["valid_responses"], MAX_ATTEMPTS)
        self.assertFalse(completed["stopped_early"])
        self.assertEqual(self.post.call_count, MAX_ATTEMPTS)
        predictions = load_classification_predictions(
            self.packet / PREDICTIONS_FILE, {c["id"] for c in self.cases},
        )
        score = score_classification_predictions(self.cases, predictions)
        self.assertTrue(score["coverage_complete"])
        self.assertEqual(score["predicted"], 32)
        self.assertLess(score["exact_matches"], 32)
        self.assertGreater(score["missed_classifications"], 0)
        self.assertFalse(score["eligible_for_automatic_enforcement"])
        self.fallback.assert_not_called()

    def test_used_packet_and_partial_writing_file_prevent_replay(self):
        (self.packet / (JOURNAL_FILE + ".writing")).write_text(
            "interrupted", encoding="utf-8",
        )
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_not_called()
        (self.packet / (JOURNAL_FILE + ".writing")).unlink()
        (self.packet / LOCK_FILE).write_text(
            "already used", encoding="utf-8",
        )
        with self.assertRaises(ClassificationAuditError):
            self._live()
        self.post.assert_not_called()

    def test_packet_inside_checkout_is_rejected(self):
        from api.verification import cloudflare_classification_accuracy_capture as accuracy
        repo_path = Path(accuracy.__file__).resolve().parents[4]
        with self.assertRaises(ClassificationAuditError):
            validate_accuracy_packet(self.corpus, repo_path)
        self.post.assert_not_called()
