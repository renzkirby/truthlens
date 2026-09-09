import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
)
from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    DuplicateActiveModerationCase,
    create_moderation_case,
)
from .organization_service import PartnerCapability
from .publishing_service import (
    ACTIVE_DRAFT_STATUSES,
    PublishingAuthorizationError,
    PublishingConflict,
    _lock_publication_context,
    _validate_editorial_revision_chain,
)


class FactualCorrectionError(Exception):
    pass


class FactualCorrectionAuthorizationError(FactualCorrectionError):
    pass


class InvalidFactualCorrectionRequest(FactualCorrectionError):
    pass


class FactualCorrectionConflict(FactualCorrectionError):
    pass


def _parse_uuid(value, field_name):
    if isinstance(value, bool):
        raise InvalidFactualCorrectionRequest(f"{field_name} must be a valid UUID.")
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise InvalidFactualCorrectionRequest(
            f"{field_name} must be a valid UUID."
        ) from error


def _parse_positive_integer(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidFactualCorrectionRequest(
            f"{field_name} must be a positive integer."
        )
    return value


def _normalize_reason(value):
    if not isinstance(value, str):
        raise InvalidFactualCorrectionRequest(
            "correction_reason must be a string."
        )
    reason = value.strip()
    if not reason:
        raise InvalidFactualCorrectionRequest(
            "A nonblank correction reason is required."
        )
    if len(reason) > 2000:
        raise InvalidFactualCorrectionRequest(
            "Correction reason must be 2000 characters or fewer."
        )
    return reason


def _get_request_identity(*, predecessor_id, organization_id):
    predecessor_id = _parse_uuid(predecessor_id, "predecessor_id")
    organization_id = _parse_uuid(organization_id, "organization_id")
    identity = (
        OfficialFactCheck.objects.filter(pk=predecessor_id)
        .values("claim_id", "adjudication_decision_id")
        .first()
    )
    if (
        identity is None
        or identity["claim_id"] is None
        or identity["adjudication_decision_id"] is None
    ):
        raise FactualCorrectionConflict(
            "The requested published predecessor is unavailable."
        )
    return {
        "claim_id": identity["claim_id"],
        "organization_id": organization_id,
        "decision_id": identity["adjudication_decision_id"],
        "fact_check_id": predecessor_id,
    }


def _is_expected_active_request_conflict(error):
    cause = getattr(error, "__cause__", None)
    diagnostic = getattr(cause, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name == "uniq_active_factual_correction_request":
        return True
    message = str(error).lower()
    return (
        "uniq_active_factual_correction_request" in message
        or "api_factualcorrectionrequest.claim_id" in message
    )


def _is_expected_active_adjudication_case_conflict(error):
    cause = getattr(error, "__cause__", None)
    if cause is None:
        return True
    diagnostic = getattr(cause, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name == "uniq_active_adjudication_case":
        return True
    message = str(cause).lower()
    return (
        "uniq_active_adjudication_case" in message
        or "api_moderationcase.claim_id" in message
    )


def _lock_correction_request_context(*, identity, actor):
    """Lock Claim through publication history, then requests and cases.

    The order is Claim, open Assignment, Organization, Membership, current
    Decision, Decision Snapshot, all Fact-checks, Sources, Source Lineage,
    Publication Snapshots, Correction Requests, then Adjudication Cases.
    """

    try:
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.ADJUDICATE,
        )
    except PublishingAuthorizationError as error:
        raise FactualCorrectionAuthorizationError(str(error)) from error
    except PublishingConflict as error:
        raise FactualCorrectionConflict(str(error)) from error

    correction_requests = list(
        FactualCorrectionRequest.objects.select_for_update(of=("self",))
        .filter(claim=context["claim"])
        .order_by("requested_at", "id")
    )
    adjudication_cases = list(
        ModerationCase.objects.select_for_update(of=("self",))
        .filter(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=context["claim"],
        )
        .order_by("created_at", "id")
    )
    return {
        **context,
        "correction_requests": correction_requests,
        "adjudication_cases": adjudication_cases,
    }


def request_factual_correction(
    *,
    predecessor_id,
    actor,
    organization_id,
    expected_predecessor_version,
    expected_decision_revision,
    correction_reason,
):
    """Reserve attributable correction work without changing public authority."""

    if not actor or not actor.is_authenticated:
        raise FactualCorrectionAuthorizationError("Authentication is required.")
    expected_predecessor_version = _parse_positive_integer(
        expected_predecessor_version,
        "expected_predecessor_version",
    )
    expected_decision_revision = _parse_positive_integer(
        expected_decision_revision,
        "expected_decision_revision",
    )
    reason = _normalize_reason(correction_reason)
    identity = _get_request_identity(
        predecessor_id=predecessor_id,
        organization_id=organization_id,
    )

    with transaction.atomic():
        context = _lock_correction_request_context(
            identity=identity,
            actor=actor,
        )
        predecessor = context["fact_check"]
        decision = context["decision"]
        organization = context["organization"]

        if predecessor.version != expected_predecessor_version:
            raise FactualCorrectionConflict(
                "The published predecessor changed before correction work was "
                "requested."
            )
        if decision.revision_number != expected_decision_revision:
            raise FactualCorrectionConflict(
                "The adjudication decision changed before correction work was "
                "requested."
            )

        published = [
            item
            for item in context["fact_checks"]
            if item.publication_status
            == OfficialFactCheck.PublicationStatus.PUBLISHED
        ]
        if len(published) != 1 or published[0].id != predecessor.id:
            raise FactualCorrectionConflict(
                "The selected predecessor is not the current published fact-check."
            )
        if (
            predecessor.organization_id != organization.id
            or predecessor.adjudication_decision_id != decision.id
            or predecessor.claim_id != context["claim"].id
        ):
            raise FactualCorrectionConflict(
                "The selected predecessor no longer matches its publication "
                "authority."
            )

        if context["assignment"] is not None:
            raise FactualCorrectionConflict(
                "Open verification work must be resolved before a factual "
                "correction can be requested."
            )
        if any(
            item.id != predecessor.id
            and item.publication_status in ACTIVE_DRAFT_STATUSES
            for item in context["fact_checks"]
        ):
            raise FactualCorrectionConflict(
                "Competing publication work is active for this claim."
            )
        if any(
            item.status == FactualCorrectionRequest.Status.ACTIVE
            for item in context["correction_requests"]
        ):
            raise FactualCorrectionConflict(
                "An active factual correction request already exists for this claim."
            )
        if any(
            item.status in ACTIVE_CASE_STATUSES
            for item in context["adjudication_cases"]
        ):
            raise FactualCorrectionConflict(
                "Active Adjudication work must be resolved before a factual "
                "correction can be requested."
            )

        try:
            predecessor_snapshot = _validate_editorial_revision_chain(
                predecessor=predecessor,
                fact_checks=context["fact_checks"],
                publication_snapshots=context["publication_snapshots"],
                decision=decision,
                decision_snapshot=context["decision_snapshot"],
                organization=organization,
            )
        except PublishingConflict as error:
            raise FactualCorrectionConflict(str(error)) from error

        try:
            correction_case = create_moderation_case(
                case_type=ModerationCase.CaseType.ADJUDICATION,
                actor=actor,
                source=ModerationCase.Source.MODERATOR,
                claim=context["claim"],
                organization=organization,
            )
        except DuplicateActiveModerationCase as error:
            if not _is_expected_active_adjudication_case_conflict(error):
                raise error.__cause__
            raise FactualCorrectionConflict(
                "Active Adjudication work already exists for this claim."
            ) from error

        requested_at = timezone.now()
        correction_request = FactualCorrectionRequest(
            claim=context["claim"],
            organization=organization,
            predecessor_decision=decision,
            predecessor_fact_check=predecessor,
            predecessor_publication_snapshot=predecessor_snapshot,
            moderation_case=correction_case,
            requested_by=actor,
            requested_by_snapshot={
                "id": str(actor.pk),
                "username": actor.username,
            },
            organization_snapshot={
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            },
            correction_reason=reason,
            status=FactualCorrectionRequest.Status.ACTIVE,
            requested_at=requested_at,
        )
        try:
            with transaction.atomic():
                correction_request.save()
        except IntegrityError as error:
            if not _is_expected_active_request_conflict(error):
                raise
            raise FactualCorrectionConflict(
                "An active factual correction request already exists for this claim."
            ) from error

        ModerationEvent.objects.create(
            case=correction_case,
            actor=actor,
            event_type=ModerationEvent.EventType.FACTUAL_CORRECTION_REQUESTED,
            to_status=ModerationCase.Status.OPEN,
            notes=reason,
            metadata={
                "correction_request_id": str(correction_request.id),
                "predecessor_decision_id": str(decision.id),
                "predecessor_decision_revision": decision.revision_number,
                "predecessor_fact_check_id": str(predecessor.id),
                "predecessor_fact_check_version": predecessor.version,
                "predecessor_publication_snapshot_id": str(
                    predecessor_snapshot.id
                ),
            },
        )

        return {
            "request": correction_request,
            "case": correction_case,
        }
