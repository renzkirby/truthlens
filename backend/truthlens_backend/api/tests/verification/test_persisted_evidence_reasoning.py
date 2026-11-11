import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services
from api.services import (
    LLMProviderUnavailableError,
    OFFICIAL_FACT_CHECK_RESOLUTION_FAKE_CONFLICT,
    OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
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

    def test_equivalent_official_satire_resolution_allows_neutral_submission_satire(self):
        evidence_id = "11111111-1111-1111-1111-111111111111"
        result_payload = {
            **self.result,
            "verdict": "SATIRE",
            "contextual_basis_kind": "SATIRE_PROVENANCE",
            "contextual_basis_evidence_ids": [evidence_id],
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(result_payload),
        ) as call_llm:
            result = evaluate_claim_with_persisted_evidence(
                "A factual-looking claim.",
                "Persisted evidence.",
                article_stance="NEUTRAL",
                official_fact_check_resolution=OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
                official_satire_evidence_ids=[evidence_id],
            )

        self.assertEqual(result["verdict"], "SATIRE")
        self.assertEqual(result["contextual_basis_kind"], "SATIRE_PROVENANCE")
        user_prompt = call_llm.call_args.args[1]
        self.assertIn(
            "<official_fact_check_resolution>SATIRE</official_fact_check_resolution>",
            user_prompt,
        )
        self.assertIn(evidence_id, user_prompt)

    def test_official_satire_resolution_fails_closed_when_evaluator_ignores_policy(self):
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(self.result),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "A claim with equivalent official satire provenance.",
                "Persisted evidence.",
                official_fact_check_resolution=OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)

    def test_satire_false_conflict_requires_fake_verdict(self):
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(self.result),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "A claim with conflicting official ratings.",
                "Persisted evidence.",
                official_fact_check_resolution=(
                    OFFICIAL_FACT_CHECK_RESOLUTION_FAKE_CONFLICT
                ),
            )

        self.assertEqual(result["verdict"], "FAKE")

        invalid = {**self.result, "verdict": "SATIRE"}
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(invalid),
        ):
            result = evaluate_claim_with_persisted_evidence(
                "A claim with conflicting official ratings.",
                "Persisted evidence.",
                official_fact_check_resolution=(
                    OFFICIAL_FACT_CHECK_RESOLUTION_FAKE_CONFLICT
                ),
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)

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

    def test_materiality_audit_turns_narrow_supported_claim_into_fact(self):
        evidence_id = "11111111-1111-1111-1111-111111111111"
        initial = {
            **self.result,
            "verdict": "MISLEADING",
            "reasoning": "The evidence adds broader continuing-risk context.",
            "summary": "The claim is true but omits broader context.",
            "contextual_basis_kind": "MISSING_CONTEXT",
            "contextual_basis_evidence_ids": [evidence_id],
        }
        audited = {
            **self.result,
            "verdict": "FACT",
            "reasoning": (
                "The evidence directly supports the exact submitted proposition; "
                "the additional material concerns a broader topic not asserted."
            ),
            "summary": "The exact submitted proposition is supported.",
            "confidence_score": 94,
            "score_context": "The exact claim is directly supported by the dossier.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(initial), json.dumps(audited)],
        ) as call_llm:
            result = evaluate_claim_with_persisted_evidence(
                "The agency ended the declared emergency on May 5.",
                (
                    f"Evidence link ID: {evidence_id}\n"
                    "The agency ended the declared emergency on May 5. "
                    "Officials separately noted that underlying risks continued."
                ),
            )

        self.assertEqual(result["verdict"], "FACT")
        self.assertEqual(result["contextual_basis_kind"], "NONE")
        self.assertEqual(result["contextual_basis_evidence_ids"], [])
        self.assertEqual(call_llm.call_count, 2)
        audit_system = call_llm.call_args_list[1].args[0]
        audit_user = call_llm.call_args_list[1].args[1]
        self.assertIn("CLAIM-SCOPE MATERIALITY RULES", audit_system)
        self.assertIn("do not import a stronger, broader", audit_system.lower())
        self.assertIn("<claim>The agency ended the declared emergency on May 5.</claim>", audit_user)
        self.assertIn("underlying risks continued", audit_user)

    def test_materiality_audit_preserves_broader_materially_distorted_claim(self):
        evidence_id = "22222222-2222-2222-2222-222222222222"
        initial = {
            **self.result,
            "verdict": "MISLEADING",
            "reasoning": "The claim overstates what ending the declaration meant.",
            "summary": "The declaration ended, but the underlying risk did not.",
            "contextual_basis_kind": "FALSE_CONTEXT",
            "contextual_basis_evidence_ids": [evidence_id],
        }
        audited = {
            **initial,
            "confidence_score": 91,
            "score_context": "The cited evidence establishes the material false context.",
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(initial), json.dumps(audited)],
        ):
            result = evaluate_claim_with_persisted_evidence(
                (
                    "The agency ended the declared emergency on May 5, meaning "
                    "the underlying public-health risk was completely over."
                ),
                (
                    f"Evidence link ID: {evidence_id}\n"
                    "The declaration ended on May 5, but officials explicitly "
                    "said the underlying risk and response needs continued."
                ),
            )

        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["contextual_basis_kind"], "FALSE_CONTEXT")
        self.assertEqual(result["contextual_basis_evidence_ids"], [evidence_id])

    def test_materiality_audit_abstains_when_exact_proposition_is_not_established(self):
        evidence_id = "33333333-3333-3333-3333-333333333333"
        initial = {
            **self.result,
            "verdict": "MISLEADING",
            "reasoning": "Related evidence provides context but not direct support.",
            "summary": "The claim may omit context.",
            "contextual_basis_kind": "MISSING_CONTEXT",
            "contextual_basis_evidence_ids": [evidence_id],
        }
        audited = {
            **self.result,
            "verdict": "UNVERIFIED",
            "reasoning": "The dossier does not establish the exact submitted proposition.",
            "summary": "The exact claim is not established by the available evidence.",
            "confidence_score": 35,
            "score_context": "The dossier is related but insufficient for the exact claim.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(initial), json.dumps(audited)],
        ):
            result = evaluate_claim_with_persisted_evidence(
                "The agency ended a specific national declaration on May 5.",
                (
                    f"Evidence link ID: {evidence_id}\n"
                    "The source discusses the agency's emergency policy generally "
                    "but does not establish the specified declaration or date."
                ),
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["contextual_basis_kind"], "NONE")
        self.assertEqual(result["contextual_basis_evidence_ids"], [])

    def test_materiality_audit_invalid_misleading_basis_fails_closed(self):
        evidence_id = "44444444-4444-4444-4444-444444444444"
        initial = {
            **self.result,
            "verdict": "MISLEADING",
            "contextual_basis_kind": "MISSING_CONTEXT",
            "contextual_basis_evidence_ids": [evidence_id],
        }
        invalid_audit = {
            **initial,
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(initial), json.dumps(invalid_audit)],
        ):
            result = evaluate_claim_with_persisted_evidence(
                "Example claim.",
                f"Evidence link ID: {evidence_id}\nPersisted evidence.",
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
        self.assertEqual(result["contextual_basis_kind"], "NONE")

    def test_duplicate_contextual_basis_ids_fail_closed_through_materiality_audit(self):
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

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
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
        self.assertIn("SATIRE requires verified provenance", system_prompt)
        self.assertIn("official_fact_check_resolution is SATIRE", system_prompt)
        self.assertIn("FAKE_CONFLICT", system_prompt)
        self.assertIn("Failure to corroborate a claim alone is not sufficient", system_prompt)
        self.assertIn("Preserve entity, event, location, and time scope", system_prompt)
        self.assertIn("Materiality is claim-scoped", system_prompt)
        self.assertIn("Do NOT widen the claim", system_prompt)
        self.assertIn("official status, declaration, policy, emergency", system_prompt)
        self.assertIn("Evidence link ID", system_prompt)
        self.assertIn("USER-FACING SUMMARY RULES", system_prompt)
        self.assertIn("Start with the best-supported factual reality", system_prompt)
        self.assertIn("Never mention TruthLens", system_prompt)
        self.assertIn("Add information beyond merely restating", system_prompt)
        self.assertIn("Do not characterize independence", system_prompt)
        self.assertNotIn("45-75 words", system_prompt)
