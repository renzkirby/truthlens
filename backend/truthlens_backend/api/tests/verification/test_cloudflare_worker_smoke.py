"""Cloudflare-only Celery smoke safety: no external calls, DB or user claims."""
import io
import json
import os
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from api import services
from api.tasks import cloudflare_single_request_smoke
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.cloudflare_worker_smoke import FIXED_CASE_ID
from api.verification.realworld_benchmark import load_corpus


ACCOUNT_ID = "a" * 32
TEST_TOKEN = "worker-test-secret-not-for-logs"
VALID_FINAL = json.dumps({
    "reasoning": "The cited constitutional text specifies twenty-four senators.",
    "verdict": "FACT",
    "summary": "The reviewed evidence directly supports the claim.",
    "confidence_score": 94,
    "score_context": "The provided constitutional excerpt supports the precise number.",
})


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflareSingleRequestSmokeTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID,
            "CLOUDFLARE_API_TOKEN": TEST_TOKEN,
        }))

    def test_approved_fixture_and_same_production_prompt_one_http_call_only(self):
        fake_response = Mock(status_code=200)
        fake_response.json.return_value = {
            "choices": [{"message": {"content": VALID_FINAL}}],
            "usage": {},
        }
        with (
            patch(
                "api.verification.cloudflare_evaluation.requests.post",
                return_value=fake_response,
            ) as post,
            patch("api.services.call_llm_with_fallback") as routed,
        ):
            result = cloudflare_single_request_smoke.run()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["case_id"], FIXED_CASE_ID)
        self.assertTrue(result["matches_approved_label"])
        self.assertTrue(result["contract_valid"])
        self.assertEqual(result["expected_verdict"], "FACT")
        self.assertEqual(result["actual_verdict"], "FACT")
        self.assertEqual(result["requests_attempted"], 1)
        self.assertIsInstance(result["worker_pid"], int)
        post.assert_called_once()
        routed.assert_not_called()
        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 2048)
        case = next(c for c in load_corpus() if c["id"] == FIXED_CASE_ID)
        system, user = services.build_persisted_evidence_prompt(
            case["claim"], case["evidence_snapshot"], "NEUTRAL",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["messages"],
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        self.assertNotIn(TEST_TOKEN, str(result))
        self.assertNotIn(ACCOUNT_ID, str(result))
        self.assertNotIn(case["claim"], str(result))
        self.assertNotIn(case["evidence_snapshot"], str(result))

    def test_http_error_is_sanitized_no_fallback_or_retry(self):
        response = Mock(status_code=429, text="private-provider-body")
        with (
            patch("api.verification.cloudflare_evaluation.requests.post",
                  return_value=response) as post,
            patch("api.services.call_llm_with_fallback") as routed,
            self.assertLogs("api.verification.cloudflare_worker_smoke", level="INFO") as logs,
        ):
            result = cloudflare_single_request_smoke.run()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "HTTP_429")
        self.assertEqual(result["requests_attempted"], 1)
        post.assert_called_once()
        routed.assert_not_called()
        self.assertNotIn("private-provider-body", str(result))
        self.assertNotIn("private-provider-body", "\n".join(logs.output))
        self.assertNotIn(TEST_TOKEN, "\n".join(logs.output))

    def test_invalid_json_refused_no_unverified_substitution(self):
        with patch(
            "api.verification.cloudflare_worker_smoke.generate_evaluation_json",
            return_value='{"verdict":"UNVERIFIED"}',
        ) as call:
            result = cloudflare_single_request_smoke.run()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "INVALID_EVALUATION_JSON")
        self.assertNotIn("actual_verdict", result)
        self.assertEqual(result["requests_attempted"], 1)
        call.assert_called_once()

    def test_bounded_sanitizer_drops_unknown_exception_body(self):
        secret = "PRIVATE_BEARER_EXCEPTION"
        with patch(
            "api.verification.cloudflare_worker_smoke.generate_evaluation_json",
            side_effect=RuntimeError(secret),
        ) as call:
            result = cloudflare_single_request_smoke.run()
        self.assertEqual(result["reason"], "OTHER_SMOKE_FAILURE")
        self.assertNotIn(secret, str(result))
        call.assert_called_once()

    def test_invalid_credentials_and_disabled_flag_block_network(self):
        for overrides, expected in (
            ({"CLOUDFLARE_ACCOUNT_ID": "invalid"}, "MISSING_OR_INVALID_ACCOUNT_ID"),
            ({"CLOUDFLARE_API_TOKEN": ""}, "MISSING_API_TOKEN"),
            ({"ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "0"}, "PILOT_DISABLED"),
        ):
            with (
                self.subTest(expected=expected),
                patch.dict(os.environ, overrides),
                patch("api.verification.cloudflare_worker_smoke.generate_evaluation_json") as call,
            ):
                result = cloudflare_single_request_smoke.run()
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], expected)
            self.assertEqual(result["requests_attempted"], 0)
            call.assert_not_called()

    def test_unapproved_public_case_blocks_network(self):
        case = next(c for c in load_corpus() if c["id"] == FIXED_CASE_ID)
        case["review"]["status"] = "PENDING"
        with (
            patch("api.verification.cloudflare_worker_smoke.load_corpus", return_value=[case]),
            patch("api.verification.cloudflare_worker_smoke.generate_evaluation_json") as call,
        ):
            result = cloudflare_single_request_smoke.run()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "CASE_NOT_APPROVED")
        call.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_production_never_sends_request_even_if_enabled(self):
        with patch(
            "api.verification.cloudflare_worker_smoke.generate_evaluation_json",
        ) as call:
            result = cloudflare_single_request_smoke.run()
        self.assertEqual(result, {
            "status": "blocked", "reason": "DEVELOPMENT_ONLY",
        })
        call.assert_not_called()

    def test_celery_task_disallows_retries_and_late_ack(self):
        self.assertEqual(cloudflare_single_request_smoke.max_retries, 0)
        self.assertFalse(cloudflare_single_request_smoke.acks_late)


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflareSingleRequestSmokeCommandTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID,
            "CLOUDFLARE_API_TOKEN": TEST_TOKEN,
        }))

    def test_dry_run_does_not_enqueue(self):
        out = io.StringIO()
        with patch(
            "api.management.commands.cloudflare_worker_smoke.cloudflare_single_request_smoke"
        ) as task:
            call_command("cloudflare_worker_smoke", stdout=out)
        task.delay.assert_not_called()
        self.assertIn("DRY RUN", out.getvalue())

    def test_live_needs_explicit_confirmation_no_enqueue(self):
        with patch(
            "api.management.commands.cloudflare_worker_smoke.cloudflare_single_request_smoke"
        ) as task, self.assertRaisesRegex(CommandError, "--confirm-one-request"):
            call_command("cloudflare_worker_smoke", live=True)
        task.delay.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_production_command_cannot_enqueue(self):
        with patch(
            "api.management.commands.cloudflare_worker_smoke.cloudflare_single_request_smoke"
        ) as task, self.assertRaisesRegex(CommandError, "development"):
            call_command(
                "cloudflare_worker_smoke",
                live=True,
                confirm_one_request=True,
            )
        task.delay.assert_not_called()

    def test_one_enqueued_task_and_bounded_safe_report(self):
        out = io.StringIO()
        result = Mock(id="mock-task-id")
        result.get.return_value = {
            "status": "success", "provider": "cloudflare",
            "worker_pid": 128, "case_id": FIXED_CASE_ID,
            "elapsed_ms": 1200, "requests_attempted": 1,
            "actual_verdict": "FACT", "expected_verdict": "FACT",
            "matches_approved_label": True, "contract_valid": True,
            "reasoning": "PRIVATE_RATIONALE_DO_NOT_LOG",
        }
        with patch(
            "api.management.commands.cloudflare_worker_smoke.cloudflare_single_request_smoke"
        ) as task:
            task.delay.return_value = result
            call_command(
                "cloudflare_worker_smoke",
                live=True, confirm_one_request=True, stdout=out,
            )
        task.delay.assert_called_once_with()
        result.get.assert_called_once_with(timeout=70)
        self.assertIn("actual_verdict=FACT", out.getvalue())
        self.assertNotIn("PRIVATE_RATIONALE_DO_NOT_LOG", out.getvalue())

    def test_valid_json_with_wrong_verdict_requires_quality_review(self):
        out = io.StringIO()
        result = Mock(id="mock-task-id")
        result.get.return_value = {
            "status": "success", "case_id": FIXED_CASE_ID,
            "actual_verdict": "FAKE", "expected_verdict": "FACT",
            "matches_approved_label": False,
            "requests_attempted": 1,
        }
        with (
            patch("api.management.commands.cloudflare_worker_smoke.cloudflare_single_request_smoke") as task,
            self.assertRaisesRegex(CommandError, "disagreed"),
        ):
            task.delay.return_value = result
            call_command(
                "cloudflare_worker_smoke",
                live=True, confirm_one_request=True, stdout=out,
            )
        task.delay.assert_called_once()
        self.assertIn("matches_approved_label=False", out.getvalue())

    def test_provider_failure_reports_code_and_does_not_requeue(self):
        out = io.StringIO()
        result = Mock(id="mock-task-id")
        result.get.return_value = {
            "status": "failed", "reason": "HTTP_429",
            "requests_attempted": 1, "elapsed_ms": 17,
        }
        with (
            patch("api.management.commands.cloudflare_worker_smoke.cloudflare_single_request_smoke") as task,
            self.assertRaisesRegex(CommandError, "did not succeed"),
        ):
            task.delay.return_value = result
            call_command(
                "cloudflare_worker_smoke",
                live=True, confirm_one_request=True, stdout=out,
            )
        task.delay.assert_called_once()
        self.assertIn("reason=HTTP_429", out.getvalue())
