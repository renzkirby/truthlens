"""Offline tests of the sanitized, read-only local run inspector."""
import io
import uuid

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from api.models import Claim, VerificationRun, VerificationTelemetryEvent


class VerificationRunTelemetryInspectorTests(TestCase):
    @override_settings(APP_ENV="development", DEBUG=True)
    def test_shows_sanitized_run_and_provider_metrics_without_evidence(self):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="SECRET CLAIM TEXT NEVER PRINT",
        )
        run = VerificationRun.objects.create(
            claim=claim,
            status=VerificationRun.Status.FAILED,
            started_at=timezone.now(),
            completed_at=timezone.now(),
            failure_stage="final_evaluator",
            failure_code="LLM_UNAVAILABLE",
            failure_message="PRIVATE ERROR MESSAGE NEVER PRINT",
        )
        VerificationTelemetryEvent.objects.create(
            verification_run=run,
            sequence=1,
            event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
            name="persisted_evidence_evaluation",
            provider="cloudflare",
            duration_ms=12000,
            outcome="failed",
            error_label="PRIVATE MODEL MESSAGE NEVER PRINT",
            metadata={"private_claim": "SECRET CLAIM TEXT NEVER PRINT"},
            occurred_at=timezone.now(),
        )
        VerificationTelemetryEvent.objects.create(
            verification_run=run,
            sequence=2,
            event_type=VerificationTelemetryEvent.EventType.PIPELINE_STAGE,
            name="core_text_pipeline_total",
            duration_ms=13000,
            outcome="failed",
            metadata={},
            occurred_at=timezone.now(),
        )
        output = io.StringIO()
        with self.assertNumQueries(2):
            call_command(
                "inspect_verification_run_telemetry",
                run_id=str(run.pk),
                stdout=output,
            )
        value = output.getvalue()
        self.assertIn("status=FAILED", value)
        self.assertIn("failure_code=LLM_UNAVAILABLE", value)
        self.assertIn("provider=cloudflare", value)
        self.assertIn("duration_ms=12000", value)
        self.assertIn("STAGE name=core_text_pipeline_total", value)
        for secret in ("SECRET CLAIM", "PRIVATE ERROR", "PRIVATE MODEL"):
            self.assertNotIn(secret, value)

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_rejects_non_development(self):
        with self.assertRaisesRegex(CommandError, "Only local development"):
            call_command(
                "inspect_verification_run_telemetry",
                run_id=str(uuid.uuid4()),
            )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_rejects_missing_and_malformed_id(self):
        with self.assertRaisesRegex(CommandError, "Invalid run UUID"):
            call_command("inspect_verification_run_telemetry", run_id="not-a-uuid")
        with self.assertRaisesRegex(CommandError, "Run not found"):
            call_command(
                "inspect_verification_run_telemetry",
                run_id=str(uuid.uuid4()),
            )
