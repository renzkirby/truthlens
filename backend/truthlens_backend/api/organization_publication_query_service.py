"""Organization-scoped read models for the internal publication library."""

from django.contrib.postgres.search import SearchQuery
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, Prefetch, Q

from .evidence_snapshot_schema import (
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)
from .models import (
    FactualCorrectionRequest,
    ModerationCase,
    OfficialFactCheck,
    OfficialFactCheckSource,
    VerificationAssignment,
)
from .organization_service import PartnerCapability, has_capability
from .factual_correction_query_service import can_access_factual_corrections
from .moderation_service import ACTIVE_CASE_STATUSES
from .publication_snapshot_schema import (
    EDITORIAL_REVISION_SCHEMA_VERSION,
    FACTUAL_CORRECTION_SCHEMA_VERSION,
    FIRST_PUBLICATION_SCHEMA_VERSION,
    PublicationSnapshotSchemaError,
    validate_publication_snapshot,
)
from .publication_workflow_query_service import (
    publication_source_payloads,
    sealed_evidence_payload,
)
from .verification_assignment_service import OPEN_ASSIGNMENT_STATUSES


class OrganizationPublicationQueryError(Exception):
    pass


class OrganizationPublicationAuthorizationError(OrganizationPublicationQueryError):
    pass


class OrganizationPublicationNotFound(OrganizationPublicationQueryError):
    pass


RECORD_SEALED = "SEALED"
RECORD_LEGACY_UNSEALED = "LEGACY_UNSEALED"
RECORD_INVALID_SEAL = "INVALID_SEAL"
HISTORY_CURRENT = "CURRENT"
HISTORY_SUPERSEDED = "SUPERSEDED"


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


def _can_read(actor, organization):
    return has_capability(
        actor,
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        organization=organization,
    ) or has_capability(
        actor,
        PartnerCapability.PUBLISH_FACT_CHECK,
        organization=organization,
    )


def _require_read(actor, organization):
    if not _can_read(actor, organization):
        raise OrganizationPublicationAuthorizationError(
            "You do not have permission to view this organization's publications."
        )


def _published_history_filter():
    return Q(published_at__isnull=False) | Q(publication_snapshot__isnull=False)


def _base_queryset(organization):
    return OfficialFactCheck.objects.filter(
        organization=organization,
        claim__isnull=False,
        adjudication_decision__isnull=False,
    ).select_related(
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
        "supersedes__adjudication_decision",
        "publication_snapshot",
        "publication_snapshot__decision_snapshot",
        "supersedes__publication_snapshot",
    )


def _detail_queryset(organization):
    return _base_queryset(organization).prefetch_related(
        Prefetch(
            "source_items",
            queryset=OfficialFactCheckSource.objects.select_related(
                "added_by"
            ).prefetch_related("evidence_links"),
        )
    )


def _publication_snapshot(fact_check):
    try:
        return fact_check.publication_snapshot
    except ObjectDoesNotExist:
        return None


