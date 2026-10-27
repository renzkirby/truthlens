"""Read-only investigation-centered workflow projection for the Verification Workspace."""

from .adjudication_provenance import get_adjudication_decision_provenance
from .adjudication_service import get_adjudication_case_detail
from .models import (
    AdjudicationDecision,
    EvidenceReviewDecision,
    EvidenceSubmission,
    ModerationCase,
    OfficialFactCheck,
    Thread,
    VerificationAssignment,
)
from .moderation_service import ACTIVE_CASE_STATUSES
from .organization_service import PartnerCapability, has_capability
from .publication_workflow_query_service import (
    RESOURCE_ELIGIBLE_CLAIM,
    RESOURCE_FACT_CHECK,
    PublicationWorkflowAuthorizationError,
    PublicationWorkflowNotFound,
    get_publication_work_item_detail,
)


WORKSPACE_VIEW_CAPABILITIES = frozenset(
    {
        PartnerCapability.CLAIM_VERIFICATION_WORK,
        PartnerCapability.REVIEW_EVIDENCE,
        PartnerCapability.ADJUDICATE,
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        PartnerCapability.PUBLISH_FACT_CHECK,
        }
)


class InvestigationWorkspaceError(Exception):
    pass


class InvestigationWorkspaceAuthorizationError(InvestigationWorkspaceError):
    pass


class InvestigationWorkspaceNotFound(InvestigationWorkspaceError):
    pass


def _timestamp(value):
    return value.isoformat() if value is not None else None


def _user_payload(user):
    if user is None:
        return None
    return {
        "id": user.pk,
        "username": user.username,
    }


def _organization_payload(organization):
    return {
        "id": str(organization.pk),
        "name": organization.name,
        "slug": organization.slug,
    }


def _claim_payload(claim):
    community_threads = [
        {
            "id": str(thread.pk),
            "claim_id": str(thread.claim_id),
            "caption": thread.caption,
            "status": thread.status,
            "created_at": _timestamp(thread.created_at),
        }
        for thread in Thread.objects.filter(claim=claim)
        .only("id", "claim_id", "caption", "status", "created_at")
        .order_by("-created_at", "id")
    ]

    return {
        "id": str(claim.pk),
        "claim_type": claim.claim_type,
        "context_text": claim.context_text,
        "url_link": claim.url_link,
        "source_link": claim.source_link,
        "media_url": claim.media_url,
        "last_updated": _timestamp(claim.last_updated),
        "community_threads": community_threads,
    }


def _has_any_workspace_capability(actor, organization):
    return any(
        has_capability(actor, capability, organization=organization)
        for capability in WORKSPACE_VIEW_CAPABILITIES
    )


def _current_attributable_decision(claim, organization):
    decision = (
        AdjudicationDecision.objects.filter(
            claim=claim,
            organization=organization,
            is_current=True,
        )
        .select_related(
            "decided_by",
            "moderation_case",
            "moderation_case__organization",
            "organization",
        )
        .order_by("-revision_number", "-decided_at", "id")
        .first()
    )
    if decision is None:
        return None

    provenance = get_adjudication_decision_provenance(claim, decision)
    if not provenance["is_attributable"]:
        return None

    return decision


def _decision_payload(decision):
    if decision is None:
        return None
    return {
        "id": str(decision.pk),
        "revision_number": decision.revision_number,
        "verdict": decision.verdict,
        "canonical_claim": decision.canonical_claim,
        "decided_at": _timestamp(decision.decided_at),
        "decided_by": _user_payload(decision.decided_by),
    }


def _evidence_context(claim, organization):
    evidence = list(
        EvidenceSubmission.objects.filter(thread__claim=claim)
        .select_related("verified_by")
        .only(
            "id",
            "evidence_status",
            "verified_at",
            "verified_by_id",
            "verified_by__id",
            "verified_by__username",
        )
        .order_by("submitted_at", "id")
    )
    organization_review_basis = {}
    for review_decision in (
        EvidenceReviewDecision.objects.filter(
            evidence_submission__thread__claim=claim,
            organization=organization,
        )
        .order_by("evidence_submission_id", "-reviewed_at", "-id")
        .values("evidence_submission_id", "disposition")
    ):
        organization_review_basis.setdefault(
            review_decision["evidence_submission_id"],
            review_decision["disposition"],
        )
    active_cases = list(
        ModerationCase.objects.filter(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission__thread__claim=claim,
            organization=organization,
            status__in=ACTIVE_CASE_STATUSES,
        )
        .only("id", "status", "priority", "created_at")
        .order_by("created_at", "id")
    )

    return {
        "summary": {
            "total": len(evidence),
            "verified": sum(
                item.evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED
                for item in evidence
            ),
            "rejected": sum(
                item.evidence_status == EvidenceSubmission.EvidenceStatus.REJECTED
                for item in evidence
            ),
            "unreviewed": sum(
                item.evidence_status == EvidenceSubmission.EvidenceStatus.UNVERIFIED
                for item in evidence
            ),
            "inherited_review_pending": sum(
                item.evidence_status != EvidenceSubmission.EvidenceStatus.UNVERIFIED
                and organization_review_basis.get(item.pk) != item.evidence_status
                for item in evidence
            ),
            "active_case_count": len(active_cases),
        },
        "active_case_id": str(active_cases[0].pk) if active_cases else None,
    }


