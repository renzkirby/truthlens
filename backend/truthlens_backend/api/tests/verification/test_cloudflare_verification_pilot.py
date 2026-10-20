"""Offline safeguards for the disabled-by-default Cloudflare verification pilot."""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from api.services import (
    LLMProviderUnavailableError,
    call_llm_with_fallback,
    evaluate_claim_with_persisted_evidence,
    llm_provider_scope,
)
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.cloudflare_pilot import (
    PILOT_COMPLETION_TOKENS,
    PILOT_OPERATION,
    cloudflare_pilot_enabled,
)
from api.verification.telemetry import SAFE_LLM_PROVIDERS


VALID_EVALUATION = json.dumps({
    "reasoning": "The document directly states twenty-four senators.",
    "verdict": "FACT",
    "summary": "The Constitution sets the Senate at 24.",
    "confidence_score": 95,
    "score_context": "Direct textual corroboration.",
})


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflarePilotRoutingTests(SimpleTestCase):
    def setUp(self):
        # Independently control all opt-in flags regardless of the machine's env.
        self.flags = self.enterContext(patch.dict(
            os.environ,
            {"ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "0"},
        ))
        self.cloud = self.enterContext(patch(
            "api.services.call_validated_cloudflare_pilot",
            return_value=VALID_EVALUATION,
        ))
        self.gemini = Mock()
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text='{"provider":"gemini"}',
        )
        self.groq = Mock()
        self.groq.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"provider":"groq"}'),
            )],
        )
        self.enterContext(patch("api.services.gemini_client", self.gemini))
        self.enterContext(patch("api.services.groq_client", self.groq))

    def _call(self, *, operation=PILOT_OPERATION):
        return call_llm_with_fallback(
            "System instructions", "User dossier", operation=operation,
        )

    def _enable(self):
        os.environ["ENABLE_CLOUDFLARE_VERIFICATION_PILOT"] = "1"

    def test_feature_is_off_by_default_and_old_evaluation_flag_is_not_enough(self):
        os.environ["ENABLE_CLOUDFLARE_EVALUATION"] = "1"
        self.assertFalse(cloudflare_pilot_enabled(PILOT_OPERATION))
        self.assertEqual(self._call(), '{"provider":"gemini"}')
        self.cloud.assert_not_called()
        self.groq.chat.completions.create.assert_not_called()

    def test_explicit_dev_opt_in_routes_only_verdict_stage_to_cloudflare(self):
        self._enable()
        self.assertTrue(cloudflare_pilot_enabled(PILOT_OPERATION))
        self.assertEqual(self._call(), VALID_EVALUATION)
        self.cloud.assert_called_once_with(
            "System instructions", "User dossier",
        )
        self.gemini.models.generate_content.assert_not_called()
        self.groq.chat.completions.create.assert_not_called()

    def test_other_pipeline_stages_keep_legacy_provider_order(self):
        self._enable()
        self.assertEqual(
            self._call(operation="claim_gate"), '{"provider":"gemini"}',
        )
        self.cloud.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_production_denies_pilot_even_with_flag_set(self):
        self._enable()
        self.assertFalse(cloudflare_pilot_enabled(PILOT_OPERATION))
        self.assertEqual(self._call(), '{"provider":"gemini"}')
        self.cloud.assert_not_called()

    @override_settings(APP_ENV="staging", DEBUG=True)
    def test_staging_denies_pilot_even_with_debug_and_flag(self):
        self._enable()
        self.assertFalse(cloudflare_pilot_enabled(PILOT_OPERATION))
        self.assertEqual(self._call(), '{"provider":"gemini"}')
        self.cloud.assert_not_called()

    @override_settings(APP_ENV="development", DEBUG=False)
    def test_debug_false_blocks_pilot(self):
        self._enable()
        self.assertFalse(cloudflare_pilot_enabled(PILOT_OPERATION))
        self.assertEqual(self._call(), '{"provider":"gemini"}')
        self.cloud.assert_not_called()

    def test_cloudflare_outage_falls_back_to_gemini_and_does_not_fabricate_verdict(self):
        self._enable()
        self.cloud.side_effect = CloudflareEvaluationError("HTTP_429")
        with self.assertLogs("api.services", level="WARNING") as events:
            result = self._call()
        self.assertEqual(result, '{"provider":"gemini"}')
        self.assertIn("CloudflareEvaluationError", "\n".join(events.output))
        self.assertNotIn("UNVERIFIED", "\n".join(events.output))
        self.gemini.models.generate_content.assert_called_once()

    def test_failed_cloudflare_and_gemini_reach_original_groq(self):
        self._enable()
        self.cloud.side_effect = CloudflareEvaluationError("TRANSPORT_ReadTimeout")
        self.gemini.models.generate_content.side_effect = RuntimeError(
            "Gemini outage",
        )
        self.assertEqual(self._call(), '{"provider":"groq"}')
        self.cloud.assert_called_once()
        self.gemini.models.generate_content.assert_called_once()
        self.groq.chat.completions.create.assert_called_once()

    def test_all_unavailable_propagates_existing_provider_exception(self):
        self._enable()
        self.cloud.side_effect = CloudflareEvaluationError("HTTP_402")
        self.gemini.models.generate_content.side_effect = RuntimeError(
            "unavailable",
        )
        self.groq.chat.completions.create.side_effect = RuntimeError(
            "unavailable",
        )
        with self.assertRaises(LLMProviderUnavailableError):
            evaluate_claim_with_persisted_evidence(
                "The Senate has 24 senators.", "Article VI says 24.",
            )
        self.assertEqual(self.cloud.call_count, 1)

    def test_cloudflare_circuit_break_is_scoped_to_one_job(self):
        self._enable()
        self.cloud.side_effect = [
            CloudflareEvaluationError("HTTP_429"),
            VALID_EVALUATION,
        ]
        with llm_provider_scope():
            self.assertEqual(self._call(), '{"provider":"gemini"}')
            self.assertEqual(self._call(), '{"provider":"gemini"}')
        self.assertEqual(self.cloud.call_count, 1)
        with llm_provider_scope():
            self.assertEqual(self._call(), VALID_EVALUATION)
        self.assertEqual(self.cloud.call_count, 2)

    def test_cloudflare_scope_is_reset_after_exception(self):
        self._enable()
        self.cloud.side_effect = [
            CloudflareEvaluationError("HTTP_429"),
            VALID_EVALUATION,
        ]
        with self.assertRaises(RuntimeError):
            with llm_provider_scope():
                self.assertEqual(self._call(), '{"provider":"gemini"}')
                raise RuntimeError("verification interrupted")
        with llm_provider_scope():
            self.assertEqual(self._call(), VALID_EVALUATION)

    def test_valid_cloudflare_response_survives_production_evaluator(self):
        self._enable()
        evaluated = evaluate_claim_with_persisted_evidence(
            "The Senate is composed of 24 senators.",
            "=== SOURCE IDENTITY GROUP 1 ===\nArticle VI sets 24.",
        )
        self.assertEqual(evaluated["verdict"], "FACT")
        self.assertEqual(evaluated["confidence_score"], 95)
        self.assertEqual(self.cloud.call_count, 1)

    def test_non_verdict_operation_preserves_original_groq_fallback(self):
        self._enable()
        self.gemini.models.generate_content.side_effect = RuntimeError(
            "gemini error",
        )
        self.assertEqual(
            self._call(operation="claim_equivalence"), '{"provider":"groq"}',
        )
        self.cloud.assert_not_called()

    def test_telemetry_provider_allowlist_includes_cloudflare(self):
        self.assertIn("cloudflare", SAFE_LLM_PROVIDERS)


