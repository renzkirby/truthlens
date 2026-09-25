from datetime import timedelta

from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


REMEMBER_ME_CLAIM = "remember_me"
REMEMBERED_REFRESH_TOKEN_LIFETIME = timedelta(days=30)


class SessionRefreshToken(RefreshToken):
    """Refresh token whose rotation preserves the session lifetime policy."""

    no_copy_claims = (*RefreshToken.no_copy_claims, REMEMBER_ME_CLAIM)

    def set_exp(self, claim="exp", from_time=None, lifetime=None):
        if lifetime is None and self.payload.get(REMEMBER_ME_CLAIM) is True:
            lifetime = REMEMBERED_REFRESH_TOKEN_LIFETIME

        return super().set_exp(
            claim=claim,
            from_time=from_time,
            lifetime=lifetime,
        )


def issue_refresh_token(user, remember_me=False):
    """Issue a finite refresh token with an explicit session-policy claim."""

    refresh = SessionRefreshToken.for_user(user)
    refresh[REMEMBER_ME_CLAIM] = remember_me is True
    refresh.set_exp()
    return refresh


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    token_class = SessionRefreshToken


class SessionTokenRefreshView(TokenRefreshView):
    serializer_class = SessionTokenRefreshSerializer


class SessionTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        return issue_refresh_token(user)


class SessionTokenObtainPairView(TokenObtainPairView):
    serializer_class = SessionTokenObtainPairSerializer


class GoogleRememberedTokenObtainPairSerializer(SessionTokenObtainPairSerializer):
    """Issue Google social-login JWTs under the persistent session policy."""

    @classmethod
    def get_token(cls, user):
        return issue_refresh_token(user, remember_me=True)
