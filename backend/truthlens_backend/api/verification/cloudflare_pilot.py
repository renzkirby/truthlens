"""Dev-only, stage-gated Cloudflare provider pilot.

The original verdict pilot is unchanged unless explicitly opted in. Evidence
assessment has a separate flag and strict per-item JSON validation.
"""
import json
import math
import os
from numbers import Real

from django.conf import settings

from .cloudflare_evaluation import (
    CloudflareEvaluationError, MAX_INPUT_CHARS, generate_evaluation_json,
)
from .provider_audit_metrics import validate_user_facing_evaluation

PILOT_FLAG = "ENABLE_CLOUDFLARE_VERIFICATION_PILOT"
ASSESSMENT_PILOT_FLAG = "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"
# Explicit opt-in only for capacity-queue diagnosis, never final verdicts.
ASSESSMENT_REJECT_BUSY_FLAG = "CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY"
PILOT_OPERATION = "persisted_evidence_evaluation"
ASSESSMENT_OPERATION = "evidence_assessment"
PILOT_COMPLETION_TOKENS = 2048
ASSESSMENT_COMPLETION_TOKENS = 2048
# Keep the initial Workers AI assessment pilot to small batches. Larger
# original batches go intact to the existing providers, not to truncated
# or sliced Cloudflare requests.
ASSESSMENT_MAX_ITEMS = 4
ASSESSMENT_HTTP_TIMEOUT = (3, 15)
FINAL_BUDGET_ENV = "CLOUDFLARE_PILOT_FINAL_MAX_TOKENS"
PILOT_MAX_INPUT_CHARS = MAX_INPUT_CHARS
_ASSESSMENT_PREFIX = "UNTRUSTED ASSESSMENT DATA:\n"
_ASSESSMENT_FIELDS = frozenset({
    "key", "stance", "relevance_score", "directness_score",
})
_ASSESSMENT_STANCES = frozenset({"SUPPORTS", "REFUTES", "CONTEXT", "UNKNOWN"})


def cloudflare_pilot_enabled(operation):
    """Staging/production cannot be enabled via environment flags."""
    if not (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
        and os.getenv(PILOT_FLAG, "") == "1"
    ):
        return False
    if operation == PILOT_OPERATION:
        return True
    return (
        operation == ASSESSMENT_OPERATION
        and os.getenv(ASSESSMENT_PILOT_FLAG, "") == "1"
    )


def cloudflare_assessment_reject_if_busy_enabled():
    """Dev-only experiment: bypass Workers AI capacity queue for assessment.

    Requires the independent AI-RQ-2 routing and assessment-stage pilot
    flags. Never changes final-evaluation inference or legacy routing.
    """
    from .provider_hierarchy import hierarchy_enabled

    return (
        hierarchy_enabled()
        and cloudflare_pilot_enabled(ASSESSMENT_OPERATION)
        and os.getenv(ASSESSMENT_REJECT_BUSY_FLAG, "") == "1"
    )


def _final_completion_budget():
    """Optional controlled dev-only latency experiment; default unchanged."""
    if not (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
    ):
        return PILOT_COMPLETION_TOKENS
    # Keep a limited two-arm experiment; never silently accept arbitrary
    # low budgets or trim the final JSON.
    return (
        1536 if os.getenv(FINAL_BUDGET_ENV, "").strip() == "1536"
        else PILOT_COMPLETION_TOKENS
    )


def _expected_assessment_keys(user_prompt):
    """Extract only opaque item IDs from the trusted evidence prompt envelope."""
    if not isinstance(user_prompt, str) or not user_prompt.startswith(
        _ASSESSMENT_PREFIX
    ):
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")
    try:
        payload = json.loads(user_prompt[len(_ASSESSMENT_PREFIX):])
    except (ValueError, TypeError):
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT") from None
    if not isinstance(payload, dict) or set(payload) != {
        "claim_text", "evidence_items",
    }:
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")
    items = payload["evidence_items"]
    if (
        not isinstance(payload["claim_text"], str)
        or not payload["claim_text"].strip()
        or not isinstance(items, list) or not items
    ):
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")
    keys = []
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {"key", "evidence_content"}
            or not isinstance(item["key"], str)
            or not item["key"].startswith("item_")
            or not item["key"][5:].isdigit()
            or not isinstance(item["evidence_content"], str)
            or not item["evidence_content"].strip()
        ):
            raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")
        keys.append(item["key"])
    if len(keys) != len(set(keys)):
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")
    return set(keys)


