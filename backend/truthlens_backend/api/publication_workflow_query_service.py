"""Read-only organization-scoped projections for publication work."""

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch, Q

from .evidence_snapshot_schema import (
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)
from .models import (
    AdjudicationDecision,
    FactualCorrectionRequest,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OfficialFactCheckSource,
    VerificationAssignment,
)
from .organization_service import PartnerCapability, has_capability
from .verification_assignment_service import OPEN_ASSIGNMENT_STATUSES


class PublicationWorkflowQueryError(Exception):
    pass


class PublicationWorkflowAuthorizationError(PublicationWorkflowQueryError):
    pass


class PublicationWorkflowNotFound(PublicationWorkflowQueryError):
    pass


RESOURCE_ELIGIBLE_CLAIM = "ELIGIBLE_CLAIM"
RESOURCE_FACT_CHECK = "FACT_CHECK"
QUEUE_DRAFTING = "DRAFTING"
QUEUE_REVIEW = "REVIEW"
WORKFLOW_INITIAL = OfficialFactCheck.RevisionKind.INITIAL
WORKFLOW_EDITORIAL_REVISION = OfficialFactCheck.RevisionKind.EDITORIAL_REVISION
WORKFLOW_ALL = "ALL"

SOURCE_ORIGIN_BY_TYPE = {
    OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE: "DECISION_EVIDENCE",
    OfficialFactCheckSource.SourceType.MODERATOR_ADDED: "ORGANIZATION_EDITORIAL",
    OfficialFactCheckSource.SourceType.LEGACY_IMPORT: "LEGACY_IMPORT",
}


def _actor_payload(actor):
    if actor is None:
        return None
    return {
        "id": actor.pk,
        "username": actor.username,
    }


def _organization_payload(organization):
    return {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
    }


def _claim_payload(claim):
    return {
        "id": str(claim.id),
        "claim_type": claim.claim_type,
        "context_text": claim.context_text,
        "url_link": claim.url_link,
        "source_link": claim.source_link,
        "media_url": claim.media_url,
    }


def _decision_payload(decision):
    return {
        "id": str(decision.id),
        "revision_number": decision.revision_number,
        "canonical_claim": decision.canonical_claim,
        "verdict": decision.verdict,
        "rationale": decision.rationale,
        "decided_at": decision.decided_at,
        "decided_by": _actor_payload(decision.decided_by),
        "is_current": decision.is_current,
    }


def _blocker(code, detail):
    return {"code": code, "detail": detail}


def _valid_decision_snapshot(decision):
    try:
        snapshot = decision.evidence_snapshot
    except ObjectDoesNotExist:
        return None, None
    if str(snapshot.claim_id) != str(decision.claim_id):
        return snapshot, None
    try:
        records = validate_evidence_snapshot(
            schema_version=snapshot.schema_version,
            evidence_records=snapshot.evidence_records,
        )
    except EvidenceSnapshotSchemaError:
        return snapshot, None
    return snapshot, records


def sealed_evidence_payload(decision):
    snapshot, records = _valid_decision_snapshot(decision)
    if snapshot is None or records is None:
        return None
    return {
        "basis": "SEALED_DECISION_EVIDENCE",
        "decision_snapshot_id": str(snapshot.id),
        "schema_version": snapshot.schema_version,
        "captured_at": snapshot.captured_at,
        "count": len(records),
        "entries": [
            {
                "id": record["id"],
                "thread_id": record["thread_id"],
                "evidence_status": record["evidence_status"],
                "evidence_type": record["evidence_type"],
                "evidence_caption": record["evidence_caption"],
                "evidence_url": record["evidence_url"],
                "contributor_id": record["contributor_id"],
                "reviewer_id": record["reviewer_id"],
                "submitted_at": record["submitted_at"],
                "reviewed_at": record["reviewed_at"],
                "moderator_notes": record["moderator_notes"],
                "rejection_reason": record["rejection_reason"],
            }
            for record in records
        ],
    }


def _active_correction_exists(claim_id):
    return FactualCorrectionRequest.objects.filter(
        claim_id=claim_id,
        status=FactualCorrectionRequest.Status.ACTIVE,
    ).exists()


