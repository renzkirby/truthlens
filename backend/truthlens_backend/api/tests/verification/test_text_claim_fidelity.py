from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase

from api.claim_matching import compute_fingerprint
from api.models import Claim
from api.services import inspect_direct_text_claim_fidelity


class DirectTextClaimFidelityTests(APITestCase):
    def test_preserves_equivalent_numeric_formatting(self):
        self.assertEqual(
            inspect_direct_text_claim_fidelity(
                "The rate was 62% in 2024.",
                "The rate was 62 percent in 2024.",
            ),
            "PASS",
        )

    def test_missing_material_year_fails(self):
        self.assertEqual(
            inspect_direct_text_claim_fidelity(
                (
                    "The Philippines had 109,035,343 people according to PSA, "
                    "so that figure should be used as its 2024 census population."
                ),
                (
                    "The Philippines had a population of 109,035,343 according "
                    "to the Philippine Statistics Authority (PSA)."
                ),
            ),
            "FAIL",
        )

    def test_changed_numeric_comparator_fails(self):
        self.assertEqual(
            inspect_direct_text_claim_fidelity(
                "The threshold is less than 62 km/h.",
                "The threshold is up to 62 km/h.",
            ),
            "FAIL",
        )

    def test_removed_tagalog_negation_fails(self):
        self.assertEqual(
            inspect_direct_text_claim_fidelity(
                "Hindi inaprubahan ng lungsod ang 2024 budget.",
                "The city approved the 2024 budget.",
            ),
            "FAIL",
        )

    def test_non_negating_not_only_phrase_does_not_false_block(self):
        self.assertEqual(
            inspect_direct_text_claim_fidelity(
                (
                    "The program not only reached 10 schools but also opened "
                    "new training centers."
                ),
                (
                    "The program reached 10 schools and opened new training "
                    "centers."
                ),
            ),
            "PASS",
        )

    def test_newly_introduced_year_fails(self):
        self.assertEqual(
            inspect_direct_text_claim_fidelity(
                "The city approved the project.",
                "The city approved the project in 2024.",
            ),
            "FAIL",
        )

    def test_long_or_multi_sentence_text_is_skipped_not_blocked(self):
        self.assertEqual(
            inspect_direct_text_claim_fidelity(
                "The city opened the bridge in 2024. Officials later discussed repairs.",
                "The city opened the bridge in 2024.",
            ),
            "SKIP",
        )
        self.assertEqual(
            inspect_direct_text_claim_fidelity(
                "A" * 501,
                "A" * 501,
            ),
            "SKIP",
        )


class TextCacheFidelityTests(APITestCase):
    def setUp(self):
        self.enterContext(
            patch(
                "api.throttles.FactCheckRateThrottle.allow_request",
                return_value=True,
            )
        )

    def _cached_fact(self, *, raw_text, stored_text):
        return Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=stored_text,
            claim_fingerprint=compute_fingerprint("TEXT", raw_text),
            claimability_status=Claim.ClaimabilityStatus.CLAIMABLE,
            ai_verdict="FACT",
            ai_summary="Cached summary.",
            consensus_score=90,
            source_type="Live Web Search",
        )

    @patch("api.views.text_fact_check_process.delay")
    def test_lossy_cached_text_is_not_reused(self, enqueue):
        raw_text = (
            "The Philippines had 109,035,343 people according to PSA, "
            "so that figure should be used as its 2024 census population."
        )
        cached = self._cached_fact(
            raw_text=raw_text,
            stored_text=(
                "The Philippines had a population of 109,035,343 according "
                "to the Philippine Statistics Authority (PSA)."
            ),
        )

        response = self.client.post(
            reverse("verify_text"),
            {"text": raw_text},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["cached"])
        self.assertNotEqual(payload["claim_id"], str(cached.pk))
        enqueue.assert_called_once()

    @patch("api.views.text_fact_check_process.delay")
    def test_faithful_cached_text_remains_reusable(self, enqueue):
        raw_text = "The city opened the bridge in 2024."
        cached = self._cached_fact(
            raw_text=raw_text,
            stored_text="The city opened the bridge in 2024.",
        )

        response = self.client.post(
            reverse("verify_text"),
            {"text": raw_text},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["cached"])
        self.assertEqual(payload["claim_id"], str(cached.pk))
        enqueue.assert_not_called()
