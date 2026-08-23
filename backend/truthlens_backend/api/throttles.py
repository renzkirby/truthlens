from rest_framework.throttling import SimpleRateThrottle
from rest_framework.throttling import AnonRateThrottle


class PasswordResetRateThrottle(AnonRateThrottle):
    scope = "password_reset"

class FactCheckRateThrottle(SimpleRateThrottle):
    scope = "fact_check"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            # Force rate limiting by IP for unauthenticated users
            ident = f"guest_ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}

class EmailVerificationRateThrottle(
    SimpleRateThrottle
):
    scope = "email_verification"

    def get_cache_key(self, request, view):
        if (
            request.user
            and request.user.is_authenticated
        ):
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