def _assignment_conflict(decision):
    assignment = (
        VerificationAssignment.objects.filter(
            claim_id=decision.claim_id,
            status__in=OPEN_ASSIGNMENT_STATUSES,
        )
        .only("organization_id", "status", "created_at")
        .order_by("-created_at")
        .first()
    )
    return bool(
        assignment is not None
        and (
            assignment.status != VerificationAssignment.Status.ACTIVE
            or assignment.organization_id != decision.organization_id
        )
    )


def _open_assignment_exists(decision):
    return VerificationAssignment.objects.filter(
        claim_id=decision.claim_id,
        status__in=OPEN_ASSIGNMENT_STATUSES,
    ).exists()


def _decision_blockers(decision):
    blockers = []
    if not decision.is_current:
        blockers.append(
            _blocker(
                "STALE_DECISION_REVISION",
                "The fact-check does not use the current adjudication decision.",
            )
        )
    _snapshot, records = _valid_decision_snapshot(decision)
    if records is None:
        blockers.append(
            _blocker(
                "PUBLICATION_NOT_READY",
                "The current adjudication decision has no valid sealed evidence basis.",
            )
        )
    if _assignment_conflict(decision):
        blockers.append(
            _blocker(
                "ASSIGNMENT_CONFLICT",
                "The open verification assignment is not active for this "
                "organization.",
            )
        )
    if _active_correction_exists(decision.claim_id):
        blockers.append(
            _blocker(
                "ACTIVE_CORRECTION_RESERVATION",
                "An active factual-correction request reserves this claim.",
            )
        )
    return blockers


def publication_source_payloads(fact_check):
    sources = []
    for source in fact_check.source_items.all():
        links = list(source.evidence_links.all())
        sealed = source.source_type == OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE
        sources.append(
            {
                "id": str(source.id),
                "url": source.url,
                "title": source.title,
                "source_type": source.source_type,
                "source_origin": SOURCE_ORIGIN_BY_TYPE.get(
                    source.source_type,
                    "UNKNOWN",
                ),
                "provenance": "SEALED_EVIDENCE" if sealed else "EDITORIAL",
                "immutable": sealed
                or fact_check.publication_status
                in {
                    OfficialFactCheck.PublicationStatus.PUBLISHED,
                    OfficialFactCheck.PublicationStatus.ARCHIVED,
                },
                "is_editorially_selected": source.is_editorially_selected,
                "added_by": _actor_payload(source.added_by),
                "captured_evidence_ids": [
                    str(link.captured_evidence_id) for link in links
                ],
            }
        )
    return sources


def _article_ready(fact_check):
    return bool(
        (fact_check.headline or "").strip()
        and (fact_check.summary or "").strip()
        and (fact_check.article_body or "").strip()
        and fact_check.source_items.all()
    )


def _fact_check_blockers(fact_check):
    blockers = _decision_blockers(fact_check.adjudication_decision)
    sources = publication_source_payloads(fact_check)
    if any(
        source["source_type"]
        == OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE
        and not source["captured_evidence_ids"]
        for source in sources
    ):
        blockers.append(
            _blocker(
                "PUBLICATION_NOT_READY",
                "A verified-evidence source is missing sealed evidence lineage.",
            )
        )
    if not _article_ready(fact_check):
        blockers.append(
            _blocker(
                "PUBLICATION_NOT_READY",
                "Headline, summary, article analysis, and at least one source are "
                "required before review or publication.",
            )
        )
    if fact_check.revision_kind == WORKFLOW_EDITORIAL_REVISION:
        predecessor = fact_check.supersedes
        if (
            predecessor is None
            or predecessor.publication_status
            != OfficialFactCheck.PublicationStatus.PUBLISHED
        ):
            blockers.append(
                _blocker(
                    "ACTIVE_PUBLICATION_WORK_EXISTS",
                    "The editorial revision predecessor is no longer the current "
                    "published fact-check.",
                )
            )
        elif (
            predecessor.claim_id != fact_check.claim_id
            or predecessor.organization_id != fact_check.organization_id
            or predecessor.adjudication_decision_id
            != fact_check.adjudication_decision_id
        ):
            blockers.append(
                _blocker(
                    "INVALID_PUBLICATION_STATE",
                    "The editorial revision no longer matches its predecessor.",
                )
            )
        if (
            _open_assignment_exists(fact_check.adjudication_decision)
            and "ASSIGNMENT_CONFLICT" not in _blocking_codes(blockers)
        ):
            blockers.append(
                _blocker(
                    "ASSIGNMENT_CONFLICT",
                    "Open verification work must be resolved before editorial "
                    "revision work can continue.",
                )
            )
    return blockers


