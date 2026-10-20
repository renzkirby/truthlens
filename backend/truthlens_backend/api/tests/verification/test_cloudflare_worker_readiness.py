"""No-network, no-DB checks for sanitized worker readiness logging."""
import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from truthlens_backend.celery import report_cloudflare_pilot_worker_readiness


class CloudflarePilotWorkerReadinessTests(SimpleTestCase):
    @override_settings(APP_ENV="development", DEBUG=True)
    def test_ready_status_from_worker_environment_does_not_print_credentials(self):
        secret = "test-secret-not-to-be-logged"
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": secret,
        }):
            with self.assertLogs("truthlens_backend.celery", level="INFO") as messages:
                report_cloudflare_pilot_worker_readiness()
        value = "\n".join(messages.output)
        self.assertIn("enabled=True", value)
        self.assertIn("account_id_valid=True", value)
        self.assertIn("api_token_present=True", value)
        self.assertNotIn(secret, value)
        self.assertNotIn("a" * 32, value)

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_missing_pilot_credentials_show_only_boolean_status(self):
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "CLOUDFLARE_ACCOUNT_ID": "",
            "CLOUDFLARE_API_TOKEN": "",
        }):
            with self.assertLogs("truthlens_backend.celery", level="INFO") as messages:
                report_cloudflare_pilot_worker_readiness()
        value = "\n".join(messages.output)
        self.assertIn("enabled=True", value)
        self.assertIn("account_id_valid=False", value)
        self.assertIn("api_token_present=False", value)

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_production_does_not_emit_worker_credential_status(self):
        with patch("truthlens_backend.celery.logger.info") as logger:
            report_cloudflare_pilot_worker_readiness()
        logger.assert_not_called()
