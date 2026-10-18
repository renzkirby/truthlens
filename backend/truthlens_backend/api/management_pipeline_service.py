from collections import defaultdict
from datetime import timedelta
import math
import re

from django.db.models import Count
from django.utils import timezone

from .models import VerificationRun, VerificationTelemetryEvent
from .verification.telemetry import (
    SAFE_LLM_OPERATION_LABELS,
    SAFE_LLM_PROVIDERS,
    sanitize_stage_metadata,
)


WINDOW_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
DEFAULT_WINDOW = "7d"
_OPERATIONAL_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_ERROR_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?: code=[0-9]+)?$")


class ManagementPipelineRunNotFound(LookupError):
    pass


def _safe_run_queryset():
    return VerificationRun.objects.select_related("claim").only(
        "id",
        "claim",
        "claim__claim_type",
        "status",
        "pipeline_version",
        "started_at",
        "completed_at",
        "failure_stage",
        "failure_code",
        "abstention_reason",
        "created_at",
    )


def _window(window_value, *, now=None):
    captured_now = now or timezone.now()
    return {
        "value": window_value,
        "since": captured_now - WINDOW_DELTAS[window_value],
        "until": captured_now,
    }


def _run_duration_ms(started_at, completed_at):
    if started_at is None or completed_at is None:
        return None
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def _percentiles(values):
    if not values:
        return {
            "sample_count": 0,
            "median_duration_ms": None,
            "p95_duration_ms": None,
        }
    ordered = sorted(values)
    size = len(ordered)
    middle = size // 2
    if size % 2:
        median = ordered[middle]
    else:
        median = int((ordered[middle - 1] + ordered[middle]) / 2)
    p95 = ordered[math.ceil(0.95 * size) - 1]
    return {
        "sample_count": size,
        "median_duration_ms": median,
        "p95_duration_ms": p95,
    }


def _is_failure(name, outcome):
    normalized_name = str(name or "").lower()
    normalized_outcome = str(outcome or "").lower()
    return (
        normalized_name.endswith("_failed")
        or normalized_outcome == "failed"
        or normalized_outcome.endswith("_failed")
        or "_failed_" in normalized_outcome
        or normalized_outcome == "fatal_error"
        or normalized_outcome.endswith("_unavailable")
    )


def _safe_operational_label(value, fallback=""):
    normalized = str(value or "")
    return normalized if _OPERATIONAL_LABEL_RE.fullmatch(normalized) else fallback


def _safe_error_label(value):
    normalized = str(value or "")
    return normalized if _ERROR_LABEL_RE.fullmatch(normalized) else ""


def _safe_llm_operation(value):
    return value if value in SAFE_LLM_OPERATION_LABELS else "unspecified"


def _safe_llm_provider(value):
    return value if value in SAFE_LLM_PROVIDERS else "unknown"


def serialize_management_pipeline_run(run):
    return {
        "id": str(run.id),
        "claim_id": str(run.claim_id),
        "claim_type": run.claim.claim_type,
        "status": run.status,
        "pipeline_version": run.pipeline_version,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "duration_ms": _run_duration_ms(run.started_at, run.completed_at),
        "failure_stage": run.failure_stage,
        "failure_code": run.failure_code,
        "abstention_reason": run.abstention_reason,
        "created_at": run.created_at,
    }


def list_management_pipeline_runs(*, window_value, status="", claim_type=""):
    selected_window = _window(window_value)
    queryset = _safe_run_queryset().filter(
        created_at__gte=selected_window["since"],
        created_at__lte=selected_window["until"],
    )
    if status:
        queryset = queryset.filter(status=status)
    if claim_type:
        queryset = queryset.filter(claim__claim_type=claim_type)
    return queryset.order_by("-created_at", "-id")