def _blocking_codes(blockers):
    return {item["code"] for item in blockers}


def _eligible_claim_actions(actor, organization, blockers):
    if blockers:
        return []
    if has_capability(
        actor,
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        organization=organization,
    ):
        return ["CREATE_DRAFT"]
    return []


def _fact_check_actions(actor, organization, fact_check, blockers):
    codes = _blocking_codes(blockers)
    stale_or_reserved = bool(
        codes
        & {
            "STALE_DECISION_REVISION",
            "ASSIGNMENT_CONFLICT",
            "ACTIVE_CORRECTION_RESERVATION",
            "ACTIVE_PUBLICATION_WORK_EXISTS",
            "INVALID_PUBLICATION_STATE",
        }
    )
    actions = []
    can_draft = has_capability(
        actor,
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        organization=organization,
    )
    can_publish = has_capability(
        actor,
        PartnerCapability.PUBLISH_FACT_CHECK,
        organization=organization,
    )
    if fact_check.publication_status == OfficialFactCheck.PublicationStatus.DRAFT:
        if can_draft and not stale_or_reserved:
            actions.extend(["UPDATE_DRAFT", "ABANDON"])
            if "PUBLICATION_NOT_READY" not in codes:
                actions.append("SUBMIT")
    elif fact_check.publication_status == OfficialFactCheck.PublicationStatus.IN_REVIEW:
        if can_publish and not stale_or_reserved:
            actions.append("RETURN_FOR_REWORK")
            if "PUBLICATION_NOT_READY" not in codes:
                actions.append(
                    "PUBLISH_REPLACEMENT"
                    if fact_check.revision_kind == WORKFLOW_EDITORIAL_REVISION
                    else "PUBLISH"
                )
    return actions


def _concurrency_payload(fact_check, decision):
    return {
        "edit_generation": (
            fact_check.edit_generation if fact_check is not None else None
        ),
        "article_version": fact_check.version if fact_check is not None else None,
        "decision_revision": decision.revision_number,
        "predecessor_version": (
            fact_check.supersedes.version
            if fact_check is not None and fact_check.supersedes_id is not None
            else None
        ),
    }


def _revision_payload(fact_check):
    if fact_check.revision_kind != WORKFLOW_EDITORIAL_REVISION:
        return None
    predecessor = fact_check.supersedes
    return {
        "kind": WORKFLOW_EDITORIAL_REVISION,
        "reason": fact_check.revision_reason,
        "requested_by": _actor_payload(fact_check.revision_requested_by),
        "requested_at": fact_check.revision_requested_at,
        "predecessor": {
            "id": str(predecessor.id),
            "version": predecessor.version,
            "headline": predecessor.headline,
            "published_at": predecessor.published_at,
        },
    }


def _eligible_claim_list_item(actor, organization, decision, *, blockers=None):
    blockers = _decision_blockers(decision) if blockers is None else blockers
    return {
        "resource_type": RESOURCE_ELIGIBLE_CLAIM,
        "resource_id": str(decision.claim_id),
        "workflow_kind": OfficialFactCheck.RevisionKind.INITIAL,
        "revision": None,
        "fact_check_id": None,
        "organization": _organization_payload(organization),
        "claim": _claim_payload(decision.claim),
        "decision": _decision_payload(decision),
        "article": None,
        "lifecycle": {
            "actionable_at": decision.decided_at,
            "created_at": None,
            "updated_at": None,
            "drafted_at": None,
            "drafted_by": None,
            "submitted_for_review_at": None,
            "reviewed_at": None,
            "reviewed_by": None,
            "published_at": None,
            "published_by": None,
            "archived_at": None,
        },
        "concurrency": _concurrency_payload(None, decision),
        "allowed_actions": _eligible_claim_actions(actor, organization, blockers),
        "blockers": blockers,
    }


