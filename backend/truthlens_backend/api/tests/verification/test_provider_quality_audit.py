"""Offline tests for provider comparison quality and safe token telemetry."""
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from api.verification.cloudflare_evaluation import (
    CloudflareEvaluationError, generate_evaluation_json,
)
from api.verification.mistral_evaluation import (
    MistralEvaluationError, generate_mistral_evaluation_json,
)
from api.verification.provider_audit_metrics import (
    safe_completion_metadata, validate_user_facing_evaluation,
)


ACCOUNT = "a" * 32
EVALUATION = json.dumps({
    "reasoning": "Article VI provides the number of senators.",
    "verdict": "FACT",
    "summary": "The provided dossier supports the claim.",
    "confidence_score": 91,
    "score_context": "Explicit constitutional evidence.",
})


def fake_chat_response(text=EVALUATION):
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": text,
                "reasoning_content": "PRIVATE MODEL INTERNAL ANALYSIS",
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 438,
            "completion_tokens": 176,
            "total_tokens": 614,
            "completion_tokens_details": {"reasoning_tokens": 91},
        },
    }
    return response


class SafeProviderAuditMetricsTests(SimpleTestCase):
    def test_cloudflare_exposes_only_usage_counts_and_final_answer(self):
        metadata = {}
        result = generate_evaluation_json(
            "System JSON instruction", "User prompt",
            account_id=ACCOUNT, api_token="mock-only-secret",
            http_post=Mock(return_value=fake_chat_response()),
            audit_metadata=metadata,
        )
        self.assertEqual(result, EVALUATION)
        self.assertEqual(metadata["prompt_tokens"], 438)
        self.assertEqual(metadata["completion_tokens"], 176)
        self.assertEqual(metadata["total_tokens"], 614)
        self.assertEqual(metadata["reasoning_tokens"], 91)
        self.assertEqual(metadata["finish_reason"], "stop")
        self.assertTrue(metadata["reasoning_present"])
        self.assertNotIn("PRIVATE MODEL INTERNAL ANALYSIS", repr(metadata))
        self.assertNotIn("mock-only-secret", repr(metadata))

    def test_missing_or_malformed_token_fields_are_unknown_not_zero(self):
        meta = safe_completion_metadata(
            {"finish_reason": "secret-unknown",
             "message": {"reasoning": "not for audit"}},
            {"prompt_tokens": "25", "completion_tokens": True,
             "total_tokens": -1, "completion_tokens_details": {
                 "reasoning_tokens": "20"
             }},
        )
        self.assertEqual(meta["finish_reason"], "other")
        for field in (
            "prompt_tokens", "completion_tokens", "total_tokens",
            "reasoning_tokens",
        ):
            self.assertIsNone(meta[field])
        self.assertNotIn("not for audit", repr(meta))

    def test_mistral_json_mode_usage_and_payload(self):
        post = Mock(return_value=fake_chat_response())
        meta = {}
        got = generate_mistral_evaluation_json(
            "System JSON instruction", "User prompt",
            api_token="mistral-test-secret",
            http_post=post, audit_metadata=meta,
        )
        self.assertEqual(got, EVALUATION)
        self.assertEqual(
            post.call_args.args[0],
            "https://api.mistral.ai/v1/chat/completions",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["model"], "mistral-small-2603",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["response_format"],
            {"type": "json_object"},
        )
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 45))
        self.assertEqual(meta["prompt_tokens"], 438)
        self.assertNotIn("PRIVATE MODEL INTERNAL ANALYSIS", repr(meta))

    def test_mistral_rate_limit_is_not_retried_and_no_body_leaks(self):
        post = Mock(return_value=Mock(status_code=429, text="private-body"))
        with self.assertRaisesRegex(MistralEvaluationError, "^HTTP_429$"):
            generate_mistral_evaluation_json(
                "System", "User", api_token="token", http_post=post,
            )
        post.assert_called_once()

    def test_invalid_model_token_budget_and_credentials_block_requests(self):
        post = Mock()
        for args in (
            {"model": "mistral-random"},
            {"max_completion_tokens": 100},
            {"api_token": ""},
        ):
            with self.subTest(args=args), self.assertRaises(MistralEvaluationError):
                generate_mistral_evaluation_json(
                    "System", "User", api_token=args.get("api_token", "mock"),
                    model=args.get("model", "mistral-small-2603"),
                    max_completion_tokens=args.get("max_completion_tokens", 2048),
                    http_post=post,
                )
        post.assert_not_called()

    def test_final_evaluation_validator_rejects_missing_fields(self):
        self.assertIsNone(validate_user_facing_evaluation("{}"))
        self.assertIsNone(validate_user_facing_evaluation('{"verdict":"FACT"}'))
        self.assertEqual(
            validate_user_facing_evaluation(EVALUATION)["verdict"], "FACT",
        )
        invalid = json.loads(EVALUATION)
        invalid["confidence_score"] = True
        self.assertIsNone(
            validate_user_facing_evaluation(json.dumps(invalid)),
        )