def build_management_pipeline_overview(*, window_value):
    selected_window = _window(window_value)
    run_filter = {
        "created_at__gte": selected_window["since"],
        "created_at__lte": selected_window["until"],
    }
    runs = VerificationRun.objects.filter(**run_filter)
    status_counts = {value: 0 for value, _label in VerificationRun.Status.choices}
    for row in runs.values("status").annotate(total=Count("id")):
        status_counts[row["status"]] = row["total"]

    durations = [
        duration
        for started_at, completed_at in runs.values_list("started_at", "completed_at")
        if (duration := _run_duration_ms(started_at, completed_at)) is not None
    ]
    run_stats = _percentiles(durations)

    event_rows = VerificationTelemetryEvent.objects.filter(
        verification_run__created_at__gte=selected_window["since"],
        verification_run__created_at__lte=selected_window["until"],
    ).values(
        "verification_run_id",
        "event_type",
        "name",
        "provider",
        "duration_ms",
        "outcome",
    )
    stage_groups = defaultdict(lambda: {"durations": [], "failures": 0})
    provider_groups = defaultdict(
        lambda: {"durations": [], "successes": 0, "failures": 0}
    )
    groq_attempts = 0
    groq_successes = 0
    groq_run_ids = set()
    for event in event_rows:
        if event["event_type"] == VerificationTelemetryEvent.EventType.PIPELINE_STAGE:
            raw_name = _safe_operational_label(event["name"], "unknown_stage")
            stage_name = raw_name[:-7] if raw_name.endswith("_failed") else raw_name
            group = stage_groups[stage_name]
            group["durations"].append(event["duration_ms"])
            if _is_failure(raw_name, event["outcome"]):
                group["failures"] += 1
            continue

        operation = _safe_llm_operation(event["name"])
        provider = _safe_llm_provider(event["provider"])
        group = provider_groups[(operation, provider)]
        group["durations"].append(event["duration_ms"])
        if event["outcome"] == "success":
            group["successes"] += 1
        elif _is_failure("", event["outcome"]):
            group["failures"] += 1
        if provider == "groq":
            groq_attempts += 1
            groq_run_ids.add(event["verification_run_id"])
            if event["outcome"] == "success":
                groq_successes += 1

    stages = []
    for stage, group in stage_groups.items():
        stats = _percentiles(group["durations"])
        stages.append(
            {
                "stage": stage,
                "samples": stats["sample_count"],
                "failures": group["failures"],
                "median_duration_ms": stats["median_duration_ms"],
                "p95_duration_ms": stats["p95_duration_ms"],
                "max_duration_ms": max(group["durations"]),
            }
        )
    stages.sort(key=lambda row: (-row["p95_duration_ms"], row["stage"]))

    providers = []
    for (operation, provider), group in provider_groups.items():
        stats = _percentiles(group["durations"])
        providers.append(
            {
                "operation": operation,
                "provider": provider,
                "attempts": stats["sample_count"],
                "successes": group["successes"],
                "failures": group["failures"],
                "median_duration_ms": stats["median_duration_ms"],
                "p95_duration_ms": stats["p95_duration_ms"],
                "max_duration_ms": max(group["durations"]),
            }
        )
    providers.sort(key=lambda row: (row["operation"], row["provider"]))

    recent_failures = [
        serialize_management_pipeline_run(run)
        for run in _safe_run_queryset()
        .filter(**run_filter, status=VerificationRun.Status.FAILED)
        .order_by("-created_at", "-id")[:5]
    ]
    return {
        "window": selected_window,
        "runs": {
            "total": sum(status_counts.values()),
            "statuses": status_counts,
            "duration_samples": run_stats["sample_count"],
            "median_duration_ms": run_stats["median_duration_ms"],
            "p95_duration_ms": run_stats["p95_duration_ms"],
        },
        "stages": stages,
        "providers": providers,
        "fallback": {
            "groq_attempts": groq_attempts,
            "groq_successes": groq_successes,
            "runs_using_groq": len(groq_run_ids),
        },
        "recent_failures": recent_failures,
    }


def get_management_pipeline_run(*, run_id):
    try:
        run = _safe_run_queryset().get(pk=run_id)
    except VerificationRun.DoesNotExist as error:
        raise ManagementPipelineRunNotFound from error

    payload = serialize_management_pipeline_run(run)
    events = []
    for event in run.telemetry_events.order_by("sequence"):
        base = {
            "sequence": event.sequence,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at,
            "duration_ms": event.duration_ms,
            "outcome": _safe_operational_label(event.outcome),
        }
        if event.event_type == VerificationTelemetryEvent.EventType.PIPELINE_STAGE:
            events.append(
                {
                    **base,
                    "stage": _safe_operational_label(event.name, "unknown_stage"),
                    "metadata": sanitize_stage_metadata(event.metadata),
                }
            )
        elif event.event_type == VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL:
            events.append(
                {
                    **base,
                    "operation": _safe_llm_operation(event.name),
                    "provider": _safe_llm_provider(event.provider),
                    "provider_call_id": (
                        str(event.provider_call_id) if event.provider_call_id else None
                    ),
                    "error_label": _safe_error_label(event.error_label),
                }
            )
    payload["telemetry_events"] = events
    return payload
