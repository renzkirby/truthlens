"""Opt-in asynchronous automatic investigation classification.

Deliberately separate from fact checking: no verdict, credibility score, or
publication authority is read or modified here.

Modes:
  off (default) — no provider calls.
  shadow — proposals are stored but never made claimable.
  enforce — store eligible classification only after offline accuracy validation.
"""
import hashlib
import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    AccountabilityEvent,
    Claim,
    ClaimInvestigationClassification,
    InvestigationClassificationAssessment,
    VerificationAssignment,
)
from .accountability_service import record_accountability_event
from .verification_domain_policy import DOMAIN_CODES, validate_jurisdiction

logger = logging.getLogger(__name__)
CLASSIFIER_VERSION = "v1"
MAX_CLAIM_LENGTH = 2400
MAX_DOMAINS = 3

# Only explicitly named localities are automatically geocoded at this stage.
# Unrecognized, conflicting, or ambiguous references must abstain.
JURISDICTION_TERMS = {
    "PH": ("philippines", "philippine", "luzon", "visayas", "mindanao"),
    "PH-NCR": ("metro manila", "national capital region", "taguig", "makati"),
    "US": ("united states", "u.s.", "usa"),
    "GLOBAL": ("worldwide", "globally", "every country", "across the world"),
}


def classification_mode():
    mode = str(getattr(settings, "INVESTIGATION_CLASSIFICATION_MODE", "off")).lower()
    return mode if mode in {"off", "shadow", "enforce"} else "off"


def _evidence_in_text(text, evidence):
    return (
        isinstance(evidence, str)
        and len(evidence.strip()) >= 4
        and evidence.strip().casefold() in text.casefold()
    )


def validate_model_suggestion(text, payload):
    """Apply deterministic structural + quoted-source evidence checks.

    This is not a substitute for empirical accuracy evaluation.
    """
    if not isinstance(payload, dict) or payload.get("decision") != "CLASSIFY":
        return None
    tags = payload.get("domains")
    if not isinstance(tags, list) or not (1 <= len(tags) <= MAX_DOMAINS):
        return None
    codes = []
    for tag in tags:
        if (
            not isinstance(tag, dict)
            or tag.get("code") not in DOMAIN_CODES
            or not _evidence_in_text(text, tag.get("evidence"))
        ):
            return None
        codes.append(tag["code"])
    if len(set(codes)) != len(codes):
        return None
    jurisdiction = payload.get("jurisdiction")
    if not isinstance(jurisdiction, str):
        return None
    try:
        validate_jurisdiction(jurisdiction)
    except Exception:
        return None
    geo_evidence = payload.get("jurisdiction_evidence")
    if not _evidence_in_text(text, geo_evidence):
        return None
    # Extra guard against a model mapping geographic evidence to an
    # unrelated jurisdiction. Unknown countries/subdivisions abstain.
    terms = JURISDICTION_TERMS.get(jurisdiction)
    if not terms or not any(term in str(geo_evidence).casefold() for term in terms):
        return None
    return sorted(codes), jurisdiction


def _query_classifier(text):
    from .services import call_llm_with_fallback

    system = (
        "You classify the subjects and explicitly stated geographic scope of "
        "a factual claim. You DO NOT determine truthfulness. Return only JSON: "
        "{decision: CLASSIFY or ABSTAIN, domains: [{code, evidence}], "
        "jurisdiction: an ISO-style code or GLOBAL, jurisdiction_evidence: "
        "exact quotation from claim}. Use only these subject codes: "
        + ", ".join(sorted(DOMAIN_CODES))
        + ". Each domain evidence and jurisdiction evidence MUST quote exact "
        "words from the claim; never infer the user's location or assume GLOBAL. "
        "If uncertain, context insufficient, mixed jurisdictions, image-only "
        "content, or scope ambiguous, return ABSTAIN."
    )
    return json.loads(call_llm_with_fallback(
        system, text, operation="investigation_classification"
    ))


def classify_investigation_claim(claim_id):
    """Called by a background job; never block creation of community threads."""
    mode = classification_mode()
    if mode == "off":
        return "DISABLED"
    try:
        claim = Claim.objects.get(pk=claim_id)
    except Claim.DoesNotExist:
        return "MISSING"
    if ClaimInvestigationClassification.objects.filter(claim=claim).exists():
        return "ALREADY_CLASSIFIED"

    text = (claim.context_text or "").strip()
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    accepted = None
    reason = "INSUFFICIENT_TEXT"
    if claim.claim_type == Claim.ClaimType.TEXT and 20 <= len(text) <= MAX_CLAIM_LENGTH:
        try:
            accepted = validate_model_suggestion(text, _query_classifier(text))
            reason = "STRUCTURE_OR_EVIDENCE_UNSUPPORTED" if not accepted else ""
        except Exception:
            reason = "PROVIDER_UNAVAILABLE"
            logger.warning("Investigation classification provider unavailable for claim %s", claim_id)

    with transaction.atomic():
        locked = Claim.objects.select_for_update().get(pk=claim_id)
        # Once work has been claimed or concluded, late jobs cannot alter
        # the assignment's governing classification.
        if VerificationAssignment.objects.filter(
            claim=locked,
            status__in=[
                VerificationAssignment.Status.ACTIVE,
                VerificationAssignment.Status.COMPLETED,
            ],
        ).exists() or ClaimInvestigationClassification.objects.filter(claim=locked).exists():
            return "NO_LONGER_ELIGIBLE"
        status = (
            InvestigationClassificationAssessment.Status.FAILED
            if reason == "PROVIDER_UNAVAILABLE"
            else (
                InvestigationClassificationAssessment.Status.ABSTAINED
                if not accepted else (
                    InvestigationClassificationAssessment.Status.APPLIED
                    if mode == "enforce"
                    else InvestigationClassificationAssessment.Status.SUGGESTED
                )
            )
        )
        InvestigationClassificationAssessment.objects.update_or_create(
            claim=locked,
            defaults={
                "status": status,
                "candidate_domains": accepted[0] if accepted else [],
                "candidate_jurisdiction": accepted[1] if accepted else "",
                "reason_code": reason,
                "classifier_version": CLASSIFIER_VERSION,
                "input_fingerprint": fingerprint,
                "assessed_at": timezone.now(),
            },
        )
        if not accepted or mode != "enforce":
            return status
        # Only enable 'enforce' after validating actual classification
        # reliability against an independently labeled evaluation dataset.
        classification = ClaimInvestigationClassification(
            claim=locked, domains=accepted[0], jurisdiction=accepted[1],
            rationale="Automated classification from explicit claim quotation.",
            source=ClaimInvestigationClassification.Source.AUTOMATIC,
        )
        classification.full_clean()
        classification.save()
        record_accountability_event(
            action_type=AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
            resource_type=AccountabilityEvent.ResourceType.CLAIM,
            resource_id=locked.pk,
            authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
            previous_state={},
            new_state={
                "domains": accepted[0], "jurisdiction": accepted[1],
                "source": "AUTOMATIC", "classifier_version": CLASSIFIER_VERSION,
            },
        )
        return "APPLIED"


def dispatch_classification_task(claim_id):
    """Never undo committed threads when Celery's queue is unavailable."""
    if classification_mode() == "off":
        return False
    from .tasks import classify_investigation_claim_task
    try:
        classify_investigation_claim_task.delay(str(claim_id))
        return True
    except Exception:
        logger.exception("Could not queue investigation classification for claim %s", claim_id)
        return False
