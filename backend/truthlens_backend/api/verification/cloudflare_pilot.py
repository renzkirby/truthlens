"""Fail-closed enablement for an optional, development-only Cloudflare verdict pilot.

This module does not modify existing production Gemini/Groq routing. The
pilot is limited to the persisted-evidence evaluation stage, with the same
production prompt and evidence dossier.
"""
import os

from django.conf import settings

from .cloudflare_evaluation import (
    CloudflareEvaluationError,
    MAX_INPUT_CHARS,
    generate_evaluation_json,
)
from .provider_audit_metrics import validate_user_facing_evaluation


PILOT_FLAG = "ENABLE_CLOUDFLARE_VERIFICATION_PILOT"
PILOT_OPERATION = "persisted_evidence_evaluation"
PILOT_COMPLETION_TOKENS = 2048
# Exact adapter preflight maximum, not an advertised Cloudflare model limit.
PILOT_MAX_INPUT_CHARS = MAX_INPUT_CHARS


def cloudflare_pilot_enabled(operation):
    """A feature flag alone never enables the live verification pilot.

    An explicit development environment with DEBUG on is also required.
    No staging/production overrides are supported in this phase.
    """
    return (
        operation == PILOT_OPERATION
        and getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
        and os.getenv(PILOT_FLAG, "") == "1"
    )


def call_validated_cloudflare_pilot(system_instructions, user_prompt):
    """Return raw JSON only when it passes the *final* evaluation contract.

    The production evaluator remains responsible for canonical verdict and
    confidence normalization. Never return malformed provider content.
    """
    raw = generate_evaluation_json(
        system_instructions,
        user_prompt,
        max_completion_tokens=PILOT_COMPLETION_TOKENS,
    )
    if validate_user_facing_evaluation(raw) is None:
        raise CloudflareEvaluationError("INVALID_EVALUATION_JSON")
    return raw
