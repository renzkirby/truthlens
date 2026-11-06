from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APIRequestFactory

from api.throttles import (
    FactCheckRateThrottle,
    TruthLensAnonRateThrottle,
    TruthLensUserRateThrottle,
)


class _UnavailableCache:
    def get(self, key, default=None):
        raise RedisConnectionError("cache unavailable")


class ThrottleCacheFailureTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _request(self, *, authenticated):
        request = self.factory.get("/api/cache-outage-test/")
        request.user = (
            SimpleNamespace(is_authenticated=True, pk=42)
            if authenticated
            else AnonymousUser()
        )
        return request

    def test_default_anonymous_throttle_fails_open_when_cache_is_unavailable(self):
        throttle = TruthLensAnonRateThrottle()
        throttle.cache = _UnavailableCache()

        self.assertTrue(
            throttle.allow_request(
                self._request(authenticated=False),
                None,
            )
        )

    def test_default_user_throttle_fails_open_when_cache_is_unavailable(self):
        throttle = TruthLensUserRateThrottle()
        throttle.cache = _UnavailableCache()

        self.assertTrue(
            throttle.allow_request(
                self._request(authenticated=True),
                None,
            )
        )

    def test_custom_fact_check_throttle_fails_open_when_cache_is_unavailable(self):
        throttle = FactCheckRateThrottle()
        throttle.cache = _UnavailableCache()

        self.assertTrue(
            throttle.allow_request(
                self._request(authenticated=False),
                None,
            )
        )