@override_settings(DEBUG=True, APP_ENV="development")
class QualityAuditCommandTests(SimpleTestCase):
    def setUp(self):
        self.env = {
            "ENABLE_PROVIDER_QUALITY_AUDIT": "1",
            "CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
            "CLOUDFLARE_API_TOKEN": "hidden-cloudflare-token",
            "MISTRAL_API_KEY": "hidden-mistral-token",
        }

    def test_dry_run_has_no_network_activity_or_files(self):
        out = io.StringIO()
        with (
            patch(
                "api.management.commands.audit_verification_providers.generate_evaluation_json"
            ) as cloudflare,
            patch(
                "api.management.commands.audit_verification_providers.generate_mistral_evaluation_json"
            ) as mistral,
        ):
            call_command("audit_verification_providers", stdout=out)
        self.assertIn("DRY RUN", out.getvalue())
        cloudflare.assert_not_called()
        mistral.assert_not_called()

    def test_live_needs_exact_reviewed_cases_and_explicit_opt_in(self):
        with patch.dict("os.environ", self.env):
            with self.assertRaisesRegex(CommandError, "explicit --case"):
                call_command("audit_verification_providers", live=True)
            with self.assertRaisesRegex(CommandError, "human-approved"):
                call_command(
                    "audit_verification_providers",
                    live=True, case=["law_sim_registration_support"],
                )
        with patch.dict("os.environ", {"ENABLE_PROVIDER_QUALITY_AUDIT": "0"}):
            with self.assertRaisesRegex(CommandError, "ENABLE_PROVIDER_QUALITY_AUDIT"):
                call_command(
                    "audit_verification_providers",
                    live=True, case=["civics__support"],
                )

    @override_settings(DEBUG=False)
    def test_live_needs_development_debug(self):
        with patch.dict("os.environ", self.env):
            with self.assertRaisesRegex(CommandError, "development"):
                call_command(
                    "audit_verification_providers",
                    live=True, case=["civics__support"],
                )

    def test_only_public_final_explanations_go_to_local_review_report(self):
        with tempfile.TemporaryDirectory() as folder:
            out = io.StringIO()
            with (
                override_settings(BASE_DIR=Path(folder)),
                patch.dict("os.environ", self.env),
                patch(
                    "api.management.commands.audit_verification_providers.generate_evaluation_json",
                    side_effect=lambda a,b,**kw: (
                        kw["audit_metadata"].update({
                            "prompt_tokens": 438,
                            "completion_tokens": 176,
                            "total_tokens": 614,
                            "reasoning_tokens": 91,
                            "finish_reason": "stop",
                            "reasoning_present": True,
                        }) or EVALUATION
                    ),
                ) as cloudflare,
            ):
                call_command(
                    "audit_verification_providers",
                    live=True, case=["civics__support"],
                    save_review=True, stdout=out,
                )
            self.assertEqual(cloudflare.call_count, 1)
            self.assertIn("SUMMARY provider=cloudflare matched=1/1", out.getvalue())
            reports = list((Path(folder) / ".provider_audit_reports").glob("*.json"))
            self.assertEqual(len(reports), 1)
            raw = reports[0].read_text(encoding="utf-8")
            report = json.loads(raw)
            self.assertEqual(len(report["results"]), 1)
            item = report["results"][0]
            self.assertEqual(item["model_final_evaluation"]["reasoning"],
                             "Article VI provides the number of senators.")
            self.assertEqual(item["provider_reported_usage"]["reasoning_tokens"], 91)
            self.assertIsNone(item["human_review_worksheet"]["evidence_grounded_0_to_2"])
            self.assertFalse(item["human_review_worksheet"]["review_completed"])
            self.assertNotIn("hidden-cloudflare-token", raw)
            self.assertNotIn("PRIVATE MODEL INTERNAL ANALYSIS", raw)

    def test_both_providers_can_use_the_same_reviewed_prompt(self):
        observed = []
        def model_call(name):
            def call(system, user, **kwargs):
                observed.append((name, system, user))
                kwargs["audit_metadata"].update({
                    "prompt_tokens": 100, "completion_tokens": 50,
                    "finish_reason": "stop",
                })
                return EVALUATION
            return call
        out = io.StringIO()
        with (
            patch.dict("os.environ", self.env),
            patch(
                "api.management.commands.audit_verification_providers.generate_evaluation_json",
                side_effect=model_call("cloudflare"),
            ),
            patch(
                "api.management.commands.audit_verification_providers.generate_mistral_evaluation_json",
                side_effect=model_call("mistral"),
            ),
        ):
            call_command(
                "audit_verification_providers",
                live=True, provider="both",
                case=["civics__support"], stdout=out,
            )
        self.assertEqual(len(observed), 2)
        self.assertEqual(observed[0][1:], observed[1][1:])
        self.assertIn("SUMMARY provider=cloudflare matched=1/1", out.getvalue())
        self.assertIn("SUMMARY provider=mistral matched=1/1", out.getvalue())

    def test_provider_429_is_recorded_and_blocks_followup_requests(self):
        out = io.StringIO()
        with (
            patch.dict("os.environ", self.env),
            patch(
                "api.management.commands.audit_verification_providers.generate_evaluation_json",
                side_effect=CloudflareEvaluationError("HTTP_429"),
            ) as cloudflare,
        ):
            call_command(
                "audit_verification_providers",
                live=True, case=["civics__support", "civics__contradict"],
                stdout=out,
            )
        cloudflare.assert_called_once()
        self.assertIn("error=HTTP_429", out.getvalue())
        self.assertIn("matched=0/1", out.getvalue())

    def test_empty_json_cannot_pass_an_unverified_reference_label(self):
        out = io.StringIO()
        with (
            patch.dict("os.environ", self.env),
            patch(
                "api.management.commands.audit_verification_providers.generate_evaluation_json",
                return_value="{}",
            ),
        ):
            call_command(
                "audit_verification_providers",
                live=True, case=["health_source_insufficient"],
                stdout=out,
            )
        self.assertIn("matched=0/1", out.getvalue())
        self.assertIn("valid=0", out.getvalue())
