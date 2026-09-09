import logging
import uuid

from django.core.exceptions import (
    ValidationError,
)
from django.core.validators import (
    URLValidator,
)
from django.db import IntegrityError, transaction
from django.utils import timezone

from .evidence_snapshot_schema import (
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)
from .publication_snapshot_schema import (
    EDITORIAL_REVISION_SCHEMA_VERSION,
    FACTUAL_CORRECTION_SCHEMA_VERSION,
    FIRST_PUBLICATION_SCHEMA_VERSION,
    PublicationSnapshotSchemaError,
    validate_publication_snapshot,
)
from .factual_correction_proposal_schema import (
    FactualCorrectionProposalSchemaError,
    validate_factual_correction_proposal,
)

from .models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    Claim,
    EvidenceSubmission,
    FactualCorrectionProposal,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OfficialFactCheckSource,
    OfficialFactCheckSourceEvidenceLink,
    Organization,
    OrganizationMembership,
    VerificationAssignment,
)

from .organization_service import (
    PartnerCapability,
    get_membership_capabilities,
)
from .verification_assignment_service import (
    VerificationAssignmentConflict,
    complete_verification_assignment,
    get_open_verification_assignment,
)

logger = logging.getLogger(__name__)


def _queue_fact_check_index(
    fact_check_id,
):
    """
    Best-effort background indexing.

    Publication has already committed at this
    point, so a broker/indexing failure must not
    undo or invalidate the publication.
    """

    try:
        from .tasks import (
            index_official_fact_check_task,
        )

        (index_official_fact_check_task.delay(str(fact_check_id)))

    except Exception as error:
        logger.exception(
            "Failed to queue fact-check " "indexing for %s: %s",
            fact_check_id,
            error,
        )


class PublishingError(Exception):
    pass


class PublishingAuthorizationError(PublishingError):
    pass


class InvalidPublicationTransition(PublishingError):
    pass


class InvalidFactCheckContent(PublishingError):
    pass


class PublishingConflict(PublishingError):
    pass


ACTIVE_DRAFT_STATUSES = {
    OfficialFactCheck.PublicationStatus.DRAFT,
    OfficialFactCheck.PublicationStatus.IN_REVIEW,
}


_url_validator = URLValidator(
    schemes=[
        "http",
        "https",
    ]
)


def _require_locked_capability(
    actor,
    capability,
    *,
    organization,
):
    if not actor or not actor.is_authenticated:
        raise PublishingAuthorizationError(
            "You do not have permission to perform this publication action."
        )

    membership = (
        OrganizationMembership.objects.select_related("organization")
        .select_for_update(of=("self",))
        .filter(
            user=actor,
            organization=organization,
        )
        .first()
    )
    capabilities = (
        get_membership_capabilities(membership) if membership is not None else set()
    )
    if capability in capabilities:
        return

    raise PublishingAuthorizationError(
        "You do not have permission to " "perform this publication action."
    )


def _publication_conflict():
    return PublishingConflict(
        "The adjudication decision used for this fact-check is no longer "
        "current. Create a new draft from the latest decision."
    )


def _get_decision_publication_identity(decision):
    identity = (
        AdjudicationDecision.objects.filter(pk=getattr(decision, "pk", None))
        .values(
            "claim_id",
            "organization_id",
        )
        .first()
    )
    if (
        identity is None
        or identity["claim_id"] is None
        or identity["organization_id"] is None
    ):
        raise _publication_conflict()
    return {
        **identity,
        "decision_id": decision.pk,
        "fact_check_id": None,
    }


def _get_fact_check_publication_identity(fact_check):
    identity = (
        OfficialFactCheck.objects.filter(pk=getattr(fact_check, "pk", None))
        .values(
            "claim_id",
            "organization_id",
            "adjudication_decision_id",
        )
        .first()
    )
    if (
        identity is None
        or identity["claim_id"] is None
        or identity["organization_id"] is None
        or identity["adjudication_decision_id"] is None
    ):
        raise _publication_conflict()
    return {
        "claim_id": identity["claim_id"],
        "organization_id": identity["organization_id"],
        "decision_id": identity["adjudication_decision_id"],
        "fact_check_id": fact_check.pk,
    }


def _parse_uuid_identity(value, field_name):
    if isinstance(value, bool):
        raise InvalidFactCheckContent(f"{field_name} must be a valid UUID.")
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise InvalidFactCheckContent(f"{field_name} must be a valid UUID.") from error


