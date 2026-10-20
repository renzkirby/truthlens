from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import inspect
import logging
import math
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from ..models import VerificationTelemetryEvent


logger = logging.getLogger(__name__)

SAFE_STAGE_METADATA_KEYS = frozenset(
    {
        "status_code",
        "has_results",
        "bytes",
        "text_length",
        "ai_probability",
        "claims",
        "relevant",
        "evidence_sources",
        "evidence_links",
        "eligible_items",
        "persisted",
        "query_index",
        "query_count",
        "results",
    }
)
SAFE_LLM_OPERATION_LABELS = frozenset(
    {
        "unspecified",
        "claim_gate",
        "claim_equivalence",
        "fact_check_relevance",
        "gfc_evaluation",
        "tavily_evaluation",
        "persisted_evidence_evaluation",
        "evidence_assessment",
    }
)
SAFE_LLM_PROVIDERS = frozenset({"gemini", "groq", "cloudflare"})


@dataclass
class _TelemetryCollector:
    claim_id: str
    verification_run_id: UUID | None = None
    sequence: int = 0
    events: list[dict] = field(default_factory=list)


_current_collector = ContextVar("verification_telemetry_collector", default=None)


def sanitize_stage_metadata(metadata):
    safe = {}
    for key in SAFE_STAGE_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, bool) or isinstance(value, int):
            safe[key] = value
        elif isinstance(value, float) and math.isfinite(value):
            safe[key] = value
    return safe


def _append_event(**event):
    collector = _current_collector.get()
    if collector is None:
        return
    collector.sequence += 1
    collector.events.append(
        {
            "sequence": collector.sequence,
            "occurred_at": timezone.now(),
            **event,
        }
    )


def record_pipeline_stage(stage, duration_ms, **metadata):
    outcome = metadata.get("outcome") or ("failed" if stage.endswith("_failed") else "")
    _append_event(
        event_type=VerificationTelemetryEvent.EventType.PIPELINE_STAGE,
        name=stage,
        provider="",
        provider_call_id=None,
        duration_ms=max(0, int(duration_ms)),
        outcome=str(outcome),
        error_label="",
        metadata=sanitize_stage_metadata(metadata),
    )


def record_llm_provider_call(
    operation,
    provider,
    provider_call_id,
    duration_ms,
    outcome,
    error_label="",
):
    operation_label = operation if operation in SAFE_LLM_OPERATION_LABELS else "unspecified"
    provider_label = provider if provider in SAFE_LLM_PROVIDERS else ""
    _append_event(
        event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
        name=operation_label,
        provider=provider_label,
        provider_call_id=provider_call_id,
        duration_ms=max(0, int(duration_ms)),
        outcome=outcome,
        error_label=error_label,
        metadata={},
    )


def bind_verification_run(run):
    collector = _current_collector.get()
    if collector is None or str(run.claim_id) != collector.claim_id:
        return
    collector.verification_run_id = run.pk


def flush_verification_telemetry(collector):
    if collector.verification_run_id is None or not collector.events:
        return
    rows = [
        VerificationTelemetryEvent(
            verification_run_id=collector.verification_run_id,
            **event,
        )
        for event in collector.events
    ]
    try:
        with transaction.atomic():
            VerificationTelemetryEvent.objects.bulk_create(rows)
    except Exception:
        logger.error(
            "Verification telemetry persistence failed for run_id=%s event_count=%s.",
            collector.verification_run_id,
            len(rows),
        )


def verification_telemetry_scope(*, claim_id_parameter="claim_id"):
    """Collect and batch-persist one synchronous verification execution."""

    def decorator(func):
        signature = inspect.signature(func)

        @wraps(func)
        def wrapped(*args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            claim_id = str(bound.arguments.get(claim_id_parameter, ""))
            current = _current_collector.get()
            if current is not None and current.claim_id == claim_id:
                return func(*args, **kwargs)

            collector = _TelemetryCollector(claim_id=claim_id)
            token = _current_collector.set(collector)
            try:
                return func(*args, **kwargs)
            finally:
                try:
                    flush_verification_telemetry(collector)
                finally:
                    _current_collector.reset(token)

        return wrapped

    return decorator


def get_current_collector():
    """Expose execution-local state for focused tests without ORM access."""

    return _current_collector.get()