def _fact_check_list_item(actor, organization, fact_check):
    decision = fact_check.adjudication_decision
    blockers = _fact_check_blockers(fact_check)
    return {
        "resource_type": RESOURCE_FACT_CHECK,
        "resource_id": str(fact_check.id),
        "workflow_kind": (
            WORKFLOW_EDITORIAL_REVISION
            if fact_check.revision_kind == WORKFLOW_EDITORIAL_REVISION
            else WORKFLOW_INITIAL
        ),
        "revision": _revision_payload(fact_check),
        "fact_check_id": str(fact_check.id),
        "organization": _organization_payload(organization),
        "claim": _claim_payload(fact_check.claim),
        "decision": _decision_payload(decision),
        "article": {
            "publication_status": fact_check.publication_status,
            "version": fact_check.version,
            "edit_generation": fact_check.edit_generation,
            "headline": fact_check.headline,
            "summary": fact_check.summary,
        },
        "lifecycle": {
            "actionable_at": fact_check.updated_at,
            "created_at": fact_check.created_at,
            "updated_at": fact_check.updated_at,
            "drafted_at": fact_check.created_at,
            "drafted_by": _actor_payload(fact_check.drafted_by),
            "submitted_for_review_at": fact_check.submitted_for_review_at,
            "reviewed_at": fact_check.reviewed_at,
            "reviewed_by": _actor_payload(fact_check.reviewed_by),
            "published_at": fact_check.published_at,
            "published_by": _actor_payload(fact_check.published_by),
            "archived_at": fact_check.archived_at,
        },
        "concurrency": _concurrency_payload(fact_check, decision),
        "allowed_actions": _fact_check_actions(
            actor,
            organization,
            fact_check,
            blockers,
        ),
        "blockers": blockers,
    }


def _fact_check_queryset(organization, workflow_kind=WORKFLOW_INITIAL):
    if workflow_kind == WORKFLOW_INITIAL:
        queryset = OfficialFactCheck.initial_workflow_queryset()
    elif workflow_kind == WORKFLOW_EDITORIAL_REVISION:
        queryset = OfficialFactCheck.objects.filter(
            revision_kind=WORKFLOW_EDITORIAL_REVISION,
            supersedes__isnull=False,
            claim__isnull=False,
            adjudication_decision__isnull=False,
            organization__isnull=False,
        )
    elif workflow_kind == WORKFLOW_ALL:
        queryset = OfficialFactCheck.objects.filter(
            (
                (
                    Q(revision_kind=WORKFLOW_INITIAL)
                    | Q(revision_kind__isnull=True)
                )
                & Q(supersedes__isnull=True)
                | Q(
                    revision_kind=WORKFLOW_EDITORIAL_REVISION,
                    supersedes__isnull=False,
                )
            ),
            claim__isnull=False,
            adjudication_decision__isnull=False,
            organization__isnull=False,
        )
    else:
        raise PublicationWorkflowNotFound("Publication workflow kind not found.")
    return (
        queryset.filter(organization=organization)
        .select_related(
            "organization",
            "claim",
            "adjudication_decision",
            "adjudication_decision__decided_by",
            "adjudication_decision__evidence_snapshot",
            "drafted_by",
            "reviewed_by",
            "published_by",
            "revision_requested_by",
            "supersedes",
        )
        .prefetch_related(
            Prefetch(
                "source_items",
                queryset=OfficialFactCheckSource.objects.select_related(
                    "added_by"
                ).prefetch_related("evidence_links"),
            )
        )
    )


def _current_decision_queryset(organization):
    return AdjudicationDecision.objects.filter(
        organization=organization,
        is_current=True,
    ).select_related(
        "organization",
        "claim",
        "decided_by",
        "evidence_snapshot",
    )


