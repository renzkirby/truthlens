"""Manually authorized one-request Cloudflare smoke via the real Celery worker."""
import os

from celery.exceptions import TimeoutError as CeleryTimeoutError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.tasks import cloudflare_single_request_smoke
from api.verification.cloudflare_worker_smoke import FIXED_CASE_ID


class Command(BaseCommand):
    help = (
        "Development-only single-request Cloudflare worker smoke. "
        "Without --live and --confirm-one-request, no work is queued."
    )

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--confirm-one-request", action="store_true")

    def handle(self, *args, **options):
        if not options["live"]:
            self.stdout.write(
                f"DRY RUN: fixed reviewer-approved case={FIXED_CASE_ID}; "
                "Cloudflare only, at most one provider request, no claim DB writes. "
                "Add --live --confirm-one-request to queue exactly one task."
            )
            return

        if not options["confirm_one_request"]:
            raise CommandError("Live mode requires --confirm-one-request.")
        if not (
            getattr(settings, "APP_ENV", None) == "development"
            and getattr(settings, "DEBUG", False) is True
            and os.getenv("ENABLE_CLOUDFLARE_VERIFICATION_PILOT", "") == "1"
        ):
            raise CommandError(
                "Live smoke requires APP_ENV=development, DEBUG=True, and "
                "ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1 in this shell and worker."
            )

        # Exactly one enqueue, no automatic retry or fallback on timeout.
        async_result = cloudflare_single_request_smoke.delay()
        self.stdout.write(f"Queued smoke task_id={async_result.id}; waiting once.")
        try:
            result = async_result.get(timeout=70)
        except CeleryTimeoutError as exc:
            raise CommandError(
                "Worker did not return within 70 seconds. "
                "Do not requeue automatically; inspect the worker task_id first."
            ) from exc
        except Exception as exc:
            raise CommandError(
                "Smoke task did not produce a result. Do not blindly retry."
            ) from exc

        if not isinstance(result, dict):
            raise CommandError("Invalid smoke result. Do not blindly retry.")

        # Defense in depth: emit only explicit safe fields, not a raw result dump.
        keys = (
            "status", "provider", "case_id", "worker_pid",
            "pilot_enabled", "account_id_valid", "api_token_present",
            "requests_attempted", "elapsed_ms", "reason",
            "expected_verdict", "actual_verdict", "matches_approved_label",
            "confidence_score", "contract_valid",
        )
        sanitized = {
            key: result[key] for key in keys
            if key in result and isinstance(result[key], (str, int, float, bool))
            and (not isinstance(result[key], str) or len(result[key]) <= 80)
        }
        # Task only emits enum-like strings, never claim/evidence/error bodies.
        self.stdout.write("CLOUDFLARE_WORKER_SMOKE " +
                          " ".join(f"{key}={value}" for key, value in sanitized.items()))
        if result.get("status") != "success":
            raise CommandError(
                "Cloudflare smoke did not succeed; inspect sanitized status "
                "and reason above before any new attempt."
            )