def _record_state(fact_check):
    snapshot = _publication_snapshot(fact_check)
    if snapshot is None:
        return RECORD_LEGACY_UNSEALED
    try:
        payload = validate_publication_snapshot(
            schema_version=snapshot.schema_version,
            payload=snapshot.payload,
        )
        evidence_records = validate_evidence_snapshot(
            schema_version=snapshot.decision_snapshot.schema_version,
            evidence_records=snapshot.decision_snapshot.evidence_records,
        )
    except (PublicationSnapshotSchemaError, EvidenceSnapshotSchemaError):
        return RECORD_INVALID_SEAL

    decision = fact_check.adjudication_decision
    decision_snapshot = snapshot.decision_snapshot
    identity_is_valid = (
        snapshot.fact_check_id == fact_check.id
        and decision_snapshot.decision_id == fact_check.adjudication_decision_id
        and str(decision_snapshot.claim_id) == str(fact_check.claim_id)
        and decision.claim_id == fact_check.claim_id
        and decision.organization_id == fact_check.organization_id
        and decision.canonical_claim == fact_check.canonical_claim
        and decision.verdict == fact_check.verdict
        and payload["fact_check_id"] == str(fact_check.id)
        and payload["claim_id"] == str(fact_check.claim_id)
        and payload["decision_id"] == str(fact_check.adjudication_decision_id)
        and payload["decision_evidence_snapshot_id"]
        == str(snapshot.decision_snapshot_id)
        and payload["organization"]["id"] == str(fact_check.organization_id)
        and payload["article_version"] == fact_check.version
        and fact_check.published_at is not None
        and snapshot.captured_at == fact_check.published_at
        and payload["published_at"] == snapshot.captured_at.isoformat()
        and payload["canonical_claim"] == fact_check.canonical_claim
        and payload["verdict"] == fact_check.verdict
        and payload["headline"] == fact_check.headline
        and payload["summary"] == fact_check.summary
        and payload["article_body"] == fact_check.article_body
    )
    if not identity_is_valid:
        return RECORD_INVALID_SEAL

    revision_kind = _revision_kind(fact_check)
    if snapshot.schema_version == FIRST_PUBLICATION_SCHEMA_VERSION:
        if (
            revision_kind != OfficialFactCheck.RevisionKind.INITIAL
            or fact_check.supersedes_id is not None
        ):
            return RECORD_INVALID_SEAL
    elif snapshot.schema_version == EDITORIAL_REVISION_SCHEMA_VERSION:
        predecessor = fact_check.supersedes
        predecessor_snapshot = (
            _publication_snapshot(predecessor) if predecessor is not None else None
        )
        revision = payload["revision"]
        if (
            revision_kind != OfficialFactCheck.RevisionKind.EDITORIAL_REVISION
            or predecessor is None
            or predecessor.claim_id != fact_check.claim_id
            or predecessor.organization_id != fact_check.organization_id
            or predecessor.adjudication_decision_id
            != fact_check.adjudication_decision_id
            or predecessor_snapshot is None
            or predecessor_snapshot.decision_snapshot_id
            != snapshot.decision_snapshot_id
            or revision["supersedes_fact_check_id"] != str(predecessor.id)
            or revision["supersedes_publication_snapshot_id"]
            != str(predecessor_snapshot.id)
            or revision["predecessor_article_version"] != predecessor.version
            or revision["predecessor_published_at"]
            != predecessor_snapshot.captured_at.isoformat()
            or revision["revision_reason"] != fact_check.revision_reason
            or fact_check.revision_requested_at is None
            or revision["revision_requested_at"]
            != fact_check.revision_requested_at.isoformat()
            or (
                fact_check.revision_requested_by_id is not None
                and revision["revision_requested_by"]["id"]
                != str(fact_check.revision_requested_by_id)
            )
        ):
            return RECORD_INVALID_SEAL
    elif snapshot.schema_version == FACTUAL_CORRECTION_SCHEMA_VERSION:
        predecessor = fact_check.supersedes
        predecessor_snapshot = (
            _publication_snapshot(predecessor) if predecessor is not None else None
        )
        correction = payload["correction"]
        if (
            revision_kind != OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION
            or predecessor is None
            or predecessor.adjudication_decision_id is None
            or predecessor.claim_id != fact_check.claim_id
            or predecessor.organization_id != fact_check.organization_id
            or predecessor_snapshot is None
            or correction["predecessor_fact_check_id"] != str(predecessor.id)
            or correction["predecessor_fact_check_version"]
            != predecessor.version
            or correction["predecessor_decision_id"]
            != str(predecessor.adjudication_decision_id)
            or correction["predecessor_decision_revision"]
            != predecessor.adjudication_decision.revision_number
            or correction["predecessor_decision_evidence_snapshot_id"]
            != str(predecessor_snapshot.decision_snapshot_id)
            or correction["predecessor_publication_snapshot_id"]
            != str(predecessor_snapshot.id)
            or correction["predecessor_published_at"]
            != predecessor_snapshot.captured_at.isoformat()
            or correction["new_decision_id"] != str(decision.id)
            or correction["new_decision_revision"] != decision.revision_number
            or correction["new_decision_evidence_snapshot_id"]
            != str(decision_snapshot.id)
            or decision.supersedes_id != predecessor.adjudication_decision_id
            or correction["correction_reason"] != fact_check.revision_reason
            or fact_check.revision_requested_at is None
            or correction["correction_requested_at"]
            != fact_check.revision_requested_at.isoformat()
            or (
                fact_check.revision_requested_by_id is not None
                and correction["correction_requested_by"]["id"]
                != str(fact_check.revision_requested_by_id)
            )
        ):
            return RECORD_INVALID_SEAL
    else:
        return RECORD_INVALID_SEAL

    evidence_by_id = {item["id"]: item for item in evidence_records}
    for source in payload["sources"]:
        for link in source["lineage"]:
            record = evidence_by_id.get(link["captured_evidence_id"])
            if (
                record is None
                or record["evidence_status"] != "VERIFIED"
                or link["decision_evidence_snapshot_id"]
                != str(snapshot.decision_snapshot_id)
                or (record.get("evidence_url") or "").strip() != source["url"]
            ):
                return RECORD_INVALID_SEAL
    return RECORD_SEALED