def _adjudication_context(*, actor, organization, claim):
    case = (
        ModerationCase.objects.filter(
            claim=claim,
            organization=organization,
            case_type=ModerationCase.CaseType.ADJUDICATION,
            factual_correction_request__isnull=True,
        )
        .only("id", "status", "priority", "created_at", "updated_at")
        .order_by("-created_at", "id")
        .first()
    )
    if case is None:
        return {
            "case": None,
            "actor_action_state": None,
        }

    action_state = None
    if has_capability(
        actor,
        PartnerCapability.ADJUDICATE,
        organization=organization,
    ):
        detail = get_adjudication_case_detail(
            actor=actor,
            organization=organization,
            case_id=case.pk,
        )
        action_state = detail.adjudication_action_state

    return {
        "case": {
            "id": str(case.pk),
            "status": case.status,
            "priority": case.priority,
            "created_at": _timestamp(case.created_at),
            "updated_at": _timestamp(case.updated_at),
        },
        "actor_action_state": action_state,
    }


def _active_initial_fact_check(claim, organization):
    return (
        OfficialFactCheck.initial_workflow_queryset()
        .filter(
            claim=claim,
            organization=organization,
            publication_status__in={
                OfficialFactCheck.PublicationStatus.DRAFT,
                OfficialFactCheck.PublicationStatus.IN_REVIEW,
            },
        )
        .select_related(
            "adjudication_decision",
            "adjudication_decision__decided_by",
            "adjudication_decision__evidence_snapshot",
            "supersedes",
        )
        .prefetch_related("source_items", "source_items__evidence_links")
        .order_by("-updated_at", "id")
        .first()
    )


def _publication_context(*, actor, organization, claim, decision):
    fact_check = _active_initial_fact_check(claim, organization)
    can_view_publication_work = any(
        has_capability(actor, capability, organization=organization)
        for capability in (
            PartnerCapability.CREATE_FACT_CHECK_DRAFT,
            PartnerCapability.PUBLISH_FACT_CHECK,
        )
    )

    detail = None
    if can_view_publication_work:
        try:
            if fact_check is not None:
                detail = get_publication_work_item_detail(
                    actor=actor,
                    organization=organization,
                    resource_type=RESOURCE_FACT_CHECK,
                    resource_id=fact_check.pk,
                )
            elif decision is not None:
                detail = get_publication_work_item_detail(
                    actor=actor,
                    organization=organization,
                    resource_type=RESOURCE_ELIGIBLE_CLAIM,
                    resource_id=claim.pk,
                )
        except (PublicationWorkflowAuthorizationError, PublicationWorkflowNotFound):
            detail = None

    return {
        "fact_check": (
            {
                "id": str(fact_check.pk),
                "publication_status": fact_check.publication_status,
                "updated_at": _timestamp(fact_check.updated_at),
            }
            if fact_check is not None
            else None
        ),
        "actor_allowed_actions": list(detail.get("allowed_actions", [])) if detail else [],
        "actor_blockers": list(detail.get("blockers", [])) if detail else [],
    }


def _pending_item(code, detail, *, count=None):
    item = {
        "code": code,
        "detail": detail,
    }
    if count is not None:
        item["count"] = count
    return item


def _action(code, label, target_type, target_id):
    return {
        "code": code,
        "label": label,
        "target": {
            "type": target_type,
            "id": str(target_id),
        },
    }


