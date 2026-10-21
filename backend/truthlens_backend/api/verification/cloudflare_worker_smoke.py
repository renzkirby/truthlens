"""Single-shot, development-only Cloudflare worker smoke.

A fixed, approved public-source dossier only. No user data, database access,
provider fallback, retries, or raw response text in returned task metadata.
"""
import logging
import os
import time

from django.conf import settings
from django.core.exceptions import ValidationError

from .cloudflare_evaluation import (
    ACCOUNT_ID_PATTERN,
    CloudflareEvaluationError,
    generate_evaluation_json,
    sanitized_cloudflare_error_code,
)
from .cloudflare_pilot import PILOT_COMPLETION_TOKENS, cloudflare_pilot_enabled
from .provider_audit_metrics import validate_user_facing_evaluation
from .realworld_benchmark import load_corpus, reviewed_gold_verdict

logger = logging.getLogger(__name__)

FIXED_CASE_ID = "civics__support"


def run_cloudflare_worker_smoke():
    """One invocation = zero or one outbound Cloudflare chat request."""
    if not (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
    ):
        return {"status": "blocked", "reason": "DEVELOPMENT_ONLY"}

    worker_pid = os.getpid()
    pilot_enabled = cloudflare_pilot_enabled("persisted_evidence_evaluation")
    account_id_valid = bool(ACCOUNT_ID_PATTERN.fullmatch(
        os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    ))
    api_token_present = bool(os.getenv("CLOUDFLARE_API_TOKEN", "").strip())
    base = {
        "worker_pid": worker_pid,
        "provider": "cloudflare",
        "case_id": FIXED_CASE_ID,
        "pilot_enabled": pilot_enabled,
        "account_id_valid": account_id_valid,
        "api_token_present": api_token_present,
        "requests_attempted": 0,
        "elapsed_ms": 0,
    }
    if not pilot_enabled:
        return {**base, "status": "blocked", "reason": "PILOT_DISABLED"}
    if not account_id_valid:
        return {
            **base, "status": "blocked",
            "reason": "MISSING_OR_INVALID_ACCOUNT_ID",
        }
    if not api_token_present:
        return {**base, "status": "blocked", "reason": "MISSING_API_TOKEN"}

    try:
        case = next(c for c in load_corpus() if c["id"] == FIXED_CASE_ID)
        expected = reviewed_gold_verdict(case)
        if expected is None or case["public_only"] is not True:
            return {**base, "status": "blocked", "reason": "CASE_NOT_APPROVED"}
        from api.services import build_persisted_evidence_prompt
        system_prompt, user_prompt = build_persisted_evidence_prompt(
            case["claim"], case["evidence_snapshot"], "NEUTRAL",
        )
        if len(system_prompt) + len(user_prompt) > 28000:
            return {**base, "status": "blocked", "reason": "PROMPT_TOO_LONG"}
    except (ValidationError, ValueError, TypeError, LookupError, StopIteration):
        return {**base, "status": "blocked", "reason": "INVALID_REVIEWED_CASE"}

    started = time.perf_counter()
    # Exactly one provider invocation. Never use call_llm_with_fallback().
    try:
        raw = generate_evaluation_json(
            system_prompt, user_prompt,
            max_completion_tokens=PILOT_COMPLETION_TOKENS,
        )
        result = validate_user_facing_evaluation(raw)
        if result is None:
            raise CloudflareEvaluationError("INVALID_EVALUATION_JSON")
    except CloudflareEvaluationError as exc:
        elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
        safe_code = sanitized_cloudflare_error_code(exc)
        logger.info("CLOUDFLARE_WORKER_SMOKE outcome=failed code=%s elapsed_ms=%s",
                    safe_code, elapsed_ms)
        return {
            **base, "requests_attempted": 1, "elapsed_ms": elapsed_ms,
            "status": "failed", "reason": safe_code,
        }
    except Exception:
        elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
        # Explicitly do not emit exception repr or provider response bodies.
        logger.info("CLOUDFLARE_WORKER_SMOKE outcome=failed code=OTHER_SMOKE_FAILURE "
                    "elapsed_ms=%s", elapsed_ms)
        return {
            **base, "requests_attempted": 1, "elapsed_ms": elapsed_ms,
            "status": "failed", "reason": "OTHER_SMOKE_FAILURE",
        }

    elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
    verdict = result["verdict"]
    logger.info("CLOUDFLARE_WORKER_SMOKE outcome=success elapsed_ms=%s", elapsed_ms)
    return {
        **base,
        "requests_attempted": 1,
        "elapsed_ms": elapsed_ms,
        "status": "success",
        "expected_verdict": expected,
        "actual_verdict": verdict,
        "matches_approved_label": verdict == expected,
        "confidence_score": result["confidence_score"],
        "contract_valid": True,
    }