def cloudflare_assessment_bypass_reason(system_instructions, user_prompt):
    """Return a safe reason to use legacy assessment without calling Cloudflare.

    Bypassing locally must not trip the job-scoped Cloudflare breaker: the
    final evaluator is independently eligible for the original pilot.
    """
    if (
        not isinstance(system_instructions, str)
        or not system_instructions.strip()
        or not isinstance(user_prompt, str)
        or not user_prompt.strip()
    ):
        return "INVALID_ASSESSMENT_INPUT"
    if len(system_instructions) + len(user_prompt) > PILOT_MAX_INPUT_CHARS:
        return "PROMPT_TOO_LONG"
    try:
        expected = _expected_assessment_keys(user_prompt)
    except CloudflareEvaluationError:
        return "INVALID_ASSESSMENT_INPUT"
    if len(expected) > ASSESSMENT_MAX_ITEMS:
        return "ASSESSMENT_BATCH_TOO_LARGE"
    return None


def _valid_assessment_batch(raw, user_prompt):
    try:
        expected = _expected_assessment_keys(user_prompt)
        parsed = json.loads(raw)
    except (ValueError, TypeError, CloudflareEvaluationError):
        return False
    if not isinstance(parsed, dict) or set(parsed) != {"assessments"}:
        return False
    rows = parsed["assessments"]
    if not isinstance(rows, list) or len(rows) != len(expected):
        return False
    seen = set()
    for item in rows:
        if not isinstance(item, dict) or set(item) != _ASSESSMENT_FIELDS:
            return False
        key = item["key"]
        if not isinstance(key, str) or key not in expected or key in seen:
            return False
        seen.add(key)
        stance = item["stance"]
        if not isinstance(stance, str) or stance not in _ASSESSMENT_STANCES:
            return False
        for field in ("relevance_score", "directness_score"):
            value = item[field]
            if (
                not isinstance(value, Real)
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                return False
    return seen == expected


def validate_pilot_response(operation, raw, user_prompt):
    """A valid response must satisfy the exact operation-specific contract."""
    if operation == PILOT_OPERATION:
        return validate_user_facing_evaluation(raw) is not None
    if operation == ASSESSMENT_OPERATION:
        return _valid_assessment_batch(raw, user_prompt)
    return False


def call_validated_cloudflare_pilot(
    system_instructions, user_prompt, *,
    operation=PILOT_OPERATION, audit_metadata=None,
):
    """Only return a fully validated JSON response; one provider attempt."""
    if operation not in {PILOT_OPERATION, ASSESSMENT_OPERATION}:
        raise CloudflareEvaluationError("INVALID_PILOT_OPERATION")
    if operation == ASSESSMENT_OPERATION:
        _expected_assessment_keys(user_prompt)
    options = {
        "max_completion_tokens": (
            ASSESSMENT_COMPLETION_TOKENS
            if operation == ASSESSMENT_OPERATION
            else _final_completion_budget()
        ),
        "audit_metadata": audit_metadata,
    }
    if operation == ASSESSMENT_OPERATION:
        # Requests timeouts are not a total wall-clock budget. They bound
        # connection/read inactivity, reducing the prior 45s stall.
        options["http_timeout"] = ASSESSMENT_HTTP_TIMEOUT
        if cloudflare_assessment_reject_if_busy_enabled():
            options["reject_if_busy"] = True
    raw = generate_evaluation_json(
        system_instructions, user_prompt, **options,
    )
    if not validate_pilot_response(operation, raw, user_prompt):
        raise CloudflareEvaluationError(
            "INVALID_ASSESSMENT_JSON"
            if operation == ASSESSMENT_OPERATION
            else "INVALID_EVALUATION_JSON"
        )
    return raw