def _historical_rows(organization, claim_ids):
    if not claim_ids:
        return []
    return list(
        _base_queryset(organization)
        .filter(
            claim_id__in=claim_ids,
            publication_status__in={
                OfficialFactCheck.PublicationStatus.PUBLISHED,
                OfficialFactCheck.PublicationStatus.ARCHIVED,
            },
        )
        .filter(_published_history_filter())
        .order_by("version", "published_at", "id")
    )


def _ordered_lineage(current, rows):
    nodes = {item.id: item for item in rows if item.claim_id == current.claim_id}
    if current.id not in nodes:
        return [], False
    roots = [item for item in nodes.values() if item.supersedes_id is None]
    children = {}
    for item in nodes.values():
        if item.supersedes_id is None:
            continue
        if item.supersedes_id not in nodes:
            return [], False
        children.setdefault(item.supersedes_id, []).append(item)
    if len(roots) != 1 or any(len(items) != 1 for items in children.values()):
        return [], False

    ordered = []
    seen = set()
    item = roots[0]
    while item is not None:
        if item.id in seen:
            return [], False
        seen.add(item.id)
        ordered.append(item)
        successors = children.get(item.id, [])
        item = successors[0] if successors else None
    if len(seen) != len(nodes) or ordered[-1].id != current.id:
        return [], False
    return ordered, True


def evaluate_publication_lineage_integrity(*, organization, current_publications):
    """Batch-project existing publication lineage integrity for public reads."""

    current_publications = list(current_publications)
    current_ids = {item.id for item in current_publications}
    histories = _historical_rows(
        organization,
        {item.claim_id for item in current_publications},
    )
    history_by_claim = {}
    history_by_id = {}
    for item in histories:
        history_by_claim.setdefault(item.claim_id, []).append(item)
        history_by_id[item.id] = item

    evaluations = {}
    for current_id in current_ids:
        current = history_by_id.get(current_id)
        if current is None:
            evaluations[current_id] = {
                "current": None,
                "lineage": [],
                "lineage_valid": False,
                "record_states": {},
                "all_records_sealed": False,
            }
            continue

        lineage, lineage_valid = _ordered_lineage(
            current,
            history_by_claim.get(current.claim_id, []),
        )
        record_states = (
            {item.id: _record_state(item) for item in lineage}
            if lineage_valid
            else {}
        )
        evaluations[current_id] = {
            "current": current,
            "lineage": lineage,
            "lineage_valid": lineage_valid,
            "record_states": record_states,
            "all_records_sealed": bool(record_states)
            and all(state == RECORD_SEALED for state in record_states.values()),
        }

    return evaluations


def _revision_kind(fact_check):
    return fact_check.revision_kind or OfficialFactCheck.RevisionKind.INITIAL


