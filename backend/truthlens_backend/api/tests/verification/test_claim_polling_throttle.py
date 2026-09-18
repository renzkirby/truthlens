from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import Claim
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
        response = APIClient().get(self.polling_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"verdict": "PENDING"})