def _eligible_claim_blockers(decision):
    """Return blockers when current decision can be projected as initial work.

    ``None`` means ordinary initial draft creation is structurally unavailable.
    A blocker list means the claim is discoverable, with CREATE_DRAFT available
    only when that list is empty.
    """
    claim_fact_checks = list(
        OfficialFactCheck.objects.filter(claim_id=decision.claim_id).only(
            "id",
            "adjudication_decision_id",
            "publication_status",
            "revision_kind",
            "supersedes_id",
        )
    )
    if any(
        item.publication_status == OfficialFactCheck.PublicationStatus.PUBLISHED
        for item in claim_fact_checks
    ) or OfficialFactCheckPublicationSnapshot.objects.filter(
        fact_check__claim_id=decision.claim_id,
    ).exists():
        return None

    active_work = [
        item
        for item in claim_fact_checks
        if item.publication_status
        in {
            OfficialFactCheck.PublicationStatus.DRAFT,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        }
    ]
    if any(
        item.adjudication_decision_id == decision.id
        or item.supersedes_id is not None
        or item.revision_kind
        in {
            OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
        }
        for item in active_work
    ):
        return None

    return _decision_blockers(decision)


def _require_queue_capability(actor, organization, queue):
    capability = (
        PartnerCapability.CREATE_FACT_CHECK_DRAFT
        if queue == QUEUE_DRAFTING
        else PartnerCapability.PUBLISH_FACT_CHECK
    )
    if not has_capability(actor, capability, organization=organization):
        raise PublicationWorkflowAuthorizationError(
            "You do not have permission to view this publication queue."
        )


def list_publication_work_items(
    *,
    actor,
    organization,
    queue,
    limit,
    offset,
    workflow_kind=WORKFLOW_INITIAL,
):
    _require_queue_capability(actor, organization, queue)
    active_fact_checks = list(
        _fact_check_queryset(organization, workflow_kind).filter(
            publication_status__in={
                OfficialFactCheck.PublicationStatus.DRAFT,
                OfficialFactCheck.PublicationStatus.IN_REVIEW,
            }
        )
    )

    if queue == QUEUE_REVIEW:
        items = [
            _fact_check_list_item(actor, organization, fact_check)
            for fact_check in active_fact_checks
            if fact_check.publication_status
            == OfficialFactCheck.PublicationStatus.IN_REVIEW
        ]
        items.sort(
            key=lambda item: (
                item["lifecycle"]["submitted_for_review_at"] is None,
                item["lifecycle"]["submitted_for_review_at"]
                or item["lifecycle"]["actionable_at"],
                item["resource_id"],
            )
        )
    else:
        items = [
            _fact_check_list_item(actor, organization, fact_check)
            for fact_check in active_fact_checks
        ]
        if workflow_kind in {WORKFLOW_INITIAL, WORKFLOW_ALL}:
            for decision in _current_decision_queryset(organization):
                blockers = _eligible_claim_blockers(decision)
                if blockers is None:
                    continue
                items.append(
                    _eligible_claim_list_item(
                        actor,
                        organization,
                        decision,
                        blockers=blockers,
                    )
                )
        status_rank = {
            OfficialFactCheck.PublicationStatus.DRAFT: 0,
            OfficialFactCheck.PublicationStatus.IN_REVIEW: 1,
            None: 2,
        }
        items.sort(
            key=lambda item: (
                status_rank[
                    item["article"]["publication_status"]
                    if item["article"] is not None
                    else None
                ],
                item["lifecycle"]["actionable_at"],
                item["resource_id"],
            )
        )

    return {
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "organization": _organization_payload(organization),
        "results": items[offset : offset + limit],
    }


