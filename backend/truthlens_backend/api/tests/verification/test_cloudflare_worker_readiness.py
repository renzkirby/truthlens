"""No-network, no-DB checks for sanitized worker readiness logging."""
import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from truthlens_backend.celery import report_cloudflare_pilot_worker_readiness
from api.tasks import inspect_cloudflare_pilot_worker_environment


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


class CloudflareWorkerRuntimeProbeTests(SimpleTestCase):
    @override_settings(APP_ENV="development", DEBUG=True)
    def test_worker_executed_probe_never_exposes_credentials(self):
        secret = "PRIVATE_TOKEN_MUST_NOT_LEAK"
        account_id = "a" * 32
        with (
            patch.dict(os.environ, {
                "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
                "CLOUDFLARE_ACCOUNT_ID": account_id,
                "CLOUDFLARE_API_TOKEN": secret,
            }),
            patch("api.verification.cloudflare_evaluation.requests.post") as http,
        ):
            value = inspect_cloudflare_pilot_worker_environment.run()
        self.assertTrue(value["diagnostics_available"])
        self.assertTrue(value["pilot_enabled"])
        self.assertTrue(value["account_id_valid"])
        self.assertTrue(value["api_token_present"])
        self.assertIsInstance(value["worker_pid"], int)
        http.assert_not_called()
        self.assertNotIn(account_id, str(value))
        self.assertNotIn(secret, str(value))
        self.assertEqual(
            set(value),
            {
                "diagnostics_available", "worker_pid", "pilot_enabled",
                "ai_rq2_hierarchy_enabled",
                "evidence_assessment_pilot_enabled",
                "classification_pilot_enabled",
                "investigation_classification_mode",
                "account_id_valid", "api_token_present",
            },
        )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_worker_reports_ai_rq2_hierarchy_without_provider_call(self):
        with patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
        }):
            result = inspect_cloudflare_pilot_worker_environment.run()
        self.assertTrue(result["ai_rq2_hierarchy_enabled"])
        with patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0",
        }):
            result = inspect_cloudflare_pilot_worker_environment.run()
        self.assertFalse(result["ai_rq2_hierarchy_enabled"])

    @override_settings(
        APP_ENV="development", DEBUG=True,
        INVESTIGATION_CLASSIFICATION_MODE="shadow",
    )
    def test_worker_probe_reports_classification_routing_and_mode(self):
        with patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "1",
        }):
            value = inspect_cloudflare_pilot_worker_environment.run()
        self.assertTrue(value["classification_pilot_enabled"])
        self.assertEqual(value["investigation_classification_mode"], "shadow")
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "0",
        }):
            self.assertFalse(
                inspect_cloudflare_pilot_worker_environment.run()[
                    "classification_pilot_enabled"
                ],
            )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_worker_probe_reports_independent_assessment_flag(self):
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "1",
        }):
            result = inspect_cloudflare_pilot_worker_environment.run()
        self.assertTrue(result["pilot_enabled"])
        self.assertTrue(result["evidence_assessment_pilot_enabled"])
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "0",
        }):
            result = inspect_cloudflare_pilot_worker_environment.run()
        self.assertTrue(result["pilot_enabled"])
        self.assertFalse(result["evidence_assessment_pilot_enabled"])

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_worker_probe_reports_missing_account_without_provider_call(self):
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "CLOUDFLARE_ACCOUNT_ID": "",
            "CLOUDFLARE_API_TOKEN": "a-nonempty-token",
        }):
            value = inspect_cloudflare_pilot_worker_environment.run()
        self.assertTrue(value["pilot_enabled"])
        self.assertFalse(value["account_id_valid"])
        self.assertTrue(value["api_token_present"])

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_worker_probe_denied_outside_development(self):
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "present",
        }):
            self.assertEqual(
                inspect_cloudflare_pilot_worker_environment.run(),
                {"diagnostics_available": False},
            )
