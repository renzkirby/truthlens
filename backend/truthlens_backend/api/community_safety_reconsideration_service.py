"""Community Safety reconsideration and reversal workflow."""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    CommunitySafetyDecision,
    CommunitySafetyReconsideration,
    FlagResolutionLog,
    ModerationCase,
    Thread,
)
from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    InvalidModerationTransition,
    transition_moderation_case,
    unassign_moderation_case,
)
from .platform_identity_service import can_review_platform_safety


logger = logging.getLogger(__name__)

RESTORABLE_THREAD_STATUSES = {
    Thread.Status.PENDING,
    Thread.Status.OPEN,
    Thread.Status.CLOSED,
}


class CommunitySafetyReconsiderationError(Exception):
    pass


class CommunitySafetyReconsiderationNotFound(CommunitySafetyReconsiderationError):
    pass


class CommunitySafetyReconsiderationAuthorizationError(
    CommunitySafetyReconsiderationError
):
    pass


class CommunitySafetyReconsiderationConflict(CommunitySafetyReconsiderationError):
    pass


def _decision_queryset():
    return CommunitySafetyDecision.objects.select_related(
        "moderation_case",
    )


def can_request_reconsideration(*, decision, actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        return False
    if decision.thread_author_id != actor.pk:
        return False
    if decision.action != CommunitySafetyDecision.Action.REMOVE:
        return False
    if not decision.restoration_snapshot_complete:
        return False
    if decision.pre_removal_thread_status not in RESTORABLE_THREAD_STATUSES:
        return False
    if decision.moderation_case.status != ModerationCase.Status.RESOLVED:
        return False
    if CommunitySafetyReconsideration.objects.filter(
        safety_decision=decision,
    ).exists():
        return False

    return Thread.objects.filter(
        pk=decision.thread_id_snapshot,
        status=Thread.Status.REJECTED,
    ).exists()


@transaction.atomic
def submit_reconsideration(*, decision_id, actor, request_statement):
    try:
        decision = CommunitySafetyDecision.objects.select_for_update().get(
            pk=decision_id,
        )
    except CommunitySafetyDecision.DoesNotExist as error:
        raise CommunitySafetyReconsiderationNotFound() from error

    if decision.thread_author_id != getattr(actor, "pk", None):
        raise CommunitySafetyReconsiderationNotFound()

    if decision.action != CommunitySafetyDecision.Action.REMOVE:
        raise CommunitySafetyReconsiderationConflict(
            "Only removed Community content can be reconsidered."
        )

    if not decision.restoration_snapshot_complete:
        raise CommunitySafetyReconsiderationConflict(
            "This historical removal predates complete restoration snapshots "
            "and cannot be reversed safely."
        )

    if decision.pre_removal_thread_status not in RESTORABLE_THREAD_STATUSES:
        raise CommunitySafetyReconsiderationConflict(
            "This historical removal does not have a safe restoration state."
        )

    case = ModerationCase.objects.select_for_update().get(
        pk=decision.moderation_case_id,
        case_type=ModerationCase.CaseType.SAFETY,
    )
    try:
        thread = Thread.objects.select_for_update().get(
            pk=decision.thread_id_snapshot,
        )
    except Thread.DoesNotExist as error:
        raise CommunitySafetyReconsiderationConflict(
            "The removed discussion is no longer available for reconsideration."
        ) from error

    if case.thread_id != thread.pk or thread.author_id != decision.thread_author_id:
        raise CommunitySafetyReconsiderationConflict(
            "The original Safety decision no longer matches the discussion."
        )

    if case.status != ModerationCase.Status.RESOLVED:
        raise CommunitySafetyReconsiderationConflict(
            "This Safety decision is not in a final state that can be reconsidered."
        )

    if thread.status != Thread.Status.REJECTED:
        raise CommunitySafetyReconsiderationConflict(
            "The discussion is no longer in the removed state targeted by this decision."
        )

    if CommunitySafetyReconsideration.objects.filter(
        safety_decision=decision,
    ).exists():
        raise CommunitySafetyReconsiderationConflict(
            "A reconsideration request has already been submitted for this removal."
        )

    competing_case_exists = (
        ModerationCase.objects.select_for_update()
        .filter(
            case_type=ModerationCase.CaseType.SAFETY,
            thread=thread,
            status__in=ACTIVE_CASE_STATUSES,
        )
        .exclude(pk=case.pk)
        .exists()
    )
    if competing_case_exists:
        raise CommunitySafetyReconsiderationConflict(
            "Another active Safety review must finish before this removal can be reconsidered."
        )

    try:
        reconsideration = CommunitySafetyReconsideration.objects.create(
            safety_decision=decision,
            requested_by=actor,
            request_statement=request_statement,
        )
    except IntegrityError as error:
        raise CommunitySafetyReconsiderationConflict(
            "A reconsideration request has already been submitted for this removal."
        ) from error

    try:
        reopened_case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.REOPENED,
            actor=actor,
            reason_code="RECONSIDERATION_REQUESTED",
            notes="The discussion author requested reconsideration of the removal.",
            metadata={
                "decision_id": str(decision.pk),
                "reconsideration_id": str(reconsideration.pk),
            },
        )
    except (IntegrityError, InvalidModerationTransition) as error:
        raise CommunitySafetyReconsiderationConflict(
            "The Safety case changed before reconsideration could be opened."
        ) from error

    if reopened_case.assigned_to_id is not None:
        unassign_moderation_case(
            reopened_case,
            actor=actor,
        )

    return reconsideration


