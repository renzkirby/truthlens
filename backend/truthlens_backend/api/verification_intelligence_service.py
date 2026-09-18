"""Deterministic workspace context over persisted facts; no intelligence generation."""

from django.db.models import Q

from .adjudication_provenance import get_adjudication_decision_provenance
from .knowledge_reuse_service import (
    build_published_fact_check_payload,
    get_published_fact_check_resolution_for_claim,
    get_related_published_fact_check_payloads,
)
from .models import (
    AdjudicationDecision,
    EvidenceSubmission,
    ModerationCase,
    VerificationAssignment,
    VerificationEvidence,
    VerificationRun,
)
from .moderation_service import ACTIVE_CASE_STATUSES
from .organization_service import PartnerCapability, has_capability


WORKLOAD_CAPABILITIES = frozenset({
    PartnerCapability.CLAIM_VERIFICATION_WORK,
    PartnerCapability.REVIEW_EVIDENCE,
    PartnerCapability.ADJUDICATE,
    PartnerCapability.CREATE_FACT_CHECK_DRAFT,
    PartnerCapability.PUBLISH_FACT_CHECK,
    PartnerCapability.MANAGE_ORGANIZATION,
})

AUTHORITY_CONTRACT = {
    "automated_analysis": "NON_AUTHORITATIVE",
    "automated_evidence": "CONTEXT_ONLY",
    "human_evidence": "REVIEWED_INPUT_NOT_FINAL_JUDGMENT",
    "adjudication_decision": "AUTHORITATIVE_HUMAN_JUDGMENT",
    "authoritative_publication": "DURABLE_INSTITUTIONAL_KNOWLEDGE",
    "related_publications": "CONTEXT_ONLY_NO_VERDICT_TRANSFER",
}


class VerificationIntelligenceError(Exception):
    pass


class VerificationIntelligenceAuthorizationError(VerificationIntelligenceError):
    pass


class VerificationIntelligenceNotFound(VerificationIntelligenceError):
    pass


def _timestamp(value):
    return value.isoformat() if value is not None else None


def _user(user):
    return {"id": user.pk, "username": user.username} if user is not None else None


def _fields(record, names):
    """Explicit allowlists keep private model fields out of the projection."""
    return {name: getattr(record, name) for name in names}


def _current_decision(claim, organization):
    # Mirror adjudication workspace visibility before classifying provenance.
    decision = (
        AdjudicationDecision.objects.filter(
            claim=claim, organization=organization, is_current=True,
        )
        .filter(Q(moderation_case__isnull=True) | Q(
            moderation_case__organization=organization,
        ))
        .select_related("moderation_case", "decided_by")
        .order_by("-decided_at", "id")
        .first()
    )
    if decision is None:
        return None
    provenance = get_adjudication_decision_provenance(claim, decision)
    if not provenance["is_attributable"]:
        return None
    return {
        "id": str(decision.pk),
        **_fields(decision, (
            "verdict", "canonical_claim", "rationale", "revision_number",
        )),
        "decided_at": _timestamp(decision.decided_at),
        "decided_by": _user(decision.decided_by),
        "organization_id": str(decision.organization_id),
        "verification_run_id": (
            str(decision.verification_run_id) if decision.verification_run_id else None
        ),
        "provenance": {key: provenance[key] for key in ("status", "is_attributable")},
    }


