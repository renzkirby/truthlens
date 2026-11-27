import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services
from api.verification.runs import CURRENT_VERIFICATION_PIPELINE_VERSION


class VerificationAuditRemediationV1416Tests(SimpleTestCase):
    def test_stable_direct_text_claims_do_not_require_a_calendar_date(self):
        accepted = (
            "Jupiter's moon Europa currently harbors microbial life in its subsurface ocean.",
            "The Philippines has 82 provinces.",
            "WHO recognizes malaria as a global health concern.",
            "Joel Santos stole 800 million pesos in 2026.",
            "The city government plans to open a new hospital in Bacoor.",
        )
        for claim in accepted:
            with self.subTest(claim=claim):
                self.assertTrue(
                    services.can_rescue_direct_text_insufficient_context(claim)
                )

    def test_only_genuinely_ambiguous_or_incomplete_direct_text_stays_blocked(self):
        rejected = (
            "He stole government funds.",
            "She approved it in 2026.",
            "They moved it to Manila.",
            "The senator was arrested yesterday.",
            "The president met NASA officials.",
            "Joel stole 800 million pesos.",
            "Sara gave back the money she stole.",
            "PBBM subway underground.",
            "DOH dengue outbreak Cebu.",
            "Maria Santos disciplinary hearing October 2026.",
            "The review team declared victory.",
        )
        for claim in rejected:
            with self.subTest(claim=claim):
                self.assertFalse(
                    services.can_rescue_direct_text_insufficient_context(claim)
                )

    def test_claim_gate_prompt_reserves_insufficient_context_for_real_ambiguity(self):
        payload = {
            "cleaned_claim": "OUT_OF_SCOPE",
            "search_query": "",
            "search_queries": [],
            "article_stance": "NEUTRAL",
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(payload),
        ) as provider:
            services.clean_ocr_text("Generic input.")
            services.extract_search_query(
                "Generic input.",
                "https://example.com/article",
            )

        prompts = [" ".join(call.args[0].split()) for call in provider.call_args_list]
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:
            self.assertIn(
                "A date is NOT required for a stable state-of-the-world claim.",
                prompt,
            )
            self.assertIn(
                "Use it only when a material referent or proposition is genuinely unresolved.",
                prompt,
            )
            self.assertIn(
                "specifically named organization, place, product/model, scientific object, celestial body",
                prompt,
            )
            # Keep benchmark wording out of the production prompt.
            self.assertNotIn(
                "Jupiter's moon Europa currently harbors microbial life",
                prompt,
            )

    def test_noun_like_suffixes_do_not_manufacture_predicates(self):
        fragments = (
            "Maria Santos disciplinary hearing October 2026.",
            "United Nations climate meeting 2026.",
            "NASA funding increase 2026.",
            "Company X building permit Manila.",
            "WHO rating update 2026.",
        )
        for text in fragments:
            with self.subTest(text=text):
                self.assertFalse(services._has_explicit_predicate_cue(text))
                self.assertFalse(
                    services.can_rescue_direct_text_insufficient_context(text)
                )

    def test_common_present_tense_factual_predicates_are_recognized(self):
        for claim in (
            "WHO recognizes malaria as a global health concern.",
            "NASA plans a new lunar mission for 2027.",
            "The report shows a decline in unemployment.",
            "Company X sells electric buses in Manila.",
            "Mars hosts a robotic research station in the fictional example.",
        ):
            with self.subTest(claim=claim):
                self.assertTrue(services._has_explicit_predicate_cue(claim))

    def test_v1416_pipeline_version(self):
        self.assertEqual(CURRENT_VERIFICATION_PIPELINE_VERSION, "1.4.16")
