import logging

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from .models import (
    Claim,
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
    get_current_adjudication_decision,
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
                requested_case = (
                    ModerationCase.objects.select_for_update(of=("self",))
                    .get(
                        pk=expected_case_id,
                        case_type=ModerationCase.CaseType.EVIDENCE,
                        evidence_submission=locked_evidence,
                    )
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
