"""Organization-scoped read models for factual-correction work."""

from collections import defaultdict

from .evidence_snapshot_schema import (
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)
from .models import (
    AdjudicationDecision,
    EvidenceSubmission,
    FactualCorrectionProposal,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
    VerificationAssignment,
)
from .moderation_service import ACTIVE_CASE_STATUSES
from .organization_service import PartnerCapability, has_capability
from .publication_workflow_query_service import sealed_evidence_payload
from .verification_assignment_service import OPEN_ASSIGNMENT_STATUSES


WORKFLOW_KIND = "FACTUAL_CORRECTION"

ACTION_REVIEW_EVIDENCE = "REVIEW_CORRECTION_EVIDENCE"
ACTION_SAVE_PROPOSAL = "SAVE_CORRECTION_PROPOSAL"
ACTION_PREPARE_PROPOSAL = "PREPARE_CORRECTION_PROPOSAL"
ACTION_PUBLISH = "PUBLISH_FACTUAL_CORRECTION"
ACTION_CANCEL = "CANCEL_FACTUAL_CORRECTION"

CORRECTION_ACCESS_CAPABILITIES = (
    PartnerCapability.REVIEW_EVIDENCE,
    PartnerCapability.ADJUDICATE,
    PartnerCapability.CREATE_FACT_CHECK_DRAFT,
    PartnerCapability.PUBLISH_FACT_CHECK,
)


class FactualCorrectionQueryError(Exception):
    pass


class FactualCorrectionQueryAuthorizationError(FactualCorrectionQueryError):
    pass


class FactualCorrectionQueryNotFound(FactualCorrectionQueryError):
    pass


def can_access_factual_corrections(actor, organization):
    return any(
        has_capability(actor, capability, organization=organization)
        for capability in CORRECTION_ACCESS_CAPABILITIES
    )


def _require_access(actor, organization):
    if not can_access_factual_corrections(actor, organization):
        raise FactualCorrectionQueryAuthorizationError(
            "You do not have permission to view this organization's factual "
            "correction work."
        )


def _actor_capabilities(actor, organization):
    return {
        capability
        for capability in CORRECTION_ACCESS_CAPABILITIES
        if has_capability(actor, capability, organization=organization)
    }


def _actor_payload(actor):
    if actor is None:
        return None
    return {"id": actor.pk, "username": actor.username}


def _organization_payload(organization):
    return {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
    }


def _blocker(code, detail):
    return {"code": code, "detail": detail}


def _base_queryset(organization):
    return FactualCorrectionRequest.objects.filter(
        organization=organization
    ).select_related(
        "organization",
        "claim",
        "requested_by",
        "predecessor_fact_check",
        "predecessor_fact_check__publication_snapshot",
        "predecessor_decision",
        "predecessor_decision__decided_by",
        "predecessor_decision__evidence_snapshot",
        "moderation_case",
        "moderation_case__resolved_by",
    )


