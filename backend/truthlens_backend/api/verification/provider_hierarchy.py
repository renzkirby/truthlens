"""Provider-routing policy for legacy pilots and the universal hierarchy.\n\nUniversal routing auto-activates when valid Cloudflare credentials are deployed,\nunless the explicit kill switch is set to 0. No network access occurs here.\n"""
import os

from django.conf import settings

from .cloudflare_pilot import (
    ASSESSMENT_OPERATION,
    PILOT_OPERATION,
    SATIRE_PROVENANCE_AUDIT_OPERATION,
    STRUCTURED_MISLEADING_AUDIT_OPERATION,
)
from .classification_contract import CLASSIFICATION_OPERATION


HIERARCHY_FLAG = "ENABLE_AI_RQ2_PROVIDER_HIERARCHY"
UNIVERSAL_HIERARCHY_FLAG = "ENABLE_UNIVERSAL_LLM_HIERARCHY"
RELIABILITY_HARDENING_FLAG = "ENABLE_PROVIDER_RELIABILITY_HARDENING"
GROQ_BOUNDED_FALLBACK_FLAG = "ENABLE_GROQ_BOUNDED_FALLBACK"
GEMINI_TRANSIENT_CIRCUIT_BREAKER_FLAG = "ENABLE_GEMINI_TRANSIENT_CIRCUIT_BREAKER"
STAGE_CONTRACT_OPERATIONS = frozenset({
    ASSESSMENT_OPERATION,
    PILOT_OPERATION,
    CLASSIFICATION_OPERATION,
    "claim_equivalence",
    "fact_check_relevance",
    "claim_gate",
    "gfc_evaluation",
    "tavily_evaluation",
    SATIRE_PROVENANCE_AUDIT_OPERATION,
    STRUCTURED_MISLEADING_AUDIT_OPERATION,
})
# These indicate the project/model cannot currently accept this request.
# Do not repeatedly retry them within a single verification job.
GEMINI_JOB_BLOCKING_CODES = frozenset({402, 404, 429})


def universal_hierarchy_enabled():
    """Enable universal routing automatically when Cloudflare is configured.

    An explicit "0" is the emergency kill switch. An explicit "1" still
    forces the hierarchy on for controlled diagnostics. When the flag is
    unset, valid deployed Cloudflare credentials activate the hierarchy.
    """
    configured = os.getenv(UNIVERSAL_HIERARCHY_FLAG)
    if configured == "0":
        return False
    if configured == "1":
        return True

    from .cloudflare_evaluation import cloudflare_credentials_configured
    return cloudflare_credentials_configured()


def hierarchy_enabled():
    """Explicit opt-in universal routing, preserving the legacy development pilot."""
    if universal_hierarchy_enabled():
        return True
    return (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
        and os.getenv(HIERARCHY_FLAG, "") == "1"
    )


def reliability_hardening_enabled():
    """Defense-period reliability patch master switch; off unless explicitly enabled."""
    return os.getenv(RELIABILITY_HARDENING_FLAG, "") == "1"


def _reliability_subfeature_enabled(name):
    if not reliability_hardening_enabled():
        return False
    configured = os.getenv(name)
    if configured == "0":
        return False
    return True


def groq_bounded_fallback_enabled():
    """Use a deterministic bounded persisted-evidence prompt only on fallback."""
    return _reliability_subfeature_enabled(GROQ_BOUNDED_FALLBACK_FLAG)


def gemini_transient_circuit_breaker_enabled():
    """Suppress repeat 5xx Gemini calls within one scoped verification job."""
    return _reliability_subfeature_enabled(GEMINI_TRANSIENT_CIRCUIT_BREAKER_FLAG)


def requires_strict_stage_contract(operation, *, pilot_active, hierarchy_active):
    """Use source-stage response contracts even when Cloudflare is bypassed."""
    return (
        pilot_active
        or (hierarchy_active and operation in STAGE_CONTRACT_OPERATIONS)
    )


def gemini_job_blocking_error(error):
    """Classify billing/model/quota rejection without logging remote error bodies."""
    code = getattr(error, "code", None)
    return type(code) is int and code in GEMINI_JOB_BLOCKING_CODES
