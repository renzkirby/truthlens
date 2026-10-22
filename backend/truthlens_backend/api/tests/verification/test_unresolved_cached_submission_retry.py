"""Ensure failed/unresolved cached matches do not permanently block verification."""
from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase

from api.claim_matching import compute_fingerprint
from api.models import Claim, VerificationRun


class UnresolvedCachedSubmissionRetryTests(APITestCase):
    def setUp(self):
        # Endpoint behavior is under test, not the independent rate limiter.
        self.enterContext(
            patch("api.throttles.FactCheckRateThrottle.allow_request", return_value=True)
        )

    def _old_claim(self, claim_type, text, status, ai_verdict=None):
        fields = {
            "claim_type": claim_type,
            "claim_fingerprint": compute_fingerprint(claim_type, text),
            "ai_verdict": ai_verdict,
        }
        if claim_type == Claim.ClaimType.TEXT:
            fields["context_text"] = text
        elif claim_type == Claim.ClaimType.URL:
            fields["url_link"] = text
        else:
            fields["media_hash"] = text
        old = Claim.objects.create(**fields)
        previous = VerificationRun.objects.create(
            claim=old,
            status=status,
            failure_stage=("final_evaluator" if status == "FAILED" else None),
            failure_code=("LLM_UNAVAILABLE" if status == "FAILED" else None),
        )
        return old, previous

    def test_failed_text_cache_creates_fresh_claim_and_preserves_failed_run(self):
        text = "Under the SIM Registration Act, Filipinos must register SIM cards."
        old, failed_run = self._old_claim(
            Claim.ClaimType.TEXT, text, VerificationRun.Status.FAILED
        )
        with patch("api.views.text_fact_check_process.delay") as enqueue:
            response = self.client.post(reverse("verify_text"), {"text": text}, format="json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["cached"])
        self.assertNotEqual(payload["claim_id"], str(old.pk))
        new = Claim.objects.get(pk=payload["claim_id"])
        self.assertEqual(new.context_text, text)
        self.assertEqual(new.claim_fingerprint, old.claim_fingerprint)
        self.assertEqual(new.claim_type, Claim.ClaimType.TEXT)
        enqueue.assert_called_once()
        self.assertEqual(enqueue.call_args.args[:2], (text, new.pk))
        failed_run.refresh_from_db()
        self.assertEqual(failed_run.status, VerificationRun.Status.FAILED)
        self.assertEqual(failed_run.failure_code, "LLM_UNAVAILABLE")
        self.assertEqual(old.verification_runs.count(), 1)

    def test_other_terminal_unresolved_text_cache_is_retryable(self):
        for status in (
            VerificationRun.Status.ABSTAINED,
            VerificationRun.Status.COMPLETED,
            VerificationRun.Status.CANCELLED,
        ):
            with self.subTest(status=status):
                text = f"This is a new public factual claim for {status} verification."
                old, previous = self._old_claim(Claim.ClaimType.TEXT, text, status)
                with patch("api.views.text_fact_check_process.delay") as enqueue:
                    response = self.client.post(
                        reverse("verify_text"), {"text": text}, format="json"
                    )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["cached"])
                self.assertNotEqual(response.json()["claim_id"], str(old.pk))
                enqueue.assert_called_once()
                previous.refresh_from_db()
                self.assertEqual(previous.status, status)

    def test_pending_and_running_cache_remains_single_inflight_verification(self):
        for status in (VerificationRun.Status.PENDING, VerificationRun.Status.RUNNING):
            with self.subTest(status=status):
                text = f"Pending public claim with existing {status} verification."
                old, _ = self._old_claim(Claim.ClaimType.TEXT, text, status)
                with patch("api.views.text_fact_check_process.delay") as enqueue:
                    response = self.client.post(
                        reverse("verify_text"), {"text": text}, format="json"
                    )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["cached"])
                self.assertEqual(response.json()["claim_id"], str(old.pk))
                self.assertEqual(response.json()["match"]["match_type"], "no_verdict")
                enqueue.assert_not_called()

    def test_substantive_ai_cache_still_returns_cached_result(self):
        text = "A historical public claim with a previously verified result."
        old, _ = self._old_claim(
            Claim.ClaimType.TEXT, text, VerificationRun.Status.COMPLETED,
            ai_verdict="FACT",
        )
        with patch("api.views.text_fact_check_process.delay") as enqueue:
            response = self.client.post(reverse("verify_text"), {"text": text}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cached"])
        self.assertEqual(response.json()["claim_id"], str(old.pk))
        self.assertEqual(response.json()["match"]["verdict"], "FACT")
        enqueue.assert_not_called()

    def test_unverified_terminal_ai_cache_can_be_reassessed(self):
        text = "A past unresolved fact-check should be independently rechecked."
        old, _ = self._old_claim(
            Claim.ClaimType.TEXT, text, VerificationRun.Status.ABSTAINED,
            ai_verdict="UNVERIFIED",
        )
        with patch("api.views.text_fact_check_process.delay") as enqueue:
            response = self.client.post(reverse("verify_text"), {"text": text}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["cached"])
        self.assertNotEqual(response.json()["claim_id"], str(old.pk))
        enqueue.assert_called_once()

    def test_authoritative_resolution_is_still_cached_without_ai_verdict(self):
        text = "A public claim with a published institutional finding."
        old, _ = self._old_claim(
            Claim.ClaimType.TEXT, text, VerificationRun.Status.FAILED
        )
        published_payload = {"resolution_source": "OFFICIAL_FACT_CHECK", "verdict": "FACT"}
        with (
            patch("api.views.get_match_result", return_value=published_payload) as result,
            patch("api.views.text_fact_check_process.delay") as enqueue,
        ):
            response = self.client.post(
                reverse("verify_text"), {"text": text}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cached"])
        self.assertEqual(response.json()["claim_id"], str(old.pk))
        self.assertEqual(response.json()["match"], published_payload)
        self.assertEqual(result.call_count, 2)
        enqueue.assert_not_called()

    def test_failed_url_cache_requeues_while_preserving_existing_claim(self):
        url = "https://example.com/previously-failed-claim"
        old, previous = self._old_claim(
            Claim.ClaimType.URL, url, VerificationRun.Status.FAILED
        )
        with (
            patch("api.views.validate_public_url", return_value=(url, None)),
            patch("api.views.check_url_threat_reputation", return_value={"status": "SAFE"}),
            patch("api.views.url_fact_check_process.delay") as enqueue,
        ):
            response = self.client.post(
                reverse("verify_url"), {"url": url}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["cached"])
        self.assertNotEqual(response.json()["claim_id"], str(old.pk))
        self.assertEqual(Claim.objects.get(pk=response.json()["claim_id"]).url_link, url)
        self.assertTrue(VerificationRun.objects.filter(pk=previous.pk).exists())
        enqueue.assert_called_once()

    def test_failed_image_cache_requeues_without_mutating_original(self):
        media_hash = "1234abcd1234abcd"
        old, previous = self._old_claim(
            Claim.ClaimType.IMAGE, media_hash, VerificationRun.Status.FAILED
        )
        with (
            patch("api.views.process_image", return_value=(media_hash, None)),
            patch("api.views.upload_image_to_database", return_value="https://example.com/media.png"),
            patch("api.views.snippet_fact_check_process.delay") as enqueue,
        ):
            response = self.client.post(
                reverse("analyze_snippet"),
                {"image_data": "aGVsbG8=", "check_deepfake": False},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["cached"])
        self.assertNotEqual(response.json()["claim_id"], str(old.pk))
        self.assertEqual(
            Claim.objects.get(pk=response.json()["claim_id"]).media_hash,
            media_hash,
        )
        self.assertTrue(VerificationRun.objects.filter(pk=previous.pk).exists())
        enqueue.assert_called_once()
