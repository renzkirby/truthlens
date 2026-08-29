from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    FlagResolutionLog,
    ModerationCase,
    ModerationEvent,
    Thread,
    ThreadFlag,
)


ACTIVE_CASE_STATUSES = {
    ModerationCase.Status.OPEN,
    ModerationCase.Status.IN_REVIEW,
    ModerationCase.Status.ESCALATED,
    ModerationCase.Status.REOPENED,
}


ALLOWED_CASE_TRANSITIONS = {
    ModerationCase.Status.OPEN: {
        ModerationCase.Status.IN_REVIEW,
        ModerationCase.Status.CANCELLED,
    },
    ModerationCase.Status.IN_REVIEW: {
        ModerationCase.Status.ESCALATED,
        ModerationCase.Status.RESOLVED,
    },
    ModerationCase.Status.ESCALATED: {
        ModerationCase.Status.IN_REVIEW,
        ModerationCase.Status.RESOLVED,
    },
    ModerationCase.Status.RESOLVED: {
        ModerationCase.Status.REOPENED,
    },
    ModerationCase.Status.REOPENED: {
        ModerationCase.Status.IN_REVIEW,
    },
    ModerationCase.Status.CANCELLED: set(),
}


class ModerationCaseError(Exception):
    pass


class InvalidModerationCaseTarget(ModerationCaseError):
    pass


class InvalidModerationTransition(ModerationCaseError):
    pass


class DuplicateActiveModerationCase(ModerationCaseError):
    pass


class InvalidModerationAssignment(ModerationCaseError):
    pass


def _transition_event_type(next_status):
    mapping = {
        ModerationCase.Status.IN_REVIEW:
            ModerationEvent.EventType.REVIEW_STARTED,

        ModerationCase.Status.ESCALATED:
            ModerationEvent.EventType.CASE_ESCALATED,

        ModerationCase.Status.RESOLVED:
            ModerationEvent.EventType.CASE_RESOLVED,

        ModerationCase.Status.REOPENED:
            ModerationEvent.EventType.CASE_REOPENED,

        ModerationCase.Status.CANCELLED:
            ModerationEvent.EventType.CASE_CANCELLED,
    }

    return mapping[next_status]


def create_moderation_case(
    *,
    case_type,
    actor=None,
    source=ModerationCase.Source.SYSTEM,
    priority=ModerationCase.Priority.NORMAL,
    thread=None,
    claim=None,
    evidence_submission=None,
):
    case = ModerationCase(
        case_type=case_type,
        source=source,
        priority=priority,
        thread=thread,
        claim=claim,
        evidence_submission=evidence_submission,
    )

    try:
        case.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )
    except ValidationError as error:
        raise InvalidModerationCaseTarget(
            error.message_dict
            if hasattr(error, "message_dict")
            else error.messages
        ) from error

    try:
        with transaction.atomic():
            case.save()

            ModerationEvent.objects.create(
                case=case,
                actor=actor,
                event_type=ModerationEvent.EventType.CASE_CREATED,
                to_status=ModerationCase.Status.OPEN,
                metadata={
                    "source": source,
                    "priority": priority,
                },
            )

    except IntegrityError as error:
        raise DuplicateActiveModerationCase(
            "An active moderation case already exists "
            "for this target."
        ) from error

    return case


def assign_moderation_case(
    case,
    *,
    assignee,
    actor,
):
    with transaction.atomic():
        locked_case = (
            ModerationCase.objects
            .select_for_update()
            .get(pk=case.pk)
        )

        if locked_case.status not in ACTIVE_CASE_STATUSES:
            raise InvalidModerationAssignment(
                "Resolved or cancelled cases cannot be assigned."
            )

        previous_assignee_id = locked_case.assigned_to_id

        locked_case.assigned_to = assignee
        locked_case.assigned_at = timezone.now()
        locked_case.save(
            update_fields=[
                "assigned_to",
                "assigned_at",
                "updated_at",
            ]
        )

        event_type = (
            ModerationEvent.EventType.CASE_CLAIMED
            if assignee.pk == actor.pk
            else ModerationEvent.EventType.CASE_ASSIGNED
        )

        ModerationEvent.objects.create(
            case=locked_case,
            actor=actor,
            event_type=event_type,
            from_status=locked_case.status,
            to_status=locked_case.status,
            metadata={
                "previous_assignee_id": (
                    str(previous_assignee_id)
                    if previous_assignee_id
                    else None
                ),
                "new_assignee_id": str(assignee.pk),
            },
        )

        return locked_case