def _load_projection_context(requests):
    request_ids = [item.id for item in requests]
    claim_ids = {item.claim_id for item in requests}

    proposals = {
        item.correction_request_id: item
        for item in FactualCorrectionProposal.objects.filter(
            correction_request_id__in=request_ids
        ).select_related("prepared_by", "verification_run")
    }
    evidence = list(
        EvidenceSubmission.objects.filter(thread__claim_id__in=claim_ids)
        .select_related("thread", "contributor", "verified_by")
        .order_by("submitted_at", "id")
    )
    evidence_by_claim = defaultdict(list)
    for item in evidence:
        evidence_by_claim[item.thread.claim_id].append(item)

    evidence_ids = [item.id for item in evidence]
    evidence_cases = list(
        ModerationCase.objects.filter(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission_id__in=evidence_ids,
        )
        .select_related("resolved_by")
        .order_by("evidence_submission_id", "created_at", "id")
    )
    cases_by_evidence = defaultdict(list)
    for case in evidence_cases:
        cases_by_evidence[case.evidence_submission_id].append(case)

    case_ids = [item.id for item in evidence_cases]
    events = list(
        ModerationEvent.objects.filter(case_id__in=case_ids)
        .select_related("actor")
        .order_by("created_at", "id")
    )
    events_by_case = defaultdict(list)
    for event in events:
        events_by_case[event.case_id].append(event)

    current_publications = {
        item.claim_id: item
        for item in OfficialFactCheck.objects.filter(
            claim_id__in=claim_ids,
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
        ).select_related("adjudication_decision")
    }
    current_decisions = {
        item.claim_id: item
        for item in AdjudicationDecision.objects.filter(
            claim_id__in=claim_ids,
            is_current=True,
        ).select_related("decided_by")
    }
    active_assignments = set(
        VerificationAssignment.objects.filter(
            claim_id__in=claim_ids,
            status__in=OPEN_ASSIGNMENT_STATUSES,
        ).values_list("claim_id", flat=True)
    )
    active_publication_work = set(
        OfficialFactCheck.objects.filter(
            claim_id__in=claim_ids,
            publication_status__in={
                OfficialFactCheck.PublicationStatus.DRAFT,
                OfficialFactCheck.PublicationStatus.IN_REVIEW,
            },
        ).values_list("claim_id", flat=True)
    )
    active_adjudication_cases = defaultdict(list)
    for case in ModerationCase.objects.filter(
        claim_id__in=claim_ids,
        case_type=ModerationCase.CaseType.ADJUDICATION,
        status__in=ACTIVE_CASE_STATUSES,
    ).only("id", "claim_id"):
        active_adjudication_cases[case.claim_id].append(case.id)

    return {
        "proposals": proposals,
        "evidence_by_claim": evidence_by_claim,
        "cases_by_evidence": cases_by_evidence,
        "events_by_case": events_by_case,
        "current_publications": current_publications,
        "current_decisions": current_decisions,
        "active_assignments": active_assignments,
        "active_publication_work": active_publication_work,
        "active_adjudication_cases": active_adjudication_cases,
    }


def _latest_correction_review(request, evidence, cases, events_by_case):
    candidates = []
    for case in cases:
        for event in events_by_case.get(case.id, []):
            metadata = event.metadata
            if (
                isinstance(metadata, dict)
                and metadata.get("correction_request_id") == str(request.id)
                and metadata.get("correction_case_id")
                == str(request.moderation_case_id)
                and metadata.get("evidence_case_id") == str(case.id)
                and event.created_at >= request.requested_at
            ):
                candidates.append((event, case))
    if not candidates:
        return None, False

    event, case = candidates[-1]
    metadata = event.metadata
    reviewer = metadata.get("reviewer_snapshot")
    record = metadata.get("evidence_record")
    previous_status = metadata.get("previous_evidence_status")
    new_status = metadata.get("new_evidence_status")
    is_reaffirmation = metadata.get("is_reaffirmation")
    expected_event_type = (
        ModerationEvent.EventType.EVIDENCE_VERIFIED
        if evidence.evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED
        else ModerationEvent.EventType.EVIDENCE_REJECTED
    )
    qualifying = False
    try:
        validated = validate_evidence_snapshot(
            schema_version=metadata.get("evidence_snapshot_schema_version"),
            evidence_records=[record],
        )[0]
        qualifying = (
            event.event_type == expected_event_type
            and evidence.evidence_status
            in {
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
            }
            and new_status == evidence.evidence_status
            and previous_status in EvidenceSubmission.EvidenceStatus.values
            and isinstance(is_reaffirmation, bool)
            and is_reaffirmation == (previous_status == new_status)
            and validated["id"] == str(evidence.id)
            and validated["thread_id"] == str(evidence.thread_id)
            and isinstance(reviewer, dict)
            and set(reviewer) == {"id", "username"}
            and all(
                isinstance(value, str) and value.strip()
                for value in reviewer.values()
            )
            and validated["reviewer_id"] == reviewer["id"]
            and (
                event.actor_id is None
                or reviewer["id"] == str(event.actor_id)
            )
        )
    except (EvidenceSnapshotSchemaError, KeyError, TypeError):
        qualifying = False

    return (
        {
            "review_event_id": str(event.id),
            "evidence_case_id": str(case.id),
            "reviewed_by": reviewer if isinstance(reviewer, dict) else None,
            "reviewed_at": event.created_at,
            "previous_evidence_status": previous_status,
            "new_evidence_status": new_status,
            "is_reaffirmation": bool(is_reaffirmation),
            "moderator_notes": event.notes,
            "rejection_reason": (
                event.reason_code
                if new_status == EvidenceSubmission.EvidenceStatus.REJECTED
                else None
            ),
        },
        qualifying,
    )


