"""Dev-only, stage-gated Cloudflare provider pilot.

The original verdict pilot is unchanged unless explicitly opted in. Evidence
assessment has a separate flag and strict per-item JSON validation.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from numbers import Real

from django.conf import settings

from .cloudflare_evaluation import (
    CloudflareEvaluationError, MAX_INPUT_CHARS, generate_evaluation_json,
)
from .provider_audit_metrics import (
    validate_persisted_evidence_evaluation,
    validate_user_facing_evaluation,
)
from .classification_contract import (
    CLASSIFICATION_OPERATION, validate_classification_response,
)

PILOT_FLAG = "ENABLE_CLOUDFLARE_VERIFICATION_PILOT"
ASSESSMENT_PILOT_FLAG = "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"
# Explicit opt-in only for capacity-queue diagnosis; never changes verdict rules.
ASSESSMENT_REJECT_BUSY_FLAG = "CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY"
ASSESSMENT_CHUNKING_FLAG = "CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING"
ASSESSMENT_CONCURRENCY_FLAG = "ENABLE_CLOUDFLARE_ASSESSMENT_CONCURRENCY"
CLASSIFICATION_PILOT_FLAG = "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT"
CLASSIFICATION_REJECT_BUSY_FLAG = "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY"
CLASSIFICATION_READ_TIMEOUT_FLAG = "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC"
CLASSIFICATION_BUDGET_FLAG = "CLOUDFLARE_PILOT_CLASSIFICATION_MAX_TOKENS"
PILOT_OPERATION = "persisted_evidence_evaluation"
EQUIVALENCE_OPERATION = "claim_equivalence"
RELEVANCE_OPERATION = "fact_check_relevance"
CLAIM_GATE_OPERATION = "claim_gate"
GFC_EVALUATION_OPERATION = "gfc_evaluation"
TAVILY_EVALUATION_OPERATION = "tavily_evaluation"
SATIRE_PROVENANCE_AUDIT_OPERATION = "satire_provenance_audit"
STRUCTURED_MISLEADING_AUDIT_OPERATION = "structured_misleading_audit"
ASSESSMENT_OPERATION = "evidence_assessment"
PILOT_COMPLETION_TOKENS = 2048
ASSESSMENT_COMPLETION_TOKENS = 2048
# Each Workers AI assessment request remains limited to four items.
# Larger batches go to original providers unless the separate dev-only
# all-or-nothing, lossless chunking experiment is explicitly enabled.
ASSESSMENT_MAX_ITEMS = 4
ASSESSMENT_MAX_CHUNKS = 3
ASSESSMENT_MAX_CONCURRENCY = 2
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
    from .provider_hierarchy import hierarchy_enabled, universal_hierarchy_enabled

    if universal_hierarchy_enabled():
        return operation in {
            PILOT_OPERATION, ASSESSMENT_OPERATION, CLASSIFICATION_OPERATION,
            EQUIVALENCE_OPERATION, RELEVANCE_OPERATION,
            GFC_EVALUATION_OPERATION, TAVILY_EVALUATION_OPERATION,
            SATIRE_PROVENANCE_AUDIT_OPERATION,
            STRUCTURED_MISLEADING_AUDIT_OPERATION,
            CLAIM_GATE_OPERATION,
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
    """Use lossless assessment chunks for reliability hardening or legacy dev opt-in."""
    from .provider_hierarchy import hierarchy_enabled, reliability_hardening_enabled

    return (
        hierarchy_enabled()
        and cloudflare_pilot_enabled(ASSESSMENT_OPERATION)
        and (
            reliability_hardening_enabled()
            or os.getenv(ASSESSMENT_CHUNKING_FLAG, "") == "1"
        )
    )


def cloudflare_assessment_concurrency_enabled():
    """Use bounded chunk concurrency by default under reliability hardening.

    The feature still requires the existing provider hierarchy, assessment
    pilot, lossless chunking eligibility, and reliability-hardening master
    switch. Setting the dedicated flag to exactly "0" is the emergency kill
    switch; unset or any other value keeps the hardened default enabled.
    """
    from .provider_hierarchy import reliability_hardening_enabled

    return (
        reliability_hardening_enabled()
        and cloudflare_assessment_chunking_enabled()
        and os.getenv(ASSESSMENT_CONCURRENCY_FLAG) != "0"
    )


def _assessment_chunk_plan(
    system_instructions,
    user_prompt,
    *,
    max_chunks=ASSESSMENT_MAX_CHUNKS,
    max_input_chars=PILOT_MAX_INPUT_CHARS,
):
    """Plan lossless keyed chunks before any network request.

    Cloudflare keeps its original four-item/three-chunk/28K envelope. The same
    planner may be reused by downstream provider recovery with a different
    bounded chunk count and without silently trimming any evidence item.
    """
    if (
        not isinstance(system_instructions, str)
        or not system_instructions.strip()
        or not isinstance(user_prompt, str)
        or not user_prompt.strip()
    ):
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")
    if (
        max_chunks is not None
        and (
            isinstance(max_chunks, bool)
            or not isinstance(max_chunks, int)
            or max_chunks < 1
        )
    ):
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")
    if (
        max_input_chars is not None
        and (
            isinstance(max_input_chars, bool)
            or not isinstance(max_input_chars, int)
            or max_input_chars < 1
        )
    ):
        raise CloudflareEvaluationError("INVALID_ASSESSMENT_INPUT")

    _expected_assessment_keys(user_prompt)
    payload = json.loads(user_prompt[len(_ASSESSMENT_PREFIX):])
    items = payload["evidence_items"]
    if (
        max_chunks is not None
        and len(items) > ASSESSMENT_MAX_ITEMS * max_chunks
    ):
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
        over_input_limit = (
            max_input_chars is not None
            and len(system_instructions) + len(candidate_prompt) > max_input_chars
        )
        if len(candidate) > ASSESSMENT_MAX_ITEMS or over_input_limit:
            if not current:
                raise CloudflareEvaluationError("PROMPT_TOO_LONG")
            chunks.append(prompt_for(current))
            current = [item]
            if (
                max_input_chars is not None
                and len(system_instructions) + len(prompt_for(current))
                > max_input_chars
            ):
                raise CloudflareEvaluationError("PROMPT_TOO_LONG")
        else:
            current = candidate
    if current:
        chunks.append(prompt_for(current))
    if max_chunks is not None and len(chunks) > max_chunks:
        raise CloudflareEvaluationError("ASSESSMENT_BATCH_TOO_LARGE")
    return chunks, [item["key"] for item in items]


def plan_lossless_assessment_chunks(
    system_instructions,
    user_prompt,
    *,
    max_chunks,
):
    """Return bounded four-item chunks for downstream 413 recovery.

    This deliberately applies no provider-specific character truncation. If a
    single original evidence item is itself too large for the downstream
    provider, that provider must fail normally rather than receiving modified
    evidence.
    """
    return _assessment_chunk_plan(
        system_instructions,
        user_prompt,
        max_chunks=max_chunks,
        max_input_chars=None,
    )


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
    """Bounded lossless assessment with optional max-two chunk concurrency.

    Sequential execution remains the default. When the explicit concurrency
    rollout flag is enabled under reliability hardening, the first two exact
    production chunk prompts run concurrently. A third chunk starts only after
    the first wave succeeds. Any failure discards partial results and propagates
    to the caller, which owns fallback to the full original provider request.
    """
    if audit_metadata is not None and not isinstance(audit_metadata, dict):
        raise CloudflareEvaluationError("INVALID_AUDIT_METADATA")
    prompts, ordered_keys = _assessment_chunk_plan(
        system_instructions, user_prompt,
    )
    completed = {}
    attempted_metadata = []
    complete = False
    use_concurrency = (
        len(prompts) > 1
        and cloudflare_assessment_concurrency_enabled()
    )
    waves_attempted = 0

    def call_chunk(chunk_prompt, chunk_metadata):
        raw = call_validated_cloudflare_pilot(
            system_instructions, chunk_prompt,
            operation=ASSESSMENT_OPERATION,
            audit_metadata=chunk_metadata,
        )
        return json.loads(raw)["assessments"]

    def merge_rows(rows):
        for result in rows:
            key = result["key"]
            if key in completed:
                raise CloudflareEvaluationError("INVALID_ASSESSMENT_JSON")
            completed[key] = result

    try:
        if use_concurrency:
            first_wave_size = min(
                ASSESSMENT_MAX_CONCURRENCY,
                len(prompts),
            )
            first_wave_metadata = [
                {} for _ in range(first_wave_size)
            ]
            attempted_metadata.extend(first_wave_metadata)
            waves_attempted = 1
            wave_results = {}
            wave_errors = {}
            with ThreadPoolExecutor(
                max_workers=ASSESSMENT_MAX_CONCURRENCY,
            ) as executor:
                futures = {
                    executor.submit(
                        call_chunk,
                        prompts[index],
                        first_wave_metadata[index],
                    ): index
                    for index in range(first_wave_size)
                }
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        wave_results[index] = future.result()
                    except Exception as exc:
                        wave_errors[index] = exc

            if wave_errors:
                raise wave_errors[min(wave_errors)]

            for index in range(first_wave_size):
                merge_rows(wave_results[index])

            for chunk_prompt in prompts[first_wave_size:]:
                waves_attempted += 1
                chunk_metadata = {}
                attempted_metadata.append(chunk_metadata)
                merge_rows(call_chunk(chunk_prompt, chunk_metadata))
        else:
            for chunk_prompt in prompts:
                chunk_metadata = {}
                attempted_metadata.append(chunk_metadata)
                merge_rows(call_chunk(chunk_prompt, chunk_metadata))

        if set(completed) != set(ordered_keys):
            raise CloudflareEvaluationError("INVALID_ASSESSMENT_JSON")
        full_response = json.dumps(
            {"assessments": [completed[key] for key in ordered_keys]},
            ensure_ascii=False,
        )
        if not validate_pilot_response(
            ASSESSMENT_OPERATION,
            full_response,
            user_prompt,
        ):
            raise CloudflareEvaluationError("INVALID_ASSESSMENT_JSON")
        complete = True
        return full_response
    finally:
        _aggregate_chunk_metadata(
            audit_metadata, attempted_metadata, complete=complete,
        )
        if audit_metadata is not None and use_concurrency:
            audit_metadata["assessment_max_concurrency"] = (
                ASSESSMENT_MAX_CONCURRENCY
            )
            audit_metadata["assessment_waves_attempted"] = waves_attempted


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


def _satire_aliases_from_prompt(user_prompt):
    if not isinstance(user_prompt, str):
        return set()
    start_tag = "<satire_signal_aliases>"
    end_tag = "</satire_signal_aliases>"
    start = user_prompt.find(start_tag)
    end = user_prompt.find(end_tag, start + len(start_tag))
    if start < 0 or end < 0:
        return set()
    try:
        mapping = json.loads(user_prompt[start + len(start_tag):end])
    except (TypeError, ValueError):
        return set()
    if not isinstance(mapping, dict):
        return set()
    return {
        key for key, value in mapping.items()
        if isinstance(key, str) and key.strip()
        and isinstance(value, str) and value.strip()
    }


def _valid_small_decision(operation, raw, user_prompt=None):
    """Strict compact JSON contracts for bounded decision-only operations."""
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
    if operation == SATIRE_PROVENANCE_AUDIT_OPERATION:
        provenance = value.get("provenance")
        aliases = value.get("evidence_aliases", [])
        valid_provenance = {
            "DIRECT_SATIRE_PROVENANCE",
            "SATIRE_ORIGIN_ONLY",
            "CONFLICTING_PROVENANCE",
            "NOT_ESTABLISHED",
        }
        if provenance not in valid_provenance or not isinstance(aliases, list):
            return False
        if any(
            not isinstance(alias, str) or not alias.strip()
            for alias in aliases
        ) or len(set(aliases)) != len(aliases):
            return False
        if provenance != "DIRECT_SATIRE_PROVENANCE":
            return not aliases
        allowed_aliases = _satire_aliases_from_prompt(user_prompt)
        return bool(aliases) and set(aliases).issubset(allowed_aliases)
    if operation == STRUCTURED_MISLEADING_AUDIT_OPERATION:
        relationship = value.get("relationship")
        basis_kind = value.get("basis_kind", "NONE")
        if relationship not in {
            "MATERIAL_MISDESCRIPTION",
            "FABRICATED_CORE",
            "FULLY_SUPPORTED",
            "INSUFFICIENT_OR_CONFLICTING",
        }:
            return False
        if relationship == "MATERIAL_MISDESCRIPTION":
            return basis_kind in {"MISSING_CONTEXT", "PARTIAL_TRUTH", "FALSE_CONTEXT"}
        return basis_kind in {None, "NONE"}
    return False


def _valid_claim_gate(raw):
    """Validate the extraction and retrieval-query envelope before acceptance."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(value, dict) or set(value) != {
        "cleaned_claim", "search_query", "search_queries", "article_stance",
    }:
        return False
    claim = value["cleaned_claim"]
    query = value["search_query"]
    queries = value["search_queries"]
    if not isinstance(claim, str) or not claim.strip():
        return False
    if not isinstance(value["article_stance"], str) or value["article_stance"] not in {"DEBUNKING", "REPORTING", "NEUTRAL"}:
        return False
    if not isinstance(query, str) or not isinstance(queries, list):
        return False
    if claim in {"OUT_OF_SCOPE", "INSUFFICIENT_CONTEXT"}:
        return not queries and not query.strip()
    if not query.strip() or not 1 <= len(queries) <= 3:
        return False
    return (
        all(isinstance(q, str) and bool(q.strip()) for q in queries)
        and query == queries[0]
        and len(set(q.strip().casefold() for q in queries)) == len(queries)
    )


def validate_pilot_response(operation, raw, user_prompt):
    """A valid response must satisfy the exact operation-specific contract."""
    if operation == CLAIM_GATE_OPERATION:
        return _valid_claim_gate(raw)
    if operation in {
        EQUIVALENCE_OPERATION,
        RELEVANCE_OPERATION,
        SATIRE_PROVENANCE_AUDIT_OPERATION,
        STRUCTURED_MISLEADING_AUDIT_OPERATION,
    }:
        return _valid_small_decision(operation, raw, user_prompt)
    if operation == PILOT_OPERATION:
        return validate_persisted_evidence_evaluation(raw) is not None
    if operation in {GFC_EVALUATION_OPERATION, TAVILY_EVALUATION_OPERATION}:
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
        SATIRE_PROVENANCE_AUDIT_OPERATION,
        STRUCTURED_MISLEADING_AUDIT_OPERATION,
        CLAIM_GATE_OPERATION,
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