def _lineage_item(fact_check, current_id):
    return {
        "publication_id": str(fact_check.id),
        "version": fact_check.version,
        "revision_kind": _revision_kind(fact_check),
        "headline": fact_check.headline,
        "published_at": fact_check.published_at,
        "published_by": _actor_payload(fact_check.published_by),
        "history_state": (
            HISTORY_CURRENT if fact_check.id == current_id else HISTORY_SUPERSEDED
        ),
        "revision_reason": fact_check.revision_reason,
    }


def _action_context(current_items, *, include_correction_details=False):
    claim_ids = {item.claim_id for item in current_items}
    correction_queryset = FactualCorrectionRequest.objects.filter(
        claim_id__in=claim_ids,
        status=FactualCorrectionRequest.Status.ACTIVE,
    )
    if include_correction_details:
        active_corrections = {
            item.claim_id: item
            for item in correction_queryset.select_related(
                "moderation_case",
                "proposal",
            )
        }
    else:
        active_corrections = set(
            correction_queryset.values_list("claim_id", flat=True)
        )
    return {
        "active_corrections": active_corrections,
        "active_work": set(
            OfficialFactCheck.objects.filter(
                claim_id__in=claim_ids,
                publication_status__in={
                    OfficialFactCheck.PublicationStatus.DRAFT,
                    OfficialFactCheck.PublicationStatus.IN_REVIEW,
                },
            ).values_list("claim_id", flat=True)
        ),
        "open_assignments": set(
            VerificationAssignment.objects.filter(
                claim_id__in=claim_ids,
                status__in=OPEN_ASSIGNMENT_STATUSES,
            ).values_list("claim_id", flat=True)
        ),
        "active_adjudication": set(
            ModerationCase.objects.filter(
                claim_id__in=claim_ids,
                case_type=ModerationCase.CaseType.ADJUDICATION,
                status__in=ACTIVE_CASE_STATUSES,
                factual_correction_request__isnull=True,
            ).values_list("claim_id", flat=True)
        ),
    }


def _active_correction_proposal(request):
    if request is None:
        return None
    try:
        return request.proposal
    except ObjectDoesNotExist:
        return None


def _factual_correction_workflow(
    *,
    actor,
    organization,
    current,
    selected_is_current,
    record_state,
    lineage_valid,
    lineage_records_sealed,
    action_context,
):
    active_request = action_context["active_corrections"].get(current.claim_id)
    proposal = _active_correction_proposal(active_request)
    concurrency = {
        "expected_predecessor_version": current.version,
        "expected_decision_revision": current.adjudication_decision.revision_number,
        "expected_proposal_version": proposal.version if proposal is not None else 0,
    }
    if active_request is not None:
        return {
            "active_request_id": str(active_request.id),
            "allowed_actions": (
                ["OPEN_FACTUAL_CORRECTION"]
                if can_access_factual_corrections(actor, organization)
                else []
            ),
            "blockers": {
                "REQUEST_FACTUAL_CORRECTION": [
                    {
                        "code": "ACTIVE_CORRECTION_RESERVATION",
                        "detail": (
                            "An active factual-correction request already exists."
                        ),
                    }
                ],
                "OPEN_FACTUAL_CORRECTION": [],
            },
            "concurrency": concurrency,
        }

    request_blockers = []
    if not selected_is_current:
        request_blockers.append(
            {
                "code": "HISTORICAL_PUBLICATION",
                "detail": "A historical publication cannot start correction work.",
            }
        )
    if record_state != RECORD_SEALED:
        request_blockers.append(
            {
                "code": "PUBLICATION_NOT_READY",
                "detail": "A valid sealed current publication is required before "
                "a factual correction can be requested.",
            }
        )
    if not current.adjudication_decision.is_current:
        request_blockers.append(
            {
                "code": "STALE_DECISION_REVISION",
                "detail": "The publication is not bound to the current decision.",
            }
        )
    if sealed_evidence_payload(current.adjudication_decision) is None:
        request_blockers.append(
            {
                "code": "PUBLICATION_NOT_READY",
                "detail": "The current decision has no valid sealed evidence basis.",
            }
        )
    if not lineage_valid or not lineage_records_sealed:
        request_blockers.append(
            {
                "code": "PUBLICATION_NOT_READY",
                "detail": "The complete publication history must be valid and sealed.",
            }
        )
    if current.claim_id in action_context["active_work"]:
        request_blockers.append(
            {
                "code": "ACTIVE_PUBLICATION_WORK_EXISTS",
                "detail": "Competing publication work is active for this claim.",
            }
        )
    if current.claim_id in action_context["open_assignments"]:
        request_blockers.append(
            {
                "code": "ASSIGNMENT_CONFLICT",
                "detail": "Open verification work must be resolved first.",
            }
        )
    if current.claim_id in action_context["active_adjudication"]:
        request_blockers.append(
            {
                "code": "ACTIVE_ADJUDICATION_WORK_EXISTS",
                "detail": "Active Adjudication work must be resolved first.",
            }
        )
    allowed_actions = []
    if (
        not request_blockers
        and has_capability(
            actor,
            PartnerCapability.ADJUDICATE,
            organization=organization,
        )
    ):
        allowed_actions.append("REQUEST_FACTUAL_CORRECTION")
    return {
        "active_request_id": None,
        "allowed_actions": allowed_actions,
        "blockers": {
            "REQUEST_FACTUAL_CORRECTION": request_blockers,
            "OPEN_FACTUAL_CORRECTION": [],
        },
        "concurrency": concurrency,
    }


