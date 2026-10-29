"""Offline AI-RQ-2 opt-in Gemini -> Cloudflare -> Groq routing tests."""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from api.services import (
    LLMProviderUnavailableError,
    call_llm_with_fallback,
    llm_provider_scope,
)
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.provider_hierarchy import (
    gemini_job_blocking_error,
    hierarchy_enabled,
    requires_strict_stage_contract,
)


VALID_VERDICT = json.dumps({
    "reasoning": "The persisted evidence explicitly supports the dated event.",
    "verdict": "FACT",
    "summary": "The provided sources explicitly substantiate the claim.",
    "confidence_score": 92,
    "score_context": "A directly relevant persisted evidence passage.",
})


def evidence_prompt(size):
    return "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps({
        "claim_text": "The mission returned samples on September 24, 2023.",
        "evidence_items": [
            {"key": f"item_{i}", "evidence_content": f"Source passage {i}"}
            for i in range(size)
        ],
    })


def evidence_response(size):
    return json.dumps({
        "assessments": [
            {
                "key": f"item_{i}",
                "stance": "SUPPORTS",
                "relevance_score": 0.9,
                "directness_score": 0.8,
            }
            for i in range(size)
        ],
    })


class ExampleGeminiError(RuntimeError):
    def __init__(self, code):
        super().__init__("Never persist vendor request or claim details")
        self.code = code


class ExampleGroqRateLimit(RuntimeError):
    status_code = 429


