from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.throttles import PasswordResetRateThrottle


PASSWORD_RESET_URL = "/api/auth/password-reset/"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@truthlens.test",
)
class PasswordResetThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.original_rates = PasswordResetRateThrottle.THROTTLE_RATES
        PasswordResetRateThrottle.THROTTLE_RATES = {
            **(self.original_rates or {}),
            "password_reset": "3/hour",
        }
        self.user = User.objects.create_user(
            username="reset-user",
            email="reset-user@example.com",
            password="pass1234",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        PasswordResetRateThrottle.THROTTLE_RATES = self.original_rates
        cache.clear()

    def test_authenticated_password_reset_requests_are_throttled_by_user(self):
        payload = {"email": "missing-account@example.com"}

        first = self.client.post(PASSWORD_RESET_URL, payload, format="json")
        second = self.client.post(PASSWORD_RESET_URL, payload, format="json")
        third = self.client.post(PASSWORD_RESET_URL, payload, format="json")
        fourth = self.client.post(PASSWORD_RESET_URL, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(third.status_code, status.HTTP_200_OK)
        self.assertEqual(fourth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_passwordless_account_receives_password_setup_copy(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])

        response = self.client.post(
            PASSWORD_RESET_URL,
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Set your TruthLens password")
        self.assertIn(
            "add a password to your TruthLens account",
            message.body,
        )
        self.assertIn("Set your password", message.alternatives[0][0])
