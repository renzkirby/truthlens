"""Sanitized accounting metadata only; no prompts, output text, or hidden reasoning."""
import json


KNOWN_FINISH = frozenset({"stop", "length", "tool_calls", "content_filter"})


def safe_int(value):
    if type(value) is int and 0 <= value <= 10000000:
        return value
    return None


def safe_completion_metadata(choice, usage):
    """Preserve numeric provider-reported usage without inventing token estimates."""
    if not isinstance(choice, dict):
        choice = {}
    if not isinstance(usage, dict):
        usage = {}
    details = usage.get("completion_tokens_details")
    if not isinstance(details, dict):
        details = {}
    finish = choice.get("finish_reason")
    return {
        "finish_reason": finish if finish in KNOWN_FINISH else "other",
        "prompt_tokens": safe_int(usage.get("prompt_tokens")),
        "completion_tokens": safe_int(usage.get("completion_tokens")),
        "total_tokens": safe_int(usage.get("total_tokens")),
        "reasoning_tokens": safe_int(details.get("reasoning_tokens")),
        "reasoning_present": bool(
            isinstance(choice.get("message"), dict) and (
                choice["message"].get("reasoning_content")
                or choice["message"].get("reasoning")
            )
        ),
    }


_BASE_EVALUATION_FIELDS = frozenset({
    "reasoning", "verdict", "summary", "confidence_score", "score_context",
})
_CONTEXTUAL_EVALUATION_FIELDS = frozenset({
    "contextual_basis_kind", "contextual_basis_evidence_ids",
})
_CONTEXTUAL_BASIS_KINDS = frozenset({
    "NONE",
    "MISSING_CONTEXT",
    "PARTIAL_TRUTH",
    "FALSE_CONTEXT",
    "SATIRE_PROVENANCE",
    "SATIRE_ORIGIN_OF_MISINFORMATION",
})


def _valid_base_evaluation(result):
    if not isinstance(result, dict):
        return False
    if not all(
        isinstance(result.get(key), str) and result.get(key).strip()
        for key in ("reasoning", "summary", "score_context")
    ):
        return False
    if result.get("verdict") not in {
        "FACT", "FAKE", "MISLEADING", "UNVERIFIED", "SATIRE"
    }:
        return False
    score = result.get("confidence_score")
    return not (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not 0 <= score <= 100
    )


def validate_user_facing_evaluation(raw_text):
    """Validate the legacy five-field final-answer contract."""
    try:
        result = json.loads(raw_text)
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(result, dict)
        or set(result) != _BASE_EVALUATION_FIELDS
        or not _valid_base_evaluation(result)
    ):
        return None
    return {key: result[key] for key in _BASE_EVALUATION_FIELDS}


def validate_persisted_evidence_evaluation(raw_text):
    """Accept legacy or contextual persisted-evidence evaluation responses.

    Contextual basis metadata is confidence-only. A legacy five-field response
    remains valid so missing metadata cannot force provider failover and thereby
    alter verdict authority.
    """
    try:
        result = json.loads(raw_text)
    except (TypeError, ValueError):
        return None
    if not isinstance(result, dict):
        return None

    fields = set(result)
    allowed_shapes = {
        frozenset(_BASE_EVALUATION_FIELDS),
        frozenset(_BASE_EVALUATION_FIELDS | _CONTEXTUAL_EVALUATION_FIELDS),
    }
    if frozenset(fields) not in allowed_shapes or not _valid_base_evaluation(result):
        return None

    if fields == set(_BASE_EVALUATION_FIELDS):
        return result

    basis_kind = result.get("contextual_basis_kind")
    basis_ids = result.get("contextual_basis_evidence_ids")
    if (
        basis_kind not in _CONTEXTUAL_BASIS_KINDS
        or not isinstance(basis_ids, list)
        or len(basis_ids) > 128
        or any(
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value) > 128
            for value in basis_ids
        )
        or len(set(basis_ids)) != len(basis_ids)
    ):
        return None
    return result