def _derive_state(
    *,
    actor,
    organization,
    assignment,
    evidence,
    adjudication,
    decision,
    publication,
):
    evidence_summary = evidence["summary"]
    fact_check = publication["fact_check"]
    adjudication_case = adjudication["case"]
    allowed_actions = []
    actor_blockers = []
    pending = []

    if (
        fact_check is not None
        and fact_check["publication_status"] == OfficialFactCheck.PublicationStatus.IN_REVIEW
    ):
        state = {
            "code": "PUBLICATION_REVIEW",
            "label": "Publication review",
            "detail": "The fact-check draft is waiting for publication review.",
        }
        pending.append(
            _pending_item(
                "PUBLICATION_REVIEW_PENDING",
                "The draft has been submitted and still needs an authorized publication decision.",
            )
        )
        publication_actions = set(publication["actor_allowed_actions"])
        if {"PUBLISH", "RETURN_FOR_REWORK"} & publication_actions:
            allowed_actions.append(
                _action(
                    "REVIEW_PUBLICATION",
                    "Review publication",
                    "FACT_CHECK",
                    fact_check["id"],
                )
            )
        actor_blockers.extend(publication["actor_blockers"])

    elif (
        fact_check is not None
        and fact_check["publication_status"] == OfficialFactCheck.PublicationStatus.DRAFT
    ):
        state = {
            "code": "DRAFTING",
            "label": "Drafting",
            "detail": "An institutional fact-check draft is in progress.",
        }
        pending.append(
            _pending_item(
                "DRAFT_IN_PROGRESS",
                "Complete the fact-check draft and submit it for publication review.",
            )
        )
        if "UPDATE_DRAFT" in publication["actor_allowed_actions"]:
            allowed_actions.append(
                _action(
                    "CONTINUE_DRAFT",
                    "Continue draft",
                    "FACT_CHECK",
                    fact_check["id"],
                )
            )
        actor_blockers.extend(publication["actor_blockers"])

    elif decision is not None:
        state = {
            "code": "DRAFTING_READY",
            "label": "Ready for drafting",
            "detail": "An attributable human adjudication exists. Publication drafting can begin.",
        }
        pending.append(
            _pending_item(
                "DRAFT_NOT_STARTED",
                "Create the institutional fact-check draft from the current adjudication decision.",
            )
        )
        if "CREATE_DRAFT" in publication["actor_allowed_actions"]:
            allowed_actions.append(
                _action(
                    "CREATE_DRAFT",
                    "Create fact-check draft",
                    "ELIGIBLE_CLAIM",
                    assignment.claim_id,
                )
            )
        actor_blockers.extend(publication["actor_blockers"])

    elif (
        evidence_summary["unreviewed"] > 0
        or evidence_summary["inherited_review_pending"] > 0
        or evidence_summary["active_case_count"] > 0
    ):
        pending_count = max(
            evidence_summary["unreviewed"]
            + evidence_summary["inherited_review_pending"],
            evidence_summary["active_case_count"],
        )
        if (
            evidence_summary["inherited_review_pending"] > 0
            and evidence_summary["unreviewed"] == 0
        ):
            detail = (
                f"{pending_count} previously reviewed evidence "
                f"{'item requires' if pending_count == 1 else 'items require'} "
                "this organization to accept the prior review or conduct an "
                "independent re-review before adjudication."
            )
        else:
            detail = (
                f"{pending_count} evidence "
                f"{'item requires' if pending_count == 1 else 'items require'} "
                "review before adjudication."
            )
        state = {
            "code": "EVIDENCE_REVIEW",
            "label": "Evidence review",
            "detail": detail,
        }
        if evidence_summary["unreviewed"] > 0:
            pending.append(
                _pending_item(
                    "UNREVIEWED_EVIDENCE",
                    "Every newly submitted evidence item must be reviewed before adjudication.",
                    count=evidence_summary["unreviewed"],
                )
            )
        if evidence_summary["inherited_review_pending"] > 0:
            pending.append(
                _pending_item(
                    "INHERITED_EVIDENCE_REVIEW",
                    (
                        "Previously reviewed evidence must be explicitly accepted "
                        "or independently re-reviewed by this organization."
                    ),
                    count=evidence_summary["inherited_review_pending"],
                )
            )
        if evidence_summary["active_case_count"]:
            pending.append(
                _pending_item(
                    "ACTIVE_EVIDENCE_CASE",
                    "Evidence review work is still active for this investigation.",
                    count=evidence_summary["active_case_count"],
                )
            )
        if (
            evidence["active_case_id"]
            and has_capability(
                actor,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=organization,
            )
        ):
            allowed_actions.append(
                _action(
                    "REVIEW_EVIDENCE",
                    "Review evidence",
                    "EVIDENCE_CASE",
                    evidence["active_case_id"],
                )
            )

    elif evidence_summary["total"] == 0:
        state = {
            "code": "ACTIVE_NO_EVIDENCE",
            "label": "Investigation started",
            "detail": "No community evidence has been submitted for human review yet.",
        }
        pending.append(
            _pending_item(
                "NO_EVIDENCE",
                "At least one reviewed evidence submission is required before adjudication.",
            )
        )
        if has_capability(
            actor,
            PartnerCapability.CLAIM_VERIFICATION_WORK,
            organization=organization,
        ):
            allowed_actions.append(
                _action(
                    "RELEASE_INVESTIGATION",
                    "Release investigation",
                    "ASSIGNMENT",
                    assignment.pk,
                )
            )

    elif adjudication_case is not None:
        state = {
            "code": "ADJUDICATION",
            "label": "Adjudication",
            "detail": "Evidence review is complete and the factual decision workflow is active.",
        }
        action_state = adjudication["actor_action_state"]
        if action_state is not None:
            actor_blockers.extend(action_state.get("blockers", []))
            if action_state.get("can_issue_first_decision") is True:
                allowed_actions.append(
                    _action(
                        "ADJUDICATE",
                        "Open adjudication",
                        "ADJUDICATION_CASE",
                        adjudication_case["id"],
                    )
                )
        if not allowed_actions:
            pending.append(
                _pending_item(
                    "ADJUDICATION_PENDING",
                    "The investigation is waiting for an authorized adjudicator.",
                )
            )

    else:
        state = {
            "code": "ADJUDICATION_READY",
            "label": "Ready for adjudication",
            "detail": "All submitted evidence is reviewed and the investigation is ready for adjudication.",
        }
        pending.append(
            _pending_item(
                "ADJUDICATION_CASE_PENDING",
                "The adjudication work item has not been opened yet.",
            )
        )

    return {
        "state": state,
        "pending": pending,
        "allowed_actions": allowed_actions,
        "actor_blockers": actor_blockers,
    }


