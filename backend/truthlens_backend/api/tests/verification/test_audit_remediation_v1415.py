from django.test import SimpleTestCase

from api import services
from api.verification.runs import CURRENT_VERIFICATION_PIPELINE_VERSION


class VerificationAuditRemediationV1415Tests(SimpleTestCase):
    def test_high_specificity_direct_text_rescue_is_narrow(self):
        self.assertTrue(
            services.can_rescue_direct_text_insufficient_context(
                (
                    "The review team in Maria Santos's disciplinary hearing "
                    "declared victory in October 2026."
                )
            )
        )

        rejected = (
            "He stole funds from DSWD in 2026.",
            "The senator was arrested in October 2026.",
            "Joel Santos stole 800 million pesos in 2026.",
            "The review team declared victory.",
            "Maria Santos disciplinary hearing October 2026.",
        )
        for claim in rejected:
            with self.subTest(claim=claim):
                self.assertFalse(
                    services.can_rescue_direct_text_insufficient_context(claim)
                )

    def test_direct_text_rescue_requires_exact_source_specificity_not_truth(self):
        # The helper must remain structural only. A false or implausible claim can
        # still be claimable; retrieval/evidence reasoning decides its verdict.
        claim = (
            "The Lunar Council in Maria Santos's 2026 hearing declared victory "
            "in November 2026."
        )
        self.assertTrue(
            services.can_rescue_direct_text_insufficient_context(claim)
        )

    def test_final_claimgate_refinement_has_new_pipeline_version(self):
        self.assertEqual(CURRENT_VERIFICATION_PIPELINE_VERSION, "1.4.15")
