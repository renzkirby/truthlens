import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services


DART_CLAIM = (
    "NASA's DART spacecraft intentionally collided with Dimorphos, "
    "the moonlet of asteroid Didymos, on September 26, 2022."
)
DART_FOOTAGE_CLAIM = (
    "A viral video authentically shows NASA's DART spacecraft "
    "colliding with Dimorphos."
)


class GoogleFactCheckPropositionCoverageTests(SimpleTestCase):
    def test_same_event_different_proposition_is_rejected_by_coverage_contract(self):
        response = json.dumps({
            "reasoning": (
                "The reviewed claim concerns footage authenticity and does not "
                "cover the submitted claim's intent and exact date."
            ),
            "is_relevant": False,
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ) as llm:
            self.assertFalse(
                services.is_fact_check_relevant(
                    DART_CLAIM,
                    DART_FOOTAGE_CLAIM,
                )
            )

        system_prompt, user_prompt = llm.call_args.args
        self.assertIn("same materially asserted factual proposition", system_prompt)
        self.assertIn("intent or purpose", system_prompt)
        self.assertIn("dates/time period", system_prompt)
        self.assertIn("Topical overlap", system_prompt)
        self.assertEqual(
            json.loads(user_prompt),
            {
                "claim": DART_CLAIM,
                "fact_check_reviewed_claim": DART_FOOTAGE_CLAIM,
            },
        )
        self.assertEqual(
            llm.call_args.kwargs["operation"],
            "fact_check_relevance",
        )

    def test_equivalent_reviewed_claim_can_pass_coverage_gate(self):
        response = json.dumps({
            "reasoning": "The reviewed claim preserves the same material proposition.",
            "is_relevant": True,
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ):
            self.assertTrue(
                services.is_fact_check_relevant(
                    DART_CLAIM,
                    (
                        "On September 26, 2022, NASA intentionally sent DART "
                        "into Dimorphos, the moonlet of asteroid Didymos."
                    ),
                )
            )

    def test_loose_or_malformed_relevance_json_fails_closed(self):
        for response in (
            '{"reasoning":"Same event.","is_relevant":true,"extra":"unsafe"}',
            '{"reasoning":"","is_relevant":true}',
            '{"reasoning":"Same event.","is_relevant":"true"}',
            '[]',
            'not-json',
        ):
            with self.subTest(response=response), patch(
                "api.services.call_llm_with_fallback",
                return_value=response,
            ):
                self.assertFalse(
                    services.is_fact_check_relevant(
                        DART_CLAIM,
                        DART_FOOTAGE_CLAIM,
                    )
                )

    def test_blank_inputs_fail_closed_without_provider_call(self):
        with patch("api.services.call_llm_with_fallback") as llm:
            for incoming, reviewed in (
                ("", DART_FOOTAGE_CLAIM),
                (DART_CLAIM, ""),
                (None, DART_FOOTAGE_CLAIM),
                (DART_CLAIM, None),
            ):
                with self.subTest(incoming=incoming, reviewed=reviewed):
                    self.assertFalse(
                        services.is_fact_check_relevant(incoming, reviewed)
                    )
        llm.assert_not_called()