def _eligible_claim_detail(actor, organization, claim_id):
    decision = _current_decision_queryset(organization).filter(claim_id=claim_id).first()
    if decision is None:
        raise PublicationWorkflowNotFound("Publication work item not found.")
    blockers = _eligible_claim_blockers(decision)
    if blockers is None:
        raise PublicationWorkflowNotFound("Publication work item not found.")
    item = _eligible_claim_list_item(
        actor,
        organization,
        decision,
        blockers=blockers,
    )
    item.update(
        {
            "id": None,
            "claim_id": str(decision.claim_id),
            "adjudication_decision_id": str(decision.id),
            "canonical_claim": decision.canonical_claim,
            "verdict": decision.verdict,
            "headline": None,
            "summary": None,
            "article_body": None,
            "publication_status": None,
            "version": None,
            "edit_generation": None,
            "sources": [],
            "source_items": [],
            "drafted_by": None,
            "submitted_for_review_at": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "published_by": None,
            "published_at": None,
            "archived_at": None,
            "created_at": None,
            "updated_at": None,
            "sealed_evidence": sealed_evidence_payload(decision),
            "blockers": blockers,
        }
    )
    return item


def _fact_check_detail(actor, organization, fact_check):
    item = _fact_check_list_item(actor, organization, fact_check)
    source_items = publication_source_payloads(fact_check)
    item.update(
        {
            "article": {
                "publication_status": fact_check.publication_status,
                "version": fact_check.version,
                "edit_generation": fact_check.edit_generation,
                "headline": fact_check.headline,
                "summary": fact_check.summary,
                "article_body": fact_check.article_body,
            },
            "id": str(fact_check.id),
            "claim_id": str(fact_check.claim_id),
            "adjudication_decision_id": str(fact_check.adjudication_decision_id),
            "canonical_claim": fact_check.canonical_claim,
            "verdict": fact_check.verdict,
            "headline": fact_check.headline,
            "summary": fact_check.summary,
            "article_body": fact_check.article_body,
            "publication_status": fact_check.publication_status,
            "version": fact_check.version,
            "edit_generation": fact_check.edit_generation,
            "sources": [source["url"] for source in source_items],
            "source_items": source_items,
            "drafted_by": _actor_payload(fact_check.drafted_by),
            "submitted_for_review_at": fact_check.submitted_for_review_at,
            "reviewed_by": _actor_payload(fact_check.reviewed_by),
            "reviewed_at": fact_check.reviewed_at,
            "published_by": _actor_payload(fact_check.published_by),
            "published_at": fact_check.published_at,
            "archived_at": fact_check.archived_at,
            "created_at": fact_check.created_at,
            "updated_at": fact_check.updated_at,
            "sealed_evidence": sealed_evidence_payload(
                fact_check.adjudication_decision
            ),
        }
    )
    return item


def get_publication_work_item_detail(
    *,
    actor,
    organization,
    resource_type,
    resource_id,
    workflow_kind=WORKFLOW_INITIAL,
):
    if resource_type not in {RESOURCE_ELIGIBLE_CLAIM, RESOURCE_FACT_CHECK}:
        raise PublicationWorkflowNotFound("Publication work item not found.")
    fact_check = None
    if resource_type == RESOURCE_ELIGIBLE_CLAIM:
        if workflow_kind == WORKFLOW_EDITORIAL_REVISION:
            raise PublicationWorkflowNotFound("Publication work item not found.")
        if not _current_decision_queryset(organization).filter(
            claim_id=resource_id
        ).exists():
            raise PublicationWorkflowNotFound("Publication work item not found.")
    else:
        fact_check = (
            _fact_check_queryset(organization, workflow_kind)
            .filter(id=resource_id)
            .first()
        )
        if fact_check is None:
            raise PublicationWorkflowNotFound("Publication work item not found.")

    can_draft = has_capability(
        actor,
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        organization=organization,
    )
    can_publish = has_capability(
        actor,
        PartnerCapability.PUBLISH_FACT_CHECK,
        organization=organization,
    )
    if not (can_draft or can_publish):
        raise PublicationWorkflowAuthorizationError(
            "You do not have permission to view this publication work item."
        )
    if resource_type == RESOURCE_ELIGIBLE_CLAIM:
        if not can_draft:
            raise PublicationWorkflowAuthorizationError(
                "You do not have permission to view drafting work."
        )
        return _eligible_claim_detail(actor, organization, resource_id)
    return _fact_check_detail(actor, organization, fact_check)
