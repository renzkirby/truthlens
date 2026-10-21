"""Opt-in development routing policy for the AI-RQ-2 verification pilot.

Legacy provider order stays unchanged until a separate deployment decision.
No network access or prompt manipulation occurs in this policy module.
"""
import os

from django.conf import settings

from .cloudflare_pilot import (
    ASSESSMENT_OPERATION,
    PILOT_OPERATION,
)


HIERARCHY_FLAG = "ENABLE_AI_RQ2_PROVIDER_HIERARCHY"
STAGE_CONTRACT_OPERATIONS = frozenset({
    ASSESSMENT_OPERATION,
    PILOT_OPERATION,
})
# These indicate the user's account cannot currently accept this request.
# Do not repeatedly retry them within a single verification job.
GEMINI_JOB_BLOCKING_CODES = frozenset({402, 429})


def hierarchy_enabled():
    """Explicit opt-in; stage and production never activate the pilot."""
    return (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
        and os.getenv(HIERARCHY_FLAG, "") == "1"
    )


def requires_strict_stage_contract(operation, *, pilot_active, hierarchy_active):
    """Use source-stage response contracts even when Cloudflare is bypassed."""
    return (
        pilot_active
        or (hierarchy_active and operation in STAGE_CONTRACT_OPERATIONS)
    )


def gemini_job_blocking_error(error):
    """Classify quota/billing rejection without logging remote error bodies."""
    code = getattr(error, "code", None)
    return type(code) is int and code in GEMINI_JOB_BLOCKING_CODES
