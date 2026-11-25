"""Offline validation for verification tail-latency guardrails."""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api import tasks
from api.services import (
    GROQ_RELIABILITY_HTTP_TIMEOUT_SECONDS,
    LLMProviderUnavailableError,
    call_llm_with_fallback,
    llm_provider_scope,
)


def _groq_timeout_check():
    gemini = Mock()
    gemini.models.generate_content.side_effect = RuntimeError(
        "synthetic Gemini failure"
    )

    groq = Mock()
    groq_lane = groq.with_options.return_value
    groq_lane.chat.completions.create.side_effect = TimeoutError(
        "synthetic Groq timeout"
    )

    cloudflare = Mock(side_effect=RuntimeError("synthetic Cloudflare failure"))

    terminal_exception = None
    with (
        patch.dict(
            os.environ,
            {
                "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
                "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
                "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
                "ENABLE_GEMINI_TRANSIENT_MODEL_FALLBACK": "0",
                "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            },
            clear=False,
        ),
        patch("api.services.gemini_client", gemini),
        patch("api.services.groq_client", groq),
        patch("api.services.call_validated_cloudflare_pilot", cloudflare),
        patch("api.services.record_llm_provider_call") as telemetry,
        llm_provider_scope(),
    ):
        try:
            call_llm_with_fallback(
                "Strict persisted-evidence evaluation instructions.",
                "Synthetic persisted-evidence prompt.",
                operation="persisted_evidence_evaluation",
            )
        except LLMProviderUnavailableError as exc:
            terminal_exception = type(exc).__name__

    provider_route = [call.args[1] for call in telemetry.call_args_list]
    groq_options = groq.with_options.call_args.kwargs
    groq_attempts = groq_lane.chat.completions.create.call_count

    passed = (
        terminal_exception == "LLMProviderUnavailableError"
        and provider_route == ["gemini", "cloudflare", "groq"]
        and groq_options == {
            "max_retries": 0,
            "timeout": GROQ_RELIABILITY_HTTP_TIMEOUT_SECONDS,
        }
        and groq_attempts == 1
    )
    return {
        "id": "groq_timeout_guardrail",
        "passed": passed,
        "provider_route": provider_route,
        "configured_timeout_seconds": groq_options.get("timeout"),
        "sdk_retries": groq_options.get("max_retries"),
        "groq_attempts": groq_attempts,
        "terminal_exception": terminal_exception,
    }


def _recovery_check(*, elapsed_seconds):
    initial_result = {
        "verdict": "UNVERIFIED",
        "summary": "Evidence remains insufficient.",
        "confidence_score": 35,
    }
    provider = Mock()
    provider.search_with_payload.return_value = ({}, [])

    pipeline_started_at = 100.0
    now = pipeline_started_at + elapsed_seconds
    # The late-skip path consumes two clock reads: elapsed calculation and the
    # synthetic stage-start timestamp. The early path consumes two as well:
    # elapsed calculation and recovery start.
    clock = [now, now + 0.01]

    with (
        patch("api.tasks.time.perf_counter", side_effect=clock),
        patch(
            "api.tasks.load_reasoning_evidence_dossier_for_run",
            return_value=[],
        ) as load_dossier,
        patch("api.tasks.TavilyProvider", return_value=provider) as provider_class,
        patch("api.tasks._log_stage") as log_stage,
    ):
        result = tasks._attempt_primary_source_recovery(
            initial_result=initial_result,
            cleaned_claim="A verifiable public claim.",
            claim_id="tail-latency-validation",
            run=SimpleNamespace(pk="synthetic-run"),
            article_stance="NEUTRAL",
            official_rating_policy={"resolution": "NONE"},
            gfc_evidence_assessed=False,
            is_text_claim=True,
            pipeline_started_at=pipeline_started_at,
        )

    recovery_requested = provider.search_with_payload.called
    preserved = result is initial_result

    if elapsed_seconds >= tasks.OPTIONAL_PRIMARY_SOURCE_RECOVERY_CUTOFF_SECONDS:
        expected_recovery = False
        stage_outcome = (
            log_stage.call_args.kwargs.get("outcome")
            if log_stage.call_args is not None
            else None
        )
        passed = (
            preserved
            and not recovery_requested
            and not load_dossier.called
            and not provider_class.called
            and stage_outcome == "skipped_tail_latency_budget"
        )
    else:
        expected_recovery = True
        stage_outcome = None
        passed = (
            preserved
            and recovery_requested
            and load_dossier.called
            and provider_class.called
        )

    return {
        "id": (
            "recovery_before_cutoff"
            if expected_recovery
            else "recovery_after_cutoff"
        ),
        "passed": passed,
        "elapsed_seconds": elapsed_seconds,
        "cutoff_seconds": tasks.OPTIONAL_PRIMARY_SOURCE_RECOVERY_CUTOFF_SECONDS,
        "recovery_requested": recovery_requested,
        "expected_recovery": expected_recovery,
        "unverified_preserved": preserved,
        "stage_outcome": stage_outcome,
    }


def build_tail_latency_validation_report():
    checks = [
        _groq_timeout_check(),
        _recovery_check(elapsed_seconds=60.0),
        _recovery_check(elapsed_seconds=80.0),
    ]
    return {
        "passed": all(check["passed"] for check in checks),
        "nfr_seconds": {"minimum": 30, "maximum": 90},
        "guardrails": {
            "groq_request_timeout_seconds": (
                GROQ_RELIABILITY_HTTP_TIMEOUT_SECONDS
            ),
            "optional_recovery_cutoff_seconds": (
                tasks.OPTIONAL_PRIMARY_SOURCE_RECOVERY_CUTOFF_SECONDS
            ),
        },
        "checks": checks,
        "offline_only": True,
        "database_writes": False,
        "external_calls": False,
    }


class Command(BaseCommand):
    help = (
        "Offline deterministic validation of verification tail-latency "
        "guardrails. No database writes and no external provider calls."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the complete validation report as JSON.",
        )

    def handle(self, *args, **options):
        if not (
            getattr(settings, "APP_ENV", None) == "development"
            and getattr(settings, "DEBUG", False) is True
        ):
            raise CommandError(
                "Tail-latency validation is development-only."
            )

        report = build_tail_latency_validation_report()

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            self.stdout.write("TRUTHLENS VERIFICATION TAIL-LATENCY VALIDATION")
            self.stdout.write(
                "NFR target: 30-90 seconds; offline deterministic simulation"
            )
            for check in report["checks"]:
                status = "PASS" if check["passed"] else "FAIL"
                self.stdout.write(f"{status:4} {check['id']}")
            self.stdout.write(
                "OVERALL " + ("PASS" if report["passed"] else "FAIL")
            )
            self.stdout.write(
                "No database writes; no external provider calls."
            )

        if not report["passed"]:
            raise CommandError("Tail-latency validation failed.")