def get_investigation_workspace_context(*, actor, organization, assignment_id):
    """Project one active organization investigation from persisted workflow facts."""

    if not actor or not actor.is_authenticated:
        raise InvestigationWorkspaceAuthorizationError("Authentication is required.")

    if not _has_any_workspace_capability(actor, organization):
        raise InvestigationWorkspaceAuthorizationError(
            "You do not have permission to view verification work for this organization."
        )

    assignment = (
        VerificationAssignment.objects.filter(
            pk=assignment_id,
            organization=organization,
            status=VerificationAssignment.Status.ACTIVE,
        )
        .select_related("claim", "organization", "claimed_by")
        .first()
    )
    if assignment is None:
        raise InvestigationWorkspaceNotFound("Active investigation not found.")

    claim = assignment.claim
    evidence = _evidence_context(claim, organization)
    adjudication = _adjudication_context(
        actor=actor,
        organization=organization,
        claim=claim,
    )
    decision = _current_attributable_decision(claim, organization)
    publication = _publication_context(
        actor=actor,
        organization=organization,
        claim=claim,
        decision=decision,
    )
    guidance = _derive_state(
        actor=actor,
        organization=organization,
        assignment=assignment,
        evidence=evidence,
        adjudication=adjudication,
        decision=decision,
        publication=publication,
    )

    return {
        "schema_version": "1.0",
        "assignment": {
            "id": str(assignment.pk),
            "status": assignment.status,
            "claimed_at": _timestamp(assignment.claimed_at),
            "claimed_by": _user_payload(assignment.claimed_by),
        },
        "organization": _organization_payload(organization),
        "claim": _claim_payload(claim),
        "state": guidance["state"],
        "pending": guidance["pending"],
        "allowed_actions": guidance["allowed_actions"],
        "actor_blockers": guidance["actor_blockers"],
        "evidence": evidence["summary"],
        "adjudication": {
            "case": adjudication["case"],
            "current_decision": _decision_payload(decision),
        },
        "publication": publication["fact_check"],
        "context_links": {
            "verification_intelligence_claim_id": str(claim.pk),
            "evidence_case_id": evidence["active_case_id"],
            "adjudication_case_id": (
                adjudication["case"]["id"] if adjudication["case"] is not None else None
            ),
            "fact_check_id": (
                publication["fact_check"]["id"]
                if publication["fact_check"] is not None
                else None
            ),
        },
    }