def unassign_moderation_case(
    case,
    *,
    actor,
):
    with transaction.atomic():
        locked_case = (
            ModerationCase.objects
            .select_for_update()
            .get(pk=case.pk)
        )

        if locked_case.status not in ACTIVE_CASE_STATUSES:
            raise InvalidModerationAssignment(
                "Resolved or cancelled cases cannot be unassigned."
            )

        previous_assignee_id = locked_case.assigned_to_id

        locked_case.assigned_to = None
        locked_case.assigned_at = None
        locked_case.save(
            update_fields=[
                "assigned_to",
                "assigned_at",
                "updated_at",
            ]
        )

        ModerationEvent.objects.create(
            case=locked_case,
            actor=actor,
            event_type=ModerationEvent.EventType.CASE_UNASSIGNED,
            from_status=locked_case.status,
            to_status=locked_case.status,
            metadata={
                "previous_assignee_id": (
                    str(previous_assignee_id)
                    if previous_assignee_id
                    else None
                ),
            },
        )

        return locked_case


def transition_moderation_case(
    case,
    *,
    next_status,
    actor,
    reason_code="",
    notes="",
    resolution_code=None,
    resolution_summary=None,
    metadata=None,
):
    metadata = dict(metadata or {})

    with transaction.atomic():
        locked_case = (
            ModerationCase.objects
            .select_for_update()
            .get(pk=case.pk)
        )

        current_status = locked_case.status

        allowed_next_statuses = ALLOWED_CASE_TRANSITIONS.get(
            current_status,
            set(),
        )

        if next_status not in allowed_next_statuses:
            raise InvalidModerationTransition(
                f"Invalid moderation case transition "
                f"from {current_status} to {next_status}."
            )

        if next_status == ModerationCase.Status.RESOLVED:
            locked_case.resolution_code = resolution_code
            locked_case.resolution_summary = resolution_summary
            locked_case.resolved_by = actor
            locked_case.resolved_at = timezone.now()

        elif next_status == ModerationCase.Status.REOPENED:
            metadata.setdefault(
                "previous_resolution_code",
                locked_case.resolution_code,
            )

            locked_case.resolution_code = None
            locked_case.resolution_summary = None
            locked_case.resolved_by = None
            locked_case.resolved_at = None

        locked_case.status = next_status

        locked_case.save(
            update_fields=[
                "status",
                "resolution_code",
                "resolution_summary",
                "resolved_by",
                "resolved_at",
                "updated_at",
            ]
        )

        ModerationEvent.objects.create(
            case=locked_case,
            actor=actor,
            event_type=_transition_event_type(next_status),
            from_status=current_status,
            to_status=next_status,
            reason_code=reason_code or None,
            notes=notes or None,
            metadata=metadata,
        )

        return locked_case


SAFETY_ACTION_DISMISS = "DISMISS"
SAFETY_ACTION_REMOVE = "REMOVE"
SAFETY_ACTION_ESCALATE = "ESCALATE"

SAFETY_RESOLUTION_NO_VIOLATION = "NO_VIOLATION"
SAFETY_RESOLUTION_CONTENT_REMOVED = "CONTENT_REMOVED"


def get_active_safety_case(
    thread,
    *,
    lock=False,
):
    queryset = ModerationCase.objects.filter(
        case_type=ModerationCase.CaseType.SAFETY,
        thread=thread,
        status__in=ACTIVE_CASE_STATUSES,
    )

    if lock:
        queryset = queryset.select_for_update()

    return (
        queryset
        .order_by("-created_at")
        .first()
    )


def ensure_safety_case(
    *,
    thread,
    actor=None,
):
    existing_case = get_active_safety_case(thread)

    if existing_case:
        return existing_case

    try:
        return create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=actor,
            source=ModerationCase.Source.USER_REPORT,
            thread=thread,
        )

    except DuplicateActiveModerationCase:
        # Handles the race where two reports create the first
        # Safety case at nearly the same time.
        existing_case = get_active_safety_case(thread)

        if existing_case:
            return existing_case

        raise


def _prepare_safety_case_for_action(
    case,
    *,
    actor,
):
    if case.status in {
        ModerationCase.Status.OPEN,
        ModerationCase.Status.REOPENED,
    }:
        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.IN_REVIEW,
            actor=actor,
        )

    if case.status not in {
        ModerationCase.Status.IN_REVIEW,
        ModerationCase.Status.ESCALATED,
    }:
        raise InvalidModerationTransition(
            f"Safety action cannot be performed "
            f"while case is {case.status}."
        )

    return case