def _current_blockers(
    current,
    record_state,
    lineage_valid,
    lineage_records_sealed,
    action_context,
):
    blockers = []
    if record_state != RECORD_SEALED:
        blockers.append(
            {
                "code": "PUBLICATION_NOT_READY",
                "detail": "A valid sealed publication record is required before "
                "an editorial revision can be created.",
            }
        )
    decision = current.adjudication_decision
    if not decision.is_current:
        blockers.append(
            {
                "code": "STALE_DECISION_REVISION",
                "detail": "The publication is not bound to the current "
                "adjudication decision.",
            }
        )
    if sealed_evidence_payload(decision) is None:
        blockers.append(
            {
                "code": "PUBLICATION_NOT_READY",
                "detail": "The adjudication decision has no valid sealed evidence "
                "basis.",
            }
        )
    if current.claim_id in action_context["active_corrections"]:
        blockers.append(
            {
                "code": "ACTIVE_CORRECTION_RESERVATION",
                "detail": "An active factual-correction request reserves this claim.",
            }
        )
    if current.claim_id in action_context["active_work"]:
        blockers.append(
            {
                "code": "ACTIVE_PUBLICATION_WORK_EXISTS",
                "detail": "Publication work is already active for this claim.",
            }
        )
    if current.claim_id in action_context["open_assignments"]:
        blockers.append(
            {
                "code": "ASSIGNMENT_CONFLICT",
                "detail": "Open verification work must be resolved before an "
                "editorial revision can be created.",
            }
        )
    if not lineage_valid:
        blockers.append(
            {
                "code": "PUBLICATION_NOT_READY",
                "detail": "The publication history is not a complete linear chain.",
            }
        )
    elif not lineage_records_sealed and record_state == RECORD_SEALED:
        blockers.append(
            {
                "code": "PUBLICATION_NOT_READY",
                "detail": "Every historically published predecessor must have a "
                "valid sealed publication record before revision work can begin.",
            }
        )
    return blockers


