from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings

from api.email_verification import (
    build_email_verification_url,
    send_email_verification,
)
from api.models import UserProfile


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="TruthLens <no-reply@truthlens.social>",
    FRONTEND_URL="https://truthlens.example",
    EMAIL_VERIFICATION_TOKEN_LIFETIME_HOURS=24,
)
class EmailVerificationMessageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="verify-user",
            email="verify-user@example.com",
            password="test-password",
        )
        UserProfile.objects.get_or_create(user=self.user)

    def test_verification_email_has_branded_html_and_text_fallback(self):
        delivered_count = send_email_verification(self.user)

        self.assertEqual(delivered_count, 1)
        self.assertEqual(len(mail.outbox), 1)

        self.user.profile.refresh_from_db()
        token = self.user.profile.email_verification_token
        self.assertTrue(token)

        verification_url = build_email_verification_url(token)
        message = mail.outbox[0]

        self.assertEqual(message.subject, "Verify your TruthLens email")
        self.assertEqual(
            message.from_email,
            "TruthLens <no-reply@truthlens.social>",
        )
        self.assertEqual(message.to, [self.user.email])

        self.assertIn("Verify your email address", message.body)
        self.assertIn(
            "secure your TruthLens account",
            message.body,
        )
        self.assertIn(verification_url, message.body)
        self.assertIn(
            "This verification link expires in 24 hours.",
            message.body,
        )

        self.assertEqual(len(message.alternatives), 1)
        html_body, mime_type = message.alternatives[0]
        self.assertEqual(mime_type, "text/html")
        self.assertIn("Verify email address", html_body)
        self.assertIn("TruthLens account security", html_body)
        self.assertIn(verification_url, html_body)
        self.assertIn("expires in 24 hours", html_body)
