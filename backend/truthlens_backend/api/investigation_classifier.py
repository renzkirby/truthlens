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
from .verification_domain_policy import DOMAIN_CODES

logger = logging.getLogger(__name__)
CLASSIFIER_VERSION = "v2-subject-only"
MAX_CLAIM_LENGTH = 2400
MAX_DOMAINS = 3

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
    return sorted(codes)


def _query_classifier(text):
    from .services import call_llm_with_fallback

    system = (
        "Classify the subject matter of the user's factual claim, NOT its "
        "truthfulness, credibility, location, or jurisdiction. Return only "
        "JSON with decision CLASSIFY or ABSTAIN and domains as a list of "
        "{code, evidence} objects. Use only these subject codes: "
        + ", ".join(sorted(DOMAIN_CODES))
        + ". Evidence MUST quote exact words from the supplied claim text. "
        "Never infer subjects, add geographic authority, invent context, "
        "or classify without enough explicit subject evidence. "
        "When unsupported or ambiguous, return ABSTAIN."
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
        # Classification must correspond to the exact text evaluated. Late
        # provider responses may not classify a subsequently revised claim.
        current_text = (locked.context_text or "").strip()
        if hashlib.sha256(current_text.encode("utf-8")).hexdigest() != fingerprint:
            return "STALE_CONTEXT"
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
                "candidate_domains": accepted if accepted else [],
                "candidate_jurisdiction": "",
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
            claim=locked, domains=accepted, jurisdiction="",
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
                "domains": accepted,
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