def _list_item(
    current,
    lineage,
    lineage_valid,
    action_context,
    *,
    can_create_revision,
):
    lineage_record_states = (
        [_record_state(item) for item in lineage] if lineage_valid else []
    )
    record_state = (
        lineage_record_states[-1]
        if lineage_record_states
        else _record_state(current)
    )
    lineage_records_sealed = bool(lineage_record_states) and all(
        state == RECORD_SEALED for state in lineage_record_states
    )
    blockers = _current_blockers(
        current,
        record_state,
        lineage_valid,
        lineage_records_sealed,
        action_context,
    )
    allowed_actions = []
    if not blockers and can_create_revision:
        allowed_actions.append("CREATE_EDITORIAL_REVISION")
    return {
        "publication_id": str(current.id),
        "current_publication_id": str(current.id),
        "history_state": HISTORY_CURRENT,
        "record_state": record_state,
        "publication_status": current.publication_status,
        "version": current.version,
        "revision_kind": _revision_kind(current),
        "claim": {
            "id": str(current.claim_id),
            "canonical_claim": current.canonical_claim,
        },
        "verdict": current.verdict,
        "headline": current.headline,
        "summary": current.summary,
        "published_at": current.published_at,
        "published_by": _actor_payload(current.published_by),
        "lineage": {
            "has_predecessor": bool(lineage_valid and len(lineage) > 1),
            "previous_versions_count": len(lineage) - 1 if lineage_valid else 0,
        },
        "concurrency": {
            "predecessor_version": current.version,
            "decision_revision": current.adjudication_decision.revision_number,
        },
        "allowed_actions": allowed_actions,
        "blockers": blockers,
    }


def list_organization_publications(
    *, actor, organization, search="", limit=20, offset=0
):
    _require_read(actor, organization)
    queryset = _base_queryset(organization).filter(
        publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED
    )
    if search:
        queryset = queryset.filter(
            search_vector=SearchQuery(search, search_type="plain")
        )
    queryset = queryset.order_by(
        F("published_at").desc(nulls_last=True),
        "id",
    )
    count = queryset.count()
    current_items = list(queryset[offset : offset + limit])
    histories = _historical_rows(
        organization, {item.claim_id for item in current_items}
    )
    history_by_claim = {}
    for item in histories:
        history_by_claim.setdefault(item.claim_id, []).append(item)
    action_context = _action_context(current_items)
    can_create_revision = has_capability(
        actor,
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        organization=organization,
    )
    results = []
    for current in current_items:
        lineage, lineage_valid = _ordered_lineage(
            current, history_by_claim.get(current.claim_id, [])
        )
        results.append(
            _list_item(
                current,
                lineage,
                lineage_valid,
                action_context,
                can_create_revision=can_create_revision,
            )
        )
    return {
        "count": count,
        "limit": limit,
        "offset": offset,
        "organization": _organization_payload(organization),
        "results": results,
    }


def _revision_payload(fact_check, predecessor):
    if fact_check.revision_kind == OfficialFactCheck.RevisionKind.INITIAL:
        return None
    if fact_check.revision_kind is None and fact_check.supersedes_id is None:
        return None
    return {
        "kind": _revision_kind(fact_check),
        "reason": fact_check.revision_reason,
        "requested_by": _actor_payload(fact_check.revision_requested_by),
        "requested_at": fact_check.revision_requested_at,
        "predecessor": (
            {
                "publication_id": str(predecessor.id),
                "version": predecessor.version,
            }
            if predecessor is not None
            else None
        ),
    }