@transaction.atomic
def resolve_reconsideration(*, case, actor, outcome, resolution_rationale):
    if not can_review_platform_safety(actor):
        raise CommunitySafetyReconsiderationAuthorizationError(
            "Platform Safety review authority is required."
        )

    locked_case = ModerationCase.objects.select_for_update().get(
        pk=case.pk,
        case_type=ModerationCase.CaseType.SAFETY,
    )

    if locked_case.assigned_to_id is None:
        raise CommunitySafetyReconsiderationConflict(
            "Claim this Safety case before deciding the reconsideration."
        )
    if locked_case.assigned_to_id != actor.pk:
        raise CommunitySafetyReconsiderationAuthorizationError(
            "This reconsideration is assigned to another Safety reviewer."
        )
    if locked_case.status not in {
        ModerationCase.Status.REOPENED,
        ModerationCase.Status.IN_REVIEW,
    }:
        raise CommunitySafetyReconsiderationConflict(
            "This Safety case is not awaiting a reconsideration decision."
        )

    try:
        decision = (
            CommunitySafetyDecision.objects.select_for_update()
            .get(moderation_case=locked_case)
        )
        reconsideration = (
            CommunitySafetyReconsideration.objects.select_for_update()
            .get(safety_decision=decision)
        )
    except (
        CommunitySafetyDecision.DoesNotExist,
        CommunitySafetyReconsideration.DoesNotExist,
    ) as error:
        raise CommunitySafetyReconsiderationConflict(
            "This Safety case does not have an active reconsideration request."
        ) from error

    if reconsideration.outcome:
        raise CommunitySafetyReconsiderationConflict(
            "This reconsideration has already been resolved."
        )

    if decision.action != CommunitySafetyDecision.Action.REMOVE:
        raise CommunitySafetyReconsiderationConflict(
            "Only a removed-content decision can be reconsidered."
        )
    if not decision.restoration_snapshot_complete:
        raise CommunitySafetyReconsiderationConflict(
            "This historical removal does not have a complete restoration snapshot."
        )

    try:
        thread = Thread.objects.select_for_update().get(
            pk=decision.thread_id_snapshot,
        )
    except Thread.DoesNotExist as error:
        raise CommunitySafetyReconsiderationConflict(
            "The removed discussion no longer exists."
        ) from error

    if (
        locked_case.thread_id != thread.pk
        or thread.status != Thread.Status.REJECTED
    ):
        raise CommunitySafetyReconsiderationConflict(
            "The discussion is no longer in the removed state targeted by this reconsideration."
        )

    if locked_case.status == ModerationCase.Status.REOPENED:
        locked_case = transition_moderation_case(
            locked_case,
            next_status=ModerationCase.Status.IN_REVIEW,
            actor=actor,
            reason_code="RECONSIDERATION_REVIEW_STARTED",
            metadata={
                "decision_id": str(decision.pk),
                "reconsideration_id": str(reconsideration.pk),
            },
        )

    previous_thread_status = thread.status
    if outcome == CommunitySafetyReconsideration.Outcome.REVERSED:
        if decision.pre_removal_thread_status not in RESTORABLE_THREAD_STATUSES:
            raise CommunitySafetyReconsiderationConflict(
                "The original thread state cannot be restored safely."
            )
        thread.status = decision.pre_removal_thread_status
        thread.moderated_by_id = decision.pre_removal_moderated_by_id
        thread.moderated_at = decision.pre_removal_moderated_at
        thread.moderator_notes = decision.pre_removal_moderator_notes
        thread.save(
            update_fields=[
                "status",
                "moderated_by",
                "moderated_at",
                "moderator_notes",
            ]
        )
        resolution_code = "RECONSIDERATION_REVERSED"
    else:
        resolution_code = "RECONSIDERATION_UPHELD"

    reconsideration.outcome = outcome
    reconsideration.resolution_rationale = resolution_rationale
    reconsideration.reviewed_by = actor
    reconsideration.resolved_at = timezone.now()
    reconsideration.save(
        update_fields=[
            "outcome",
            "resolution_rationale",
            "reviewed_by",
            "resolved_at",
        ]
    )

    resolved_case = transition_moderation_case(
        locked_case,
        next_status=ModerationCase.Status.RESOLVED,
        actor=actor,
        reason_code=resolution_code,
        notes=resolution_rationale,
        resolution_code=resolution_code,
        resolution_summary=resolution_rationale,
        metadata={
            "decision_id": str(decision.pk),
            "reconsideration_id": str(reconsideration.pk),
            "thread_status_before": previous_thread_status,
            "thread_status_after": thread.status,
        },
    )

    confirmed_reporter_ids = set(
        FlagResolutionLog.objects.filter(
            safety_decision=decision,
            is_valid_report=True,
        ).values_list("flagged_by_id", flat=True)
    )

    return {
        "case": resolved_case,
        "thread": thread,
        "decision": decision,
        "reconsideration": reconsideration,
        "author_id": decision.thread_author_id,
        "confirmed_reporter_ids": confirmed_reporter_ids,
    }


