"""Durable drafting and human preparation for factual corrections."""

import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from .adjudication_service import (
    _build_decision_evidence_records,
    has_adjudication_conflict,
)
from .evidence_snapshot_schema import (
    CURRENT_SCHEMA_VERSION as EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)
from .factual_correction_proposal_schema import (
    CURRENT_SCHEMA_VERSION as PROPOSAL_SCHEMA_VERSION,
    FactualCorrectionProposalSchemaError,
    validate_factual_correction_proposal,
)
from .models import (
    AdjudicationDecision,
    EvidenceSubmission,
    FactualCorrectionProposal,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
    VerificationRun,
)
from .moderation_service import ACTIVE_CASE_STATUSES
from .organization_service import PartnerCapability
from .publishing_service import (
    ACTIVE_DRAFT_STATUSES,
    InvalidFactCheckContent,
    PublishingAuthorizationError,
    PublishingConflict,
    _lock_publication_context,
    _normalize_source_urls,
    _validate_editorial_revision_chain,
)


class FactualCorrectionProposalError(Exception):
    pass


class FactualCorrectionProposalAuthorizationError(FactualCorrectionProposalError):
    pass


class InvalidFactualCorrectionProposal(FactualCorrectionProposalError):
    pass


class FactualCorrectionProposalConflict(FactualCorrectionProposalError):
    pass


