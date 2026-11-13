from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .community_policy import (
    COMMUNITY_POLICY_TITLE,
    COMMUNITY_POLICY_VERSION,
    get_community_violation,
)
from .community_safety_target_service import (
    CommunitySafetyTargetError,
    get_case_target,
    remove_target,
    target_excerpt,
    target_owner,
)
from .models import (
    CommunityReport,
    CommunityReportOutcome,
    CommunitySafetyDecision,
    ModerationCase,
    ModerationEvent,
    Thread,
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
    thread_comment=None,
    claim=None,
    evidence_submission=None,
    organization=None,
    safety_target_type=None,
):
    case = ModerationCase(
        case_type=case_type,
        source=source,
        priority=priority,
        thread=thread,
        thread_comment=thread_comment,
        claim=claim,
        evidence_submission=evidence_submission,
        organization=organization,
        safety_target_type=safety_target_type,
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


def _safety_target_filters(
    *,
    target_type,
    thread,
    comment=None,
    evidence_submission=None,
):
    filters = {
        "case_type": ModerationCase.CaseType.SAFETY,
        "status__in": ACTIVE_CASE_STATUSES,
        "safety_target_type": target_type,
        "thread": thread,
    }

    if target_type == ModerationCase.SafetyTargetType.THREAD:
        filters.update(
            thread_comment__isnull=True,
            evidence_submission__isnull=True,
        )
    elif target_type == ModerationCase.SafetyTargetType.COMMENT:
        if comment is None:
            raise InvalidModerationCaseTarget(
                "Comment Safety cases require a comment target."
            )
        filters["thread_comment"] = comment
    elif target_type == ModerationCase.SafetyTargetType.EVIDENCE:
        if evidence_submission is None:
            raise InvalidModerationCaseTarget(
                "Evidence Safety cases require an evidence target."
            )
        filters["evidence_submission"] = evidence_submission
    else:
        raise InvalidModerationCaseTarget(
            "Unsupported Community Safety target type."
        )

    return filters


def get_active_safety_case(
    thread,
    *,
    target_type=ModerationCase.SafetyTargetType.THREAD,
    comment=None,
    evidence_submission=None,
    lock=False,
):
    queryset = ModerationCase.objects.filter(
        **_safety_target_filters(
            target_type=target_type,
            thread=thread,
            comment=comment,
            evidence_submission=evidence_submission,
        )
    )

    if lock:
        queryset = queryset.select_for_update()

    return queryset.order_by("-created_at").first()


def ensure_safety_case(
    *,
    thread,
    actor=None,
    target_type=ModerationCase.SafetyTargetType.THREAD,
    comment=None,
    evidence_submission=None,
):
    existing_case = get_active_safety_case(
        thread,
        target_type=target_type,
        comment=comment,
        evidence_submission=evidence_submission,
    )

    if existing_case:
        return existing_case

    try:
        return create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=actor,
            source=ModerationCase.Source.USER_REPORT,
            thread=thread,
            thread_comment=comment,
            evidence_submission=evidence_submission,
            safety_target_type=target_type,
        )

    except DuplicateActiveModerationCase:
        existing_case = get_active_safety_case(
            thread,
            target_type=target_type,
            comment=comment,
            evidence_submission=evidence_submission,
        )

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
            f"Safety action cannot be performed while case is {case.status}."
        )

    return case


