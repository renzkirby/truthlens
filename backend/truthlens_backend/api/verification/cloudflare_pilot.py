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
from .classification_contract import (
    CLASSIFICATION_OPERATION, validate_classification_response,
)

PILOT_FLAG = "ENABLE_CLOUDFLARE_VERIFICATION_PILOT"
ASSESSMENT_PILOT_FLAG = "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"
# Explicit opt-in only for capacity-queue diagnosis, never final verdicts.
ASSESSMENT_REJECT_BUSY_FLAG = "CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY"
ASSESSMENT_CHUNKING_FLAG = "CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING"
CLASSIFICATION_PILOT_FLAG = "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT"
CLASSIFICATION_REJECT_BUSY_FLAG = "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY"
CLASSIFICATION_READ_TIMEOUT_FLAG = "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC"
CLASSIFICATION_BUDGET_FLAG = "CLOUDFLARE_PILOT_CLASSIFICATION_MAX_TOKENS"
PILOT_OPERATION = "persisted_evidence_evaluation"
EQUIVALENCE_OPERATION = "claim_equivalence"
RELEVANCE_OPERATION = "fact_check_relevance"
GFC_EVALUATION_OPERATION = "gfc_evaluation"
TAVILY_EVALUATION_OPERATION = "tavily_evaluation"
ASSESSMENT_OPERATION = "evidence_assessment"
PILOT_COMPLETION_TOKENS = 2048
ASSESSMENT_COMPLETION_TOKENS = 2048
# Each Workers AI assessment request remains limited to four items.
# Larger batches go to original providers unless the separate dev-only
# all-or-nothing, lossless chunking experiment is explicitly enabled.
ASSESSMENT_MAX_ITEMS = 4
ASSESSMENT_MAX_CHUNKS = 3
ASSESSMENT_HTTP_TIMEOUT = (3, 15)
CLASSIFICATION_HTTP_TIMEOUT = (3, 15)
# Conservative baseline; 4096 requires a distinct, dev-only opt-in.
CLASSIFICATION_COMPLETION_TOKENS = 1024
CLASSIFICATION_MAX_INPUT_CHARS = 2400
CLASSIFICATION_MIN_INPUT_CHARS = 20
FINAL_BUDGET_ENV = "CLOUDFLARE_PILOT_FINAL_MAX_TOKENS"
PILOT_MAX_INPUT_CHARS = MAX_INPUT_CHARS
_ASSESSMENT_PREFIX = "UNTRUSTED ASSESSMENT DATA:\n"
_ASSESSMENT_FIELDS = frozenset({
    "key", "stance", "relevance_score", "directness_score",
})
_ASSESSMENT_STANCES = frozenset({"SUPPORTS", "REFUTES", "CONTEXT", "UNKNOWN"})


def cloudflare_pilot_enabled(operation):
    """Select only validated Cloudflare stages under either routing policy.

    The universal hierarchy is independently opt-in in any environment.
    Unvalidated operations must not be sent to the Cloudflare pilot adapter.
    """
    from .provider_hierarchy import UNIVERSAL_HIERARCHY_FLAG, hierarchy_enabled

    if os.getenv(UNIVERSAL_HIERARCHY_FLAG, "") == "1":
        return operation in {
            PILOT_OPERATION, ASSESSMENT_OPERATION, CLASSIFICATION_OPERATION,
            EQUIVALENCE_OPERATION, RELEVANCE_OPERATION,
            GFC_EVALUATION_OPERATION, TAVILY_EVALUATION_OPERATION,
        }

    # Preserve the original, development-only pilot semantics.
    if not (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
        and os.getenv(PILOT_FLAG, "") == "1"
    ):
        return False
    if operation == PILOT_OPERATION:
        return True
    if operation == CLASSIFICATION_OPERATION:
        return (
            hierarchy_enabled()
            and os.getenv(CLASSIFICATION_PILOT_FLAG, "") == "1"
        )
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


def cloudflare_classification_reject_if_busy_enabled():
    """Opt-in to documented queue fast-fail for classification only.

    The existing assessment fast-fail flag is separate. Final evaluation
    deliberately retains its original request body.
    """
    return (
        cloudflare_pilot_enabled(CLASSIFICATION_OPERATION)
        and os.getenv(CLASSIFICATION_REJECT_BUSY_FLAG, "") == "1"
    )


def cloudflare_classification_completion_budget():
    """4096 is opt-in for dev-only classification; legacy default is 1024.

    Never let this setting affect evidence assessment or factual verdicts.
    Only the exact string "4096" is accepted; all other inputs fail closed.
    """
    if (
        cloudflare_pilot_enabled(CLASSIFICATION_OPERATION)
        and os.getenv(CLASSIFICATION_BUDGET_FLAG, "") == "4096"
    ):
        return 4096
    return CLASSIFICATION_COMPLETION_TOKENS


