from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Claim


EXPECTED_MESSAGE = (
    "URL detected. Please use URL Verification to analyze this webpage."
)


class TextInputRoutingTests(APITestCase):
    @patch("api.views.text_fact_check_process.delay")
    @patch("api.views.compute_fingerprint")
    def test_standalone_url_is_rejected_before_text_verification(
        self,
        compute_fingerprint,
        text_task,
    ):
        response = self.client.post(
            reverse("verify_text"),
            {"text": "  https://example.com/article  "},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {
                "code": "URL_INPUT_DETECTED",
                "detail": EXPECTED_MESSAGE,
            },
        )
        self.assertEqual(Claim.objects.count(), 0)
        compute_fingerprint.assert_not_called()
        text_task.assert_not_called()

    @patch("api.views.text_fact_check_process.delay")
    @patch("api.views.find_matching_claim", return_value=None)
    @patch("api.views.compute_fingerprint", return_value=None)
    def test_text_claim_containing_url_stays_in_text_verification(
        self,
        compute_fingerprint,
        find_matching_claim,
        text_task,
    ):
        claim_text = (
            "According to https://example.com/article, "
            "the mayor resigned yesterday."
        )

        response = self.client.post(
            reverse("verify_text"),
            {"text": claim_text},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()["cached"])

        claim = Claim.objects.get(pk=response.json()["claim_id"])
        self.assertEqual(claim.claim_type, Claim.ClaimType.TEXT)
        self.assertEqual(claim.context_text, claim_text)

        compute_fingerprint.assert_called_once_with("TEXT", claim_text)
        find_matching_claim.assert_called_once()
        text_task.assert_called_once()

    @patch("api.views.text_fact_check_process.delay")
    @patch("api.views.find_matching_claim", return_value=None)
    @patch("api.views.compute_fingerprint", return_value=None)
    def test_url_like_text_without_http_scheme_is_not_silently_rerouted(
        self,
        compute_fingerprint,
        find_matching_claim,
        text_task,
    ):
        claim_text = "example.com/article"

        response = self.client.post(
            reverse("verify_text"),
            {"text": claim_text},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()["cached"])
        self.assertEqual(Claim.objects.get().context_text, claim_text)
        text_task.assert_called_once()