class CloudflarePilotValidationTests(SimpleTestCase):
    def test_adapter_output_must_be_complete_json_before_routing(self):
        from api.verification.cloudflare_pilot import call_validated_cloudflare_pilot
        with patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json",
            return_value=VALID_EVALUATION,
        ) as llm:
            self.assertEqual(
                call_validated_cloudflare_pilot("System", "Dossier"),
                VALID_EVALUATION,
            )
        self.assertEqual(
            llm.call_args.kwargs["max_completion_tokens"],
            PILOT_COMPLETION_TOKENS,
        )

    def test_truncated_or_invalid_result_is_rejected_not_treated_as_unverified(self):
        from api.verification.cloudflare_pilot import call_validated_cloudflare_pilot
        for bad in (
            "",
            "{}",
            "not json",
            '{"verdict":"UNVERIFIED"}',
            json.dumps({
                **json.loads(VALID_EVALUATION),
                "confidence_score": True,
            }),
        ):
            with self.subTest(output=bad[:20]), patch(
                "api.verification.cloudflare_pilot.generate_evaluation_json",
                return_value=bad,
            ):
                with self.assertRaisesRegex(
                    CloudflareEvaluationError, "INVALID_EVALUATION_JSON",
                ):
                    call_validated_cloudflare_pilot("System", "Dossier")