def cloudflare_classification_http_timeout():
    """Bound classification socket inactivity, NOT total wall-clock time.

    Default is 15s. The established dev-only flag supports 30s.
    A 45s read limit is available ONLY with the explicit 4096-token arm.
    Neither modifies final-evaluation or evidence-assessment timeouts.
    """
    if cloudflare_pilot_enabled(CLASSIFICATION_OPERATION):
        requested = os.getenv(CLASSIFICATION_READ_TIMEOUT_FLAG, "")
        if requested == "30":
            return (CLASSIFICATION_HTTP_TIMEOUT[0], 30)
        if (
            requested == "45"
            and cloudflare_classification_completion_budget() == 4096
        ):
            return (CLASSIFICATION_HTTP_TIMEOUT[0], 45)
    return CLASSIFICATION_HTTP_TIMEOUT


def cloudflare_assessment_chunking_enabled():
    """Opt-in bounded assessment chunks, never a production routing change."""
    from .provider_hierarchy import hierarchy_enabled

    return (
        hierarchy_enabled()
        and cloudflare_pilot_enabled(ASSESSMENT_OPERATION)
        and os.getenv(ASSESSMENT_CHUNKING_FLAG, "") == "1"
    )


def _assessment_chunk_plan(system_instructions, user_prompt):
    """Plan all chunks before any network request; preserve every item byte.

    Fails locally instead of silently truncating, omitting, or reordering
    original evidence. A single oversized item cannot be safely split.
    """
    if (
        not isinstance(system_instructions, str)
        or not system_instructions.strip()
        or not isinstance(user_prompt, str)
        or not user_prompt.strip()
    ):
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")
    _expected_assessment_keys(user_prompt)
    payload = json.loads(user_prompt[len(_ASSESSMENT_PREFIX):])
    items = payload["evidence_items"]
    if len(items) > ASSESSMENT_MAX_ITEMS * ASSESSMENT_MAX_CHUNKS:
        raise CloudflareEvaluationError("ASSESSMENT_BATCH_TOO_LARGE")

    def prompt_for(chunk_items):
        return _ASSESSMENT_PREFIX + json.dumps(
            {"claim_text": payload["claim_text"], "evidence_items": chunk_items},
            ensure_ascii=False,
        )

    chunks = []
    current = []
    for item in items:
        candidate = current + [item]
        candidate_prompt = prompt_for(candidate)
        if (
            len(candidate) > ASSESSMENT_MAX_ITEMS
            or len(system_instructions) + len(candidate_prompt) > PILOT_MAX_INPUT_CHARS
        ):
            if not current:
                raise CloudflareEvaluationError("PROMPT_TOO_LONG")
            chunks.append(prompt_for(current))
            current = [item]
            if len(system_instructions) + len(prompt_for(current)) > PILOT_MAX_INPUT_CHARS:
                raise CloudflareEvaluationError("PROMPT_TOO_LONG")
        else:
            current = candidate
    if current:
        chunks.append(prompt_for(current))
    if len(chunks) > ASSESSMENT_MAX_CHUNKS:
        raise CloudflareEvaluationError("ASSESSMENT_BATCH_TOO_LARGE")
    return chunks, [item["key"] for item in items]


def cloudflare_assessment_chunking_bypass_reason(system_instructions, user_prompt):
    """Allow Cloudflare only when the complete lossless plan fits its limits."""
    try:
        _assessment_chunk_plan(system_instructions, user_prompt)
    except CloudflareEvaluationError as exc:
        return str(exc)
    return None


def _aggregate_chunk_metadata(metadata, chunks, *, complete=False):
    """Whitelist counters, and distinguish partial attempts from success."""
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        raise CloudflareEvaluationError("INVALID_AUDIT_METADATA")
    metadata["assessment_chunks_attempted"] = len(chunks)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens",
                "reasoning_tokens"):
        values = [chunk.get(key) for chunk in chunks]
        if values and all(type(value) is int and 0 <= value <= 10000000
                          for value in values):
            metadata[key] = sum(values)
    if chunks:
        metadata["reasoning_present"] = any(
            chunk.get("reasoning_present") is True for chunk in chunks
        )
        # Only a complete multi-chunk response can claim finish_reason=stop.
        if complete and all(chunk.get("finish_reason") == "stop" for chunk in chunks):
            metadata["finish_reason"] = "stop"


