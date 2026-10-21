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
            error_label="CloudflareEvaluationError code=HTTP_429",
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
        self.assertIn("reason=HTTP_429", value)
        self.assertIn("duration_ms=12000", value)
        self.assertIn("STAGE name=core_text_pipeline_total", value)
        for secret in ("SECRET CLAIM", "PRIVATE ERROR", "PRIVATE MODEL"):
            self.assertNotIn(secret, value)

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_legacy_and_untrusted_failure_labels_are_not_disclosed(self):
        claim = Claim.objects.create(context_text="Private user context")
        run = VerificationRun.objects.create(claim=claim)
        event = VerificationTelemetryEvent.objects.create(
            verification_run=run,
            sequence=1,
            event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
            name="persisted_evidence_evaluation",
            provider="cloudflare",
            duration_ms=0,
            outcome="failed",
            error_label="CloudflareEvaluationError",
            occurred_at=timezone.now(),
        )
        out = io.StringIO()
        call_command("inspect_verification_run_telemetry", run_id=str(run.pk), stdout=out)
        self.assertIn("reason=not_recorded", out.getvalue())
        event.error_label = "CloudflareEvaluationError code=HTTP_403 Bearer PRIVATE_TOKEN"
        event.save(update_fields=["error_label"])
        out = io.StringIO()
        call_command("inspect_verification_run_telemetry", run_id=str(run.pk), stdout=out)
        self.assertIn("reason=HTTP_403", out.getvalue())
        self.assertNotIn("PRIVATE_TOKEN", out.getvalue())

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_opt_in_usage_display_has_no_private_evidence(self):
        claim = Claim.objects.create(
            context_text="SECRET SOURCE BODY DO NOT DISPLAY",
        )
        run = VerificationRun.objects.create(claim=claim)
        VerificationTelemetryEvent.objects.create(
            verification_run=run,
            sequence=1,
            event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
            name="persisted_evidence_evaluation",
            provider="cloudflare",
            duration_ms=17102,
            outcome="success",
            metadata={
                "prompt_tokens": 2410, "completion_tokens": 670,
                "reasoning_tokens": 320, "total_tokens": 3080,
                "finish_reason": "stop",
                "reasoning_present": True,
                "private_evidence": "SECRET SOURCE BODY DO NOT DISPLAY",
                "other_field": "<unsafe>",
            },
            occurred_at=timezone.now(),
        )
        default = io.StringIO()
        call_command(
            "inspect_verification_run_telemetry",
            run_id=str(run.pk), stdout=default,
        )
        self.assertNotIn("completion_tokens=", default.getvalue())

        output = io.StringIO()
        call_command(
            "inspect_verification_run_telemetry",
            run_id=str(run.pk), show_usage=True, stdout=output,
        )
        text = output.getvalue()
        self.assertIn("completion_tokens=670", text)
        self.assertIn("reasoning_tokens=320", text)
        self.assertIn("duration_ms=17102", text)
        self.assertIn("finish_reason=stop", text)
        self.assertNotIn("SECRET SOURCE", text)
        self.assertNotIn("<unsafe>", text)

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_malformed_usage_fields_do_not_leak_via_inspector(self):
        claim = Claim.objects.create(context_text="Private claim.")
        run = VerificationRun.objects.create(claim=claim)
        VerificationTelemetryEvent.objects.create(
            verification_run=run,
            sequence=1,
            event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
            name="evidence_assessment",
            provider="cloudflare",
            duration_ms=1000,
            outcome="success",
            metadata={
                "prompt_tokens": "SECRET", "completion_tokens": True,
                "finish_reason": ["secret"], "reasoning_present": "secret",
            },
            occurred_at=timezone.now(),
        )
        output = io.StringIO()
        call_command(
            "inspect_verification_run_telemetry",
            run_id=str(run.pk), show_usage=True, stdout=output,
        )
        text = output.getvalue()
        self.assertNotIn("SECRET", text)
        self.assertNotIn("reasoning_present=", text)
        self.assertNotIn("finish_reason=", text)

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