def _parse_uuid(value, field_name, *, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise InvalidFactualCorrectionProposal(f"{field_name} must be a valid UUID.")
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise InvalidFactualCorrectionProposal(
            f"{field_name} must be a valid UUID."
        ) from error


def _parse_expected_version(value, field_name, *, allow_zero=False):
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "nonnegative" if allow_zero else "positive"
        raise InvalidFactualCorrectionProposal(
            f"{field_name} must be a {qualifier} integer."
        )
    return value


def _normalize_text(value, field_name, *, max_length=None):
    if not isinstance(value, str):
        raise InvalidFactualCorrectionProposal(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise InvalidFactualCorrectionProposal(f"{field_name} is required.")
    if max_length is not None and len(normalized) > max_length:
        raise InvalidFactualCorrectionProposal(
            f"{field_name} must be {max_length} characters or fewer."
        )
    return normalized


def _normalize_content(
    *,
    verdict,
    canonical_claim,
    rationale,
    headline,
    summary,
    article_body,
    source_urls,
):
    valid_verdicts = {
        value for value, _label in AdjudicationDecision.Verdict.choices
    }
    if not isinstance(verdict, str) or verdict not in valid_verdicts:
        raise InvalidFactualCorrectionProposal("Invalid proposed verdict.")
    try:
        normalized_urls = _normalize_source_urls(source_urls)
    except InvalidFactCheckContent as error:
        raise InvalidFactualCorrectionProposal(str(error)) from error
    if not normalized_urls:
        raise InvalidFactualCorrectionProposal("At least one source URL is required.")
    return {
        "verdict": verdict,
        "canonical_claim": _normalize_text(canonical_claim, "canonical_claim"),
        "rationale": _normalize_text(rationale, "rationale"),
        "headline": _normalize_text(headline, "headline", max_length=300),
        "summary": _normalize_text(summary, "summary"),
        "article_body": _normalize_text(article_body, "article_body"),
        "source_urls": normalized_urls,
    }


def _get_identity(*, correction_request_id, organization_id):
    correction_request_id = _parse_uuid(
        correction_request_id,
        "correction_request_id",
    )
    organization_id = _parse_uuid(organization_id, "organization_id")
    identity = (
        FactualCorrectionRequest.objects.filter(pk=correction_request_id)
        .values(
            "claim_id",
            "organization_id",
            "predecessor_decision_id",
            "predecessor_fact_check_id",
        )
        .first()
    )
    if identity is None:
        raise FactualCorrectionProposalConflict(
            "The factual correction request is no longer available."
        )
    if identity["organization_id"] != organization_id:
        raise FactualCorrectionProposalConflict(
            "The factual correction request does not belong to this organization."
        )
    return {
        "correction_request_id": correction_request_id,
        "claim_id": identity["claim_id"],
        "organization_id": organization_id,
        "decision_id": identity["predecessor_decision_id"],
        "fact_check_id": identity["predecessor_fact_check_id"],
    }


def _lock_context(*, identity, actor, capability):
    try:
        return _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=capability,
        )
    except PublishingAuthorizationError as error:
        raise FactualCorrectionProposalAuthorizationError(
            "You do not have permission to perform this correction proposal action."
        ) from error
    except PublishingConflict as error:
        raise FactualCorrectionProposalConflict(str(error)) from error


def _validate_request_authority(
    context,
    *,
    correction_request_id,
    expected_predecessor_version,
    expected_decision_revision,
    require_history=False,
):
    request = next(
        (
            item
            for item in context["correction_requests"]
            if item.id == correction_request_id
        ),
        None,
    )
    if request is None or request.status != FactualCorrectionRequest.Status.ACTIVE:
        raise FactualCorrectionProposalConflict(
            "The factual correction request is no longer active."
        )
    claim = context["claim"]
    organization = context["organization"]
    decision = context["decision"]
    predecessor = context["fact_check"]
    if (
        request.claim_id != claim.id
        or request.organization_id != organization.id
        or request.predecessor_decision_id != decision.id
        or request.predecessor_fact_check_id != predecessor.id
    ):
        raise FactualCorrectionProposalConflict(
            "The correction request no longer matches its recorded authority."
        )
    if predecessor.version != expected_predecessor_version:
        raise FactualCorrectionProposalConflict(
            "The published predecessor changed before proposal preparation."
        )
    if decision.revision_number != expected_decision_revision:
        raise FactualCorrectionProposalConflict(
            "The adjudication decision changed before proposal preparation."
        )
    published = [
        item
        for item in context["fact_checks"]
        if item.publication_status == OfficialFactCheck.PublicationStatus.PUBLISHED
    ]
    if len(published) != 1 or published[0].id != predecessor.id:
        raise FactualCorrectionProposalConflict(
            "The correction predecessor is not the current published fact-check."
        )
    if require_history:
        try:
            seal = _validate_editorial_revision_chain(
                predecessor=predecessor,
                fact_checks=context["fact_checks"],
                publication_snapshots=context["publication_snapshots"],
                decision=decision,
                decision_snapshot=context["decision_snapshot"],
                organization=organization,
            )
        except PublishingConflict as error:
            raise FactualCorrectionProposalConflict(str(error)) from error
        if request.predecessor_publication_snapshot_id != seal.id:
            raise FactualCorrectionProposalConflict(
                "The correction request no longer matches its original "
                "publication seal."
            )
    else:
        seal = next(
            (
                item
                for item in context["publication_snapshots"]
                if item.id == request.predecessor_publication_snapshot_id
            ),
            None,
        )
        if seal is None or seal.fact_check_id != predecessor.id:
            raise FactualCorrectionProposalConflict(
                "The correction request no longer matches its publication seal."
            )
    return request, seal


def _lock_verification_run(verification_run_id, *, claim):
    if verification_run_id is None:
        return None
    run = (
        VerificationRun.objects.select_for_update(of=("self",))
        .filter(pk=verification_run_id, claim=claim)
        .first()
    )
    if run is None:
        raise FactualCorrectionProposalConflict(
            "The selected VerificationRun is unavailable for this claim."
        )
    if run.status != VerificationRun.Status.COMPLETED or run.completed_at is None:
        raise FactualCorrectionProposalConflict(
            "The selected VerificationRun is not complete."
        )
    return run


def _is_expected_proposal_uniqueness_conflict(error):
    cause = getattr(error, "__cause__", None)
    diagnostic = getattr(cause, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name == "api_factualcorrectionproposal_correction_request_id_key":
        return True
    message = str(error).lower()
    return (
        "api_factualcorrectionproposal.correction_request_id" in message
        or "api_factualcorrectionproposal_correction_request_id_key" in message
    )


def save_factual_correction_proposal(
    *,
    correction_request_id,
    actor,
    organization_id,
    expected_proposal_version,
    expected_predecessor_version,
    expected_decision_revision,
    verdict,
    canonical_claim,
    rationale,
    headline,
    summary,
    article_body,
    source_urls,
    verification_run_id=None,
):
    """Create or update the sole editable proposal for an active request."""

    expected_proposal_version = _parse_expected_version(
        expected_proposal_version,
        "expected_proposal_version",
        allow_zero=True,
    )
    expected_predecessor_version = _parse_expected_version(
        expected_predecessor_version,
        "expected_predecessor_version",
    )
    expected_decision_revision = _parse_expected_version(
        expected_decision_revision,
        "expected_decision_revision",
    )
    verification_run_id = _parse_uuid(
        verification_run_id,
        "verification_run_id",
        nullable=True,
    )
    content = _normalize_content(
        verdict=verdict,
        canonical_claim=canonical_claim,
        rationale=rationale,
        headline=headline,
        summary=summary,
        article_body=article_body,
        source_urls=source_urls,
    )
    if not actor or not actor.is_authenticated:
        raise FactualCorrectionProposalAuthorizationError(
            "Authentication is required to draft a correction proposal."
        )
    identity = _get_identity(
        correction_request_id=correction_request_id,
        organization_id=organization_id,
    )

    with transaction.atomic():
        context = _lock_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        request, _seal = _validate_request_authority(
            context,
            correction_request_id=identity["correction_request_id"],
            expected_predecessor_version=expected_predecessor_version,
            expected_decision_revision=expected_decision_revision,
        )
        proposal = (
            FactualCorrectionProposal.objects.select_for_update(of=("self",))
            .filter(correction_request=request)
            .first()
        )
        verification_run = _lock_verification_run(
            verification_run_id,
            claim=context["claim"],
        )
        if proposal is None:
            if expected_proposal_version != 0:
                raise FactualCorrectionProposalConflict(
                    "The correction proposal does not exist at the expected version."
                )
            proposal = FactualCorrectionProposal(
                correction_request=request,
                version=1,
                verification_run=verification_run,
                **content,
            )
            try:
                with transaction.atomic():
                    proposal.save()
            except IntegrityError as error:
                if not _is_expected_proposal_uniqueness_conflict(error):
                    raise
                raise FactualCorrectionProposalConflict(
                    "A correction proposal already exists for this request."
                ) from error
        else:
            if proposal.status != FactualCorrectionProposal.Status.DRAFT:
                raise FactualCorrectionProposalConflict(
                    "A prepared correction proposal cannot be edited or replaced."
                )
            if proposal.version != expected_proposal_version:
                raise FactualCorrectionProposalConflict(
                    "The correction proposal changed before this update."
                )
            for field, value in content.items():
                setattr(proposal, field, value)
            proposal.verification_run = verification_run
            proposal.version += 1
            proposal.save(
                update_fields=[
                    *content.keys(),
                    "verification_run",
                    "version",
                    "updated_at",
                ]
            )
        return proposal


def _lock_correction_case(context, request):
    adjudication_cases = list(
        ModerationCase.objects.select_for_update(of=("self",))
        .filter(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=context["claim"],
        )
        .order_by("created_at", "id")
    )
    correction_case = next(
        (item for item in adjudication_cases if item.id == request.moderation_case_id),
        None,
    )
    original_case = next(
        (
            item
            for item in adjudication_cases
            if item.id == context["decision"].moderation_case_id
        ),
        None,
    )
    if (
        correction_case is None
        or correction_case.organization_id != context["organization"].id
        or correction_case.status not in ACTIVE_CASE_STATUSES
        or correction_case.id == context["decision"].moderation_case_id
    ):
        raise FactualCorrectionProposalConflict(
            "The factual correction request's correction case is not active."
        )
    if (
        original_case is None
        or original_case.status != ModerationCase.Status.RESOLVED
        or original_case.organization_id != context["organization"].id
    ):
        raise FactualCorrectionProposalConflict(
            "The original resolved Adjudication case is no longer valid."
        )
    other_active_adjudication = any(
        item.id != correction_case.id and item.status in ACTIVE_CASE_STATUSES
        for item in adjudication_cases
    )
    if other_active_adjudication:
        raise FactualCorrectionProposalConflict(
            "Incompatible Adjudication work is active for this claim."
        )
    return correction_case


def _review_event_item(event, *, evidence, evidence_case, correction_case, request):
    metadata = event.metadata
    expected_fields = {
        "correction_request_id",
        "correction_case_id",
        "evidence_case_id",
        "reviewer_snapshot",
        "previous_evidence_status",
        "new_evidence_status",
        "is_reaffirmation",
        "evidence_snapshot_schema_version",
        "evidence_record",
    }
    if not isinstance(metadata, dict) or set(metadata) != expected_fields:
        raise FactualCorrectionProposalConflict(
            "A correction evidence review has malformed provenance."
        )
    reviewer = metadata["reviewer_snapshot"]
    if (
        metadata["correction_request_id"] != str(request.id)
        or metadata["correction_case_id"] != str(correction_case.id)
        or metadata["evidence_case_id"] != str(evidence_case.id)
        or not isinstance(reviewer, dict)
        or set(reviewer) != {"id", "username"}
        or not all(
            isinstance(value, str) and value.strip()
            for value in reviewer.values()
        )
        or (event.actor_id is not None and reviewer["id"] != str(event.actor_id))
    ):
        raise FactualCorrectionProposalConflict(
            "A correction evidence review has mismatched case or actor provenance."
        )
    expected_event_type = (
        ModerationEvent.EventType.EVIDENCE_VERIFIED
        if metadata["new_evidence_status"]
        == EvidenceSubmission.EvidenceStatus.VERIFIED
        else ModerationEvent.EventType.EVIDENCE_REJECTED
    )
    if (
        metadata["new_evidence_status"]
        not in {
            EvidenceSubmission.EvidenceStatus.VERIFIED,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        }
        or event.event_type != expected_event_type
    ):
        raise FactualCorrectionProposalConflict(
            "A correction evidence review has mismatched decision provenance."
        )
    try:
        record = validate_evidence_snapshot(
            schema_version=metadata["evidence_snapshot_schema_version"],
            evidence_records=[metadata["evidence_record"]],
        )[0]
    except (EvidenceSnapshotSchemaError, TypeError) as error:
        raise FactualCorrectionProposalConflict(
            "A correction evidence review contains an invalid v1 evidence record."
        ) from error
    current_record = _build_decision_evidence_records([evidence])[0]
    try:
        validate_evidence_snapshot(
            schema_version=EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
            evidence_records=[current_record],
        )
    except (EvidenceSnapshotSchemaError, TypeError) as error:
        raise FactualCorrectionProposalConflict(
            "The current evidence state cannot be sealed."
        ) from error
    if (
        record != current_record
        or record["id"] != str(evidence.id)
        or record["thread_id"] != str(evidence.thread_id)
        or record["reviewer_id"] != reviewer["id"]
        or record["evidence_status"] != metadata["new_evidence_status"]
    ):
        raise FactualCorrectionProposalConflict(
            "A correction evidence review is stale or no longer matches evidence state."
        )
    return {
        "review_event_id": str(event.id),
        "evidence_case_id": str(evidence_case.id),
        "correction_case_id": str(correction_case.id),
        "record": record,
    }


def _freeze_evidence_basis(context, *, request, correction_case, approving_actor):
    evidence = list(
        EvidenceSubmission.objects.select_for_update(of=("self",))
        .filter(thread__claim=context["claim"])
        .order_by("submitted_at", "id")
    )
    if not evidence:
        raise FactualCorrectionProposalConflict(
            "At least one reviewed evidence item is required for preparation."
        )
    if has_adjudication_conflict(approving_actor, context["claim"]):
        raise FactualCorrectionProposalAuthorizationError(
            "The approving adjudicator cannot have directly contributed to this claim."
        )
    if any(
        item.evidence_status == EvidenceSubmission.EvidenceStatus.UNVERIFIED
        for item in evidence
    ):
        raise FactualCorrectionProposalConflict(
            "Every evidence item must have an explicit correction review."
        )
    evidence_by_id = {item.id: item for item in evidence}
    cases = list(
        ModerationCase.objects.select_for_update(of=("self",))
        .filter(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission_id__in=evidence_by_id,
        )
        .order_by("evidence_submission_id", "created_at", "id")
    )
    if any(item.status in ACTIVE_CASE_STATUSES for item in cases):
        raise FactualCorrectionProposalConflict(
            "An Evidence case is still active for this claim."
        )
    case_by_id = {item.id: item for item in cases}
    events = list(
        ModerationEvent.objects.select_for_update(of=("self",))
        .filter(case_id__in=case_by_id)
        .order_by("created_at", "id")
    )
    candidates = {evidence_id: [] for evidence_id in evidence_by_id}
    request_id = str(request.id)
    for event in events:
        metadata = event.metadata
        if (
            not isinstance(metadata, dict)
            or metadata.get("correction_request_id") != request_id
        ):
            continue
        evidence_case = case_by_id[event.case_id]
        evidence_id = evidence_case.evidence_submission_id
        if evidence_id not in candidates:
            raise FactualCorrectionProposalConflict(
                "A correction review references evidence outside the claim basis."
            )
        candidates[evidence_id].append((event, evidence_case))

    items = []
    for evidence_item in evidence:
        reviews = candidates[evidence_item.id]
        if not reviews:
            raise FactualCorrectionProposalConflict(
                "The complete claim evidence set has not been reviewed for "
                "this correction."
            )
        expected_fields = {
            "correction_request_id",
            "correction_case_id",
            "evidence_case_id",
            "reviewer_snapshot",
            "previous_evidence_status",
            "new_evidence_status",
            "is_reaffirmation",
            "evidence_snapshot_schema_version",
            "evidence_record",
        }
        for historical_event, historical_case in reviews:
            metadata = historical_event.metadata
            reviewer = metadata.get("reviewer_snapshot") if isinstance(metadata, dict) else None
            new_status = metadata.get("new_evidence_status") if isinstance(metadata, dict) else None
            previous_status = (
                metadata.get("previous_evidence_status")
                if isinstance(metadata, dict)
                else None
            )
            expected_event_type = (
                ModerationEvent.EventType.EVIDENCE_VERIFIED
                if new_status == EvidenceSubmission.EvidenceStatus.VERIFIED
                else ModerationEvent.EventType.EVIDENCE_REJECTED
            )
            if (
                not isinstance(metadata, dict)
                or set(metadata) != expected_fields
                or metadata["correction_request_id"] != str(request.id)
                or metadata["correction_case_id"] != str(correction_case.id)
                or metadata["evidence_case_id"] != str(historical_case.id)
                or historical_case.evidence_submission_id != evidence_item.id
                or historical_case.organization_id != context["organization"].id
                or historical_event.created_at < request.requested_at
                or not isinstance(reviewer, dict)
                or set(reviewer) != {"id", "username"}
                or not all(
                    isinstance(value, str) and value.strip()
                    for value in reviewer.values()
                )
                or (
                    historical_event.actor_id is not None
                    and reviewer["id"] != str(historical_event.actor_id)
                )
                or new_status
                not in {
                    EvidenceSubmission.EvidenceStatus.VERIFIED,
                    EvidenceSubmission.EvidenceStatus.REJECTED,
                }
                or previous_status
                not in {
                    EvidenceSubmission.EvidenceStatus.UNVERIFIED,
                    EvidenceSubmission.EvidenceStatus.VERIFIED,
                    EvidenceSubmission.EvidenceStatus.REJECTED,
                }
                or not isinstance(metadata["is_reaffirmation"], bool)
                or metadata["is_reaffirmation"]
                != (previous_status == new_status)
                or historical_event.event_type != expected_event_type
            ):
                raise FactualCorrectionProposalConflict(
                    "The correction evidence review history is malformed."
                )
            try:
                historical_record = validate_evidence_snapshot(
                    schema_version=metadata["evidence_snapshot_schema_version"],
                    evidence_records=[metadata["evidence_record"]],
                )[0]
            except (EvidenceSnapshotSchemaError, TypeError) as error:
                raise FactualCorrectionProposalConflict(
                    "The correction evidence review history is malformed."
                ) from error
            if (
                historical_record["id"] != str(evidence_item.id)
                or historical_record["thread_id"] != str(evidence_item.thread_id)
                or historical_record["reviewer_id"] != reviewer["id"]
                or historical_record["evidence_status"] != new_status
            ):
                raise FactualCorrectionProposalConflict(
                    "The correction evidence review history is mismatched."
                )
        latest_time = reviews[-1][0].created_at
        if sum(event.created_at == latest_time for event, _case in reviews) != 1:
            raise FactualCorrectionProposalConflict(
                "The latest correction evidence review is ambiguous."
            )
        event, evidence_case = reviews[-1]
        if (
            evidence_case.organization_id != context["organization"].id
            or evidence_case.evidence_submission_id != evidence_item.id
        ):
            raise FactualCorrectionProposalConflict(
                "A correction evidence review has invalid Evidence-case provenance."
            )
        items.append(
            _review_event_item(
                event,
                evidence=evidence_item,
                evidence_case=evidence_case,
                correction_case=correction_case,
                request=request,
            )
        )
    return items


def _freeze_sources(source_urls, evidence_items, *, actor_snapshot):
    # editorial_actor records accountable approval for source inclusion.
    # It must not be presented as the original researcher or URL discoverer.
    reviewed_by_url = {}
    rejected_urls = set()
    for item in evidence_items:
        record = item["record"]
        url = record["evidence_url"]
        if not isinstance(url, str) or not url.strip():
            continue
        if record["evidence_status"] == EvidenceSubmission.EvidenceStatus.VERIFIED:
            reviewed_by_url.setdefault(url, []).append(item)
        else:
            rejected_urls.add(url)

    sources = []
    for url in source_urls:
        reviewed = reviewed_by_url.get(url, [])
        if reviewed:
            sources.append(
                {
                    "url": url,
                    "provenance": "CORRECTION_REVIEW_EVIDENCE",
                    "editorial_actor": None,
                    "evidence": [
                        {
                            "evidence_id": item["record"]["id"],
                            "review_event_id": item["review_event_id"],
                        }
                        for item in reviewed
                    ],
                }
            )
        elif url in rejected_urls:
            raise FactualCorrectionProposalConflict(
                "A rejected evidence URL cannot be selected as an editorial source."
            )
        else:
            sources.append(
                {
                    "url": url,
                    "provenance": "EDITORIAL",
                    "editorial_actor": actor_snapshot,
                    "evidence": [],
                }
            )
    # actor_snapshot is deliberately required by the caller even though the
    # approval block already provides the stable editorial attribution.
    if not actor_snapshot:
        raise FactualCorrectionProposalConflict(
            "Editorial source attribution is unavailable."
        )
    return sources


def _verification_run_payload(run):
    if run is None:
        return None
    return {
        "id": str(run.id),
        "claim_id": str(run.claim_id),
        "status": run.status,
        "pipeline_version": run.pipeline_version,
        "triggered_by_id": (
            str(run.triggered_by_id) if run.triggered_by_id is not None else None
        ),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat(),
        "created_at": run.created_at.isoformat(),
    }


def prepare_factual_correction_proposal(
    *,
    correction_request_id,
    actor,
    organization_id,
    expected_proposal_version,
    expected_predecessor_version,
    expected_decision_revision,
):
    """Human-approve and atomically seal a non-authoritative proposal."""

    expected_proposal_version = _parse_expected_version(
        expected_proposal_version,
        "expected_proposal_version",
    )
    expected_predecessor_version = _parse_expected_version(
        expected_predecessor_version,
        "expected_predecessor_version",
    )
    expected_decision_revision = _parse_expected_version(
        expected_decision_revision,
        "expected_decision_revision",
    )
    if not actor or not actor.is_authenticated:
        raise FactualCorrectionProposalAuthorizationError(
            "Authentication is required to prepare a correction proposal."
        )
    identity = _get_identity(
        correction_request_id=correction_request_id,
        organization_id=organization_id,
    )

    with transaction.atomic():
        context = _lock_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.ADJUDICATE,
        )
        request, predecessor_seal = _validate_request_authority(
            context,
            correction_request_id=identity["correction_request_id"],
            expected_predecessor_version=expected_predecessor_version,
            expected_decision_revision=expected_decision_revision,
            require_history=True,
        )
        proposal = (
            FactualCorrectionProposal.objects.select_for_update(of=("self",))
            .filter(correction_request=request)
            .first()
        )
        if proposal is None:
            raise FactualCorrectionProposalConflict(
                "A draft correction proposal is required before preparation."
            )
        if proposal.status != FactualCorrectionProposal.Status.DRAFT:
            raise FactualCorrectionProposalConflict(
                "This correction proposal has already been prepared."
            )
        if proposal.version != expected_proposal_version:
            raise FactualCorrectionProposalConflict(
                "The correction proposal changed before preparation."
            )
        if context["assignment"] is not None:
            raise FactualCorrectionProposalConflict(
                "Ordinary verification work is active for this claim."
            )
        if any(
            item.id != context["fact_check"].id
            and item.publication_status in ACTIVE_DRAFT_STATUSES
            for item in context["fact_checks"]
        ):
            raise FactualCorrectionProposalConflict(
                "Competing publication work is active for this claim."
            )
        correction_case = _lock_correction_case(context, request)
        evidence_items = _freeze_evidence_basis(
            context,
            request=request,
            correction_case=correction_case,
            approving_actor=actor,
        )
        verification_run = _lock_verification_run(
            proposal.verification_run_id,
            claim=context["claim"],
        )
        prepared_at = timezone.now()
        actor_snapshot = {"id": str(actor.pk), "username": actor.username}
        organization_snapshot = {
            "id": str(context["organization"].id),
            "name": context["organization"].name,
            "slug": context["organization"].slug,
        }
        payload = {
            "proposal_id": str(proposal.id),
            "proposal_version": proposal.version,
            "correction_request_id": str(request.id),
            "claim_id": str(context["claim"].id),
            "correction_case_id": str(correction_case.id),
            "organization": organization_snapshot,
            "predecessor": {
                "decision_id": str(context["decision"].id),
                "decision_revision": context["decision"].revision_number,
                "fact_check_id": str(context["fact_check"].id),
                "fact_check_version": context["fact_check"].version,
                "publication_snapshot_id": str(predecessor_seal.id),
                "publication_snapshot_schema_version": predecessor_seal.schema_version,
                "published_at": predecessor_seal.captured_at.isoformat(),
            },
            "decision": {
                "verdict": proposal.verdict,
                "canonical_claim": proposal.canonical_claim,
                "rationale": proposal.rationale,
            },
            "evidence_basis": {
                "schema_version": EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
                "items": evidence_items,
            },
            "verification_run": _verification_run_payload(verification_run),
            "article": {
                "headline": proposal.headline,
                "summary": proposal.summary,
                "article_body": proposal.article_body,
            },
            "sources": _freeze_sources(
                proposal.source_urls,
                evidence_items,
                actor_snapshot=actor_snapshot,
            ),
            "approval": {
                "actor": actor_snapshot,
                "prepared_at": prepared_at.isoformat(),
            },
        }
        try:
            validate_factual_correction_proposal(
                schema_version=PROPOSAL_SCHEMA_VERSION,
                payload=payload,
            )
        except FactualCorrectionProposalSchemaError as error:
            raise FactualCorrectionProposalConflict(
                "The correction proposal could not be sealed as a valid v1 payload."
            ) from error

        proposal.status = FactualCorrectionProposal.Status.PREPARED
        proposal.prepared_payload_schema_version = PROPOSAL_SCHEMA_VERSION
        proposal.prepared_payload = payload
        proposal.prepared_by = actor
        proposal.prepared_by_snapshot = actor_snapshot
        proposal.organization_snapshot = organization_snapshot
        proposal.prepared_at = prepared_at
        proposal.save(
            update_fields=[
                "status",
                "prepared_payload_schema_version",
                "prepared_payload",
                "prepared_by",
                "prepared_by_snapshot",
                "organization_snapshot",
                "prepared_at",
                "updated_at",
            ]
        )
        event = ModerationEvent.objects.create(
            case=correction_case,
            actor=actor,
            event_type=(
                ModerationEvent.EventType.FACTUAL_CORRECTION_PROPOSAL_PREPARED
            ),
            from_status=correction_case.status,
            to_status=correction_case.status,
            notes=proposal.rationale,
            metadata={
                "correction_request_id": str(request.id),
                "proposal_id": str(proposal.id),
                "proposal_version": proposal.version,
                "prepared_payload_schema_version": PROPOSAL_SCHEMA_VERSION,
                "predecessor_decision_id": str(context["decision"].id),
                "predecessor_decision_revision": context["decision"].revision_number,
                "predecessor_fact_check_id": str(context["fact_check"].id),
                "predecessor_fact_check_version": context["fact_check"].version,
                "predecessor_publication_snapshot_id": str(predecessor_seal.id),
                "approver_snapshot": actor_snapshot,
                "prepared_at": prepared_at.isoformat(),
            },
        )
        return {"proposal": proposal, "event": event, "case": correction_case}
