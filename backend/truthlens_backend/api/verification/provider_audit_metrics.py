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


def validate_user_facing_evaluation(raw_text):
    """Only five final-answer fields, not provider reasoning_content."""
    try:
        result = json.loads(raw_text)
    except (TypeError, ValueError):
        return None
    allowed = {"reasoning", "verdict", "summary", "confidence_score", "score_context"}
    if not isinstance(result, dict) or not allowed.issubset(result):
        return None
    if not all(
        isinstance(result.get(key), str) and result.get(key).strip()
        for key in ("reasoning", "summary", "score_context")
    ):
        return None
    if result.get("verdict") not in {
        "FACT", "FAKE", "MISLEADING", "UNVERIFIED", "SATIRE"
    }:
        return None
    score = result.get("confidence_score")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not 0 <= score <= 100
    ):
        return None
    # Existing production JSON validation remains the ultimate source of truth.
    return {key: result[key] for key in (
        "reasoning", "verdict", "summary", "confidence_score", "score_context"
    )}