def call_validated_cloudflare_assessment_chunks(
    system_instructions, user_prompt, *, audit_metadata=None,
):
    """Bounded lossless sequential assessment; all-or-nothing JSON output.

    No silent partial acceptance and no retry within a chunk. The caller
    owns failover to the full original Gemini/Groq assessment request.
    """
    if audit_metadata is not None and not isinstance(audit_metadata, dict):
        raise CloudflareEvaluationError("INVALID_AUDIT_METADATA")
    prompts, ordered_keys = _assessment_chunk_plan(
        system_instructions, user_prompt,
    )
    completed = {}
    attempted_metadata = []
    complete = False
    try:
        for chunk_prompt in prompts:
            chunk_metadata = {}
            attempted_metadata.append(chunk_metadata)
            raw = call_validated_cloudflare_pilot(
                system_instructions, chunk_prompt,
                operation=ASSESSMENT_OPERATION,
                audit_metadata=chunk_metadata,
            )
            for result in json.loads(raw)["assessments"]:
                key = result["key"]
                if key in completed:
                    raise CloudflareEvaluationError("INVALID_ASSESSMENT_JSON")
                completed[key] = result
        if set(completed) != set(ordered_keys):
            raise CloudflareEvaluationError("INVALID_ASSESSMENT_JSON")
        full_response = json.dumps(
            {"assessments": [completed[key] for key in ordered_keys]},
            ensure_ascii=False,
        )
        if not validate_pilot_response(ASSESSMENT_OPERATION, full_response, user_prompt):
            raise CloudflareEvaluationError("INVALID_ASSESSMENT_JSON")
        complete = True
        return full_response
    finally:
        _aggregate_chunk_metadata(
            audit_metadata, attempted_metadata, complete=complete,
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


def _valid_small_decision(operation, raw):
    """Strict JSON shape for the two bounded decision-only operations."""
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return False
    if not isinstance(value, dict):
        return False
    if operation == RELEVANCE_OPERATION:
        return (
            set(value) == {"reasoning", "is_relevant"}
            and type(value["is_relevant"]) is bool
            and isinstance(value["reasoning"], str)
            and bool(value["reasoning"].strip())
        )
    if operation == EQUIVALENCE_OPERATION:
        return (
            set(value) == {"equivalent", "reasoning", "material_differences"}
            and type(value["equivalent"]) is bool
            and isinstance(value["reasoning"], str)
            and bool(value["reasoning"].strip())
            and isinstance(value["material_differences"], list)
            and all(
                isinstance(v, str) and bool(v.strip())
                for v in value["material_differences"]
            )
            and (
                not value["equivalent"]
                or not value["material_differences"]
            )
        )
    return False


def validate_pilot_response(operation, raw, user_prompt):
    """A valid response must satisfy the exact operation-specific contract."""
    if operation in {EQUIVALENCE_OPERATION, RELEVANCE_OPERATION}:
        return _valid_small_decision(operation, raw)
    if operation in {PILOT_OPERATION, GFC_EVALUATION_OPERATION, TAVILY_EVALUATION_OPERATION}:
        return validate_user_facing_evaluation(raw) is not None
    if operation == ASSESSMENT_OPERATION:
        return _valid_assessment_batch(raw, user_prompt)
    if operation == CLASSIFICATION_OPERATION:
        return validate_classification_response(raw, user_prompt)
    return False


def call_validated_cloudflare_pilot(
    system_instructions, user_prompt, *,
    operation=PILOT_OPERATION, audit_metadata=None,
):
    """Only return a fully validated JSON response; one provider attempt."""
    if operation not in {
        PILOT_OPERATION, ASSESSMENT_OPERATION, CLASSIFICATION_OPERATION,
        EQUIVALENCE_OPERATION, RELEVANCE_OPERATION,
        GFC_EVALUATION_OPERATION, TAVILY_EVALUATION_OPERATION,
    }:
        raise CloudflareEvaluationError("INVALID_PILOT_OPERATION")
    if operation == ASSESSMENT_OPERATION:
        _expected_assessment_keys(user_prompt)
    if operation == CLASSIFICATION_OPERATION and (
        not isinstance(user_prompt, str)
        or not CLASSIFICATION_MIN_INPUT_CHARS <= len(user_prompt.strip()) <= CLASSIFICATION_MAX_INPUT_CHARS
    ):
        raise CloudflareEvaluationError("INVALID_CLASSIFICATION_INPUT")
    options = {
        "max_completion_tokens": (
            ASSESSMENT_COMPLETION_TOKENS
            if operation == ASSESSMENT_OPERATION
            else (
                cloudflare_classification_completion_budget()
                if operation == CLASSIFICATION_OPERATION
                else _final_completion_budget()
            )
        ),
        "audit_metadata": audit_metadata,
    }
    if operation == CLASSIFICATION_OPERATION:
        options["http_timeout"] = cloudflare_classification_http_timeout()
        if cloudflare_classification_reject_if_busy_enabled():
            options["reject_if_busy"] = True
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
            else (
                "INVALID_CLASSIFICATION_JSON"
                if operation == CLASSIFICATION_OPERATION
                else "INVALID_EVALUATION_JSON"
            )
        )
    return raw