def _evidence_projection(request, actor, capabilities, context):
    items = []
    has_active_case = False
    has_actor_reviewable_item = False
    can_review = PartnerCapability.REVIEW_EVIDENCE in capabilities
    for evidence in context["evidence_by_claim"].get(request.claim_id, []):
        cases = context["cases_by_evidence"].get(evidence.id, [])
        active_cases = [item for item in cases if item.status in ACTIVE_CASE_STATUSES]
        has_active_case = has_active_case or bool(active_cases)
        selected_case = (
            active_cases[-1]
            if active_cases
            else (cases[-1] if cases else None)
        )
        review, qualifying = _latest_correction_review(
            request,
            evidence,
            cases,
            context["events_by_case"],
        )
        actions = []
        actor_can_review_item = evidence.contributor_id != actor.id
        has_actor_reviewable_item = (
            has_actor_reviewable_item or actor_can_review_item
        )
        if (
            request.status == FactualCorrectionRequest.Status.ACTIVE
            and can_review
            and actor_can_review_item
        ):
            actions.append(ACTION_REVIEW_EVIDENCE)
        items.append(
            {
                "evidence_id": str(evidence.id),
                "evidence_case_id": (
                    str(selected_case.id) if selected_case is not None else None
                ),
                "evidence_caption": evidence.evidence_caption,
                "evidence_url": evidence.evidence_url,
                "evidence_type": evidence.evidence_type,
                "evidence_status": evidence.evidence_status,
                "moderator_notes": evidence.moderator_notes,
                "rejection_reason": evidence.rejection_reason,
                "submitted_at": evidence.submitted_at,
                "contributor": _actor_payload(evidence.contributor),
                "correction_review": review,
                "has_qualifying_correction_review": qualifying,
                "is_reaffirmation": (
                    review["is_reaffirmation"] if review is not None else False
                ),
                "allowed_actions": actions,
            }
        )
    evidence_ready = bool(items) and all(
        item["has_qualifying_correction_review"] for item in items
    )
    return {
        "count": len(items),
        "reviewed_count": sum(
            item["has_qualifying_correction_review"] for item in items
        ),
        "is_complete": evidence_ready and not has_active_case,
        "has_active_evidence_case": has_active_case,
        "has_actor_reviewable_item": has_actor_reviewable_item,
        "items": items,
    }


def _relationship_blockers(request, context):
    blockers = []
    current_publication = context["current_publications"].get(request.claim_id)
    current_decision = context["current_decisions"].get(request.claim_id)
    case = request.moderation_case
    if (
        request.predecessor_fact_check.claim_id != request.claim_id
        or request.predecessor_fact_check.organization_id != request.organization_id
        or request.predecessor_fact_check.adjudication_decision_id
        != request.predecessor_decision_id
        or request.predecessor_decision.claim_id != request.claim_id
        or request.predecessor_decision.organization_id != request.organization_id
        or case.claim_id != request.claim_id
        or case.organization_id != request.organization_id
        or case.case_type != ModerationCase.CaseType.ADJUDICATION
    ):
        blockers.append(
            _blocker(
                "CORRECTION_AUTHORITY_CHANGED",
                "The correction request no longer matches its recorded authority.",
            )
        )
    if (
        current_publication is None
        or current_publication.id != request.predecessor_fact_check_id
    ):
        blockers.append(
            _blocker(
                "PREDECESSOR_NOT_CURRENT",
                "The correction predecessor is no longer the current publication.",
            )
        )
    if (
        current_decision is None
        or current_decision.id != request.predecessor_decision_id
    ):
        blockers.append(
            _blocker(
                "STALE_DECISION_REVISION",
                "The predecessor decision is no longer current.",
            )
        )
    if (
        request.status == FactualCorrectionRequest.Status.ACTIVE
        and case.status not in ACTIVE_CASE_STATUSES
    ):
        blockers.append(
            _blocker(
                "CORRECTION_CASE_NOT_ACTIVE",
                "The correction Adjudication case is no longer active.",
            )
        )
    active_case_ids = context["active_adjudication_cases"].get(
        request.claim_id,
        [],
    )
    if any(case_id != request.moderation_case_id for case_id in active_case_ids):
        blockers.append(
            _blocker(
                "ACTIVE_ADJUDICATION_WORK_EXISTS",
                "Competing Adjudication work is active for this claim.",
            )
        )
    return blockers


