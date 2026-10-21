"""Read-only local verification timing and provider audit. Never prints claim data."""
import re
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.models import VerificationRun, VerificationTelemetryEvent
from api.verification.cloudflare_evaluation import (
    CloudflareEvaluationError,
    sanitized_cloudflare_error_code,
)

SAFE_LABEL = re.compile(r"^[a-zA-Z0-9_]{1,80}$")


def _safe(value):
    if isinstance(value, str) and SAFE_LABEL.fullmatch(value):
        return value
    return "other"


class Command(BaseCommand):
    help = "Read sanitized stage and provider timings for one dev verification run."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", required=True)
        parser.add_argument(
            "--show-usage", action="store_true",
            help="Show sanitized Cloudflare completion metadata when present.",
        )

    def handle(self, *args, **options):
        if not (
            getattr(settings, "APP_ENV", None) == "development"
            and getattr(settings, "DEBUG", False) is True
        ):
            raise CommandError("Only local development can inspect run telemetry.")
        try:
            run_id = uuid.UUID(options["run_id"])
        except (ValueError, TypeError, AttributeError) as exc:
            raise CommandError("Invalid run UUID.") from exc
        run = VerificationRun.objects.filter(pk=run_id).first()
        if run is None:
            raise CommandError("Run not found.")

        total_ms = "n/a"
        if run.started_at is not None and run.completed_at is not None:
            total_ms = max(
                0, int((run.completed_at - run.started_at).total_seconds() * 1000)
            )
        events = list(
            VerificationTelemetryEvent.objects.filter(verification_run_id=run.pk)
            .order_by("sequence")
        )
        self.stdout.write(
            f"RUN id={run.pk} status={_safe(run.status)} "
            f"duration_ms={total_ms} failure_stage={_safe(run.failure_stage)} "
            f"failure_code={_safe(run.failure_code)} events={len(events)}"
        )
        for event in events:
            if event.event_type == VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL:
                reason = ""
                if (
                    event.provider == "cloudflare"
                    and event.outcome in {"failed", "skipped"}
                ):
                    prefix = "CloudflareEvaluationError code="
                    if isinstance(event.error_label, str) and event.error_label.startswith(prefix):
                        candidate = event.error_label[len(prefix):]
                        safe_code = sanitized_cloudflare_error_code(
                            CloudflareEvaluationError(candidate)
                        )
                        reason = f" reason={safe_code}"
                    else:
                        # Historical events have only an exception type.
                        reason = " reason=not_recorded"
                usage = ""
                if options["show_usage"] and event.provider == "cloudflare":
                    metadata = event.metadata if isinstance(event.metadata, dict) else {}
                    for key in (
                        "prompt_tokens", "completion_tokens",
                        "reasoning_tokens", "total_tokens",
                    ):
                        count = metadata.get(key)
                        if type(count) is int and 0 <= count <= 10000000:
                            usage += f" {key}={count}"
                    finish = metadata.get("finish_reason")
                    if isinstance(finish, str) and finish in {
                        "stop", "length", "tool_calls", "content_filter",
                    }:
                        usage += f" finish_reason={finish}"
                    reasoning = metadata.get("reasoning_present")
                    if isinstance(reasoning, bool):
                        usage += f" reasoning_present={str(reasoning).lower()}"
                self.stdout.write(
                    f"PROVIDER name={_safe(event.name)} "
                    f"provider={_safe(event.provider)} "
                    f"outcome={_safe(event.outcome)} "
                    f"duration_ms={event.duration_ms}{reason}{usage}"
                )
            elif event.event_type == VerificationTelemetryEvent.EventType.PIPELINE_STAGE:
                self.stdout.write(
                    f"STAGE name={_safe(event.name)} "
                    f"outcome={_safe(event.outcome)} "
                    f"duration_ms={event.duration_ms}"
                )
        self.stdout.write(
            "Stage durations can overlap or contain nested calls; do not sum "
            "them as end-to-end elapsed time. No claim text, evidence or "
            "provider credentials are included."
        )
