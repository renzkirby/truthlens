from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.claim_matching import get_match_result
from api.models import Claim, VerificationRun
from api.throttles import ClaimPollingRateThrottle
from api.views import claim_polling_endpoint


class ClaimPollingThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.original_throttle_rates = ClaimPollingRateThrottle.THROTTLE_RATES
        ClaimPollingRateThrottle.THROTTLE_RATES = {
            "claim_polling": "10/minute",
        }
        self.timer_patch = patch.object(
            ClaimPollingRateThrottle,
            "timer",
            return_value=1000,
        )
        self.timer_patch.start()
        self.claim = Claim.objects.create(ai_verdict=None)
        self.polling_url = reverse(
            "claim_status",
            kwargs={"claim_id": self.claim.id},
        )

    def tearDown(self):
        self.timer_patch.stop()
        ClaimPollingRateThrottle.THROTTLE_RATES = self.original_throttle_rates
        cache.clear()
        super().tearDown()

    def test_endpoint_uses_exactly_claim_polling_throttle(self):
        self.assertEqual(
            claim_polling_endpoint.cls.throttle_classes,
            [ClaimPollingRateThrottle],
        )

    def test_claim_polling_throttle_scope(self):
        self.assertEqual(ClaimPollingRateThrottle.scope, "claim_polling")

    def test_polling_rate_is_configured_independently_from_anonymous_rate(self):
        throttle_rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertEqual(throttle_rates["anon"], "5/minute")
        self.assertIn("claim_polling", throttle_rates)
        self.assertNotEqual(ClaimPollingRateThrottle.scope, "anon")

        # Supplying only the dedicated rate proves no global rate is needed.
        ClaimPollingRateThrottle.THROTTLE_RATES = {
            "claim_polling": throttle_rates["claim_polling"],
        }
        self.assertEqual(
            ClaimPollingRateThrottle().rate,
            throttle_rates["claim_polling"],
        )

    def test_anonymous_polling_is_allowed_beyond_five_requests(self):
        client = APIClient()
        for _ in range(6):
            response = client.get(self.polling_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_dedicated_polling_quota_eventually_returns_429(self):
        ClaimPollingRateThrottle.THROTTLE_RATES = {
            "claim_polling": "2/minute",
        }
        client = APIClient()
        for _ in range(2):
            self.assertEqual(
                client.get(self.polling_url).status_code,
                status.HTTP_200_OK,
            )
        self.assertEqual(
            client.get(self.polling_url).status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def test_authenticated_polling_quota_is_isolated_by_user_identity(self):
        ClaimPollingRateThrottle.THROTTLE_RATES = {
            "claim_polling": "1/minute",
        }
        first_user = User.objects.create_user(username="first-claim-poller")
        second_user = User.objects.create_user(username="second-claim-poller")
        first_client = APIClient()
        first_client.force_authenticate(first_user)
        second_client = APIClient()
        second_client.force_authenticate(second_user)

        self.assertEqual(
            first_client.get(self.polling_url).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            first_client.get(self.polling_url).status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        self.assertEqual(
            second_client.get(self.polling_url).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_client.get(self.polling_url).status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def test_pending_response_is_unchanged(self):
        with patch(
            "api.views.get_published_fact_check_resolution_for_claim",
            return_value=None,
        ) as published_resolution, patch("api.views.get_match_result") as match_result:
            response = APIClient().get(self.polling_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"verdict": "PENDING"})
        published_resolution.assert_called_once_with(self.claim)
        match_result.assert_not_called()

    def test_pending_and_running_runs_keep_exact_pending_contract(self):
        for run_status in (
            VerificationRun.Status.PENDING,
            VerificationRun.Status.RUNNING,
        ):
            with self.subTest(run_status=run_status):
                self.claim.verification_runs.all().delete()
                VerificationRun.objects.create(
                    claim=self.claim,
                    status=run_status,
                )
                response = APIClient().get(self.polling_url)
                self.assertEqual(response.json(), {"verdict": "PENDING"})

    def test_failed_run_returns_safe_terminal_contract(self):
        VerificationRun.objects.create(
            claim=self.claim,
            status=VerificationRun.Status.FAILED,
            failure_code="LLM_UNAVAILABLE",
            failure_message="SECRET provider rate limit and stack trace",
        )

        response = APIClient().get(self.polling_url)
        payload = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(payload["verdict"], "PENDING")
        self.assertEqual(payload["run_status"], "FAILED")
        self.assertEqual(payload["failure_code"], "LLM_UNAVAILABLE")
        self.assertEqual(
            payload["detail"],
            "TruthLens couldn't complete this analysis. Please try again.",
        )
        self.assertNotIn("failure_message", payload)
        self.assertNotIn("SECRET", str(payload))

    def test_cancelled_run_returns_safe_terminal_contract(self):
        VerificationRun.objects.create(
            claim=self.claim,
            status=VerificationRun.Status.CANCELLED,
        )

        response = APIClient().get(self.polling_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["verdict"], "PENDING")
        self.assertEqual(response.json()["run_status"], "CANCELLED")
        self.assertEqual(response.json()["detail"], "This analysis was cancelled.")

    def test_out_of_scope_abstention_is_terminal_without_ai_verdict(self):
        VerificationRun.objects.create(
            claim=self.claim,
            status=VerificationRun.Status.ABSTAINED,
            abstention_reason=VerificationRun.AbstentionReason.OUT_OF_SCOPE,
        )

        response = APIClient().get(self.polling_url)
        payload = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(payload["id"], str(self.claim.pk))
        self.assertEqual(payload["verdict"], "OUT_OF_SCOPE")
        self.assertIsNone(payload["ai_verdict"])
        self.assertIsNone(payload["final_verdict"])
        self.assertEqual(payload["run_status"], "ABSTAINED")
        self.assertEqual(payload["abstention_reason"], "OUT_OF_SCOPE")
        self.assertIn("sufficiently verifiable public factual claim", payload["summary"])

    def test_generic_abstention_does_not_fabricate_unverified(self):
        VerificationRun.objects.create(
            claim=self.claim,
            status=VerificationRun.Status.ABSTAINED,
        )

        response = APIClient().get(self.polling_url)
        payload = response.json()

        self.assertEqual(payload["verdict"], "PENDING")
        self.assertEqual(payload["run_status"], "ABSTAINED")
        self.assertIsNone(payload["abstention_reason"])
        self.assertNotEqual(payload.get("ai_verdict"), "UNVERIFIED")

    def test_completed_run_without_verdict_returns_safe_terminal_contract(self):
        VerificationRun.objects.create(
            claim=self.claim,
            status=VerificationRun.Status.COMPLETED,
        )

        with patch(
            "api.views.get_published_fact_check_resolution_for_claim",
            return_value=None,
        ) as published_resolution, patch("api.views.get_match_result") as match_result:
            response = APIClient().get(self.polling_url)

        payload = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(payload["run_status"], "COMPLETED")
        self.assertEqual(payload["verdict"], "PENDING")
        self.assertIsNone(payload["ai_verdict"])
        self.assertIsNone(payload["final_verdict"])
        self.assertEqual(
            payload["detail"],
            "Analysis finished, but no automated verdict is available.",
        )
        self.assertNotIn("UNVERIFIED", str(payload))
        published_resolution.assert_called_once_with(self.claim)
        match_result.assert_not_called()

    def test_existing_ai_result_skips_pending_probe_and_uses_full_result(self):
        self.claim.ai_verdict = "MISLEADING"
        self.claim.ai_summary = "Existing AI result."
        self.claim.save(update_fields=["ai_verdict", "ai_summary"])
        VerificationRun.objects.create(
            claim=self.claim,
            status=VerificationRun.Status.FAILED,
            failure_message="Must not override the AI result.",
        )

        with patch(
            "api.views.get_published_fact_check_resolution_for_claim",
        ) as published_resolution, patch(
            "api.views.get_match_result",
            wraps=get_match_result,
        ) as match_result:
            response = APIClient().get(self.polling_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["resolution_source"], "AI")
        published_resolution.assert_not_called()
        match_result.assert_called_once_with(self.claim)

    def test_authoritative_resolution_precedes_terminal_run_probe(self):
        VerificationRun.objects.create(
            claim=self.claim,
            status=VerificationRun.Status.FAILED,
            failure_message="Must not override publication authority.",
        )
        match_payload = {
            "verdict": "FACT",
            "ai_verdict": None,
            "final_verdict": "FACT",
            "summary": "Published resolution.",
            "confidence_score": None,
            "source_type": "Official Fact Check",
            "source_url": None,
            "sources": [],
            "is_ai_generated": False,
            "thread_id": None,
            "resolution_source": "OFFICIAL_FACT_CHECK",
            "score_context": None,
            "official_fact_check": {"fact_check_id": "published-id"},
            "related_fact_checks": [],
        }

        with patch(
            "api.views.get_published_fact_check_resolution_for_claim",
            return_value=object(),
        ) as published_resolution, patch(
            "api.views.get_match_result",
            return_value=match_payload,
        ) as match_result:
            response = APIClient().get(self.polling_url)

        self.assertEqual(response.json()["verdict"], "FACT")
        self.assertEqual(response.json()["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertNotIn("run_status", response.json())
        published_resolution.assert_called_once_with(self.claim)
        match_result.assert_called_once_with(self.claim)

    def test_missing_claim_response_is_unchanged(self):
        response = APIClient().get(
            reverse("claim_status", kwargs={"claim_id": uuid4()})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json(), {"detail": "Claim not found."})