def _parse_expected_version(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidFactCheckContent(f"{field_name} must be a positive integer.")
    return value


def _get_editorial_revision_identity(*, predecessor_id, organization_id):
    predecessor_id = _parse_uuid_identity(predecessor_id, "predecessor_id")
    organization_id = _parse_uuid_identity(organization_id, "organization_id")
    identity = (
        OfficialFactCheck.objects.filter(pk=predecessor_id)
        .values(
            "claim_id",
            "adjudication_decision_id",
        )
        .first()
    )
    if (
        identity is None
        or identity["claim_id"] is None
        or identity["adjudication_decision_id"] is None
    ):
        raise PublishingConflict(
            "The requested publication predecessor is unavailable."
        )
    return {
        "claim_id": identity["claim_id"],
        "organization_id": organization_id,
        "decision_id": identity["adjudication_decision_id"],
        "fact_check_id": predecessor_id,
    }


def _get_editorial_replacement_identity(
    *,
    revision_id,
    predecessor_id,
    organization_id,
):
    revision_id = _parse_uuid_identity(revision_id, "revision_id")
    predecessor_id = _parse_uuid_identity(predecessor_id, "predecessor_id")
    organization_id = _parse_uuid_identity(organization_id, "organization_id")
    identity = (
        OfficialFactCheck.objects.filter(pk=revision_id)
        .values("claim_id", "adjudication_decision_id")
        .first()
    )
    if (
        identity is None
        or identity["claim_id"] is None
        or identity["adjudication_decision_id"] is None
    ):
        raise PublishingConflict("The requested editorial revision is unavailable.")
    return {
        "claim_id": identity["claim_id"],
        "organization_id": organization_id,
        "decision_id": identity["adjudication_decision_id"],
        "fact_check_id": revision_id,
        "predecessor_id": predecessor_id,
    }


def _lock_publication_context(*, identity, actor, capability):
    """Lock a publication mutation using the shared Claim-first protocol.

    The canonical order is Claim, open Assignment, Organization, actor
    Membership, current AdjudicationDecision, its evidence snapshot, all claim
    fact-checks, their source rows, their evidence-lineage rows, then sealed
    publication records, then factual-correction reservations. All service
    mutation paths use this helper, and the nested assignment-completion helper
    reacquires only Claim then Assignment.
    """

    try:
        locked_claim = Claim.objects.select_for_update().get(pk=identity["claim_id"])
    except Claim.DoesNotExist as error:
        raise _publication_conflict() from error

    assignment = get_open_verification_assignment(
        locked_claim,
        lock=True,
    )

    try:
        organization = Organization.objects.select_for_update().get(
            pk=identity["organization_id"]
        )
    except Organization.DoesNotExist as error:
        raise _publication_conflict() from error

    if assignment is not None and (
        assignment.status != VerificationAssignment.Status.ACTIVE
        or assignment.organization_id != organization.id
    ):
        raise PublishingConflict(
            "The organization responsible for this claim changed after the "
            "publication workflow was opened."
        )

    _require_locked_capability(
        actor,
        capability,
        organization=organization,
    )

    current_decision = (
        AdjudicationDecision.objects.select_for_update(of=("self",))
        .filter(
            claim=locked_claim,
            is_current=True,
        )
        .first()
    )
    if (
        current_decision is None
        or current_decision.id != identity["decision_id"]
        or current_decision.organization_id != organization.id
    ):
        raise PublishingConflict(
            "The adjudication decision used for this fact-check is no longer "
            "current. Create a new draft from the latest decision."
        )

    decision_snapshot = (
        AdjudicationDecisionEvidenceSnapshot.objects.select_for_update(of=("self",))
        .filter(decision=current_decision)
        .first()
    )
    snapshot_records = _validate_decision_snapshot(
        decision_snapshot,
        decision=current_decision,
        claim=locked_claim,
    )

    fact_checks = list(
        OfficialFactCheck.objects.select_for_update(of=("self",))
        .filter(claim=locked_claim)
        .order_by(
            "version",
            "created_at",
            "id",
        )
    )
    list(
        OfficialFactCheckSource.objects.select_for_update(of=("self",))
        .filter(fact_check__claim=locked_claim)
        .order_by(
            "fact_check_id",
            "created_at",
            "id",
        )
    )
    list(
        OfficialFactCheckSourceEvidenceLink.objects.select_for_update(of=("self",))
        .filter(source__fact_check__claim=locked_claim)
        .order_by(
            "source_id",
            "captured_evidence_id",
            "id",
        )
    )
    publication_snapshots = list(
        OfficialFactCheckPublicationSnapshot.objects.select_for_update(of=("self",))
        .filter(fact_check__claim=locked_claim)
        .order_by("fact_check_id", "id")
    )
    correction_requests = list(
        FactualCorrectionRequest.objects.select_for_update(of=("self",))
        .filter(claim=locked_claim)
        .order_by("requested_at", "id")
    )

    locked_fact_check = None
    if identity["fact_check_id"] is not None:
        locked_fact_check = next(
            (item for item in fact_checks if item.id == identity["fact_check_id"]),
            None,
        )
        if (
            locked_fact_check is None
            or locked_fact_check.organization_id != organization.id
            or locked_fact_check.adjudication_decision_id != current_decision.id
        ):
            raise _publication_conflict()

    return {
        "claim": locked_claim,
        "assignment": assignment,
        "organization": organization,
        "decision": current_decision,
        "decision_snapshot": decision_snapshot,
        "snapshot_records": snapshot_records,
        "fact_checks": fact_checks,
        "fact_check": locked_fact_check,
        "publication_snapshots": publication_snapshots,
        "correction_requests": correction_requests,
    }


def _ensure_no_active_correction_reservation(context):
    if any(
        request.status == FactualCorrectionRequest.Status.ACTIVE
        for request in context["correction_requests"]
    ):
        raise PublishingConflict(
            "An active factual correction request reserves publication work for "
            "this claim."
        )


def _normalize_source_urls(
    source_urls,
):
    if source_urls is None:
        return []

    if not isinstance(
        source_urls,
        (
            list,
            tuple,
        ),
    ):
        raise InvalidFactCheckContent("source_urls must be a list.")

    normalized = []
    seen = set()

    for raw_url in source_urls:
        if not isinstance(
            raw_url,
            str,
        ):
            raise InvalidFactCheckContent("Every source URL must be " "a string.")

        url = raw_url.strip()

        if not url:
            continue

        if len(url) > 2000:
            raise InvalidFactCheckContent("A source URL exceeds the " "maximum length.")

        try:
            _url_validator(url)

        except ValidationError as error:
            raise InvalidFactCheckContent(f"Invalid source URL: {url}") from error

        if url in seen:
            continue

        seen.add(url)
        normalized.append(url)

    return normalized


def _snapshot_conflict():
    return PublishingConflict(
        "The current adjudication decision does not have a valid decision-time "
        "evidence snapshot. Publication cannot continue."
    )


def _is_expected_publication_integrity_conflict(error):
    cause = getattr(error, "__cause__", None)
    diagnostic = getattr(cause, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name in {
        "uniq_published_fact_check_claim",
        "uniq_reserved_fact_check_successor",
        "api_officialfactcheckpublicationsnapshot_fact_check_id_key",
    }:
        return True
    message = str(error).lower()
    return (
        "officialfactcheckpublicationsnapshot.fact_check_id" in message
        or "uniq_published_fact_check_claim" in message
        or "uniq_reserved_fact_check_successor" in message
    )


def _validate_decision_snapshot(snapshot, *, decision, claim):
    if (
        snapshot is None
        or snapshot.decision_id != decision.id
        or str(snapshot.claim_id) != str(claim.id)
    ):
        raise _snapshot_conflict()

    try:
        return validate_evidence_snapshot(
            schema_version=snapshot.schema_version,
            evidence_records=snapshot.evidence_records,
        )
    except EvidenceSnapshotSchemaError as error:
        raise _snapshot_conflict() from error


def _validate_predecessor_publication_snapshot(
    publication_snapshot,
    *,
    predecessor,
    organization,
):
    decision = predecessor.adjudication_decision
    decision_snapshot = (
        publication_snapshot.decision_snapshot
        if publication_snapshot is not None
        else None
    )
    if (
        publication_snapshot is None
        or publication_snapshot.fact_check_id != predecessor.id
        or decision_snapshot is None
        or publication_snapshot.decision_snapshot_id != decision_snapshot.id
        or decision_snapshot.decision_id != decision.id
        or str(decision_snapshot.claim_id) != str(predecessor.claim_id)
    ):
        raise PublishingConflict(
            "The published predecessor does not have a valid sealed publication "
            "record. Historical reconstruction requires a separate workflow."
        )
    try:
        evidence_records = validate_evidence_snapshot(
            schema_version=decision_snapshot.schema_version,
            evidence_records=decision_snapshot.evidence_records,
        )
        payload = validate_publication_snapshot(
            schema_version=publication_snapshot.schema_version,
            payload=publication_snapshot.payload,
        )
    except (EvidenceSnapshotSchemaError, PublicationSnapshotSchemaError) as error:
        raise PublishingConflict(
            "The published predecessor's sealed publication record is invalid."
        ) from error

    expected_identities = {
        "claim_id": str(predecessor.claim_id),
        "fact_check_id": str(predecessor.id),
        "decision_id": str(decision.id),
        "decision_evidence_snapshot_id": str(decision_snapshot.id),
    }
    if (
        decision.claim_id != predecessor.claim_id
        or decision.organization_id != predecessor.organization_id
        or predecessor.organization_id != organization.id
        or predecessor.adjudication_decision_id != decision.id
        or predecessor.canonical_claim != decision.canonical_claim
        or predecessor.verdict != decision.verdict
        or any(
            payload[field] != expected_value
            for field, expected_value in expected_identities.items()
        )
        or payload["organization"]["id"] != str(organization.id)
    ):
        raise PublishingConflict(
            "The published predecessor's sealed identities are inconsistent."
        )
    if (
        payload["article_version"] != predecessor.version
        or payload["canonical_claim"] != decision.canonical_claim
        or payload["verdict"] != decision.verdict
        or payload["headline"] != predecessor.headline
        or payload["summary"] != predecessor.summary
        or payload["article_body"] != predecessor.article_body
        or predecessor.published_at is None
        or predecessor.published_at != publication_snapshot.captured_at
        or payload["published_at"] != publication_snapshot.captured_at.isoformat()
    ):
        raise PublishingConflict(
            "The published predecessor's sealed decision state is inconsistent."
        )
    evidence_by_id = {record["id"]: record for record in evidence_records}
    for source in payload["sources"]:
        for link in source["lineage"]:
            record = evidence_by_id.get(link["captured_evidence_id"])
            if (
                link["decision_evidence_snapshot_id"] != str(decision_snapshot.id)
                or record is None
                or record["evidence_status"]
                != EvidenceSubmission.EvidenceStatus.VERIFIED
                or _normalize_snapshot_source_url(record["evidence_url"])
                != source["url"]
            ):
                raise PublishingConflict(
                    "The published predecessor's sealed source lineage is invalid."
                )
    return {
        "payload": payload,
        "decision": decision,
        "decision_snapshot": decision_snapshot,
        "evidence_records": evidence_records,
    }


def _validate_editorial_history_edge(*, predecessor, successor, nodes):
    predecessor_node = nodes[predecessor.id]
    successor_node = nodes[successor.id]
    predecessor_snapshot = predecessor_node["snapshot"]
    successor_snapshot = successor_node["snapshot"]
    revision = successor_node["payload"].get("revision")
    if (
        successor.revision_kind
        != OfficialFactCheck.RevisionKind.EDITORIAL_REVISION
        or successor.claim_id != predecessor.claim_id
        or successor.organization_id != predecessor.organization_id
        or successor.adjudication_decision_id
        != predecessor.adjudication_decision_id
        or successor.version <= predecessor.version
        or successor_snapshot.schema_version
        != EDITORIAL_REVISION_SCHEMA_VERSION
        or not isinstance(revision, dict)
        or revision.get("supersedes_fact_check_id") != str(predecessor.id)
        or revision.get("supersedes_publication_snapshot_id")
        != str(predecessor_snapshot.id)
        or revision.get("predecessor_article_version") != predecessor.version
        or revision.get("predecessor_published_at")
        != predecessor_snapshot.captured_at.isoformat()
        or revision.get("revision_reason") != successor.revision_reason
        or successor.revision_requested_at is None
        or revision.get("revision_requested_at")
        != successor.revision_requested_at.isoformat()
        or (
            successor.revision_requested_by_id is not None
            and revision.get("revision_requested_by", {}).get("id")
            != str(successor.revision_requested_by_id)
        )
    ):
        raise PublishingConflict(
            "The publication revision chain is malformed or inconsistent."
        )


def _validate_factual_correction_history_edge(
    *, predecessor, successor, nodes, organization
):
    predecessor_node = nodes[predecessor.id]
    successor_node = nodes[successor.id]
    predecessor_snapshot = predecessor_node["snapshot"]
    successor_snapshot = successor_node["snapshot"]
    predecessor_decision = predecessor_node["decision"]
    successor_decision = successor_node["decision"]
    predecessor_decision_snapshot = predecessor_node["decision_snapshot"]
    successor_decision_snapshot = successor_node["decision_snapshot"]
    correction = successor_node["payload"].get("correction")
    if (
        successor.revision_kind
        != OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION
        or successor_snapshot.schema_version != FACTUAL_CORRECTION_SCHEMA_VERSION
        or not isinstance(correction, dict)
        or successor.claim_id != predecessor.claim_id
        or successor.organization_id != predecessor.organization_id
        or successor.organization_id != organization.id
        or successor.version <= predecessor.version
        or successor_decision.supersedes_id != predecessor_decision.id
        or successor_decision.revision_number
        != predecessor_decision.revision_number + 1
        or successor_decision.claim_id != predecessor_decision.claim_id
        or successor_decision.organization_id != predecessor_decision.organization_id
        or correction.get("predecessor_decision_id")
        != str(predecessor_decision.id)
        or correction.get("predecessor_decision_revision")
        != predecessor_decision.revision_number
        or correction.get("predecessor_decision_evidence_snapshot_id")
        != str(predecessor_decision_snapshot.id)
        or correction.get("predecessor_fact_check_id") != str(predecessor.id)
        or correction.get("predecessor_fact_check_version") != predecessor.version
        or correction.get("predecessor_publication_snapshot_id")
        != str(predecessor_snapshot.id)
        or correction.get("predecessor_published_at")
        != predecessor_snapshot.captured_at.isoformat()
        or correction.get("new_decision_id") != str(successor_decision.id)
        or correction.get("new_decision_revision")
        != successor_decision.revision_number
        or correction.get("new_decision_evidence_snapshot_id")
        != str(successor_decision_snapshot.id)
    ):
        raise PublishingConflict(
            "The factual correction publication transition is malformed."
        )

    request = (
        FactualCorrectionRequest.objects.select_related("moderation_case")
        .filter(pk=correction["correction_request_id"])
        .first()
    )
    proposal = FactualCorrectionProposal.objects.filter(
        pk=correction["prepared_proposal_id"]
    ).first()
    if (
        request is None
        or proposal is None
        # A committed historical correction must have completed its
        # reservation. The final handoff may move these lifecycle rows
        # inside one transaction before validating the new history.
        or request.status != FactualCorrectionRequest.Status.COMPLETED
        or request.claim_id != successor.claim_id
        or request.organization_id != successor.organization_id
        or request.predecessor_decision_id != predecessor_decision.id
        or request.predecessor_fact_check_id != predecessor.id
        or request.predecessor_publication_snapshot_id != predecessor_snapshot.id
        or request.moderation_case.case_type
        != ModerationCase.CaseType.ADJUDICATION
        or request.moderation_case.claim_id != successor.claim_id
        or request.moderation_case.organization_id != successor.organization_id
        or request.moderation_case.status != ModerationCase.Status.RESOLVED
        or request.moderation_case.resolved_at is None
        or successor_decision.moderation_case_id != request.moderation_case_id
        or successor_decision.decision_source
        != AdjudicationDecision.DecisionSource.HUMAN_REVIEW
        or proposal.correction_request_id != request.id
        or proposal.status != FactualCorrectionProposal.Status.PREPARED
        or proposal.version != correction["prepared_proposal_version"]
        or proposal.prepared_payload_schema_version
        != correction["prepared_payload_schema_version"]
        or proposal.prepared_payload is None
        or proposal.prepared_at is None
    ):
        raise PublishingConflict(
            "The factual correction request or proposal history is inconsistent."
        )
    try:
        proposal_payload = validate_factual_correction_proposal(
            schema_version=proposal.prepared_payload_schema_version,
            payload=proposal.prepared_payload,
        )
    except FactualCorrectionProposalSchemaError as error:
        raise PublishingConflict(
            "The historical factual correction proposal is malformed."
        ) from error

    expected_predecessor = {
        "decision_id": str(predecessor_decision.id),
        "decision_revision": predecessor_decision.revision_number,
        "fact_check_id": str(predecessor.id),
        "fact_check_version": predecessor.version,
        "publication_snapshot_id": str(predecessor_snapshot.id),
        "publication_snapshot_schema_version": predecessor_snapshot.schema_version,
        "published_at": predecessor_snapshot.captured_at.isoformat(),
    }
    proposed_evidence = [
        item["record"] for item in proposal_payload["evidence_basis"]["items"]
    ]
    sealed_sources = {
        source["url"]: source for source in successor_node["payload"]["sources"]
    }
    proposed_sources = {
        source["url"]: source for source in proposal_payload["sources"]
    }
    if (
        proposal_payload["proposal_id"] != str(proposal.id)
        or proposal_payload["proposal_version"] != proposal.version
        or proposal_payload["correction_request_id"] != str(request.id)
        or proposal_payload["claim_id"] != str(successor.claim_id)
        or proposal_payload["correction_case_id"]
        != str(request.moderation_case_id)
        or proposal_payload["organization"]["id"]
        != str(successor.organization_id)
        or proposal_payload["organization"] != proposal.organization_snapshot
        or proposal_payload["predecessor"] != expected_predecessor
        or proposal_payload["decision"]
        != {
            "verdict": successor_decision.verdict,
            "canonical_claim": successor_decision.canonical_claim,
            "rationale": successor_decision.rationale,
        }
        or proposal_payload["decision"]
        != {
            "verdict": proposal.verdict,
            "canonical_claim": proposal.canonical_claim,
            "rationale": proposal.rationale,
        }
        or proposal_payload["article"]
        != {
            "headline": successor.headline,
            "summary": successor.summary,
            "article_body": successor.article_body,
        }
        or proposal_payload["article"]
        != {
            "headline": proposal.headline,
            "summary": proposal.summary,
            "article_body": proposal.article_body,
        }
        or [source["url"] for source in proposal_payload["sources"]]
        != proposal.source_urls
        or proposed_evidence != successor_node["evidence_records"]
        or proposal_payload["evidence_basis"]["schema_version"]
        != successor_decision_snapshot.schema_version
        or successor_decision.verification_run_id != proposal.verification_run_id
        or (
            proposal_payload["verification_run"] is None
            and successor_decision.verification_run_id is not None
        )
        or (
            proposal_payload["verification_run"] is not None
            and proposal_payload["verification_run"]["id"]
            != str(successor_decision.verification_run_id)
        )
        or set(sealed_sources) != set(proposed_sources)
        or correction["correction_reason"] != request.correction_reason
        or correction["correction_requested_by"] != request.requested_by_snapshot
        or correction["correction_requested_at"] != request.requested_at.isoformat()
        or correction["approved_by"] != proposal.prepared_by_snapshot
        or correction["approved_at"] != proposal.prepared_at.isoformat()
        or proposal_payload["approval"]["actor"] != correction["approved_by"]
        or proposal_payload["approval"]["prepared_at"]
        != correction["approved_at"]
        or successor.revision_reason != request.correction_reason
        or successor.revision_requested_at != request.requested_at
        or (
            successor.revision_requested_by_id is not None
            and correction["correction_requested_by"]["id"]
            != str(successor.revision_requested_by_id)
        )
        or (
            successor_decision.decided_by_id is not None
            and correction["approved_by"]["id"]
            != str(successor_decision.decided_by_id)
        )
    ):
        raise PublishingConflict(
            "The factual correction publication provenance is inconsistent."
        )
    for source_url, proposed_source in proposed_sources.items():
        sealed_source = sealed_sources[source_url]
        if (
            sealed_source["is_editorially_selected"] is not True
            or {
                link["captured_evidence_id"] for link in sealed_source["lineage"]
            }
            != {link["evidence_id"] for link in proposed_source["evidence"]}
        ):
            raise PublishingConflict(
                "The corrected publication source provenance is inconsistent."
            )


def _validate_complete_publication_history(
    *,
    predecessor,
    fact_checks,
    publication_snapshots,
    organization,
):
    """Validate one complete immutable publication history across decisions."""

    snapshots_by_fact_check_id = {
        item.fact_check_id: item for item in publication_snapshots
    }
    published_history = {
        item.id: item
        for item in fact_checks
        if (
            item.publication_status
            == OfficialFactCheck.PublicationStatus.PUBLISHED
            or item.published_at is not None
            or item.id in snapshots_by_fact_check_id
        )
    }
    if predecessor.id not in published_history:
        raise PublishingConflict("The publication revision chain is incomplete.")

    nodes = {}
    for item in published_history.values():
        if item.publication_status not in {
            OfficialFactCheck.PublicationStatus.PUBLISHED,
            OfficialFactCheck.PublicationStatus.ARCHIVED,
        }:
            raise PublishingConflict(
                "The stored publication history has an invalid lifecycle state."
            )
        snapshot = snapshots_by_fact_check_id.get(item.id)
        validated = _validate_predecessor_publication_snapshot(
            snapshot,
            predecessor=item,
            organization=organization,
        )
        nodes[item.id] = {"snapshot": snapshot, **validated}

    roots = []
    children_by_predecessor_id = {}
    for item in published_history.values():
        if item.supersedes_id is None:
            roots.append(item)
            continue
        if item.supersedes_id not in published_history:
            raise PublishingConflict(
                "The publication revision chain is disconnected."
            )
        children_by_predecessor_id.setdefault(item.supersedes_id, []).append(item)

    if any(len(children) > 1 for children in children_by_predecessor_id.values()):
        raise PublishingConflict(
            "The publication revision chain is branched or ambiguous."
        )
    if len(roots) != 1:
        raise PublishingConflict(
            "The publication revision chain is cyclic, disconnected, or ambiguous."
        )

    root = roots[0]
    if (
        root.revision_kind
        not in {None, OfficialFactCheck.RevisionKind.INITIAL}
        or nodes[root.id]["snapshot"].schema_version
        != FIRST_PUBLICATION_SCHEMA_VERSION
    ):
        raise PublishingConflict(
            "The publication revision chain has uncertain root provenance."
        )

    visited = set()
    current = root
    while current is not None:
        if current.id in visited:
            raise PublishingConflict(
                "The publication revision chain contains a cycle."
            )
        visited.add(current.id)
        children = children_by_predecessor_id.get(current.id, [])
        if not children:
            break
        successor = children[0]
        if successor.revision_kind == OfficialFactCheck.RevisionKind.EDITORIAL_REVISION:
            _validate_editorial_history_edge(
                predecessor=current,
                successor=successor,
                nodes=nodes,
            )
        elif successor.revision_kind == (
            OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION
        ):
            _validate_factual_correction_history_edge(
                predecessor=current,
                successor=successor,
                nodes=nodes,
                organization=organization,
            )
        else:
            raise PublishingConflict(
                "The publication revision chain has unsupported provenance."
            )
        current = successor

    if current.id != predecessor.id or visited != set(published_history):
        raise PublishingConflict(
            "The selected predecessor is not the unique tip of the stored "
            "publication history."
        )
    return nodes[predecessor.id]["snapshot"]


def _validate_editorial_revision_chain(
    *,
    predecessor,
    fact_checks,
    publication_snapshots,
    decision,
    decision_snapshot,
    organization,
):
    """Compatibility wrapper returning the selected tip's exact original seal."""

    if (
        predecessor.adjudication_decision_id != decision.id
        or decision_snapshot.decision_id != decision.id
        or str(decision_snapshot.claim_id) != str(predecessor.claim_id)
    ):
        raise PublishingConflict(
            "The selected publication tip does not match its decision evidence."
        )
    return _validate_complete_publication_history(
        predecessor=predecessor,
        fact_checks=fact_checks,
        publication_snapshots=publication_snapshots,
        organization=organization,
    )


def _inherited_editorial_source_urls(payload):
    inherited = []
    seen = set()
    for source in payload["sources"]:
        if source["is_editorially_selected"] is not True:
            continue
        raw_url = source["url"]
        try:
            normalized = _normalize_source_urls([raw_url])
        except InvalidFactCheckContent as error:
            raise PublishingConflict(
                "The predecessor's sealed editorial source selection is invalid."
            ) from error
        if len(normalized) != 1 or normalized[0] != raw_url or raw_url in seen:
            raise PublishingConflict(
                "The predecessor's sealed editorial source selection is invalid."
            )
        seen.add(raw_url)
        inherited.append(raw_url)
    return inherited


def _revision_content_value(value, fallback, *, field_name, required=False):
    inherited = value is None
    selected = fallback if inherited else value
    if not isinstance(selected, str):
        raise InvalidFactCheckContent(f"{field_name} must be a string.")
    normalized = selected.strip()
    if required and not normalized:
        raise InvalidFactCheckContent(f"{field_name} is required.")
    return selected if inherited else normalized


def _normalize_snapshot_source_url(raw_url):
    if not isinstance(raw_url, str):
        return None
    url = raw_url.strip()
    if not url or len(url) > 2000:
        return None
    try:
        _url_validator(url)
    except ValidationError:
        return None
    return url


def _snapshot_record_sort_key(record):
    submitted_at = record["submitted_at"]
    return (
        submitted_at is None,
        submitted_at or "",
        str(record["id"]),
    )


def _sync_snapshot_evidence_sources(
    fact_check,
    *,
    actor,
    snapshot,
    snapshot_records,
):
    records_by_url = {}
    for record in sorted(snapshot_records, key=_snapshot_record_sort_key):
        if record["evidence_status"] != "VERIFIED":
            continue
        url = _normalize_snapshot_source_url(record["evidence_url"])
        if url is not None:
            records_by_url.setdefault(url, []).append(record)

    for url, records in records_by_url.items():
        title = next(
            (
                record["evidence_caption"]
                for record in records
                if isinstance(record["evidence_caption"], str)
                and record["evidence_caption"].strip()
            ),
            None,
        )
        source, _created = OfficialFactCheckSource.objects.get_or_create(
            fact_check=fact_check,
            url=url,
            defaults={
                "title": title,
                "added_by": actor,
                "source_type": (OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE),
                "is_editorially_selected": False,
            },
        )
        for record in records:
            try:
                link, created = (
                    OfficialFactCheckSourceEvidenceLink.objects.get_or_create(
                        source=source,
                        captured_evidence_id=record["id"],
                        defaults={"snapshot": snapshot},
                    )
                )

                if link.snapshot_id != snapshot.id:
                    raise PublishingConflict(
                        "An existing source-lineage association belongs "
                        "to a different decision snapshot."
                    )

                if not created:
                    link.full_clean()

            except ValidationError as error:
                raise PublishingConflict(
                    "The existing source-lineage association is invalid."
                ) from error


def _add_editorial_sources(
    fact_check,
    *,
    actor,
    normalized_urls,
):
    for url in normalized_urls:
        source, created = OfficialFactCheckSource.objects.get_or_create(
            fact_check=fact_check,
            url=url,
            defaults={
                "added_by": actor,
                "source_type": OfficialFactCheckSource.SourceType.MODERATOR_ADDED,
                "is_editorially_selected": True,
            },
        )
        if not created and source.is_editorially_selected is not True:
            source.is_editorially_selected = True
            source.save(update_fields=["is_editorially_selected"])


def _replace_moderator_sources(
    fact_check,
    *,
    actor,
    source_urls,
):
    normalized_urls = _normalize_source_urls(source_urls)
    requested_urls = set(normalized_urls)
    lineage_source_ids = set(
        OfficialFactCheckSourceEvidenceLink.objects.filter(
            source__fact_check=fact_check
        ).values_list("source_id", flat=True)
    )

    for source in fact_check.source_items.filter(is_editorially_selected=True):
        if source.url in requested_urls:
            continue
        if source.id in lineage_source_ids:
            source.is_editorially_selected = False
            source.save(update_fields=["is_editorially_selected"])
        else:
            source.delete()

    _add_editorial_sources(
        fact_check,
        actor=actor,
        normalized_urls=normalized_urls,
    )


def _sync_sources_cache(
    fact_check,
):
    urls = list(
        fact_check.source_items.order_by(
            "created_at",
            "id",
        ).values_list(
            "url",
            flat=True,
        )
    )

    fact_check.sources = urls

    fact_check.save(
        update_fields=[
            "sources",
            "updated_at",
        ]
    )


def _sync_fact_check_sources(
    fact_check,
    *,
    actor,
    snapshot,
    snapshot_records,
    source_urls=None,
    replace_moderator_sources=False,
):
    _sync_snapshot_evidence_sources(
        fact_check,
        actor=actor,
        snapshot=snapshot,
        snapshot_records=snapshot_records,
    )

    if replace_moderator_sources:
        _replace_moderator_sources(
            fact_check,
            actor=actor,
            source_urls=(source_urls or []),
        )

    elif source_urls:
        _add_editorial_sources(
            fact_check,
            actor=actor,
            normalized_urls=_normalize_source_urls(source_urls),
        )

    _sync_sources_cache(fact_check)


def _validate_publication_content(
    fact_check,
):
    if not (fact_check.headline or "").strip():
        raise InvalidFactCheckContent(
            "A headline is required before " "review or publication."
        )

    if not (fact_check.summary or "").strip():
        raise InvalidFactCheckContent(
            "A summary is required before " "review or publication."
        )

    if not (fact_check.article_body or "").strip():
        raise InvalidFactCheckContent(
            "Article analysis is required " "before review or publication."
        )

    if not (fact_check.source_items.exists()):
        raise InvalidFactCheckContent(
            "At least one source is required " "before review or publication."
        )


def _record_publication_event(
    fact_check,
    *,
    actor,
    event_type,
    from_status=None,
    to_status=None,
    notes=None,
    metadata=None,
):
    decision = fact_check.adjudication_decision

    if not decision or not decision.moderation_case_id:
        return None

    return ModerationEvent.objects.create(
        case=decision.moderation_case,
        actor=actor,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        notes=notes,
        metadata={
            "fact_check_id": str(fact_check.id),
            "claim_id": str(fact_check.claim_id),
            "version": (fact_check.version),
            **(metadata or {}),
        },
    )


def create_fact_check_draft(
    *,
    decision,
    actor,
    headline,
    summary,
    article_body="",
    source_urls=None,
):
    headline = (headline or "").strip()

    summary = (summary or "").strip()

    article_body = (article_body or "").strip()

    if not headline:
        raise InvalidFactCheckContent("A headline is required.")

    if not summary:
        raise InvalidFactCheckContent("A summary is required.")

    if len(headline) > 300:
        raise InvalidFactCheckContent("Headline must be 300 " "characters or fewer.")

    identity = _get_decision_publication_identity(decision)

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        locked_claim = context["claim"]
        current_decision = context["decision"]
        _ensure_no_active_correction_reservation(context)

        if (
            any(
                item.publication_status == OfficialFactCheck.PublicationStatus.PUBLISHED
                for item in context["fact_checks"]
            )
            or context["publication_snapshots"]
        ):
            raise PublishingConflict(
                "A published or sealed fact-check requires an explicit revision "
                "or correction workflow."
            )

        active_drafts = [
            item
            for item in context["fact_checks"]
            if item.publication_status in ACTIVE_DRAFT_STATUSES
        ]

        same_decision_draft = next(
            (
                item
                for item in active_drafts
                if (item.adjudication_decision_id == current_decision.id)
            ),
            None,
        )

        if same_decision_draft:
            raise PublishingConflict(
                "An active fact-check draft "
                "already exists for this "
                "adjudication decision."
            )

        if any(
            item.supersedes_id is not None
            or item.revision_kind
            in {
                OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
                OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            }
            for item in active_drafts
        ):
            raise PublishingConflict(
                "An explicit revision or correction draft is already active."
            )

        # Any remaining active drafts belong to
        # an older adjudication revision. They
        # can no longer be published, so retire
        # them before allocating the new version.
        if active_drafts:
            archived_at = timezone.now()

            for stale_draft in active_drafts:
                stale_draft.publication_status = (
                    OfficialFactCheck.PublicationStatus.ARCHIVED
                )

                stale_draft.archived_at = archived_at

                stale_draft.save(
                    update_fields=[
                        "publication_status",
                        "archived_at",
                        "updated_at",
                    ]
                )

        max_version = max(
            (item.version for item in context["fact_checks"]),
            default=0,
        )

        draft = OfficialFactCheck(
            claim=locked_claim,
            adjudication_decision=(current_decision),
            organization=(current_decision.organization),
            canonical_claim=(current_decision.canonical_claim),
            verdict=(current_decision.verdict),
            headline=headline,
            summary=summary,
            article_body=article_body,
            publication_status=(OfficialFactCheck.PublicationStatus.DRAFT),
            version=max_version + 1,
            drafted_by=actor,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )

        draft.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )

        draft.save()

        _sync_fact_check_sources(
            draft,
            actor=actor,
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
            source_urls=source_urls,
        )

        _record_publication_event(
            draft,
            actor=actor,
            event_type=(ModerationEvent.EventType.ARTICLE_DRAFT_CREATED),
            to_status=(OfficialFactCheck.PublicationStatus.DRAFT),
        )

        return draft


def create_editorial_revision_draft(
    *,
    predecessor_id,
    actor,
    organization_id,
    expected_predecessor_version,
    expected_decision_revision,
    revision_reason,
    headline=None,
    summary=None,
    article_body=None,
    source_urls=None,
):
    expected_predecessor_version = _parse_expected_version(
        expected_predecessor_version,
        "expected_predecessor_version",
    )
    expected_decision_revision = _parse_expected_version(
        expected_decision_revision,
        "expected_decision_revision",
    )
    if not isinstance(revision_reason, str):
        raise InvalidFactCheckContent("revision_reason must be a string.")
    revision_reason = revision_reason.strip()
    if not revision_reason:
        raise InvalidFactCheckContent("A nonblank revision reason is required.")
    if len(revision_reason) > 2000:
        raise InvalidFactCheckContent(
            "Revision reason must be 2000 characters or fewer."
        )

    explicit_source_urls = None
    if source_urls is not None:
        explicit_source_urls = _normalize_source_urls(source_urls)

    identity = _get_editorial_revision_identity(
        predecessor_id=predecessor_id,
        organization_id=organization_id,
    )

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        predecessor = context["fact_check"]
        decision = context["decision"]
        _ensure_no_active_correction_reservation(context)

        if predecessor.version != expected_predecessor_version:
            raise PublishingConflict(
                "The published predecessor changed before the revision draft "
                "could be created."
            )
        if decision.revision_number != expected_decision_revision:
            raise PublishingConflict(
                "The adjudication decision changed before the revision draft "
                "could be created."
            )
        if (
            predecessor.organization_id != context["organization"].id
            or predecessor.adjudication_decision_id != decision.id
        ):
            raise PublishingConflict(
                "The predecessor no longer matches the selected publication "
                "authority."
            )

        published = [
            item
            for item in context["fact_checks"]
            if item.publication_status == OfficialFactCheck.PublicationStatus.PUBLISHED
        ]
        if len(published) != 1 or published[0].id != predecessor.id:
            raise PublishingConflict(
                "The selected predecessor is not the current published fact-check."
            )

        if context["assignment"] is not None:
            raise PublishingConflict(
                "Open verification work must be resolved before an editorial "
                "revision draft can be created."
            )

        # A predecessor that already has a historically published successor
        # cannot be used to create another branch of publication history.
        sealed_fact_check_ids = {
            snapshot.fact_check_id for snapshot in context["publication_snapshots"]
        }

        if any(
            item.supersedes_id == predecessor.id
            and (item.published_at is not None or item.id in sealed_fact_check_ids)
            for item in context["fact_checks"]
        ):
            raise PublishingConflict(
                "This publication already has a historically published successor."
            )

        active_successors = [
            item
            for item in context["fact_checks"]
            if item.supersedes_id == predecessor.id
            and item.publication_status in ACTIVE_DRAFT_STATUSES
        ]
        if active_successors:
            raise PublishingConflict(
                "An active editorial revision already exists for this publication."
            )
        competing_work = [
            item
            for item in context["fact_checks"]
            if item.id != predecessor.id
            and item.publication_status in ACTIVE_DRAFT_STATUSES
        ]
        if competing_work:
            raise PublishingConflict(
                "Another fact-check draft is already active for this claim."
            )

        publication_snapshot = next(
            (
                snapshot
                for snapshot in context["publication_snapshots"]
                if snapshot.fact_check_id == predecessor.id
            ),
            None,
        )
        sealed_payload = _validate_predecessor_publication_snapshot(
            publication_snapshot,
            predecessor=predecessor,
            organization=context["organization"],
        )["payload"]

        resolved_headline = _revision_content_value(
            headline,
            sealed_payload["headline"],
            field_name="headline",
            required=True,
        )
        if len(resolved_headline) > 300:
            raise InvalidFactCheckContent("Headline must be 300 characters or fewer.")
        resolved_summary = _revision_content_value(
            summary,
            sealed_payload["summary"],
            field_name="summary",
            required=True,
        )
        resolved_article_body = _revision_content_value(
            article_body,
            sealed_payload["article_body"],
            field_name="article_body",
        )
        selected_source_urls = (
            explicit_source_urls
            if explicit_source_urls is not None
            else _inherited_editorial_source_urls(sealed_payload)
        )

        max_version = max(
            (item.version for item in context["fact_checks"]),
            default=0,
        )
        requested_at = timezone.now()
        draft = OfficialFactCheck(
            claim=context["claim"],
            adjudication_decision=decision,
            organization=context["organization"],
            canonical_claim=decision.canonical_claim,
            verdict=decision.verdict,
            headline=resolved_headline,
            summary=resolved_summary,
            article_body=resolved_article_body,
            publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            version=max_version + 1,
            drafted_by=actor,
            supersedes=predecessor,
            revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            revision_reason=revision_reason,
            revision_requested_by=actor,
            revision_requested_at=requested_at,
        )
        draft.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )
        draft.save()

        _sync_fact_check_sources(
            draft,
            actor=actor,
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
            source_urls=selected_source_urls,
        )
        _record_publication_event(
            draft,
            actor=actor,
            event_type=ModerationEvent.EventType.ARTICLE_DRAFT_CREATED,
            to_status=OfficialFactCheck.PublicationStatus.DRAFT,
            metadata={
                "revision_kind": draft.revision_kind,
                "supersedes_fact_check_id": str(predecessor.id),
            },
        )
        return draft


