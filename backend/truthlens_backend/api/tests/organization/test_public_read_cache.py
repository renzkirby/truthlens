from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from api.public_read_cache import (
    get_public_partner_directory_payload,
    invalidate_public_partner_directory_cache,
    set_public_partner_directory_payload,
)


@override_settings(PUBLIC_PARTNER_DIRECTORY_CACHE_SECONDS=60)
class PublicReadCacheFailureTests(SimpleTestCase):
    def test_cache_read_failure_is_treated_as_a_miss(self):
        with (
            patch(
                "api.public_read_cache.cache.get",
                side_effect=RuntimeError("cache unavailable"),
            ),
            patch(
                "api.public_read_cache.cache.add",
                side_effect=RuntimeError("cache unavailable"),
            ),
        ):
            payload = get_public_partner_directory_payload(
                search="",
                organization_type="",
            )

        self.assertIsNone(payload)

    def test_cache_write_failure_does_not_escape_to_request_path(self):
        with patch(
            "api.public_read_cache.cache.set",
            side_effect=RuntimeError("cache unavailable"),
        ):
            written = set_public_partner_directory_payload(
                {"count": 0, "results": []},
                search="",
                organization_type="",
            )

        self.assertFalse(written)

    def test_cache_invalidation_failure_is_fail_soft(self):
        with patch(
            "api.public_read_cache.cache.set",
            side_effect=RuntimeError("cache unavailable"),
        ):
            invalidated = invalidate_public_partner_directory_cache()

        self.assertFalse(invalidated)