def _action_state(request, proposal, evidence_review, capabilities, context):
    actions = []
    blockers = {
        ACTION_REVIEW_EVIDENCE: [],
        ACTION_SAVE_PROPOSAL: [],
        ACTION_PREPARE_PROPOSAL: [],
        ACTION_PUBLISH: [],
        ACTION_CANCEL: [],
    }
    if request.status != FactualCorrectionRequest.Status.ACTIVE:
        terminal = _blocker(
            "CORRECTION_REQUEST_TERMINAL",
            "The factual correction request has reached a terminal state.",
        )
        for action in blockers:
            blockers[action].append(terminal)
        return actions, blockers

    relationship_blockers = _relationship_blockers(request, context)
    for action in blockers:
        blockers[action].extend(relationship_blockers)

    if not evidence_review["items"]:
        blockers[ACTION_REVIEW_EVIDENCE].append(
            _blocker(
                "NO_EVIDENCE",
                "No claim evidence is available for correction review.",
            )
        )
    elif not evidence_review["has_actor_reviewable_item"]:
        blockers[ACTION_REVIEW_EVIDENCE].append(
            _blocker(
                "DIRECT_CONTRIBUTION_CONFLICT",
                "The actor cannot review evidence they directly contributed.",
            )
        )
    if (
        proposal is not None
        and proposal.status == FactualCorrectionProposal.Status.PREPARED
    ):
        blockers[ACTION_REVIEW_EVIDENCE].append(
            _blocker(
                "PROPOSAL_PREPARED",
                "Correction evidence is frozen after proposal preparation.",
            )
        )
        blockers[ACTION_SAVE_PROPOSAL].append(
            _blocker(
                "PROPOSAL_PREPARED",
                "A prepared correction proposal is immutable.",
            )
        )
    if proposal is None:
        blockers[ACTION_PREPARE_PROPOSAL].append(
            _blocker(
                "PROPOSAL_REQUIRED",
                "A draft correction proposal is required before preparation.",
            )
        )
    elif proposal.status == FactualCorrectionProposal.Status.PREPARED:
        blockers[ACTION_PREPARE_PROPOSAL].append(
            _blocker("PROPOSAL_PREPARED", "The proposal is already prepared.")
        )
    if not evidence_review["is_complete"]:
        blockers[ACTION_PREPARE_PROPOSAL].append(
            _blocker(
                "CORRECTION_EVIDENCE_INCOMPLETE",
                "Every evidence item needs a qualifying correction review and no "
                "Evidence case may remain active.",
            )
        )
    if request.claim_id in context["active_assignments"]:
        blocker = _blocker(
            "ASSIGNMENT_CONFLICT",
            "Ordinary verification work is active for this claim.",
        )
        blockers[ACTION_REVIEW_EVIDENCE].append(blocker)
        blockers[ACTION_PREPARE_PROPOSAL].append(blocker)
        blockers[ACTION_PUBLISH].append(blocker)
    if request.claim_id in context["active_publication_work"]:
        blocker = _blocker(
            "ACTIVE_PUBLICATION_WORK_EXISTS",
            "Competing publication work is active for this claim.",
        )
        blockers[ACTION_PREPARE_PROPOSAL].append(blocker)
        blockers[ACTION_PUBLISH].append(blocker)
    if (
        proposal is None
        or proposal.status != FactualCorrectionProposal.Status.PREPARED
    ):
        blockers[ACTION_PUBLISH].append(
            _blocker(
                "PREPARED_PROPOSAL_REQUIRED",
                "A prepared factual correction proposal is required for publication.",
            )
        )

    capability_by_action = {
        ACTION_REVIEW_EVIDENCE: PartnerCapability.REVIEW_EVIDENCE,
        ACTION_SAVE_PROPOSAL: PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        ACTION_PREPARE_PROPOSAL: PartnerCapability.ADJUDICATE,
        ACTION_PUBLISH: PartnerCapability.PUBLISH_FACT_CHECK,
        ACTION_CANCEL: PartnerCapability.ADJUDICATE,
    }
    for action, capability in capability_by_action.items():
        if not blockers[action] and capability in capabilities:
            actions.append(action)
    return actions, blockers