def update_fact_check_draft(
    *,
    fact_check,
    actor,
    headline=None,
    summary=None,
    article_body=None,
    source_urls=None,
):
    identity = _get_fact_check_publication_identity(fact_check)

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        locked_fact_check = context["fact_check"]
        _ensure_no_active_correction_reservation(context)

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.DRAFT
        ):
            raise InvalidPublicationTransition(
                "Only draft fact-checks " "can be edited."
            )

        if headline is not None:
            headline = headline.strip()

            if not headline:
                raise InvalidFactCheckContent("Headline cannot be empty.")

            if len(headline) > 300:
                raise InvalidFactCheckContent(
                    "Headline must be 300 " "characters or fewer."
                )

            locked_fact_check.headline = headline

        if summary is not None:
            summary = summary.strip()

            if not summary:
                raise InvalidFactCheckContent("Summary cannot be empty.")

            locked_fact_check.summary = summary

        if article_body is not None:
            locked_fact_check.article_body = article_body.strip()

        locked_fact_check.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )

        locked_fact_check.save()

        _sync_fact_check_sources(
            locked_fact_check,
            actor=actor,
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
            source_urls=source_urls,
            replace_moderator_sources=(source_urls is not None),
        )

        return locked_fact_check


def submit_fact_check_for_review(
    *,
    fact_check,
    actor,
):
    identity = _get_fact_check_publication_identity(fact_check)

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        locked_fact_check = context["fact_check"]
        _ensure_no_active_correction_reservation(context)

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.DRAFT
        ):
            raise InvalidPublicationTransition(
                "Only a draft can be " "submitted for review."
            )

        _sync_fact_check_sources(
            locked_fact_check,
            actor=actor,
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
        )

        _validate_publication_content(locked_fact_check)

        previous_status = locked_fact_check.publication_status

        locked_fact_check.publication_status = (
            OfficialFactCheck.PublicationStatus.IN_REVIEW
        )

        locked_fact_check.submitted_for_review_at = timezone.now()

        locked_fact_check.save(
            update_fields=[
                "publication_status",
                ("submitted_for_" "review_at"),
                "updated_at",
            ]
        )

        _record_publication_event(
            locked_fact_check,
            actor=actor,
            event_type=(ModerationEvent.EventType.ARTICLE_SUBMITTED),
            from_status=previous_status,
            to_status=(OfficialFactCheck.PublicationStatus.IN_REVIEW),
        )

        return locked_fact_check