@override_settings(APP_ENV="development", DEBUG=True)
class AIRQ2ProviderHierarchyTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "0",
            "CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING": "0",
            "CLOUDFLARE_PILOT_FINAL_MAX_TOKENS": "",
            "GROQ_MODEL": "openai/gpt-oss-120b",
        }))
        self.cloudflare = self.enterContext(patch(
            "api.services.call_validated_cloudflare_pilot",
            return_value=VALID_VERDICT,
        ))
        gemini = Mock()
        gemini.models.generate_content.return_value = SimpleNamespace(
            text=VALID_VERDICT,
        )
        self.gemini = self.enterContext(patch(
            "api.services.gemini_client", gemini,
        ))
        groq = Mock()
        self.groq = self.enterContext(patch(
            "api.services.groq_client", groq,
        ))
        self.groq_lane = groq.with_options.return_value
        self.groq_lane.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=VALID_VERDICT),
            )],
        )

    def _verdict(self):
        return call_llm_with_fallback(
            "Strict evidence-only evaluation instructions.",
            "<claim>A verifiable event occurred.</claim><persisted_evidence>Supported.</persisted_evidence>",
            operation="persisted_evidence_evaluation",
        )

    def test_opt_in_prioritizes_valid_gemini_and_never_pays_for_cloudflare(self):
        self.assertTrue(hierarchy_enabled())
        with patch("api.services.record_llm_provider_call") as record:
            self.assertEqual(self._verdict(), VALID_VERDICT)
        self.gemini.models.generate_content.assert_called_once()
        self.cloudflare.assert_not_called()
        self.groq.with_options.assert_not_called()
        self.assertEqual(record.call_args.args[1], "gemini")
        self.assertEqual(record.call_args.args[4], "success")

    def test_402_gemini_falls_through_to_cloudflare_before_groq(self):
        self.gemini.models.generate_content.side_effect = ExampleGeminiError(402)
        with patch("api.services.record_llm_provider_call") as record:
            self.assertEqual(self._verdict(), VALID_VERDICT)
        self.cloudflare.assert_called_once()
        self.groq.with_options.assert_not_called()
        self.assertEqual(
            [(x.args[1], x.args[4]) for x in record.call_args_list],
            [("gemini", "failed"), ("cloudflare", "success")],
        )

    def test_402_or_429_gemini_blocks_same_job_without_global_breaker(self):
        for status in (402, 429):
            with self.subTest(status=status):
                self.gemini.models.generate_content.reset_mock(
                    side_effect=True,
                )
                self.cloudflare.reset_mock()
                self.gemini.models.generate_content.side_effect = ExampleGeminiError(status)
                with llm_provider_scope():
                    self.assertEqual(self._verdict(), VALID_VERDICT)
                    self.assertEqual(self._verdict(), VALID_VERDICT)
                self.assertEqual(self.gemini.models.generate_content.call_count, 1)
                self.assertEqual(self.cloudflare.call_count, 2)
                with llm_provider_scope():
                    self.assertEqual(self._verdict(), VALID_VERDICT)
                self.assertEqual(self.gemini.models.generate_content.call_count, 2)

    def test_transient_gemini_failure_then_cloudflare_failure_reaches_groq_once(self):
        self.gemini.models.generate_content.side_effect = ExampleGeminiError(503)
        self.cloudflare.side_effect = CloudflareEvaluationError("TRANSPORT_ReadTimeout")
        with patch("api.services.record_llm_provider_call") as record:
            self.assertEqual(self._verdict(), VALID_VERDICT)
        self.groq.with_options.assert_called_once_with(max_retries=0)
        self.groq_lane.chat.completions.create.assert_called_once()
        self.assertEqual(
            [x.args[1] for x in record.call_args_list],
            ["gemini", "cloudflare", "groq"],
        )
        self.assertEqual(
            [x.args[4] for x in record.call_args_list],
            ["failed", "failed", "success"],
        )

    def test_genuine_cloudflare_outage_still_uses_job_scoped_breaker(self):
        self.gemini.models.generate_content.side_effect = ExampleGeminiError(402)
        self.cloudflare.side_effect = CloudflareEvaluationError("HTTP_429")
        with llm_provider_scope():
            self.assertEqual(self._verdict(), VALID_VERDICT)
            self.assertEqual(self._verdict(), VALID_VERDICT)
        self.assertEqual(self.gemini.models.generate_content.call_count, 1)
        self.cloudflare.assert_called_once()
        self.assertEqual(self.groq_lane.chat.completions.create.call_count, 2)

    def test_large_assessment_bypass_preserves_full_input_and_final_cloudflare(self):
        # A local Cloudflare "skipped" event is only emitted when the
        # assessment pilot is enabled but the batch exceeds its limit.
        os.environ["ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"] = "1"
        self.gemini.models.generate_content.side_effect = ExampleGeminiError(402)
        original = evidence_prompt(9)
        self.groq_lane.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=evidence_response(9)),
            )],
        )
        with llm_provider_scope(), patch(
            "api.services.record_llm_provider_call"
        ) as record:
            self.assertEqual(
                call_llm_with_fallback(
                    "Assess every original item independently.", original,
                    operation="evidence_assessment",
                ),
                evidence_response(9),
            )
            self.groq_lane.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=VALID_VERDICT),
                )],
            )
            self.assertEqual(self._verdict(), VALID_VERDICT)
        self.assertEqual(
            self.groq_lane.chat.completions.create.call_args_list[0].kwargs["messages"][1]["content"],
            original,
        )
        self.cloudflare.assert_called_once()
        self.assertEqual(
            [(call.args[1], call.args[4]) for call in record.call_args_list],
            [
                ("gemini", "failed"),
                ("cloudflare", "skipped"),
                ("groq", "success"),
                ("cloudflare", "success"),
            ],
        )

    def test_disabled_assessment_does_not_record_cloudflare_skipped(self):
        # With assessment off (the recommended initial live setup), no
        # Cloudflare assessment preflight or skip event should be logged.
        # A later final evaluation remains independently eligible.
        self.assertEqual(
            os.environ["ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"], "0",
        )
        self.gemini.models.generate_content.side_effect = ExampleGeminiError(402)
        original = evidence_prompt(9)
        self.groq_lane.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=evidence_response(9)),
            )],
        )
        with llm_provider_scope(), patch(
            "api.services.record_llm_provider_call",
        ) as record:
            self.assertEqual(
                call_llm_with_fallback(
                    "Assess every original item independently.", original,
                    operation="evidence_assessment",
                ),
                evidence_response(9),
            )
            self.groq_lane.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=VALID_VERDICT),
                )],
            )
            self.assertEqual(self._verdict(), VALID_VERDICT)

        self.assertEqual(
            self.groq_lane.chat.completions.create.call_args_list[0].kwargs[
                "messages"
            ][1]["content"],
            original,
        )
        self.cloudflare.assert_called_once()
        self.assertEqual(
            [(call.args[1], call.args[4]) for call in record.call_args_list],
            [
                ("gemini", "failed"),
                ("groq", "success"),
                ("cloudflare", "success"),
            ],
        )

    def test_assessment_flag_enables_cloudflare_only_after_gemini(self):
        os.environ["ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"] = "1"
        self.gemini.models.generate_content.side_effect = ExampleGeminiError(402)
        self.cloudflare.return_value = evidence_response(2)
        self.assertEqual(call_llm_with_fallback(
            "Assess source evidence.", evidence_prompt(2),
            operation="evidence_assessment",
        ), evidence_response(2))
        self.cloudflare.assert_called_once()
        self.assertEqual(self.cloudflare.call_args.kwargs["operation"], "evidence_assessment")

    def test_invalid_gemini_schema_falls_to_cloudflare(self):
        self.gemini.models.generate_content.return_value = SimpleNamespace(text="{}")
        self.assertEqual(self._verdict(), VALID_VERDICT)
        self.cloudflare.assert_called_once()
        self.groq.with_options.assert_not_called()

    def test_no_cloudflare_flag_keeps_strict_gemini_and_groq_stage_contracts(self):
        os.environ["ENABLE_CLOUDFLARE_VERIFICATION_PILOT"] = "0"
        self.gemini.models.generate_content.return_value = SimpleNamespace(text="{}")
        self.assertEqual(self._verdict(), VALID_VERDICT)
        self.cloudflare.assert_not_called()
        self.groq.with_options.assert_called_once_with(max_retries=0)

    def test_groq_429_stops_without_model_hopping_or_sdk_retry(self):
        self.gemini.models.generate_content.side_effect = ExampleGeminiError(402)
        self.cloudflare.side_effect = CloudflareEvaluationError("HTTP_429")
        self.groq_lane.chat.completions.create.side_effect = ExampleGroqRateLimit(
            "quota exhausted",
        )
        with patch("api.services.record_llm_provider_call") as record:
            with self.assertRaises(LLMProviderUnavailableError):
                self._verdict()
        self.groq.with_options.assert_called_once_with(max_retries=0)
        self.groq_lane.chat.completions.create.assert_called_once()
        self.assertEqual(
            self.groq_lane.chat.completions.create.call_args.kwargs["model"],
            "openai/gpt-oss-120b",
        )
        self.assertEqual(record.call_args.args[4], "failed")
        self.assertIn("code=429", record.call_args.args[5])
        self.assertNotIn("quota exhausted", str(record.call_args))

    def test_gemini_empty_response_is_not_marked_success(self):
        os.environ["ENABLE_CLOUDFLARE_VERIFICATION_PILOT"] = "0"
        self.gemini.models.generate_content.return_value = SimpleNamespace(text="")
        self.assertEqual(self._verdict(), VALID_VERDICT)
        self.cloudflare.assert_not_called()
        self.groq_lane.chat.completions.create.assert_called_once()

    def test_unapproved_cloudflare_operation_remains_gemini_then_groq(self):
        self.gemini.models.generate_content.side_effect = ExampleGeminiError(402)
        data = ('{"cleaned_claim":"An event occurred.",'
                '"search_query":"event",'
                '"search_queries":["event"],'
                '"article_stance":"NEUTRAL"}')
        self.groq_lane.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=data))],
        )
        result = call_llm_with_fallback(
            "Claim gate", "Submitted input",
            operation="claim_gate",
        )
        self.assertEqual(result, data)
        self.cloudflare.assert_not_called()
        self.groq_lane.chat.completions.create.assert_called_once()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_hierarchy_and_cloudflare_are_both_disabled_in_production(self):
        self.assertFalse(hierarchy_enabled())
        self.assertEqual(self._verdict(), VALID_VERDICT)
        self.cloudflare.assert_not_called()
        self.groq.with_options.assert_not_called()

    @override_settings(APP_ENV="staging", DEBUG=True)
    def test_hierarchy_disabled_in_staging(self):
        self.assertFalse(hierarchy_enabled())
        self.assertEqual(self._verdict(), VALID_VERDICT)
        self.cloudflare.assert_not_called()
        self.groq.with_options.assert_not_called()


