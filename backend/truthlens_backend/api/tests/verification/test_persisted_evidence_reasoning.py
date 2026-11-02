import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services
from api.services import (
    LLMProviderUnavailableError,
    evaluate_claim_with_persisted_evidence,
)


class PersistedEvidenceEvaluatorTests(SimpleTestCase):
    def setUp(self):
        self.result = {
            "reasoning": "The persisted evidence explicitly contradicts the claim.",
            "verdict": "FAKE",
            "summary": "Persisted evidence contradicts the claim.",
            "confidence_score": 92,
            "score_context": "Direct persisted evidence explicitly contradicts the submitted claim.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
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
        self.assertEqual(
            call_llm.call_args.kwargs,
            {
                "operation": "persisted_evidence_evaluation",
                "gemini_timeout_ms": services.PERSISTED_EVIDENCE_GEMINI_TIMEOUT_MS,
            },
        )
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
        self.assertNotIn("TruthLens", result["summary"])
        self.assertIn("no usable persisted evidence", result["summary"])
        self.assertEqual(
            set(result),
            {
                "reasoning",
                "verdict",
                "summary",
                "confidence_score",
                "score_context",
                "contextual_basis_kind",
                "contextual_basis_evidence_ids",
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

    def test_provider_unavailable_exception_propagates(self):
        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=LLMProviderUnavailableError(
                "No configured LLM provider completed the request."
            ),
        ):
            with self.assertRaises(LLMProviderUnavailableError):
                evaluate_claim_with_persisted_evidence(
                    "Example claim.",
                    "Persisted evidence.",
                )

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

    def test_neutral_factual_submission_rejects_satire_verdict_even_with_provenance_metadata(self):
        result_payload = {
            **self.result,
            "verdict": "SATIRE",
            "contextual_basis_kind": "SATIRE_PROVENANCE",
            "contextual_basis_evidence_ids": [
                "11111111-1111-1111-1111-111111111111",
            ],
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(result_payload),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "A factual claim presented as true.",
                "Persisted evidence.",
                article_stance="NEUTRAL",
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
        self.assertEqual(result["contextual_basis_kind"], "NONE")
        self.assertEqual(result["contextual_basis_evidence_ids"], [])

    def test_deterministic_satire_stance_allows_satire_verdict(self):
        result_payload = {
            **self.result,
            "verdict": "SATIRE",
            "contextual_basis_kind": "SATIRE_PROVENANCE",
            "contextual_basis_evidence_ids": [
                "11111111-1111-1111-1111-111111111111",
            ],
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(result_payload),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "A satirical claim.",
                "Persisted evidence.",
                article_stance="SATIRE",
            )

        self.assertEqual(result["verdict"], "SATIRE")
        self.assertEqual(result["contextual_basis_kind"], "SATIRE_PROVENANCE")
        self.assertEqual(
            result["contextual_basis_evidence_ids"],
            ["11111111-1111-1111-1111-111111111111"],
        )

    def test_contextual_basis_metadata_is_preserved_for_contextual_verdicts(self):
        contextual = {
            **self.result,
            "verdict": "MISLEADING",
            "contextual_basis_kind": "MISSING_CONTEXT",
            "contextual_basis_evidence_ids": ["11111111-1111-1111-1111-111111111111"],
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(contextual),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "Persisted evidence.",
            )

        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["contextual_basis_kind"], "MISSING_CONTEXT")
        self.assertEqual(
            result["contextual_basis_evidence_ids"],
            ["11111111-1111-1111-1111-111111111111"],
        )

    def test_duplicate_contextual_basis_ids_fail_closed_without_changing_verdict(self):
        duplicate_id = "11111111-1111-1111-1111-111111111111"
        contextual = {
            **self.result,
            "verdict": "MISLEADING",
            "contextual_basis_kind": "MISSING_CONTEXT",
            "contextual_basis_evidence_ids": [duplicate_id, duplicate_id],
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(contextual),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "Persisted evidence.",
            )

        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["confidence_score"], 92)
        self.assertEqual(result["contextual_basis_kind"], "NONE")
        self.assertEqual(result["contextual_basis_evidence_ids"], [])

    def test_non_contextual_verdict_discards_contextual_basis_metadata(self):
        non_contextual = {
            **self.result,
            "contextual_basis_kind": "SATIRE_PROVENANCE",
            "contextual_basis_evidence_ids": ["11111111-1111-1111-1111-111111111111"],
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(non_contextual),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                "Persisted evidence.",
            )

        self.assertEqual(result["verdict"], "FAKE")
        self.assertEqual(result["contextual_basis_kind"], "NONE")
        self.assertEqual(result["contextual_basis_evidence_ids"], [])

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
        self.assertIn("CONTEXTUAL BASIS METADATA", system_prompt)
        self.assertIn("SATIRE_ORIGIN_OF_MISINFORMATION", system_prompt)
        self.assertIn("submitted content itself is", system_prompt)
        self.assertIn("satire/parody", system_prompt)
        self.assertIn("SATIRE describes the submitted content itself", system_prompt)
        self.assertIn("SATIRE is eligible only when <stance>SATIRE</stance>", system_prompt)
        self.assertIn("originated from satire/parody does NOT make", system_prompt)
        self.assertIn("SATIRE_ORIGIN_OF_MISINFORMATION", system_prompt)
        self.assertIn("Evidence link ID", system_prompt)
        self.assertIn("USER-FACING SUMMARY RULES", system_prompt)
        self.assertIn("Start with the best-supported factual reality", system_prompt)
        self.assertIn("Never mention TruthLens", system_prompt)
        self.assertIn("Add information beyond merely restating", system_prompt)