def publish_editorial_revision(
    *,
    revision_id,
    predecessor_id,
    actor,
    organization_id,
    expected_predecessor_version,
    expected_revision_version,
    expected_decision_revision,
):
    expected_predecessor_version = _parse_expected_version(
        expected_predecessor_version,
        "expected_predecessor_version",
    )
    expected_revision_version = _parse_expected_version(
        expected_revision_version,
        "expected_revision_version",
    )
    expected_decision_revision = _parse_expected_version(
        expected_decision_revision,
        "expected_decision_revision",
    )
    identity = _get_editorial_replacement_identity(
        revision_id=revision_id,
        predecessor_id=predecessor_id,
        organization_id=organization_id,
    )

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.PUBLISH_FACT_CHECK,
        )
        revision = context["fact_check"]
        decision = context["decision"]
        _ensure_no_active_correction_reservation(context)
        predecessor = next(
            (
                item
                for item in context["fact_checks"]
                if item.id == identity["predecessor_id"]
            ),
            None,
        )

        if predecessor is None:
            raise PublishingConflict(
                "The requested publication predecessor is unavailable."
            )
        if predecessor.version != expected_predecessor_version:
            raise PublishingConflict(
                "The published predecessor changed before replacement."
            )
        if revision.version != expected_revision_version:
            raise PublishingConflict(
                "The editorial revision changed before publication."
            )
        if decision.revision_number != expected_decision_revision:
            raise PublishingConflict(
                "The adjudication decision changed before publication."
            )

        published = [
            item
            for item in context["fact_checks"]
            if item.publication_status
            == OfficialFactCheck.PublicationStatus.PUBLISHED
        ]
        if len(published) != 1 or published[0].id != predecessor.id:
            raise PublishingConflict(
                "The selected predecessor is not the current published fact-check."
            )
        if (
            revision.publication_status
            != OfficialFactCheck.PublicationStatus.IN_REVIEW
            or revision.supersedes_id != predecessor.id
            or revision.revision_kind
            != OfficialFactCheck.RevisionKind.EDITORIAL_REVISION
        ):
            raise PublishingConflict(
                "The selected fact-check is not an approved editorial revision of "
                "the current publication."
            )
        if any(
            snapshot.fact_check_id == revision.id
            for snapshot in context["publication_snapshots"]
        ):
            raise PublishingConflict(
                "The editorial revision already has a sealed publication record."
            )
        if (
            revision.claim_id != predecessor.claim_id
            or revision.organization_id != predecessor.organization_id
            or revision.organization_id != context["organization"].id
            or revision.adjudication_decision_id != predecessor.adjudication_decision_id
            or revision.adjudication_decision_id != decision.id
            or revision.canonical_claim != decision.canonical_claim
            or revision.verdict != decision.verdict
            or predecessor.canonical_claim != decision.canonical_claim
            or predecessor.verdict != decision.verdict
        ):
            raise PublishingConflict(
                "The editorial revision no longer matches its authoritative "
                "decision or predecessor."
            )
        reason = revision.revision_reason
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or reason != reason.strip()
            or len(reason) > 2000
            or revision.revision_requested_by_id is None
            or revision.revision_requested_at is None
        ):
            raise PublishingConflict(
                "The editorial revision provenance is incomplete."
            )
        if context["assignment"] is not None:
            raise PublishingConflict(
                "Open verification work must be resolved before an editorial "
                "replacement can be published."
            )
        if any(
            item.id != revision.id
            and item.publication_status in ACTIVE_DRAFT_STATUSES
            for item in context["fact_checks"]
        ):
            raise PublishingConflict(
                "Competing publication work is active for this claim."
            )
        if (
            decision.moderation_case_id is None
            or not ModerationCase.objects.filter(
                pk=decision.moderation_case_id,
                case_type=ModerationCase.CaseType.ADJUDICATION,
                claim=context["claim"],
                organization=context["organization"],
            ).exists()
        ):
            raise PublishingConflict(
                "The editorial revision does not have attributable adjudication "
                "case provenance."
            )

        predecessor_snapshot = next(
            (
                snapshot
                for snapshot in context["publication_snapshots"]
                if snapshot.fact_check_id == predecessor.id
            ),
            None,
        )
        _validate_editorial_revision_chain(
            predecessor=predecessor,
            fact_checks=context["fact_checks"],
            publication_snapshots=context["publication_snapshots"],
            decision=decision,
            decision_snapshot=context["decision_snapshot"],
            organization=context["organization"],
        )

        _sync_fact_check_sources(
            revision,
            actor=actor,
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
        )
        _validate_publication_content(revision)

        replacement_at = timezone.now()
        previous_status = revision.publication_status
        revision.publication_status = OfficialFactCheck.PublicationStatus.PUBLISHED
        revision.reviewed_by = actor
        revision.reviewed_at = replacement_at
        revision.published_by = actor
        revision.published_at = replacement_at
        revision.archived_at = None
        try:
            revision.full_clean(
                validate_unique=False,
                validate_constraints=False,
            )
            sealed_payload = OfficialFactCheckPublicationSnapshot.build_payload(
                fact_check=revision,
                decision_snapshot=context["decision_snapshot"],
                schema_version=EDITORIAL_REVISION_SCHEMA_VERSION,
                predecessor_snapshot=predecessor_snapshot,
            )
        except ValidationError as error:
            raise PublishingConflict(
                "The editorial revision provenance or publication seal is "
                "inconsistent."
            ) from error

        try:
            with transaction.atomic():
                predecessor.publication_status = (
                    OfficialFactCheck.PublicationStatus.ARCHIVED
                )
                predecessor.archived_at = replacement_at
                predecessor.save(
                    update_fields=[
                        "publication_status",
                        "archived_at",
                        "updated_at",
                    ]
                )

                revision.save(
                    update_fields=[
                        "publication_status",
                        "reviewed_by",
                        "reviewed_at",
                        "published_by",
                        "published_at",
                        "archived_at",
                        "updated_at",
                    ]
                )
                successor_snapshot = (
                    OfficialFactCheckPublicationSnapshot.objects.create(
                        fact_check=revision,
                        decision_snapshot=context["decision_snapshot"],
                        schema_version=EDITORIAL_REVISION_SCHEMA_VERSION,
                        captured_at=replacement_at,
                        payload=sealed_payload,
                    )
                )
                revision_event = _record_publication_event(
                    revision,
                    actor=actor,
                    event_type=ModerationEvent.EventType.ARTICLE_REVISED,
                    from_status=previous_status,
                    to_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
                    notes=reason,
                    metadata={
                        "revision_kind": revision.revision_kind,
                        "revision_reason": reason,
                        "old_fact_check_id": str(predecessor.id),
                        "new_fact_check_id": str(revision.id),
                        "old_version": predecessor.version,
                        "new_version": revision.version,
                        "decision_id": str(decision.id),
                        "predecessor_publication_snapshot_id": str(
                            predecessor_snapshot.id
                        ),
                        "successor_publication_snapshot_id": str(
                            successor_snapshot.id
                        ),
                    },
                )
                if revision_event is None:
                    raise PublishingConflict(
                        "The editorial replacement could not be attributed to its "
                        "adjudication case."
                    )
        except IntegrityError as error:
            if not _is_expected_publication_integrity_conflict(error):
                raise
            raise PublishingConflict(
                "The editorial replacement conflicted with current publication "
                "state."
            ) from error
        except ValidationError as error:
            raise PublishingConflict(
                "The editorial replacement conflicted with current publication "
                "state or could not be sealed safely."
            ) from error

        revision_id_for_index = revision.id
        transaction.on_commit(
            lambda: _queue_fact_check_index(revision_id_for_index)
        )
        return {
            "fact_check": revision,
            "archived_fact_check": predecessor,
        }


