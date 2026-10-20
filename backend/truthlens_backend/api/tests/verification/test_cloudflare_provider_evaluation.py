"""No-network tests for the opt-in Cloudflare evaluation lane."""
import io
import json
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from api.verification.cloudflare_evaluation import (
    CloudflareEvaluationError,
    generate_evaluation_json,
)


ACCOUNT = "a" * 32
TOKEN = "test-secret-never-log"


class CloudflareEvaluationAdapterTests(SimpleTestCase):
    def test_json_chat_request_is_bounded_and_uses_expected_endpoint(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": '{"verdict":"FACT"}'}}]
        }
        post = Mock(return_value=response)
        result = generate_evaluation_json(
            "system", "user", account_id=ACCOUNT, api_token=TOKEN, http_post=post,
        )
        self.assertEqual(result, '{"verdict":"FACT"}')
        args, kwargs = post.call_args
        self.assertEqual(
            args[0],
            f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/v1/chat/completions",
        )
        self.assertEqual(kwargs["timeout"], (5, 45))
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})
        self.assertEqual(kwargs["json"]["model"], "@cf/google/gemma-4-26b-a4b-it")
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")

    def test_429_does_not_retry_and_does_not_expose_body(self):
        post = Mock(return_value=Mock(status_code=429, text="secret-error-body"))
        with self.assertRaisesRegex(CloudflareEvaluationError, "^HTTP_429$"):
            generate_evaluation_json(
                "system", "user", account_id=ACCOUNT, api_token=TOKEN, http_post=post,
            )
        post.assert_called_once()

    def test_invalid_account_and_credentials_block_network(self):
        post = Mock()
        with self.assertRaisesRegex(CloudflareEvaluationError, "MISSING_OR_INVALID"):
            generate_evaluation_json(
                "system", "user", account_id="not-an-id", api_token=TOKEN,
                http_post=post,
            )
        with self.assertRaisesRegex(CloudflareEvaluationError, "MISSING_API_TOKEN"):
            generate_evaluation_json(
                "system", "user", account_id=ACCOUNT, api_token="",
                http_post=post,
            )
        post.assert_not_called()

    def test_malformed_provider_payload_is_rejected_without_leaking_text(self):
        response = Mock(status_code=200)
        response.json.return_value = {"error": "internal data"}
        with self.assertRaisesRegex(CloudflareEvaluationError, "^INVALID_PROVIDER_RESPONSE$"):
            generate_evaluation_json(
                "system", "user", account_id=ACCOUNT, api_token=TOKEN,
                http_post=Mock(return_value=response),
            )

    def test_model_override_and_oversized_input_are_refused(self):
        post = Mock()
        for args in (
            {"model": "arbitrary/other-model"},
            {"user_prompt": "x" * 30000},
        ):
            with self.subTest(args=args.keys()), self.assertRaises(CloudflareEvaluationError):
                generate_evaluation_json(
                    "system", args.get("user_prompt", "user"),
                    model=args.get("model", "@cf/google/gemma-4-26b-a4b-it"),
                    account_id=ACCOUNT, api_token=TOKEN, http_post=post,
                )
        post.assert_not_called()


class OfflineProviderEvaluationCommandTests(SimpleTestCase):
    def test_dry_run_never_calls_any_provider(self):
        out = io.StringIO()
        with patch(
            "api.verification.cloudflare_evaluation.requests.post"
        ) as post:
            call_command("evaluate_verification_providers", stdout=out)
        self.assertIn("DRY RUN", out.getvalue())
        post.assert_not_called()

    @override_settings(DEBUG=False)
    def test_live_requires_debug_and_opt_in(self):
        with patch.dict(
            "os.environ", {"ENABLE_CLOUDFLARE_EVALUATION": "1"},
        ):
            with self.assertRaises(CommandError):
                call_command("evaluate_verification_providers", live=True, limit=1)

    @override_settings(DEBUG=True)
    def test_live_requires_explicit_local_credentials(self):
        with patch.dict(
            "os.environ",
            {"ENABLE_CLOUDFLARE_EVALUATION": "1",
             "CLOUDFLARE_ACCOUNT_ID": "", "CLOUDFLARE_API_TOKEN": ""},
        ):
            with self.assertRaisesRegex(CommandError, "CLOUDFLARE_ACCOUNT_ID"):
                call_command("evaluate_verification_providers", live=True, limit=1)

    @override_settings(DEBUG=True)
    def test_live_uses_exact_production_evaluator_without_claim_database(self):
        out = io.StringIO()
        valid = json.dumps({
            "reasoning": "Source explicitly supports the claim.",
            "verdict": "FACT",
            "summary": "The source says the library opens at 8 AM.",
            "confidence_score": 88,
            "score_context": "Single explicit source supports the claim.",
        })
        with (
            patch.dict("os.environ", {
                "ENABLE_CLOUDFLARE_EVALUATION": "1",
                "CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
                "CLOUDFLARE_API_TOKEN": TOKEN,
            }),
            patch(
                "api.management.commands.evaluate_verification_providers.generate_evaluation_json",
                return_value=valid,
            ) as generate,
        ):
            call_command(
                "evaluate_verification_providers", live=True, limit=1,
                stdout=out,
            )
        self.assertEqual(generate.call_count, 1)
        self.assertIn("SOURCE IDENTITY GROUP", generate.call_args.args[0])
        self.assertIn("<persisted_evidence>", generate.call_args.args[1])
        self.assertIn("match=True", out.getvalue())
        self.assertNotIn(TOKEN, out.getvalue())

    @override_settings(DEBUG=True)
    def test_cloudflare_quota_error_stops_after_one_case_not_unverified(self):
        out = io.StringIO()
        with (
            patch.dict("os.environ", {
                "ENABLE_CLOUDFLARE_EVALUATION": "1",
                "CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
                "CLOUDFLARE_API_TOKEN": TOKEN,
            }),
            patch(
                "api.management.commands.evaluate_verification_providers.generate_evaluation_json",
                side_effect=CloudflareEvaluationError("HTTP_429"),
            ) as generate,
        ):
            call_command(
                "evaluate_verification_providers", live=True, limit=4,
                stdout=out,
            )
        self.assertEqual(generate.call_count, 1)
        self.assertIn("error=HTTP_429", out.getvalue())
        self.assertIn("stopping", out.getvalue())
        self.assertNotIn("verdict=UNVERIFIED", out.getvalue())
