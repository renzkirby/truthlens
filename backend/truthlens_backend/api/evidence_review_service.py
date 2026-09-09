import logging
import uuid
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

from .models import (
    Claim,
    EvidenceSubmission,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
)

from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    DuplicateActiveModerationCase,
    InvalidModerationTransition,
    create_moderation_case,
    transition_moderation_case,
)
from .adjudication_service import (
    _build_decision_evidence_records,
    ensure_claim_adjudication_readiness,
    get_current_adjudication_decision,
)
from .evidence_snapshot_schema import (
    CURRENT_SCHEMA_VERSION as EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)
from .publishing_service import (
    PublishingAuthorizationError,
    PublishingConflict,
    _lock_publication_context,
    _validate_editorial_revision_chain,
)
from .verification_assignment_service import (
    get_claim_verification_organization,
)
from .organization_service import (
    PartnerCapability,
    has_case_capability,
    has_capability,
)

logger = logging.getLogger(__name__)


class EvidenceReviewError(Exception):
    pass


class EvidenceReviewAuthorizationError(EvidenceReviewError):
    pass


class InvalidEvidenceDecision(EvidenceReviewError):
    pass


class EvidenceReviewConflict(EvidenceReviewError):
    pass


def _parse_correction_uuid(value, field_name):
    if isinstance(value, bool):
        raise InvalidEvidenceDecision(f"{field_name} must be a valid UUID.")
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise InvalidEvidenceDecision(f"{field_name} must be a valid UUID.") from error