def publish_fact_check(
    *,
    fact_check,
    actor,
):
    identity = _get_fact_check_publication_identity(fact_check)

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.PUBLISH_FACT_CHECK,
        )
        locked_fact_check = context["fact_check"]
        current_decision = context["decision"]
        _ensure_no_active_correction_reservation(context)

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.IN_REVIEW
        ):
            raise InvalidPublicationTransition(
                "Only a fact-check in review " "can be published."
            )

        if (
            locked_fact_check.supersedes_id is not None
            or locked_fact_check.revision_kind
            in {
                OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
                OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            }
        ):
            raise PublishingConflict(
                "A revision or correction must use its explicit replacement "
                "publication workflow."
            )

        if locked_fact_check.verdict != current_decision.verdict or (
            locked_fact_check.canonical_claim != current_decision.canonical_claim
        ):
            raise PublishingConflict(
                "The fact-check no longer "
                "matches the authoritative "
                "adjudication decision."
            )

        previous_published = next(
            (
                item
                for item in context["fact_checks"]
                if item.publication_status
                == OfficialFactCheck.PublicationStatus.PUBLISHED
                and item.id != locked_fact_check.id
            ),
            None,
        )
        if previous_published:
            raise PublishingConflict(
                "This claim already has a published fact-check. An explicit "
                "correction or revision workflow is required before it can "
                "be replaced."
            )

        sealed_fact_check_ids = {
            snapshot.fact_check_id for snapshot in context["publication_snapshots"]
        }
        if any(
            item.published_at is not None
            or (
                item.id != locked_fact_check.id
                and item.id in sealed_fact_check_ids
            )
            for item in context["fact_checks"]
        ):
            raise PublishingConflict(
                "This claim already has recorded publication history. An explicit "
                "revision or correction workflow is required."
            )

        if any(
            snapshot.fact_check_id == locked_fact_check.id
            for snapshot in context["publication_snapshots"]
        ):
            raise PublishingConflict(
                "This fact-check already has a sealed publication record."
            )

        _sync_fact_check_sources(
            locked_fact_check,
            actor=actor,
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
        )

        _validate_publication_content(locked_fact_check)

        now = timezone.now()
        previous_status = locked_fact_check.publication_status

        locked_fact_check.publication_status = (
            OfficialFactCheck.PublicationStatus.PUBLISHED
        )

        locked_fact_check.reviewed_by = actor
        locked_fact_check.reviewed_at = now
        locked_fact_check.published_by = actor
        locked_fact_check.published_at = now
        locked_fact_check.archived_at = None

        locked_fact_check.save(
            update_fields=[
                "publication_status",
                "reviewed_by",
                "reviewed_at",
                "published_by",
                "published_at",
                "archived_at",
                "updated_at",
            ]
        )

        _record_publication_event(
            locked_fact_check,
            actor=actor,
            event_type=ModerationEvent.EventType.ARTICLE_PUBLISHED,
            from_status=previous_status,
            to_status=(OfficialFactCheck.PublicationStatus.PUBLISHED),
        )

        try:
            completed_assignment = complete_verification_assignment(
                claim=context["claim"],
                organization=context["organization"],
            )
        except VerificationAssignmentConflict as error:
            raise PublishingConflict(str(error)) from error

        if context["assignment"] is not None and completed_assignment is None:
            raise PublishingConflict(
                "The verification assignment changed before publication "
                "could be completed."
            )

        try:
            sealed_payload = OfficialFactCheckPublicationSnapshot.build_payload(
                fact_check=locked_fact_check,
                decision_snapshot=context["decision_snapshot"],
                schema_version=FIRST_PUBLICATION_SCHEMA_VERSION,
            )
            OfficialFactCheckPublicationSnapshot.objects.create(
                fact_check=locked_fact_check,
                decision_snapshot=context["decision_snapshot"],
                schema_version=FIRST_PUBLICATION_SCHEMA_VERSION,
                captured_at=now,
                payload=sealed_payload,
            )
        except ValidationError as error:
            raise PublishingConflict(
                "The publication record could not be sealed because its "
                "source provenance is inconsistent."
            ) from error

        published_fact_check_id = locked_fact_check.id

        transaction.on_commit(lambda: _queue_fact_check_index(published_fact_check_id))

        return {
            "fact_check": locked_fact_check,
            "archived_fact_check": previous_published,
        }
