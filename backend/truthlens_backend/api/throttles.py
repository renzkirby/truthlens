import logging

from rest_framework.throttling import (
    AnonRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)


logger = logging.getLogger(__name__)


class FailSoftThrottleMixin:
    """Keep cache outages from becoming API outages.

    DRF throttling is an abuse-control layer, not an authorization boundary.
    When the shared cache is unavailable, allow the request and record the
    infrastructure failure rather than failing an otherwise valid request.
    """

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.exception(
                "Throttle cache unavailable for %s.",
                self.__class__.__name__,
            )
            return True


class TruthLensAnonRateThrottle(FailSoftThrottleMixin, AnonRateThrottle):
    pass


class TruthLensUserRateThrottle(FailSoftThrottleMixin, UserRateThrottle):
    pass


class TruthLensSimpleRateThrottle(FailSoftThrottleMixin, SimpleRateThrottle):
    pass


class PasswordResetRateThrottle(TruthLensSimpleRateThrottle):
    scope = "password_reset"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            ident = f"guest_ip:{self.get_ident(request)}"

        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class FactCheckRateThrottle(TruthLensSimpleRateThrottle):
    scope = "fact_check"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            # Force rate limiting by IP for unauthenticated users
            ident = f"guest_ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class ClaimPollingRateThrottle(FactCheckRateThrottle):
    scope = "claim_polling"


class PublicPartnerRateThrottle(TruthLensSimpleRateThrottle):
    scope = "public_partner"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            ident = f"guest_ip:{self.get_ident(request)}"

        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class PublicReachRateThrottle(TruthLensSimpleRateThrottle):
    scope = "public_reach"

    def get_cache_key(self, request, view):
        # Temporary cache identity is never persisted in PublicReachEvent.
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class EmailVerificationRateThrottle(TruthLensSimpleRateThrottle):
    scope = "email_verification"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            ident = (
                f"guest_ip:"
                f"{self.get_ident(request)}"
            )

        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }
