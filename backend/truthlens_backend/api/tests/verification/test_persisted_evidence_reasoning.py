import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api.services import evaluate_claim_with_persisted_evidence


class PersistedEvidenceEvaluatorTests(SimpleTestCase):
    def setUp(self):
        self.result = {
            "reasoning": "The persisted evidence explicitly contradicts the claim.",
            "verdict": "FAKE",
            "summary": "Persisted evidence contradicts the claim.",
            "confidence_score": 92,
            "score_context": "Direct persisted evidence explicitly contradicts the submitted claim.",
        }

    def test_supplied_persisted_context_is_sent_without_provider_structure(self):
        evidence_context = (
            "=== SOURCE IDENTITY GROUP 1 ===\n"
            "--- EVIDENCE ITEM 1 ---\n"
            "Content:\nPersisted rating: False"
        )
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(self.result),
        ) as call_llm:
            evaluate_claim_with_persisted_evidence(
                "Example claim.",
                evidence_context,
                "NEUTRAL",
            )

        user_prompt = call_llm.call_args.args[1]
        self.assertIn(evidence_context, user_prompt)
        self.assertIn("<claim>Example claim.</claim>", user_prompt)
        self.assertNotIn("claimReview", user_prompt)
        self.assertNotIn("Web Search Answer", user_prompt)

    def test_blank_context_returns_unverified_zero_without_llm_call(self):
        with patch("api.services.call_llm_with_fallback") as call_llm:
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "  \n\t",
            )

        call_llm.assert_not_called()
        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
        self.assertEqual(
            set(result),
            {
                "reasoning",
                "verdict",
                "summary",
                "confidence_score",
                "score_context",
            },
        )

    def test_llm_exception_returns_safe_unverified_result(self):
        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "Persisted evidence.",
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
        self.assertIn("persisted evidence", result["reasoning"].lower())

    def test_valid_parsed_result_is_returned_unchanged(self):
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(self.result),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "Persisted evidence.",
            )

        self.assertEqual(result, self.result)

    def test_invalid_parsed_shape_returns_safe_unverified_result(self):
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(["not", "an", "evaluation"]),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "Persisted evidence.",
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)

    def test_invalid_verdict_returns_safe_unverified_result(self):
        invalid_result = {**self.result, "verdict": "TRUE"}
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(invalid_result),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "Persisted evidence.",
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)

    def test_prompt_contains_source_identity_and_anti_double_counting_guidance(self):
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(self.result),
        ) as call_llm:
            evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "Persisted evidence.",
            )

        system_prompt = call_llm.call_args.args[0]
        self.assertIn("SOURCE IDENTITY GROUP", system_prompt)
        self.assertIn("must not be counted", system_prompt)
        self.assertIn("not guaranteed to be editorially", system_prompt)
        self.assertIn("Source count is not proof", system_prompt)
        self.assertIn("Conflicting, irrelevant, or insufficient", system_prompt)