def get_organization_publication_detail(
    *, actor, organization, fact_check_id
):
    selected = (
        _detail_queryset(organization)
        .filter(
            id=fact_check_id,
        )
        .filter(
            Q(
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED
            )
            | (
                Q(
                    publication_status=(
                        OfficialFactCheck.PublicationStatus.ARCHIVED
                    )
                )
                & _published_history_filter()
            )
        )
        .first()
    )
    if selected is None:
        raise OrganizationPublicationNotFound("Publication not found.")
    _require_read(actor, organization)

    current = (
        _base_queryset(organization)
        .filter(
            claim_id=selected.claim_id,
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        .first()
    )
    if current is None:
        raise OrganizationPublicationNotFound("Publication not found.")
    historical = _historical_rows(organization, {selected.claim_id})
    lineage, lineage_valid = _ordered_lineage(current, historical)
    if lineage_valid:
        lineage_ids = [item.id for item in lineage]
        selected_index = lineage_ids.index(selected.id)
        predecessor = lineage[selected_index - 1] if selected_index > 0 else None
        successor = (
            lineage[selected_index + 1]
            if selected_index + 1 < len(lineage)
            else None
        )
    else:
        # The selected published row remains internally inspectable, but an
        # ambiguous/disconnected history must not be presented as ordered lineage.
        lineage = []
        predecessor = None
        successor = None
    action_context = _action_context(
        [current],
        include_correction_details=True,
    )
    lineage_record_states = (
        {item.id: _record_state(item) for item in lineage}
        if lineage_valid
        else {}
    )
    current_record_state = lineage_record_states.get(current.id)
    if current_record_state is None:
        current_record_state = _record_state(current)
    if selected.id == current.id:
        selected_record_state = current_record_state
    else:
        selected_record_state = lineage_record_states.get(selected.id)
    if selected_record_state is None:
        selected_record_state = _record_state(selected)
    lineage_records_sealed = bool(lineage_record_states) and all(
        state == RECORD_SEALED for state in lineage_record_states.values()
    )
    current_blockers = _current_blockers(
        current,
        current_record_state,
        lineage_valid,
        lineage_records_sealed,
        action_context,
    )
    allowed_actions = []
    if (
        selected.id == current.id
        and not current_blockers
        and has_capability(
            actor,
            PartnerCapability.CREATE_FACT_CHECK_DRAFT,
            organization=organization,
        )
    ):
        allowed_actions.append("CREATE_EDITORIAL_REVISION")

    source_items = publication_source_payloads(selected)
    factual_correction_workflow = _factual_correction_workflow(
        actor=actor,
        organization=organization,
        current=current,
        selected_is_current=selected.id == current.id,
        record_state=selected_record_state,
        lineage_valid=lineage_valid,
        lineage_records_sealed=lineage_records_sealed,
        action_context=action_context,
    )
    return {
        "selected_publication_id": str(selected.id),
        "current_publication_id": str(current.id),
        "history_state": (
            HISTORY_CURRENT if selected.id == current.id else HISTORY_SUPERSEDED
        ),
        "record_state": selected_record_state,
        "organization": _organization_payload(organization),
        "claim": {
            "id": str(selected.claim_id),
            "canonical_claim": selected.canonical_claim,
        },
        "decision": {
            "id": str(selected.adjudication_decision_id),
            "revision_number": selected.adjudication_decision.revision_number,
            "canonical_claim": selected.adjudication_decision.canonical_claim,
            "verdict": selected.adjudication_decision.verdict,
            "rationale": selected.adjudication_decision.rationale,
            "decided_by": _actor_payload(selected.adjudication_decision.decided_by),
            "decided_at": selected.adjudication_decision.decided_at,
        },
        "article": {
            "headline": selected.headline,
            "summary": selected.summary,
            "article_body": selected.article_body,
            "version": selected.version,
            "revision_kind": _revision_kind(selected),
            "publication_status": selected.publication_status,
        },
        "source_items": source_items,
        "sealed_evidence": sealed_evidence_payload(
            selected.adjudication_decision
        ),
        "published_by": _actor_payload(selected.published_by),
        "published_at": selected.published_at,
        "revision": _revision_payload(selected, predecessor),
        "lineage": [
            _lineage_item(item, current.id) for item in lineage
        ],
        "predecessor": (
            {
                "publication_id": str(predecessor.id),
                "version": predecessor.version,
            }
            if predecessor is not None
            else None
        ),
        "successor": (
            {
                "publication_id": str(successor.id),
                "version": successor.version,
            }
            if successor is not None
            else None
        ),
        "concurrency": {
            "predecessor_version": current.version,
            "article_version": current.version,
            "edit_generation": current.edit_generation,
            "decision_revision": current.adjudication_decision.revision_number,
        },
        "allowed_actions": allowed_actions,
        "blockers": current_blockers if selected.id == current.id else [],
        "factual_correction_workflow": factual_correction_workflow,
    }