def escalate_safety_case(
    *,
    thread,
    actor,
    target_type=ModerationCase.SafetyTargetType.THREAD,
    comment=None,
    evidence_submission=None,
    reason_code="NEEDS_FURTHER_REVIEW",
    notes="",
):
    case = get_active_safety_case(
        thread,
        target_type=target_type,
        comment=comment,
        evidence_submission=evidence_submission,
    )

    if not case:
        raise ModerationCaseError(
            "No active Safety case exists for this Community content."
        )

    case = _prepare_safety_case_for_action(
        case,
        actor=actor,
    )

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
    violation_code="",
    confirmed_report_ids=None,
    target_type=ModerationCase.SafetyTargetType.THREAD,
    comment=None,
    evidence_submission=None,
):
    if action not in {
        SAFETY_ACTION_DISMISS,
        SAFETY_ACTION_REMOVE,
    }:
        raise ModerationCaseError(
            "Safety resolution must be DISMISS or REMOVE."
        )

    if action == SAFETY_ACTION_REMOVE:
        violation = get_community_violation(violation_code)
        if violation is None:
            raise ModerationCaseError(
                "A valid Community Guidelines violation is required when removing content."
            )
        if confirmed_report_ids is None:
            raise ModerationCaseError(
                "Confirmed report selections are required when removing content."
            )
    else:
        violation = None
        if violation_code or confirmed_report_ids not in (None, []):
            raise ModerationCaseError(
                "Dismissed Safety cases cannot include a confirmed violation or confirmed reports."
            )

    with transaction.atomic():
        try:
            locked_thread = (
                Thread.objects
                .select_for_update()
                .select_related("author", "claim")
                .get(pk=thread.pk)
            )
        except Thread.DoesNotExist as error:
            raise ModerationCaseError(
                "The Safety case discussion no longer exists."
            ) from error

        case = get_active_safety_case(
            locked_thread,
            target_type=target_type,
            comment=comment,
            evidence_submission=evidence_submission,
            lock=True,
        )

        if not case:
            raise ModerationCaseError(
                "No active Safety case exists for this Community content."
            )

        case = _prepare_safety_case_for_action(
            case,
            actor=actor,
        )

        try:
            locked_target = get_case_target(case, lock=True)
        except CommunitySafetyTargetError as error:
            raise ModerationCaseError(str(error)) from error

        report_filters = {
            "thread": locked_thread,
            "target_type": case.safety_target_type,
            "resolved_at__isnull": True,
        }
        outcome_target_kwargs = {
            "comment": None,
            "evidence_submission": None,
        }
        if case.safety_target_type == ModerationCase.SafetyTargetType.COMMENT:
            report_filters["comment"] = locked_target
            outcome_target_kwargs["comment"] = locked_target
        elif case.safety_target_type == ModerationCase.SafetyTargetType.EVIDENCE:
            report_filters["evidence_submission"] = locked_target
            outcome_target_kwargs["evidence_submission"] = locked_target

        active_reports = list(
            CommunityReport.objects
            .select_for_update()
            .filter(**report_filters)
            .select_related("reporter")
            .order_by("reported_at", "id")
        )

        active_reports_by_id = {
            str(report.id): report
            for report in active_reports
        }
        raw_confirmed_ids = list(confirmed_report_ids or [])
        confirmed_ids = {str(report_id) for report_id in raw_confirmed_ids}

        if len(confirmed_ids) != len(raw_confirmed_ids):
            raise ModerationCaseError(
                "Confirmed report selections cannot contain duplicates."
            )

        unknown_confirmed_ids = confirmed_ids - set(active_reports_by_id)
        if unknown_confirmed_ids:
            raise ModerationCaseError(
                "Confirmed reports must belong to the active Safety review cycle."
            )

        reporter_ids = {
            report.reporter_id
            for report in active_reports
        }

        contributor_ids = set()
        if case.safety_target_type == ModerationCase.SafetyTargetType.THREAD:
            contributor_ids = set(
                locked_thread.evidence_submissions.values_list(
                    "contributor_id",
                    flat=True,
                ).distinct()
            )

        content_owner = target_owner(case.safety_target_type, locked_target)
        now = timezone.now()

        restoration = {
            "pre_removal_thread_status": None,
            "pre_removal_moderated_by": None,
            "pre_removal_moderated_at": None,
            "pre_removal_moderator_notes": None,
        }

        if action == SAFETY_ACTION_REMOVE:
            try:
                restoration = remove_target(
                    target_type=case.safety_target_type,
                    target=locked_target,
                    actor=actor,
                    notes=notes,
                    removed_at=now,
                )
            except CommunitySafetyTargetError as error:
                raise ModerationCaseError(str(error)) from error
        elif case.safety_target_type == ModerationCase.SafetyTargetType.THREAD:
            locked_target.moderated_by = actor
            locked_target.moderated_at = now
            if notes:
                locked_target.moderator_notes = notes
            locked_target.save(
                update_fields=[
                    "moderated_by",
                    "moderated_at",
                    "moderator_notes",
                ]
            )

        if action == SAFETY_ACTION_DISMISS:
            resolution_code = SAFETY_RESOLUTION_NO_VIOLATION
            default_summary = "No Community Guidelines violation was found."
            violation_code_snapshot = ""
            violation_label_snapshot = ""
        else:
            resolution_code = SAFETY_RESOLUTION_CONTENT_REMOVED
            violation_code_snapshot = violation["code"]
            violation_label_snapshot = violation["title"]
            default_summary = (
                f"Content was removed for {violation_label_snapshot}."
            )

        decision = CommunitySafetyDecision.objects.create(
            moderation_case=case,
            action=action,
            target_type=case.safety_target_type,
            target_id_snapshot=locked_target.pk,
            violation_code=violation_code_snapshot,
            policy_title_snapshot=COMMUNITY_POLICY_TITLE,
            policy_version=COMMUNITY_POLICY_VERSION,
            violation_label_snapshot=violation_label_snapshot,
            pre_removal_thread_status=restoration["pre_removal_thread_status"],
            pre_removal_moderated_by=restoration["pre_removal_moderated_by"],
            pre_removal_moderated_at=restoration["pre_removal_moderated_at"],
            pre_removal_moderator_notes=restoration["pre_removal_moderator_notes"],
            restoration_snapshot_complete=(action == SAFETY_ACTION_REMOVE),
            thread_id_snapshot=locked_thread.pk,
            content_owner=content_owner,
            owner_username_snapshot=content_owner.username,
            content_excerpt_snapshot=target_excerpt(
                case.safety_target_type,
                locked_target,
            ),
            rationale=notes or default_summary,
            decided_by=actor,
            decided_at=now,
        )

        report_outcomes = []
        resolved_logs = []
        for report in active_reports:
            if action == SAFETY_ACTION_DISMISS:
                report_outcome = CommunityReportOutcome.ReportOutcome.NO_VIOLATION
            elif str(report.id) in confirmed_ids:
                report_outcome = CommunityReportOutcome.ReportOutcome.CONFIRMED
            else:
                report_outcome = CommunityReportOutcome.ReportOutcome.NOT_CONFIRMED

            is_confirmed = (
                report_outcome
                == CommunityReportOutcome.ReportOutcome.CONFIRMED
            )
            resolved_logs.append(
                CommunityReportOutcome(
                    target_type=report.target_type,
                    target_id_snapshot=locked_target.pk,
                    thread=locked_thread,
                    reporter=report.reporter,
                    reason=report.reason,
                    notes=report.notes,
                    reported_at=report.reported_at,
                    resolved_action=action,
                    is_valid_report=is_confirmed,
                    report_outcome=report_outcome,
                    safety_decision=decision,
                    resolved_by=actor,
                    **outcome_target_kwargs,
                )
            )
            report_outcomes.append(
                {
                    "report_id": report.id,
                    "reporter_id": report.reporter_id,
                    "reason": report.reason,
                    "outcome": report_outcome,
                }
            )

        if resolved_logs:
            CommunityReportOutcome.objects.bulk_create(resolved_logs)
            CommunityReport.objects.filter(
                id__in=[report.id for report in active_reports]
            ).update(
                resolved_at=now,
                resolution_case=case,
            )

        event_metadata = {
            "decision_id": str(decision.id),
            "target_type": case.safety_target_type,
            "target_id": str(locked_target.pk),
            "thread_id": str(locked_thread.pk),
            "report_count": len(active_reports),
            "confirmed_report_count": (
                len(confirmed_ids)
                if action == SAFETY_ACTION_REMOVE
                else 0
            ),
            "policy_version": COMMUNITY_POLICY_VERSION,
        }

        if action == SAFETY_ACTION_DISMISS:
            ModerationEvent.objects.create(
                case=case,
                actor=actor,
                event_type=ModerationEvent.EventType.SAFETY_DISMISSED,
                from_status=case.status,
                to_status=case.status,
                reason_code=action,
                notes=notes or None,
                metadata=event_metadata,
            )
        else:
            ModerationEvent.objects.create(
                case=case,
                actor=actor,
                event_type=ModerationEvent.EventType.SAFETY_VIOLATION_CONFIRMED,
                from_status=case.status,
                to_status=case.status,
                reason_code=violation_code_snapshot,
                notes=notes or None,
                metadata={
                    **event_metadata,
                    "violation_code": violation_code_snapshot,
                },
            )
            ModerationEvent.objects.create(
                case=case,
                actor=actor,
                event_type=ModerationEvent.EventType.CONTENT_REMOVED,
                from_status=case.status,
                to_status=case.status,
                metadata={
                    **event_metadata,
                    "violation_code": violation_code_snapshot,
                },
            )

        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.RESOLVED,
            actor=actor,
            reason_code=action,
            notes=notes,
            resolution_code=resolution_code,
            resolution_summary=(notes or default_summary),
        )

        return {
            "case": case,
            "thread": locked_thread,
            "target": locked_target,
            "decision": decision,
            "report_outcomes": report_outcomes,
            "reporter_ids": reporter_ids,
            "confirmed_reporter_ids": {
                row["reporter_id"]
                for row in report_outcomes
                if row["outcome"]
                == CommunityReportOutcome.ReportOutcome.CONFIRMED
            },
            "contributor_ids": contributor_ids,
            "content_owner_id": content_owner.pk,
        }
