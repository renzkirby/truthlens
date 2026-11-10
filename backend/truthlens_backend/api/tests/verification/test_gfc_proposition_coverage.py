import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api.services import assess_fact_check_proposition_coverage


class GoogleFactCheckPropositionCoverageTests(SimpleTestCase):
    def test_batch_assessment_recognizes_later_equivalent_candidate(self):
        response = json.dumps({
            "candidates": [
                {
                    "candidate_index": 0,
                    "relationship": "PARTIAL_OR_RELATED",
                    "reasoning": "Same event, but the action differs.",
                    "material_differences": ["Different action"],
                },
                {
                    "candidate_index": 1,
                    "relationship": "EQUIVALENT_OR_COVERS",
                    "reasoning": "The second candidate preserves every material assertion.",
                    "material_differences": [],
                },
            ]
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ) as provider:
            result = assess_fact_check_proposition_coverage(
                "Person A resigned from office on Monday.",
                [
                    "Person A was investigated while holding office.",
                    "Person A resigned from office on Monday.",
                ],
            )

        self.assertTrue(result["terminally_sufficient"])
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["relevant_candidate_count"], 2)
        self.assertEqual(result["covered_candidate_count"], 1)
        self.assertEqual(
            result["reason_code"],
            "EXACT_OR_EQUIVALENT_COVERAGE",
        )
        self.assertEqual(
            provider.call_args.kwargs["operation"],
            "gfc_proposition_coverage",
        )
        system_prompt, user_prompt = provider.call_args.args
        self.assertIn("actor/subject", system_prompt)
        self.assertIn("predicate/action", system_prompt)
        self.assertIn("quantity/statistic", system_prompt)
        self.assertIn("attribution/speaker", system_prompt)
        self.assertIn("polarity/negation", system_prompt)
        payload = json.loads(user_prompt)
        self.assertEqual(len(payload["reviewed_claim_candidates"]), 2)

    def test_related_candidate_is_useful_but_not_terminal(self):
        response = json.dumps({
            "candidates": [
                {
                    "candidate_index": 0,
                    "relationship": "PARTIAL_OR_RELATED",
                    "reasoning": "The same event is discussed, but the submitted amount is not covered.",
                    "material_differences": ["Submitted amount is not covered"],
                }
            ]
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ):
            result = assess_fact_check_proposition_coverage(
                "Organization X paid 800 million pesos to Person A.",
                ["Organization X made a payment connected with the event."],
            )

        self.assertFalse(result["terminally_sufficient"])
        self.assertEqual(result["relevant_candidate_count"], 1)
        self.assertEqual(result["covered_candidate_count"], 0)
        self.assertEqual(result["reason_code"], "RELATED_BUT_INCOMPLETE")

    def test_materially_different_candidates_are_not_relevant(self):
        response = json.dumps({
            "candidates": [
                {
                    "candidate_index": 0,
                    "relationship": "DIFFERENT",
                    "reasoning": "The attribution is to a different speaker.",
                    "material_differences": ["Different speaker"],
                },
                {
                    "candidate_index": 1,
                    "relationship": "DIFFERENT",
                    "reasoning": "The candidate reverses the submitted claim's polarity.",
                    "material_differences": ["Negation differs"],
                },
            ]
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ):
            result = assess_fact_check_proposition_coverage(
                "Person A approved the proposal.",
                [
                    "Person B approved the proposal.",
                    "Person A did not approve the proposal.",
                ],
            )

        self.assertFalse(result["terminally_sufficient"])
        self.assertEqual(result["relevant_candidate_count"], 0)
        self.assertEqual(result["reason_code"], "MATERIAL_DIFFERENCE")

    def test_duplicate_reviewed_claims_are_deduplicated_before_provider_call(self):
        response = json.dumps({
            "candidates": [
                {
                    "candidate_index": 0,
                    "relationship": "EQUIVALENT_OR_COVERS",
                    "reasoning": "The proposition is equivalent.",
                    "material_differences": [],
                }
            ]
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ) as provider:
            result = assess_fact_check_proposition_coverage(
                "A claim",
                [" A reviewed claim ", "a reviewed claim"],
            )

        self.assertEqual(result["candidate_count"], 1)
        payload = json.loads(provider.call_args.args[1])
        self.assertEqual(
            payload["reviewed_claim_candidates"],
            [{"candidate_index": 0, "text": "A reviewed claim"}],
        )

    def test_malformed_response_fails_closed(self):
        with patch(
            "api.services.call_llm_with_fallback",
            return_value='{"candidates":[{"candidate_index":0,"relationship":"EQUIVALENT_OR_COVERS","reasoning":"same","material_differences":[],"extra":true}]}',
        ):
            result = assess_fact_check_proposition_coverage(
                "A claim",
                ["A reviewed claim"],
            )

        self.assertFalse(result["terminally_sufficient"])
        self.assertEqual(result["reason_code"], "ASSESSMENT_FAILED")
        self.assertEqual(
            result["candidates"][0]["relationship"],
            "UNDETERMINED",
        )

    def test_provider_failure_fails_closed_without_fabricating_coverage(self):
        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=RuntimeError("provider unavailable"),
        ):
            result = assess_fact_check_proposition_coverage(
                "A claim",
                ["A reviewed claim"],
            )

        self.assertFalse(result["terminally_sufficient"])
        self.assertEqual(result["covered_candidate_count"], 0)
        self.assertEqual(result["reason_code"], "ASSESSMENT_FAILED")

    def test_blank_candidate_set_does_not_call_provider(self):
        with patch("api.services.call_llm_with_fallback") as provider:
            result = assess_fact_check_proposition_coverage(
                "A claim",
                ["", "   ", None],
            )

        provider.assert_not_called()
        self.assertFalse(result["terminally_sufficient"])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["reason_code"], "NO_RELEVANT_CANDIDATE")
