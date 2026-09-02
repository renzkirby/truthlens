from django.db import transaction
from django.utils import timezone

from .models import (
    EvidenceSubmission,
    ModerationCase,
    ModerationEvent,
)

from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    DuplicateActiveModerationCase,
    InvalidModerationTransition,
    create_moderation_case,
    transition_moderation_case,
)
from .adjudication_service import (
    ensure_claim_adjudication_readiness,
)
from .verification_assignment_service import (
    get_claim_verification_organization,
)
from .organization_service import (
    PartnerCapability,
    has_case_capability,
)


class EvidenceReviewError(Exception):
    pass


class EvidenceReviewAuthorizationError(EvidenceReviewError):
    pass


class InvalidEvidenceDecision(EvidenceReviewError):
    pass


class EvidenceReviewConflict(EvidenceReviewError):
    pass


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
):
    if case.status == ModerationCase.Status.RESOLVED:
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


def review_evidence_submission(
    *,
    evidence,
    actor,
    evidence_status,
    moderator_notes="",
    rejection_reason=None,
    expected_status=None,
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

    with transaction.atomic():
        locked_evidence = (
            EvidenceSubmission.objects.select_for_update()
            .select_related(
                "contributor",
                "thread",
                "thread__claim",
            )
            .get(pk=evidence.pk)
        )

        if not actor or not actor.is_authenticated:
            raise EvidenceReviewAuthorizationError(
                "Authentication is required to review " "evidence."
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

        organization = get_claim_verification_organization(
            locked_evidence.thread.claim,
            lock=True,
        )

        case = ensure_evidence_case(
            evidence=locked_evidence,
            actor=actor,
            organization=organization,
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
            claim=locked_evidence.thread.claim,
            actor=actor,
            organization=organization,
        )

        return {
            "evidence": locked_evidence,
            "case": case,
            "contributor_id": (locked_evidence.contributor_id),
            "adjudication_case": adjudication_case,
        }