def _stage(request, proposal, evidence_review):
    if request.status == FactualCorrectionRequest.Status.COMPLETED:
        return "COMPLETED"
    if request.status == FactualCorrectionRequest.Status.CANCELLED:
        return "CANCELLED"
    if (
        proposal is not None
        and proposal.status == FactualCorrectionProposal.Status.PREPARED
    ):
        return "PREPARED"
    if not evidence_review["is_complete"]:
        return "EVIDENCE_REVIEW"
    return "PROPOSAL_DRAFT"


def _proposal_payload(proposal):
    if proposal is None:
        return None
    return {
        "id": str(proposal.id),
        "status": proposal.status,
        "version": proposal.version,
        "proposed_verdict": proposal.verdict,
        "proposed_canonical_claim": proposal.canonical_claim,
        "proposed_rationale": proposal.rationale,
        "headline": proposal.headline,
        "summary": proposal.summary,
        "article_body": proposal.article_body,
        "source_urls": proposal.source_urls,
        "verification_run_id": (
            str(proposal.verification_run_id)
            if proposal.verification_run_id is not None
            else None
        ),
        "prepared_by": (
            proposal.prepared_by_snapshot
            if isinstance(proposal.prepared_by_snapshot, dict)
            else _actor_payload(proposal.prepared_by)
        ),
        "prepared_at": proposal.prepared_at,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }


def _decision_payload(decision):
    if decision is None:
        return None
    return {
        "id": str(decision.id),
        "revision_number": decision.revision_number,
        "canonical_claim": decision.canonical_claim,
        "verdict": decision.verdict,
        "rationale": decision.rationale,
        "decided_by": _actor_payload(decision.decided_by),
        "decided_at": decision.decided_at,
        "is_current": decision.is_current,
    }


def _request_payload(request):
    return {
        "id": str(request.id),
        "status": request.status,
        "correction_reason": request.correction_reason,
        "requested_at": request.requested_at,
        "requested_by": request.requested_by_snapshot,
        "updated_at": request.updated_at,
    }