def schedule_reconsideration_notifications(result):
    reconsideration = result["reconsideration"]
    decision = result["decision"]
    author_id = result.get("author_id")
    confirmed_reporter_ids = set(result.get("confirmed_reporter_ids", set()))

    def deliver():
        try:
            from .notification_service import (
                Target,
                Type,
                create_notification_once,
            )
        except Exception:
            logger.exception(
                "Failed to load Community reconsideration notification service "
                "for reconsideration_id=%s.",
                reconsideration.pk,
            )
            return

        if author_id:
            if reconsideration.outcome == CommunitySafetyReconsideration.Outcome.REVERSED:
                title = "Your discussion was restored"
                message = (
                    "Platform Safety reversed the original removal after reconsideration. "
                    "Open the moderation outcome to review the decision."
                )
            else:
                title = "Your reconsideration was reviewed"
                message = (
                    "Platform Safety upheld the original removal after reconsideration. "
                    "Open the moderation outcome to review the decision."
                )

            try:
                create_notification_once(
                    recipient_id=author_id,
                    notification_type=Type.COMMUNITY_MODERATION_OUTCOME,
                    target_type=Target.MODERATION_OUTCOME,
                    target_id=decision.pk,
                    dedupe_key=f"community-reconsideration:{reconsideration.pk}:author",
                    title=title,
                    message=message,
                )
            except Exception:
                logger.exception(
                    "Failed reconsideration author notification for "
                    "reconsideration_id=%s user_id=%s.",
                    reconsideration.pk,
                    author_id,
                )

        if reconsideration.outcome != CommunitySafetyReconsideration.Outcome.REVERSED:
            return

        for reporter_id in confirmed_reporter_ids:
            try:
                create_notification_once(
                    recipient_id=reporter_id,
                    notification_type=Type.COMMUNITY_MODERATION_OUTCOME,
                    target_type=Target.MODERATION_OUTCOME,
                    target_id=decision.pk,
                    dedupe_key=(
                        f"community-reconsideration:{reconsideration.pk}:"
                        f"reporter:{reporter_id}"
                    ),
                    title="Moderation decision updated",
                    message=(
                        "Platform Safety reversed the original removal. A report that "
                        "previously counted as confirmed no longer counts toward your "
                        "Community reputation."
                    ),
                )
            except Exception:
                logger.exception(
                    "Failed reconsideration reporter notification for "
                    "reconsideration_id=%s user_id=%s.",
                    reconsideration.pk,
                    reporter_id,
                )

    transaction.on_commit(deliver, robust=True)


def schedule_reconsideration_trust_updates(result):
    reconsideration = result["reconsideration"]
    if reconsideration.outcome != CommunitySafetyReconsideration.Outcome.REVERSED:
        return

    user_ids = set(result.get("confirmed_reporter_ids", set()))
    if result.get("author_id"):
        user_ids.add(result["author_id"])

    def refresh():
        try:
            from .trust_service import recompute_user_trust_score
        except Exception:
            logger.exception(
                "Failed to load Trust recomputation after reconsideration_id=%s.",
                reconsideration.pk,
            )
            return

        for user_id in user_ids:
            try:
                recompute_user_trust_score(user_id)
            except Exception:
                logger.exception(
                    "Failed Trust recomputation after reconsideration_id=%s "
                    "for user_id=%s.",
                    reconsideration.pk,
                    user_id,
                )

    transaction.on_commit(refresh, robust=True)