class AIRQ2ProviderPolicyTests(SimpleTestCase):
    def test_only_http_402_and_429_block_gemini_for_job(self):
        for code in (402, 429):
            self.assertTrue(gemini_job_blocking_error(ExampleGeminiError(code)))
        for code in (400, 401, 403, 404, 500, 503, "402", True, None):
            self.assertFalse(gemini_job_blocking_error(ExampleGeminiError(code)))

    def test_stage_contract_selection_is_operation_aware(self):
        self.assertTrue(requires_strict_stage_contract(
            "persisted_evidence_evaluation", pilot_active=False,
            hierarchy_active=True,
        ))
        self.assertTrue(requires_strict_stage_contract(
            "evidence_assessment", pilot_active=False,
            hierarchy_active=True,
        ))
        self.assertTrue(requires_strict_stage_contract(
            "investigation_classification", pilot_active=False,
            hierarchy_active=True,
        ))
        self.assertTrue(requires_strict_stage_contract(
            "evidence_assessment", pilot_active=True,
            hierarchy_active=False,
        ))
        self.assertTrue(requires_strict_stage_contract(
            "claim_gate", pilot_active=False, hierarchy_active=True,
        ))
        self.assertFalse(requires_strict_stage_contract(
            "claim_gate", pilot_active=False, hierarchy_active=False,
        ))