def _build_detail(request, actor, organization, capabilities, context):
    proposal = context["proposals"].get(request.id)
    evidence_review = _evidence_projection(request, actor, capabilities, context)
    allowed_actions, blockers = _action_state(
        request,
        proposal,
        evidence_review,
        capabilities,
        context,
    )
    evidence_review.pop("has_actor_reviewable_item", None)
    if ACTION_REVIEW_EVIDENCE not in allowed_actions:
        for item in evidence_review["items"]:
            item["allowed_actions"] = []
    predecessor = request.predecessor_fact_check
    decision = request.predecessor_decision
    current_decision = context["current_decisions"].get(request.claim_id)
    current_publication = context["current_publications"].get(request.claim_id)
    case = request.moderation_case
    return {
        "workflow_kind": WORKFLOW_KIND,
        "request": _request_payload(request),
        "organization": _organization_payload(organization),
        "claim": {
            "id": str(request.claim_id),
            "claim_type": request.claim.claim_type,
            "context_text": request.claim.context_text,
            "url_link": request.claim.url_link,
            "source_link": request.claim.source_link,
            "media_url": request.claim.media_url,
        },
        "predecessor_publication": {
            "id": str(predecessor.id),
            "version": predecessor.version,
            "headline": predecessor.headline,
            "summary": predecessor.summary,
            "publication_status": predecessor.publication_status,
            "revision_kind": predecessor.revision_kind,
            "published_at": predecessor.published_at,
        },
        "predecessor_decision": _decision_payload(decision),
        "current_decision": _decision_payload(current_decision),
        "completed_publication": (
            {
                "id": str(current_publication.id),
                "version": current_publication.version,
                "headline": current_publication.headline,
                "summary": current_publication.summary,
                "publication_status": current_publication.publication_status,
                "revision_kind": current_publication.revision_kind,
                "published_at": current_publication.published_at,
            }
            if request.status == FactualCorrectionRequest.Status.COMPLETED
            and current_publication is not None
            else None
        ),
        "sealed_predecessor_evidence": sealed_evidence_payload(decision),
        "correction_case": {
            "id": str(case.id),
            "status": case.status,
            "priority": case.priority,
            "created_at": case.created_at,
            "updated_at": case.updated_at,
            "resolved_at": case.resolved_at,
            "resolved_by": _actor_payload(case.resolved_by),
            "resolution_code": case.resolution_code,
            "resolution_summary": case.resolution_summary,
        },
        "evidence_review": evidence_review,
        "proposal": _proposal_payload(proposal),
        "stage": _stage(request, proposal, evidence_review),
        "allowed_actions": allowed_actions,
        "blockers": blockers,
        "concurrency": {
            "expected_predecessor_version": predecessor.version,
            "expected_decision_revision": decision.revision_number,
            "expected_proposal_version": proposal.version if proposal else 0,
        },
    }


def _queue_item(detail):
    return {
        "request_id": detail["request"]["id"],
        "request_status": detail["request"]["status"],
        "workflow_kind": detail["workflow_kind"],
        "stage": detail["stage"],
        "correction_reason": detail["request"]["correction_reason"],
        "requested_at": detail["request"]["requested_at"],
        "requested_by": detail["request"]["requested_by"],
        "claim": detail["claim"],
        "predecessor_publication": detail["predecessor_publication"],
        "predecessor_decision": detail["predecessor_decision"],
        "current_decision": detail["current_decision"],
        "completed_publication": detail["completed_publication"],
        "correction_case": detail["correction_case"],
        "proposal": detail["proposal"],
        "allowed_actions": detail["allowed_actions"],
        "concurrency": detail["concurrency"],
    }


def list_factual_corrections(
    *,
    actor,
    organization,
    request_status=FactualCorrectionRequest.Status.ACTIVE,
    limit=20,
    offset=0,
):
    _require_access(actor, organization)
    queryset = _base_queryset(organization)
    if request_status != "ALL":
        queryset = queryset.filter(status=request_status)
    queryset = queryset.order_by("-requested_at", "id")
    count = queryset.count()
    requests = list(queryset[offset : offset + limit])
    context = _load_projection_context(requests)
    capabilities = _actor_capabilities(actor, organization)
    return {
        "count": count,
        "limit": limit,
        "offset": offset,
        "organization": _organization_payload(organization),
        "results": [
            _queue_item(
                _build_detail(item, actor, organization, capabilities, context)
            )
            for item in requests
        ],
    }


def get_factual_correction_detail(*, actor, organization, correction_request_id):
    _require_access(actor, organization)
    request = _base_queryset(organization).filter(pk=correction_request_id).first()
    if request is None:
        raise FactualCorrectionQueryNotFound(
            "Factual correction request not found."
        )
    context = _load_projection_context([request])
    capabilities = _actor_capabilities(actor, organization)
    return _build_detail(request, actor, organization, capabilities, context)
