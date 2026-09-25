from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from api.auth_tokens import (
    GoogleRememberedTokenObtainPairSerializer,
    REMEMBER_ME_CLAIM,
    SessionRefreshToken,
    issue_refresh_token,
)

PASSWORD_LOGIN_URL = "/api/auth/login/"
TOKEN_OBTAIN_URL = "/api/token/"
CANONICAL_REFRESH_URL = "/api/token/refresh/"
AUTH_REFRESH_URL = "/api/auth/refresh/"


class SessionTokenTests(APITestCase):
    def setUp(self):
        cache.clear()

        self.password = "test-pass-123"
        self.user = User.objects.create_user(
            username="session-user",
            email="session-user@example.com",
            password=self.password,
        )

    def tearDown(self):
        cache.clear()

    def assert_token_lifetime(self, token, expected_lifetime, tolerance_seconds=5):
        actual_seconds = token["exp"] - token["iat"]
        self.assertAlmostEqual(
            actual_seconds,
            expected_lifetime.total_seconds(),
            delta=tolerance_seconds,
        )

    def assert_access_policy(self, access):
        self.assert_token_lifetime(access, timedelta(minutes=15))
        self.assertNotIn(REMEMBER_ME_CLAIM, access.payload)

    def login(self, remember_me):
        return self.client.post(
            PASSWORD_LOGIN_URL,
            {
                "username": self.user.username,
                "password": self.password,
                "remember_me": remember_me,
            },
            format="json",
        )

    def test_password_login_without_remember_me_uses_normal_policy(self):
        response = self.login(False)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh = SessionRefreshToken(response.data["refresh"])
        access = AccessToken(response.data["access"])
        self.assertIs(refresh[REMEMBER_ME_CLAIM], False)
        self.assert_token_lifetime(refresh, timedelta(days=7))
        self.assert_token_lifetime(access, timedelta(minutes=15))
        self.assertNotIn(REMEMBER_ME_CLAIM, access.payload)

    def test_password_login_with_remember_me_uses_remembered_policy(self):
        response = self.login(True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh = SessionRefreshToken(response.data["refresh"])
        access = AccessToken(response.data["access"])
        self.assertIs(refresh[REMEMBER_ME_CLAIM], True)
        self.assert_token_lifetime(refresh, timedelta(days=30))
        self.assert_token_lifetime(access, timedelta(minutes=15))
        self.assertNotIn(REMEMBER_ME_CLAIM, access.payload)

    def test_password_login_treats_truthy_string_as_not_remembered(self):
        response = self.login("false")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh = SessionRefreshToken(response.data["refresh"])
        self.assertIs(refresh[REMEMBER_ME_CLAIM], False)
        self.assert_token_lifetime(refresh, timedelta(days=7))

    def test_standard_token_obtain_uses_normal_policy(self):
        response = self.client.post(
            TOKEN_OBTAIN_URL,
            {
                "username": self.user.username,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh = SessionRefreshToken(response.data["refresh"])
        self.assertIs(refresh[REMEMBER_ME_CLAIM], False)
        self.assert_token_lifetime(refresh, timedelta(days=7))

    def test_normal_session_rotation_preserves_normal_policy(self):
        refresh = issue_refresh_token(self.user, remember_me=False)

        response = self.client.post(
            CANONICAL_REFRESH_URL,
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rotated = SessionRefreshToken(response.data["refresh"])
        access = AccessToken(response.data["access"])
        self.assertIs(rotated[REMEMBER_ME_CLAIM], False)
        self.assert_token_lifetime(rotated, timedelta(days=7))
        self.assert_access_policy(access)

    def test_remembered_session_rotation_preserves_remembered_policy(self):
        refresh = issue_refresh_token(self.user, remember_me=True)

        response = self.client.post(
            CANONICAL_REFRESH_URL,
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rotated = SessionRefreshToken(response.data["refresh"])
        access = AccessToken(response.data["access"])
        self.assertIs(rotated[REMEMBER_ME_CLAIM], True)
        self.assert_token_lifetime(rotated, timedelta(days=30))
        self.assert_access_policy(access)

    def test_auth_refresh_route_uses_the_same_remembered_policy(self):
        refresh = issue_refresh_token(self.user, remember_me=True)

        response = self.client.post(
            AUTH_REFRESH_URL,
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rotated = SessionRefreshToken(response.data["refresh"])
        access = AccessToken(response.data["access"])
        self.assertIs(rotated[REMEMBER_ME_CLAIM], True)
        self.assert_token_lifetime(rotated, timedelta(days=30))
        self.assert_access_policy(access)

    def test_malformed_invalid_and_expired_refresh_tokens_are_rejected(self):
        expired = issue_refresh_token(self.user)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        invalid_type = AccessToken.for_user(self.user)

        rejected_tokens = (
            "not-a-jwt",
            str(invalid_type),
            str(expired),
        )

        for refresh in rejected_tokens:
            with self.subTest(refresh=refresh[:12]):
                response = self.client.post(
                    CANONICAL_REFRESH_URL,
                    {"refresh": refresh},
                    format="json",
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )

    def test_google_claims_serializer_uses_remembered_policy(self):
        refresh = GoogleRememberedTokenObtainPairSerializer.get_token(self.user)

        self.assertIs(refresh[REMEMBER_ME_CLAIM], True)
        self.assert_token_lifetime(refresh, timedelta(days=30))
        self.assert_access_policy(refresh.access_token)