def _parse_correction_version(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidEvidenceDecision(f"{field_name} must be a positive integer.")
    return value


def _validate_correction_evidence_decision(
    *,
    evidence_status,
    expected_evidence_status,
    moderator_notes,
    rejection_reason,
):
    valid_statuses = {
        value for value, _label in EvidenceSubmission.EvidenceStatus.choices
    }
    if expected_evidence_status not in valid_statuses:
        raise InvalidEvidenceDecision("Invalid expected evidence status.")
    if evidence_status not in {
        EvidenceSubmission.EvidenceStatus.VERIFIED,
        EvidenceSubmission.EvidenceStatus.REJECTED,
    }:
        raise InvalidEvidenceDecision("Evidence decision must be VERIFIED or REJECTED.")
    if not isinstance(moderator_notes, str):
        raise InvalidEvidenceDecision("Moderator notes must be a string.")
    if len(moderator_notes) > 2000:
        raise InvalidEvidenceDecision(
            "Moderator notes must be 2000 characters or fewer."
        )
    valid_rejection_reasons = {
        value for value, _label in EvidenceSubmission.RejectionReason.choices
    }
    if rejection_reason and rejection_reason not in valid_rejection_reasons:
        raise InvalidEvidenceDecision("Invalid evidence rejection reason.")
    if (
        evidence_status == EvidenceSubmission.EvidenceStatus.REJECTED
        and not rejection_reason
    ):
        raise InvalidEvidenceDecision(
            "A rejection reason is required when rejecting evidence."
        )
    if (
        evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED
        and rejection_reason
    ):
        raise InvalidEvidenceDecision(
            "A rejection reason cannot be supplied when verifying evidence."
        )


def _get_correction_review_identity(*, correction_request_id, evidence_id):
    correction_request_id = _parse_correction_uuid(
        correction_request_id,
        "correction_request_id",
    )
    evidence_id = _parse_correction_uuid(evidence_id, "evidence_id")
    request_identity = (
        FactualCorrectionRequest.objects.filter(pk=correction_request_id)
        .values(
            "claim_id",
            "organization_id",
            "predecessor_decision_id",
            "predecessor_fact_check_id",
        )
        .first()
    )
    evidence_identity = (
        EvidenceSubmission.objects.filter(pk=evidence_id)
        .values("thread__claim_id")
        .first()
    )
    if request_identity is None:
        raise EvidenceReviewConflict(
            "The factual correction request is no longer available."
        )
    if evidence_identity is None:
        raise EvidenceReviewConflict(
            "This evidence is no longer available for correction review."
        )
    if evidence_identity["thread__claim_id"] != request_identity["claim_id"]:
        raise EvidenceReviewConflict(
            "This evidence does not belong to the correction request's claim."
        )
    return {
        "correction_request_id": correction_request_id,
        "evidence_id": evidence_id,
        "claim_id": request_identity["claim_id"],
        "organization_id": request_identity["organization_id"],
        "decision_id": request_identity["predecessor_decision_id"],
        "fact_check_id": request_identity["predecessor_fact_check_id"],
    }


def ensure_can_review_evidence(actor, organization):
    if not has_capability(
        actor,
        PartnerCapability.REVIEW_EVIDENCE,
        organization=organization,
    ):
        raise EvidenceReviewAuthorizationError(
            "You do not have permission to review evidence for this organization."
        )


def get_evidence_case_queryset(*, include_events=False):
    queryset = ModerationCase.objects.filter(
        case_type=ModerationCase.CaseType.EVIDENCE,
    ).select_related(
        "organization",
        "resolved_by",
        "evidence_submission",
        "evidence_submission__contributor",
        "evidence_submission__verified_by",
        "evidence_submission__thread",
        "evidence_submission__thread__claim",
    )

    if include_events:
        queryset = queryset.prefetch_related(
            Prefetch(
                "events",
                queryset=(
                    ModerationEvent.objects.select_related("actor").order_by(
                        "-created_at",
                        "-id",
                    )
                ),
                to_attr="recent_evidence_events",
            )
        )

    return queryset


def get_evidence_case_queue(*, actor, organization, evidence_status):
    ensure_can_review_evidence(actor, organization)

    queryset = get_evidence_case_queryset().filter(
        organization=organization,
    )

    if evidence_status == EvidenceSubmission.EvidenceStatus.UNVERIFIED:
        queryset = queryset.filter(
            status__in=ACTIVE_CASE_STATUSES,
            evidence_submission__evidence_status=evidence_status,
        )
    else:
        queryset = queryset.filter(
            status=ModerationCase.Status.RESOLVED,
            resolution_code=evidence_status,
        )

    return queryset.order_by(
        "-evidence_submission__submitted_at",
        "-created_at",
        "id",
    )


def get_active_evidence_case(
    evidence,
    *,
    lock=False,
):
    queryset = ModerationCase.objects.filter(
        case_type=(ModerationCase.CaseType.EVIDENCE),
        evidence_submission=evidence,
        status__in=ACTIVE_CASE_STATUSES,
    )

    if lock:
        queryset = queryset.select_for_update()

    return queryset.order_by("-created_at").first()


def get_latest_evidence_case(
    evidence,
    *,
    lock=False,
):
    queryset = ModerationCase.objects.filter(
        case_type=(ModerationCase.CaseType.EVIDENCE),
        evidence_submission=evidence,
    )

    if lock:
        queryset = queryset.select_for_update()

    return queryset.order_by("-created_at").first()


def ensure_evidence_case(
    *,
    evidence,
    actor=None,
    organization=None,
):
    existing_case = get_active_evidence_case(evidence)

    if existing_case:
        if organization is not None:
            if (
                existing_case.organization_id
                and existing_case.organization_id != organization.id
            ):
                raise EvidenceReviewConflict(
                    "This evidence case belongs to " "another organization."
                )

            if existing_case.organization_id is None:
                existing_case.organization = organization

                existing_case.save(
                    update_fields=[
                        "organization",
                        "updated_at",
                    ]
                )

        return existing_case

    latest_case = get_latest_evidence_case(evidence)

    if latest_case and latest_case.status == ModerationCase.Status.RESOLVED:
        return latest_case

    try:
        return create_moderation_case(
            case_type=(ModerationCase.CaseType.EVIDENCE),
            actor=actor,
            source=(ModerationCase.Source.EVIDENCE_SUBMISSION),
            evidence_submission=evidence,
            organization=organization,
        )

    except DuplicateActiveModerationCase:
        existing_case = get_active_evidence_case(evidence)

        if existing_case:
            if organization is not None:
                if (
                    existing_case.organization_id
                    and existing_case.organization_id != organization.id
                ):
                    raise EvidenceReviewConflict(
                        "This evidence case belongs to " "another organization."
                    )

                if existing_case.organization_id is None:
                    existing_case.organization = organization

                    existing_case.save(
                        update_fields=[
                            "organization",
                            "updated_at",
                        ]
                    )

            return existing_case

        raise


def _prepare_evidence_case_for_review(
    case,
    *,
    actor,
    allow_reopen=True,
):
    if case.status == ModerationCase.Status.RESOLVED:
        if not allow_reopen:
            raise EvidenceReviewConflict(
                "This Evidence case is already resolved and is read-only."
            )

        case = transition_moderation_case(
            case,
            next_status=(ModerationCase.Status.REOPENED),
            actor=actor,
            reason_code="RE_REVIEW",
        )

        ModerationEvent.objects.create(
            case=case,
            actor=actor,
            event_type=(ModerationEvent.EventType.EVIDENCE_REOPENED),
            from_status=(ModerationCase.Status.RESOLVED),
            to_status=(ModerationCase.Status.REOPENED),
            reason_code="RE_REVIEW",
        )

    if case.status in {
        ModerationCase.Status.OPEN,
        ModerationCase.Status.REOPENED,
        ModerationCase.Status.ESCALATED,
    }:
        case = transition_moderation_case(
            case,
            next_status=(ModerationCase.Status.IN_REVIEW),
            actor=actor,
        )

    if case.status != ModerationCase.Status.IN_REVIEW:
        raise InvalidModerationTransition(
            "Evidence cannot be reviewed while " f"its case is {case.status}."
        )

    return case


def _is_expected_active_evidence_case_conflict(error):
    """Recognize only the active Evidence-case uniqueness violation."""
    cause = getattr(error, "__cause__", None)
    if not isinstance(cause, IntegrityError):
        return False

    driver_error = getattr(cause, "__cause__", None)
    diagnostic = getattr(driver_error, "diag", None) or getattr(cause, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    sqlstate = (
        getattr(driver_error, "sqlstate", None)
        or getattr(driver_error, "pgcode", None)
        or getattr(cause, "sqlstate", None)
        or getattr(cause, "pgcode", None)
    )

    if sqlstate is not None and sqlstate != "23505":
        return False

    if constraint_name is not None:
        return constraint_name == "uniq_active_evidence_case"

    message = str(driver_error or cause).lower().strip()

    # PostgreSQL fallback when the driver does not expose the
    # constraint name, but identifies the exact unique constraint.
    if sqlstate == "23505":
        return 'constraint "uniq_active_evidence_case"' in message

    # SQLite's exact unique-column diagnostic.
    return (
        message == "unique constraint failed: api_moderationcase.evidence_submission_id"
    )


def review_correction_evidence(
    *,
    correction_request_id,
    evidence_id,
    actor,
    evidence_status,
    expected_evidence_status,
    expected_case_id=None,
    moderator_notes="",
    rejection_reason=None,
    expected_predecessor_version,
    expected_decision_revision,
):
    """Review evidence under one explicit active factual-correction reservation.

    The shared publication context establishes the Claim-first authority lock
    order through correction requests. The correction Adjudication case, selected
    evidence row, and its Evidence cases are locked only after that context.
    """

    _validate_correction_evidence_decision(
        evidence_status=evidence_status,
        expected_evidence_status=expected_evidence_status,
        moderator_notes=moderator_notes,
        rejection_reason=rejection_reason,
    )
    expected_predecessor_version = _parse_correction_version(
        expected_predecessor_version,
        "expected_predecessor_version",
    )
    expected_decision_revision = _parse_correction_version(
        expected_decision_revision,
        "expected_decision_revision",
    )
    if expected_case_id is not None:
        expected_case_id = _parse_correction_uuid(
            expected_case_id,
            "expected_case_id",
        )
    if not actor or not actor.is_authenticated:
        raise EvidenceReviewAuthorizationError(
            "Authentication is required to review correction evidence."
        )

    identity = _get_correction_review_identity(
        correction_request_id=correction_request_id,
        evidence_id=evidence_id,
    )

    with transaction.atomic():
        try:
            context = _lock_publication_context(
                identity=identity,
                actor=actor,
                capability=PartnerCapability.REVIEW_EVIDENCE,
            )
        except PublishingAuthorizationError as error:
            raise EvidenceReviewAuthorizationError(
                "You do not have permission to review correction evidence for "
                "this organization."
            ) from error
        except PublishingConflict as error:
            raise EvidenceReviewConflict(str(error)) from error

        correction_request = next(
            (
                item
                for item in context["correction_requests"]
                if item.id == identity["correction_request_id"]
            ),
            None,
        )
        if (
            correction_request is None
            or correction_request.status != FactualCorrectionRequest.Status.ACTIVE
        ):
            raise EvidenceReviewConflict(
                "The factual correction request is no longer active."
            )

        decision = context["decision"]
        predecessor = context["fact_check"]
        if predecessor.version != expected_predecessor_version:
            raise EvidenceReviewConflict(
                "The published predecessor changed before evidence review."
            )
        if decision.revision_number != expected_decision_revision:
            raise EvidenceReviewConflict(
                "The adjudication decision changed before evidence review."
            )
        if (
            correction_request.claim_id != context["claim"].id
            or correction_request.organization_id != context["organization"].id
            or correction_request.predecessor_decision_id != decision.id
            or correction_request.predecessor_fact_check_id != predecessor.id
        ):
            raise EvidenceReviewConflict(
                "The correction request no longer matches its recorded authority."
            )

        published = [
            item
            for item in context["fact_checks"]
            if item.publication_status == OfficialFactCheck.PublicationStatus.PUBLISHED
        ]
        if len(published) != 1 or published[0].id != predecessor.id:
            raise EvidenceReviewConflict(
                "The correction request's predecessor is not the current "
                "published fact-check."
            )
        try:
            predecessor_snapshot = _validate_editorial_revision_chain(
                predecessor=predecessor,
                fact_checks=context["fact_checks"],
                publication_snapshots=context["publication_snapshots"],
                decision=decision,
                decision_snapshot=context["decision_snapshot"],
                organization=context["organization"],
            )
        except PublishingConflict as error:
            raise EvidenceReviewConflict(str(error)) from error
        if (
            correction_request.predecessor_publication_snapshot_id
            != predecessor_snapshot.id
        ):
            raise EvidenceReviewConflict(
                "The correction request no longer matches its sealed predecessor."
            )
        if context["assignment"] is not None:
            raise EvidenceReviewConflict(
                "Correction evidence review cannot run through an ordinary "
                "verification assignment."
            )

        correction_case = (
            ModerationCase.objects.select_for_update(of=("self",))
            .filter(
                pk=correction_request.moderation_case_id,
                case_type=ModerationCase.CaseType.ADJUDICATION,
                claim=context["claim"],
                organization=context["organization"],
                status__in=ACTIVE_CASE_STATUSES,
            )
            .first()
        )
        if correction_case is None or correction_case.id == decision.moderation_case_id:
            raise EvidenceReviewConflict(
                "The factual correction request's correction case is not active."
            )

        try:
            locked_evidence = (
                EvidenceSubmission.objects.select_for_update(of=("self",))
                .select_related("contributor", "thread", "thread__claim")
                .get(
                    pk=identity["evidence_id"],
                    thread__claim=context["claim"],
                )
            )
        except EvidenceSubmission.DoesNotExist as error:
            raise EvidenceReviewConflict(
                "This evidence is no longer available for correction review."
            ) from error

        if locked_evidence.contributor_id == actor.id:
            raise EvidenceReviewAuthorizationError(
                "You cannot review your own evidence."
            )
        if locked_evidence.evidence_status != expected_evidence_status:
            raise EvidenceReviewConflict(
                "This evidence changed after the correction review was opened. "
                "Refresh it before deciding."
            )

        evidence_cases = list(
            ModerationCase.objects.select_for_update(of=("self",))
            .select_related("organization")
            .filter(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=locked_evidence,
            )
            .order_by("created_at", "id")
        )
        active_cases = [
            item for item in evidence_cases if item.status in ACTIVE_CASE_STATUSES
        ]
        if expected_case_id is not None:
            case = next(
                (item for item in evidence_cases if item.id == expected_case_id),
                None,
            )
            if case is None or any(
                item.id != expected_case_id for item in active_cases
            ):
                raise EvidenceReviewConflict("This Evidence case is no longer current.")
            if case.status == ModerationCase.Status.CANCELLED:
                raise EvidenceReviewConflict(
                    "The selected Evidence case was cancelled."
                )
        elif active_cases:
            case = active_cases[-1]
        else:
            case = evidence_cases[-1] if evidence_cases else None

        if case is not None and case.organization_id != context["organization"].id:
            raise EvidenceReviewConflict(
                "This Evidence case is not owned by the organization responsible "
                "for the correction."
            )
        if case is None or case.status == ModerationCase.Status.CANCELLED:
            try:
                case = create_moderation_case(
                    case_type=ModerationCase.CaseType.EVIDENCE,
                    actor=actor,
                    source=ModerationCase.Source.EVIDENCE_SUBMISSION,
                    evidence_submission=locked_evidence,
                    organization=context["organization"],
                )
            except DuplicateActiveModerationCase as error:
                if _is_expected_active_evidence_case_conflict(error):
                    raise EvidenceReviewConflict(
                        "This Evidence case changed before correction review."
                    ) from error

                # The shared helper may wrap an unrelated IntegrityError.
                # Preserve the original failure instead of disguising it.
                underlying = getattr(error, "__cause__", None)
                if underlying is not None:
                    raise underlying from error
                raise

        if case.organization_id != context["organization"].id:
            raise EvidenceReviewConflict(
                "This Evidence case is not owned by the organization responsible "
                "for the correction."
            )
        if not has_case_capability(
            actor,
            case,
            PartnerCapability.REVIEW_EVIDENCE,
        ):
            raise EvidenceReviewAuthorizationError(
                "You do not have permission to review this correction evidence."
            )

        case = _prepare_evidence_case_for_review(
            case,
            actor=actor,
            allow_reopen=True,
        )
        previous_status = locked_evidence.evidence_status
        reviewed_at = timezone.now()
        locked_evidence.evidence_status = evidence_status
        locked_evidence.verified_by = actor
        locked_evidence.verified_at = reviewed_at
        locked_evidence.moderator_notes = moderator_notes
        locked_evidence.rejection_reason = (
            rejection_reason
            if evidence_status == EvidenceSubmission.EvidenceStatus.REJECTED
            else None
        )
        locked_evidence.save(
            update_fields=[
                "evidence_status",
                "verified_by",
                "verified_at",
                "moderator_notes",
                "rejection_reason",
            ]
        )

        try:
            evidence_records = validate_evidence_snapshot(
                schema_version=EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
                evidence_records=_build_decision_evidence_records([locked_evidence]),
            )
        except EvidenceSnapshotSchemaError as error:
            raise EvidenceReviewConflict(
                "The correction evidence review record could not be captured."
            ) from error
        evidence_record = evidence_records[0]
        event_type = (
            ModerationEvent.EventType.EVIDENCE_VERIFIED
            if evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED
            else ModerationEvent.EventType.EVIDENCE_REJECTED
        )
        review_event = ModerationEvent.objects.create(
            case=case,
            actor=actor,
            event_type=event_type,
            from_status=case.status,
            to_status=case.status,
            reason_code=rejection_reason or evidence_status,
            notes=moderator_notes or None,
            metadata={
                "correction_request_id": str(correction_request.id),
                "correction_case_id": str(correction_case.id),
                "evidence_case_id": str(case.id),
                "reviewer_snapshot": {
                    "id": str(actor.pk),
                    "username": actor.username,
                },
                "previous_evidence_status": previous_status,
                "new_evidence_status": evidence_status,
                "is_reaffirmation": previous_status == evidence_status,
                "evidence_snapshot_schema_version": (EVIDENCE_SNAPSHOT_SCHEMA_VERSION),
                "evidence_record": evidence_record,
            },
        )
        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.RESOLVED,
            actor=actor,
            resolution_code=evidence_status,
            resolution_summary=(
                moderator_notes
                or (
                    "Evidence verified."
                    if evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED
                    else "Evidence rejected."
                )
            ),
        )

        return {
            "request": correction_request,
            "correction_case": correction_case,
            "evidence": locked_evidence,
            "case": case,
            "event": review_event,
            "evidence_record": evidence_record,
            "contributor_id": locked_evidence.contributor_id,
        }


def review_evidence_submission(
    *,
    evidence,
    actor,
    evidence_status,
    moderator_notes="",
    rejection_reason=None,
    expected_status=None,
    expected_case_id=None,
    expected_organization_id=None,
    allow_reopen=True,
):
    allowed_statuses = {
        EvidenceSubmission.EvidenceStatus.VERIFIED,
        EvidenceSubmission.EvidenceStatus.REJECTED,
    }

    valid_evidence_statuses = {
        value for value, _label in EvidenceSubmission.EvidenceStatus.choices
    }

    if expected_status is not None and expected_status not in valid_evidence_statuses:
        raise InvalidEvidenceDecision("Invalid expected evidence status.")

    if evidence_status not in allowed_statuses:
        raise InvalidEvidenceDecision(
            "Evidence decision must be VERIFIED " "or REJECTED."
        )

    if len(moderator_notes or "") > 2000:
        raise InvalidEvidenceDecision(
            "Moderator notes must be 2000 characters or fewer."
        )

    if (
        evidence_status == EvidenceSubmission.EvidenceStatus.REJECTED
        and not rejection_reason
    ):
        raise InvalidEvidenceDecision(
            "A rejection reason is required " "when rejecting evidence."
        )

    valid_rejection_reasons = {
        value for value, _label in EvidenceSubmission.RejectionReason.choices
    }

    if rejection_reason and rejection_reason not in valid_rejection_reasons:
        raise InvalidEvidenceDecision("Invalid evidence rejection reason.")

    if (
        evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED
        and rejection_reason
    ):
        raise InvalidEvidenceDecision(
            "A rejection reason cannot be supplied when verifying evidence."
        )

    if not actor or not actor.is_authenticated:
        raise EvidenceReviewAuthorizationError(
            "Authentication is required to review evidence."
        )

    claim_id = evidence.thread.claim_id

    with transaction.atomic():
        try:
            locked_claim = Claim.objects.select_for_update().get(pk=claim_id)
        except Claim.DoesNotExist as error:
            raise EvidenceReviewConflict(
                "The claim for this evidence is no longer available."
            ) from error

        organization = get_claim_verification_organization(
            locked_claim,
            lock=True,
        )

        if organization is None:
            raise EvidenceReviewConflict(
                "This claim no longer has an active organization verification "
                "assignment."
            )

        if (
            expected_organization_id is not None
            and organization.pk != expected_organization_id
        ):
            raise EvidenceReviewConflict(
                "The organization responsible for this claim changed after the "
                "review was opened."
            )

        try:
            locked_evidence = (
                EvidenceSubmission.objects.select_for_update()
                .select_related(
                    "contributor",
                    "thread",
                    "thread__claim",
                )
                .get(pk=evidence.pk)
            )
        except EvidenceSubmission.DoesNotExist as error:
            raise EvidenceReviewConflict(
                "This evidence is no longer available for review."
            ) from error

        if locked_evidence.thread.claim_id != locked_claim.pk:
            raise EvidenceReviewConflict(
                "This evidence no longer belongs to the expected claim."
            )

        if locked_evidence.contributor_id == actor.id:
            raise EvidenceReviewAuthorizationError(
                "You cannot review your own evidence."
            )

        if (
            expected_status is not None
            and locked_evidence.evidence_status != expected_status
        ):
            raise EvidenceReviewConflict(
                "This evidence changed after the review "
                "was opened. Refresh it before deciding."
            )

        if get_current_adjudication_decision(
            locked_claim,
            lock=True,
        ):
            raise EvidenceReviewConflict(
                "This claim has already been adjudicated. An explicit revision "
                "workflow is required before its evidence can change."
            )

        if expected_case_id is not None:
            try:
                requested_case = ModerationCase.objects.select_for_update(
                    of=("self",)
                ).get(
                    pk=expected_case_id,
                    case_type=ModerationCase.CaseType.EVIDENCE,
                    evidence_submission=locked_evidence,
                )
            except ModerationCase.DoesNotExist as error:
                raise EvidenceReviewConflict(
                    "This Evidence case is no longer current."
                ) from error

            active_case = get_active_evidence_case(
                locked_evidence,
                lock=True,
            )

            if active_case is None or active_case.pk != requested_case.pk:
                raise EvidenceReviewConflict(
                    "This Evidence case is no longer current. Refresh before "
                    "deciding."
                )

            case = requested_case
        else:
            case = ensure_evidence_case(
                evidence=locked_evidence,
                actor=actor,
                organization=organization,
            )

        if case.organization_id != organization.pk:
            raise EvidenceReviewConflict(
                "This Evidence case is not owned by the organization currently "
                "responsible for the claim."
            )

        if (
            expected_organization_id is not None
            and case.organization_id != expected_organization_id
        ):
            raise EvidenceReviewConflict(
                "This Evidence case does not belong to the requested organization."
            )

        if not has_case_capability(
            actor,
            case,
            PartnerCapability.REVIEW_EVIDENCE,
        ):
            raise EvidenceReviewAuthorizationError(
                "You do not have permission to review " "this evidence."
            )

        case = _prepare_evidence_case_for_review(
            case,
            actor=actor,
            allow_reopen=allow_reopen,
        )

        previous_status = locked_evidence.evidence_status

        locked_evidence.evidence_status = evidence_status

        locked_evidence.verified_by = actor
        locked_evidence.verified_at = timezone.now()

        locked_evidence.moderator_notes = moderator_notes

        locked_evidence.rejection_reason = (
            rejection_reason
            if (evidence_status == EvidenceSubmission.EvidenceStatus.REJECTED)
            else None
        )

        locked_evidence.save(
            update_fields=[
                "evidence_status",
                "verified_by",
                "verified_at",
                "moderator_notes",
                "rejection_reason",
            ]
        )

        event_type = (
            ModerationEvent.EventType.EVIDENCE_VERIFIED
            if (evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED)
            else (ModerationEvent.EventType.EVIDENCE_REJECTED)
        )

        ModerationEvent.objects.create(
            case=case,
            actor=actor,
            event_type=event_type,
            from_status=case.status,
            to_status=case.status,
            reason_code=(rejection_reason if rejection_reason else evidence_status),
            notes=(moderator_notes or None),
            metadata={
                "previous_evidence_status": previous_status,
                "new_evidence_status": evidence_status,
            },
        )

        case = transition_moderation_case(
            case,
            next_status=(ModerationCase.Status.RESOLVED),
            actor=actor,
            resolution_code=(evidence_status),
            resolution_summary=(
                moderator_notes
                or (
                    "Evidence verified."
                    if (evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED)
                    else "Evidence rejected."
                )
            ),
        )

        adjudication_case = ensure_claim_adjudication_readiness(
            claim=locked_claim,
            actor=actor,
            organization=organization,
        )

        return {
            "evidence": locked_evidence,
            "case": case,
            "contributor_id": (locked_evidence.contributor_id),
            "adjudication_case": adjudication_case,
        }


def schedule_evidence_review_trust_updates(result):
    contributor_id = result.get("contributor_id")
    if not contributor_id:
        return

    evidence = result.get("evidence")
    case = result.get("case")
    evidence_id = getattr(evidence, "pk", None)
    case_id = getattr(case, "pk", None)

    try:
        from .trust_service import recompute_user_trust_score

        recompute_user_trust_score(contributor_id)
    except Exception:
        logger.exception(
            "Failed immediate post-commit Evidence trust recomputation for "
            "user_id=%s evidence_id=%s case_id=%s.",
            contributor_id,
            evidence_id,
            case_id,
        )

    def dispatch_trust_update():
        try:
            from .tasks import recompute_user_trust_score_task

            recompute_user_trust_score_task.delay(contributor_id)
        except Exception:
            logger.exception(
                "Failed to enqueue post-commit Evidence trust recomputation for "
                "user_id=%s evidence_id=%s case_id=%s.",
                contributor_id,
                evidence_id,
                case_id,
            )

    transaction.on_commit(dispatch_trust_update, robust=True)