def escalate_safety_case(
    *,
    thread,
    actor,
    reason_code="NEEDS_FURTHER_REVIEW",
    notes="",
):
    case = get_active_safety_case(thread)

    if not case:
        raise ModerationCaseError(
            "No active Safety case exists for this thread."
        )

    case = _prepare_safety_case_for_action(
        case,
        actor=actor,
    )

    # Makes repeated escalation harmless instead of
    # generating another transition.
    if case.status == ModerationCase.Status.ESCALATED:
        return case

    return transition_moderation_case(
        case,
        next_status=ModerationCase.Status.ESCALATED,
        actor=actor,
        reason_code=reason_code,
        notes=notes,
    )


def resolve_safety_case(
    *,
    thread,
    actor,
    action,
    notes="",
):
    if action not in {
        SAFETY_ACTION_DISMISS,
        SAFETY_ACTION_REMOVE,
    }:
        raise ModerationCaseError(
            "Safety resolution must be DISMISS or REMOVE."
        )

    with transaction.atomic():
        locked_thread = (
            Thread.objects
            .select_for_update()
            .get(pk=thread.pk)
        )

        case = get_active_safety_case(
            locked_thread,
            lock=True,
        )

        if not case:
            raise ModerationCaseError(
                "No active Safety case exists for this thread."
            )

        case = _prepare_safety_case_for_action(
            case,
            actor=actor,
        )

        active_flags = list(
            ThreadFlag.objects
            .select_for_update()
            .filter(
                thread=locked_thread,
                resolved_at__isnull=True,
            )
            .select_related("flagged_by")
        )

        reporter_ids = {
            flag.flagged_by_id
            for flag in active_flags
        }

        contributor_ids = set(
            locked_thread
            .evidence_submissions
            .values_list(
                "contributor_id",
                flat=True,
            )
            .distinct()
        )

        now = timezone.now()

        # Preserve the existing legacy moderation fields
        # during the migration period.
        locked_thread.moderated_by = actor
        locked_thread.moderated_at = now

        thread_update_fields = [
            "moderated_by",
            "moderated_at",
        ]

        if notes:
            locked_thread.moderator_notes = notes
            thread_update_fields.append(
                "moderator_notes"
            )

        if action == SAFETY_ACTION_REMOVE:
            # Compatibility state for now.
            # Later Thread.REJECTED will become REMOVED.
            locked_thread.status = Thread.Status.REJECTED
            thread_update_fields.append("status")

        locked_thread.save(
            update_fields=thread_update_fields
        )

        resolved_logs = [
            FlagResolutionLog(
                thread=locked_thread,
                flagged_by=flag.flagged_by,
                reason=flag.reason,
                notes=flag.notes,
                flagged_at=flag.flagged_at,
                resolved_action=action,
                is_valid_report=(
                    action == SAFETY_ACTION_REMOVE
                ),
                resolved_by=actor,
            )
            for flag in active_flags
        ]

        if resolved_logs:
            FlagResolutionLog.objects.bulk_create(
                resolved_logs
            )

            ThreadFlag.objects.filter(
                id__in=[
                    flag.id
                    for flag in active_flags
                ]
            ).update(
                resolved_at=now,
                resolution_case=case,
            )

        if action == SAFETY_ACTION_DISMISS:
            resolution_code = (
                SAFETY_RESOLUTION_NO_VIOLATION
            )

            default_summary = (
                "No policy violation was found."
            )

            ModerationEvent.objects.create(
                case=case,
                actor=actor,
                event_type=(
                    ModerationEvent
                    .EventType
                    .SAFETY_DISMISSED
                ),
                from_status=case.status,
                to_status=case.status,
                reason_code=action,
                notes=notes or None,
                metadata={
                    "report_count": len(active_flags),
                },
            )

        else:
            resolution_code = (
                SAFETY_RESOLUTION_CONTENT_REMOVED
            )

            default_summary = (
                "A policy violation was confirmed "
                "and the thread was removed."
            )

            ModerationEvent.objects.create(
                case=case,
                actor=actor,
                event_type=(
                    ModerationEvent
                    .EventType
                    .SAFETY_VIOLATION_CONFIRMED
                ),
                from_status=case.status,
                to_status=case.status,
                reason_code=action,
                notes=notes or None,
                metadata={
                    "report_count": len(active_flags),
                },
            )

            ModerationEvent.objects.create(
                case=case,
                actor=actor,
                event_type=(
                    ModerationEvent
                    .EventType
                    .CONTENT_REMOVED
                ),
                from_status=case.status,
                to_status=case.status,
                metadata={
                    "thread_id": str(
                        locked_thread.id
                    ),
                },
            )

        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.RESOLVED,
            actor=actor,
            reason_code=action,
            notes=notes,
            resolution_code=resolution_code,
            resolution_summary=(
                notes or default_summary
            ),
        )

        return {
            "case": case,
            "thread": locked_thread,
            "reporter_ids": reporter_ids,
            "contributor_ids": contributor_ids,
            "author_id": locked_thread.author_id,
        }