def get_verification_intelligence_context(*, actor, organization, claim_id):
    """Read only ACTIVE organization work, without providers or accounting writes."""
    if not any(
        has_capability(actor, capability, organization=organization)
        for capability in sorted(WORKLOAD_CAPABILITIES)
    ):
        raise VerificationIntelligenceAuthorizationError(
            "You do not have permission to view verification work for this organization."
        )

    assignment = (
        VerificationAssignment.objects.filter(
            claim_id=claim_id, organization=organization,
            status=VerificationAssignment.Status.ACTIVE,
        )
        .select_related("claim", "claimed_by")
        .order_by("-created_at", "id")
        .first()
    )
    if assignment is None:
        raise VerificationIntelligenceNotFound("Active verification work not found.")
    claim = assignment.claim
    case = (
        ModerationCase.objects.filter(
            claim=claim, organization=organization,
            case_type=ModerationCase.CaseType.ADJUDICATION,
            factual_correction_request__isnull=True,
        ).order_by("-created_at", "id").first()
    )
    run = VerificationRun.objects.filter(claim=claim).order_by(
        "-created_at", "id",
    ).first()
    automated_evidence = []
    if run is not None:
        for item in VerificationEvidence.objects.filter(
            verification_run=run,
        ).select_related("evidence_source").order_by("-created_at", "id"):
            source = item.evidence_source
            automated_evidence.append({
                "id": str(item.pk),
                **_fields(item, (
                    "evidence_role", "stance", "relevance_score",
                    "directness_score", "recency_score",
                )),
                "created_at": _timestamp(item.created_at),
                "source": {
                    "id": str(source.pk),
                    **_fields(source, (
                        "provider", "title", "publisher", "source_type",
                        "url", "canonical_url",
                    )),
                    "published_at": _timestamp(source.published_at),
                    "retrieved_at": _timestamp(source.retrieved_at),
                },
            })

    evidence = list(EvidenceSubmission.objects.filter(
        thread__claim=claim,
    ).select_related("contributor", "verified_by").order_by("submitted_at", "id"))
    counts = {
        "total": len(evidence),
        "verified": sum(item.evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED
                        for item in evidence),
        "rejected": sum(item.evidence_status == EvidenceSubmission.EvidenceStatus.REJECTED
                        for item in evidence),
        "unreviewed": sum(item.evidence_status == EvidenceSubmission.EvidenceStatus.UNVERIFIED
                          for item in evidence),
        # Same claim-wide current evidence count as the adjudication workspace.
        "active_evidence_cases": ModerationCase.objects.filter(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission__thread__claim=claim,
            status__in=ACTIVE_CASE_STATUSES,
        ).count(),
    }
    decision = _current_decision(claim, organization)
    resolution = build_published_fact_check_payload(
        get_published_fact_check_resolution_for_claim(claim)
    )
    limitations = []
    if run is None:
        limitations.append({"code": "NO_VERIFICATION_RUN",
                            "detail": "No persisted verification run exists."})
    elif run.status != VerificationRun.Status.COMPLETED:
        limitations.append({"code": "LATEST_RUN_NOT_COMPLETED",
                            "detail": "The latest persisted verification run is not completed."})
    if decision is None:
        limitations.append({"code": "NO_CURRENT_ADJUDICATION",
                            "detail": "No current attributable adjudication is visible in this organization."})
    if resolution is None:
        limitations.append({"code": "NO_AUTHORITATIVE_PUBLICATION",
                            "detail": "No durable authoritative published resolution exists."})

    return {
        "schema_version": "1.0",
        "claim": {
            "id": str(claim.pk),
            **_fields(claim, (
                "claim_type", "context_text", "url_link", "source_link", "media_url",
            )),
            "last_updated": _timestamp(claim.last_updated),
        },
        "workflow": {
            "assignment": {
                "id": str(assignment.pk), "status": assignment.status,
                "claimed_at": _timestamp(assignment.claimed_at),
                "claimed_by": _user(assignment.claimed_by),
            },
            "adjudication_case": {
                "id": str(case.pk), "status": case.status, "priority": case.priority,
                "created_at": _timestamp(case.created_at),
                "updated_at": _timestamp(case.updated_at),
            } if case is not None else None,
        },
        "automated_analysis": {
            "authority": AUTHORITY_CONTRACT["automated_analysis"],
            "claim_snapshot": {
                "basis": "CLAIM_CACHED_AUTOMATED_ANALYSIS",
                **_fields(claim, (
                    "ai_verdict", "ai_summary", "ai_reasoning", "consensus_score",
                    "score_context", "source_type", "is_ai_generated",
                )),
                "last_updated": _timestamp(claim.last_updated),
            },
            "latest_run": {
                "id": str(run.pk),
                **_fields(run, ("status", "pipeline_version", "failure_stage", "failure_code")),
                "started_at": _timestamp(run.started_at),
                "completed_at": _timestamp(run.completed_at),
                "created_at": _timestamp(run.created_at),
            } if run is not None else None,
            "evidence": {
                "authority": AUTHORITY_CONTRACT["automated_evidence"],
                "basis": "LATEST_VERIFICATION_RUN",
                "verification_run_id": str(run.pk) if run is not None else None,
                "count": len(automated_evidence), "items": automated_evidence,
            },
        },
        "human_evidence": {
            "authority": AUTHORITY_CONTRACT["human_evidence"],
            "basis": "CURRENT_EVIDENCE_RECORDS", "counts": counts,
            "items": [{
                "id": str(item.pk), "thread_id": str(item.thread_id),
                **_fields(item, (
                    "evidence_caption", "evidence_url", "evidence_type",
                    "evidence_status", "moderator_notes", "rejection_reason",
                )),
                "submitted_at": _timestamp(item.submitted_at),
                "reviewed_at": _timestamp(item.verified_at),
                "contributor": _user(item.contributor),
                "reviewed_by": _user(item.verified_by),
            } for item in evidence],
        },
        "adjudication": {
            "authority": AUTHORITY_CONTRACT["adjudication_decision"],
            "current_decision": decision,
        },
        "institutional_knowledge": {
            "authoritative_resolution": resolution,
            "related_publications": get_related_published_fact_check_payloads(claim, limit=3),
        },
        "authority_contract": dict(AUTHORITY_CONTRACT),
        "limitations": limitations,
    }
