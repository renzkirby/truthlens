import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from api.verification.semantic_benchmark import BenchmarkInputError
from api.verification.semantic_eval_gemini import (
    CONFIRMATION, EXECUTION_VERSION, INTER_REQUEST_DELAY_SEC, MODEL_ID,
    TEMPERATURE, THINKING_BUDGET, _failure_details, execute_gemini_pilot,
    validate_live_plan,
)
from api.verification.semantic_eval_runner import write_plan


BASELINE = '''BATCH ISOLATION RULE: assess each item independently.
Return "assessments" with SUPPORTS REFUTES CONTEXT UNKNOWN and relevance_score and directness_score.'''


def _case(case_id, stance, axis):
    return {
        "case_id": case_id,
        "axis": axis,
        "assertion": "The bridge opened in 2024.",
        "evidence": "Official records confirm the bridge opened in 2024.",
        "reference_stance": stance,
        "rationale": "Approved proposed label.",
        "review_status": "USER_APPROVED_AI_PROPOSED",
        "reviewer_id": "USER_APPROVAL",
        "reviewed_on": "2026-10-24",
        "source_kind": "SYNTHETIC",
        "source_url": None,
    }


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes):
        self.models = FakeModels(outcomes)


def _response(raw='{"ok":true}', *, finish="STOP", prompt=120, output=24, thoughts=0):
    return SimpleNamespace(
        text=raw,
        candidates=[SimpleNamespace(finish_reason=finish)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt,
            candidates_token_count=output,
            thoughts_token_count=thoughts,
            total_token_count=prompt + output + thoughts,
        ),
    )


class GeminiPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.gold = self.root / "gold.jsonl"
        self.baseline_source = self.root / "evidence_assessment.py"
        self.jobs = self.root / "jobs.jsonl"
        self.plan_manifest = self.root / "plan.json"
        self.subset = self.root / "subset.jsonl"
        self.responses = self.root / "responses.jsonl"
        self.attempts = self.root / "attempts.jsonl"
        self.execution = self.root / "execution.json"
        rows = [
            _case("a", "SUPPORTS", "a"),
            _case("b", "REFUTES", "b"),
            _case("c", "CONTEXT", "c"),
            _case("d", "UNKNOWN", "d"),
        ]
        self.gold.write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
        self.baseline_source.write_text("_SYSTEM_INSTRUCTIONS = " + repr(BASELINE) + "\n", encoding="utf-8")
        write_plan(
            gold_path=self.gold,
            baseline_source=self.baseline_source,
            jobs_path=self.jobs,
            manifest_path=self.plan_manifest,
            subset_gold_path=self.subset,
            cases=4,
            max_requests=8,
            output_token_cap=256,
            max_total_output_tokens=2048,
        )

    def _execute(self, outcomes=None, **overrides):
        jobs = self.jobs.read_text(encoding="utf-8").splitlines()
        if outcomes is None:
            outcomes = [_response() for _ in jobs]
        client = FakeClient(outcomes)
        slept = []
        kwargs = dict(
            jobs_path=self.jobs,
            manifest_path=self.plan_manifest,
            responses_path=self.responses,
            attempts_path=self.attempts,
            execution_manifest_path=self.execution,
            confirmation=CONFIRMATION,
            api_key="test-key",
            client_factory=lambda key: client,
            config_builder=lambda job: {"max_output_tokens": job["max_output_tokens"]},
            clock=lambda: 10.0,
            sleeper=lambda value: slept.append(value),
        )
        kwargs.update(overrides)
        result = execute_gemini_pilot(**kwargs)
        return result, client, slept

    def test_requires_exact_explicit_confirmation_before_client(self):
        called = []
        with self.assertRaisesRegex(BenchmarkInputError, "confirmation"):
            execute_gemini_pilot(
                jobs_path=self.jobs, manifest_path=self.plan_manifest,
                responses_path=self.responses, attempts_path=self.attempts,
                execution_manifest_path=self.execution, confirmation="yes",
                api_key="test-key", client_factory=lambda key: called.append(key),
            )
        self.assertEqual(called, [])

    def test_requires_api_key(self):
        with self.assertRaisesRegex(BenchmarkInputError, "GEMINI_API_KEY"):
            execute_gemini_pilot(
                jobs_path=self.jobs, manifest_path=self.plan_manifest,
                responses_path=self.responses, attempts_path=self.attempts,
                execution_manifest_path=self.execution, confirmation=CONFIRMATION,
                api_key="", client_factory=lambda key: None,
            )

    def test_validates_jobs_hash_before_live_execution(self):
        self.jobs.write_text(self.jobs.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "Job plan differs"):
            validate_live_plan(jobs_path=self.jobs, manifest_path=self.plan_manifest)

    def test_refuses_more_than_hard_sixteen_request_cap(self):
        manifest = json.loads(self.plan_manifest.read_text())
        manifest["max_requests"] = 17
        self.plan_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "16-request"):
            validate_live_plan(jobs_path=self.jobs, manifest_path=self.plan_manifest)

    def test_rejects_gold_metadata_in_live_jobs_even_if_hash_is_updated(self):
        rows = [json.loads(line) for line in self.jobs.read_text().splitlines()]
        rows[0]["reference_stance"] = "SUPPORTS"
        raw = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
        self.jobs.write_text(raw, encoding="utf-8")
        import hashlib
        manifest = json.loads(self.plan_manifest.read_text())
        manifest["jobs_sha256"] = hashlib.sha256(self.jobs.read_bytes()).hexdigest()
        self.plan_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "fields|Gold-label"):
            validate_live_plan(jobs_path=self.jobs, manifest_path=self.plan_manifest)

    def test_executes_each_job_once_with_one_fixed_model(self):
        result, client, slept = self._execute()
        self.assertEqual(result["attempted_requests"], 8)
        self.assertEqual(result["successful_responses"], 8)
        self.assertEqual(result["failed_requests"], 0)
        self.assertEqual(len(client.models.calls), 8)
        self.assertTrue(all(call["model"] == MODEL_ID for call in client.models.calls))
        self.assertEqual(slept, [INTER_REQUEST_DELAY_SEC] * 7)

    def test_saved_response_metadata_is_identical_for_both_arms(self):
        self._execute()
        rows = [json.loads(line) for line in self.responses.read_text().splitlines()]
        self.assertEqual({r["provider"] for r in rows}, {"gemini"})
        self.assertEqual({r["model_id"] for r in rows}, {MODEL_ID})
        self.assertEqual({r["temperature"] for r in rows}, {TEMPERATURE})
        self.assertEqual({r["input_tokens"] for r in rows}, {120})
        self.assertEqual({r["output_tokens"] for r in rows}, {24})

    def test_execution_manifest_records_no_fallback_and_no_gold_read(self):
        result, _, _ = self._execute()
        saved = json.loads(self.execution.read_text())
        self.assertEqual(saved, result)
        self.assertEqual(saved["schema_version"], EXECUTION_VERSION)
        self.assertEqual(saved["status"], "COMPLETED")
        self.assertFalse(saved["fallback_enabled"])
        self.assertFalse(saved["gold_reference_read"])
        self.assertEqual(saved["thinking_budget"], THINKING_BUDGET)
        self.assertEqual(saved["temperature"], TEMPERATURE)
        self.assertEqual(saved["model_id"], MODEL_ID)

    def test_provider_error_is_one_attempt_and_other_jobs_continue(self):
        outcomes = [RuntimeError("quota body must not leak")] + [_response() for _ in range(7)]
        result, client, _ = self._execute(outcomes)
        self.assertEqual(len(client.models.calls), 8)
        self.assertEqual(result["failed_requests"], 1)
        self.assertEqual(result["successful_responses"], 7)
        self.assertEqual(result["status"], "COMPLETED_WITH_FAILURES")
        attempts = [json.loads(line) for line in self.attempts.read_text().splitlines()]
        self.assertEqual(attempts[0]["outcome"], "FAILED")
        self.assertEqual(attempts[0]["error_code"], "PROVIDER_ERROR")
        self.assertEqual(attempts[0]["error_category"], "UNCLASSIFIED_ERROR")
        self.assertNotIn("http_status", attempts[0])
        self.assertNotIn("quota body", self.attempts.read_text())
        self.assertEqual(len(self.responses.read_text().splitlines()), 7)


    def test_http_error_categories_do_not_use_message_text(self):
        class ProviderException(Exception):
            def __init__(self, status, message="provider secret=do-not-log"):
                super().__init__(message)
                self.code = status

        examples = {
            400: "INVALID_REQUEST",
            401: "AUTHENTICATION_ERROR",
            402: "PAYMENT_REQUIRED",
            403: "ACCESS_DENIED",
            404: "HTTP_CLIENT_ERROR",
            408: "REQUEST_TIMEOUT",
            413: "INVALID_REQUEST",
            422: "INVALID_REQUEST",
            429: "RATE_LIMIT_OR_QUOTA",
            500: "SERVER_ERROR",
            503: "SERVER_ERROR",
            504: "REQUEST_TIMEOUT",
        }
        for status, category in examples.items():
            with self.subTest(http_status=status):
                result = _failure_details(ProviderException(status))
                self.assertEqual(result["error_code"], "PROVIDER_ERROR")
                self.assertEqual(result["http_status"], status)
                self.assertEqual(result["error_category"], category)
                self.assertNotIn("secret", json.dumps(result))
                self.assertNotIn("do-not-log", json.dumps(result))

    def test_secondary_numeric_status_and_invalid_status_fail_closed(self):
        class AlternateProviderException(Exception):
            status_code = 429

        result = _failure_details(AlternateProviderException("private body"))
        self.assertEqual(result["http_status"], 429)
        self.assertEqual(result["error_category"], "RATE_LIMIT_OR_QUOTA")

        for invalid in (None, "429", True, 99, 600, -1):
            with self.subTest(invalid=invalid):
                exc = RuntimeError("private body")
                exc.code = invalid
                result = _failure_details(exc)
                self.assertNotIn("http_status", result)
                self.assertEqual(result["error_category"], "UNCLASSIFIED_ERROR")
                self.assertEqual(result["error_code"], "PROVIDER_ERROR")

    def test_unreadable_status_and_forged_internal_prefix_are_safe(self):
        class BrokenStatus(Exception):
            @property
            def code(self):
                raise ValueError("secret from property")

        self.assertEqual(
            _failure_details(BrokenStatus("hidden text"))["error_category"],
            "UNCLASSIFIED_ERROR",
        )
        result = _failure_details(RuntimeError("GEMINI_FINISH_SECRET_API_KEY"))
        self.assertEqual(result["error_code"], "PROVIDER_ERROR")
        self.assertNotIn("SECRET_API_KEY", json.dumps(result))
        self.assertEqual(
            _failure_details(RuntimeError("GEMINI_FINISH_MAX_TOKENS"))["error_category"],
            "RESPONSE_VALIDATION",
        )

    def test_saved_provider_http_failure_is_sanitized(self):
        class ProviderException(Exception):
            def __init__(self):
                super().__init__("Bearer very-secret-token; provider message")
                self.code = 429

        outcomes = [ProviderException()] + [_response() for _ in range(7)]
        result, client, _ = self._execute(outcomes)
        self.assertEqual(result["failed_requests"], 1)
        self.assertEqual(len(client.models.calls), 8)
        first = json.loads(self.attempts.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(first["http_status"], 429)
        self.assertEqual(first["error_code"], "PROVIDER_ERROR")
        self.assertEqual(first["error_category"], "RATE_LIMIT_OR_QUOTA")
        self.assertNotIn("very-secret-token", self.attempts.read_text(encoding="utf-8"))
        self.assertNotIn("provider message", self.attempts.read_text(encoding="utf-8"))
        self.assertEqual(len(self.responses.read_text().splitlines()), 7)

    def test_non_stop_finish_is_not_saved_as_prediction(self):
        outcomes = [_response(finish="MAX_TOKENS")] + [_response() for _ in range(7)]
        result, _, _ = self._execute(outcomes)
        self.assertEqual(result["failed_requests"], 1)
        first_attempt = json.loads(self.attempts.read_text().splitlines()[0])
        self.assertEqual(first_attempt["error_code"], "GEMINI_FINISH_MAX_TOKENS")
        self.assertEqual(len(self.responses.read_text().splitlines()), 7)

    def test_reported_output_over_plan_cap_fails_closed(self):
        outcomes = [_response(output=257)] + [_response() for _ in range(7)]
        result, _, _ = self._execute(outcomes)
        self.assertEqual(result["failed_requests"], 1)
        self.assertIn("GEMINI_OUTPUT_USAGE_EXCEEDS_PLAN", self.attempts.read_text())

    def test_refuses_to_overwrite_existing_outputs(self):
        self.responses.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "overwrite"):
            self._execute()
        self.assertEqual(self.responses.read_text(), "preserve")
        self.assertFalse(self.attempts.exists())
        self.assertFalse(self.execution.exists())

    def test_config_builder_receives_each_job_cap(self):
        caps = []
        client = FakeClient([_response() for _ in range(8)])
        execute_gemini_pilot(
            jobs_path=self.jobs, manifest_path=self.plan_manifest,
            responses_path=self.responses, attempts_path=self.attempts,
            execution_manifest_path=self.execution, confirmation=CONFIRMATION,
            api_key="test-key", client_factory=lambda key: client,
            config_builder=lambda job: caps.append(job["max_output_tokens"]) or object(),
            clock=lambda: 1.0, sleeper=lambda _: None,
        )
        self.assertEqual(caps, [256] * 8)


if __name__ == "__main__":
    unittest.main()
