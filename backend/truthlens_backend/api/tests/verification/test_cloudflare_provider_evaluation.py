"""No-network tests for the opt-in Cloudflare evaluation lane."""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from api.verification.cloudflare_evaluation import (
    CloudflareEvaluationError,
    generate_evaluation_json,
    sanitized_cloudflare_error_code,
)


ACCOUNT = "a" * 32
TOKEN = "test-secret-never-log"


class CloudflareEvaluationAdapterTests(SimpleTestCase):
    def test_sanitized_error_code_never_exposes_unknown_payload(self):
        for code in (
            "MISSING_OR_INVALID_ACCOUNT_ID", "MISSING_API_TOKEN",
            "PROMPT_TOO_LONG", "INVALID_EVALUATION_JSON", "HTTP_402",
            "HTTP_429", "TRANSPORT_ReadTimeout",
            "EMPTY_PROVIDER_RESPONSE finish_reason=length completion_tokens=2048",
        ):
            with self.subTest(code=code):
                expected = code.split(" ", 1)[0]
                self.assertEqual(
                    sanitized_cloudflare_error_code(CloudflareEvaluationError(code)),
                    expected,
                )
        self.assertEqual(
            sanitized_cloudflare_error_code(
                CloudflareEvaluationError("secret-key=PRIVATE_AND_SENSITIVE")
            ),
            "OTHER_CLOUDFLARE_ERROR",
        )

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
        self.assertEqual(kwargs["json"]["max_tokens"], 1024)
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")

    def test_reject_if_busy_only_adds_documented_openai_options_when_opted_in(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": '{"verdict":"FACT"}'}}],
        }
        post = Mock(return_value=response)
        generate_evaluation_json(
            "system", "all evidence", account_id=ACCOUNT, api_token=TOKEN,
            http_post=post, reject_if_busy=True,
        )
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["options"], {"rejectIfBusy": True})
        self.assertEqual(payload["max_tokens"], 1024)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["messages"][1]["content"], "all evidence")
        self.assertFalse(payload["stream"])
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 45))
        post.reset_mock()

        generate_evaluation_json(
            "system", "all evidence", account_id=ACCOUNT, api_token=TOKEN,
            http_post=post,
        )
        self.assertNotIn("options", post.call_args.kwargs["json"])
        post.assert_called_once()

    def test_invalid_capacity_option_is_rejected_before_network(self):
        post = Mock()
        for value in (None, 1, 0, "yes", "false", [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(
                CloudflareEvaluationError, "^INVALID_REJECT_IF_BUSY$"
            ):
                generate_evaluation_json(
                    "system", "evidence", account_id=ACCOUNT, api_token=TOKEN,
                    http_post=post, reject_if_busy=value,
                )
        post.assert_not_called()

    def test_cloudflare_429_internal_codes_are_sanitized_without_vendor_message(self):
        for error_body, expected in (
            ({"errors": [{"code": 3040, "message": "SECRET CAPACITY DETAILS"}]},
             "HTTP_429_CAPACITY"),
            ({"error": {"code": 3036, "message": "SECRET ACCOUNT INFO"}},
             "HTTP_429_ALLOCATION"),
            ({"errors": [{"code": 9999, "message": "SECRET UNKNOWN ERROR"}]},
             "HTTP_429"),
            ({"errors": [{"code": "3040", "message": "STRING CODE"}]},
             "HTTP_429"),
            ({"errors": [{"code": 3040, "message": "SECRET"}],
              "error": {"code": 3036}}, "HTTP_429_CAPACITY"),
        ):
            with self.subTest(expected=expected, error_body=error_body):
                response = Mock(status_code=429)
                response.json.return_value = error_body
                post = Mock(return_value=response)
                with self.assertRaises(CloudflareEvaluationError) as raised:
                    generate_evaluation_json(
                        "system", "evidence", account_id=ACCOUNT,
                        api_token=TOKEN, http_post=post,
                        reject_if_busy=True,
                    )
                self.assertEqual(str(raised.exception), expected)
                self.assertEqual(
                    sanitized_cloudflare_error_code(raised.exception), expected,
                )
                self.assertNotIn("SECRET", str(raised.exception))
                post.assert_called_once()

    def test_unparseable_429_body_keeps_generic_status_and_no_retry(self):
        response = Mock(status_code=429)
        response.json.side_effect = ValueError("SENSITIVE ERROR MESSAGE")
        post = Mock(return_value=response)
        with self.assertRaisesRegex(CloudflareEvaluationError, "^HTTP_429$"):
            generate_evaluation_json(
                "system", "evidence", account_id=ACCOUNT,
                api_token=TOKEN, http_post=post,
            )
        post.assert_called_once()

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

    def test_empty_response_records_only_safe_finish_and_token_metadata(self):
        provider_response = Mock(status_code=200)
        provider_response.json.return_value = {
            "choices": [{
                "finish_reason": "length",
                "message": {
                    "content": "",
                    "reasoning_content": "PRIVATE INTERNAL REASONING",
                },
            }],
            "usage": {"completion_tokens": 1024},
        }
        with self.assertRaises(CloudflareEvaluationError) as caught:
            generate_evaluation_json(
                "system", "user", account_id=ACCOUNT, api_token=TOKEN,
                http_post=Mock(return_value=provider_response),
            )
        self.assertIn("finish_reason=length", str(caught.exception))
        self.assertIn("completion_tokens=1024", str(caught.exception))
        self.assertIn("reasoning_present=true", str(caught.exception))
        self.assertNotIn("PRIVATE INTERNAL", str(caught.exception))

    def test_explicit_completion_budget_is_configurable_but_bounded(self):
        provider_response = Mock(status_code=200)
        provider_response.json.return_value = {
            "choices": [{"message": {"content": '{"verdict":"FACT"}'}}]
        }
        post = Mock(return_value=provider_response)
        generate_evaluation_json(
            "system", "user", account_id=ACCOUNT, api_token=TOKEN,
            max_completion_tokens=2048, http_post=post,
        )
        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 2048)
        for bad_budget in (0, 100, 4097, "2048", True):
            with self.subTest(bad_budget=bad_budget), self.assertRaisesRegex(
                CloudflareEvaluationError, "INVALID_COMPLETION_BUDGET"
            ):
                generate_evaluation_json(
                    "system", "user", account_id=ACCOUNT, api_token=TOKEN,
                    max_completion_tokens=bad_budget, http_post=post,
                )
        self.assertEqual(post.call_count, 1)

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
