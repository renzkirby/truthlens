import logging
from collections import Counter

from django.db import transaction
from django.db.models import Prefetch

from .models import ModerationCase, ModerationEvent, Thread, ThreadFlag
from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    assign_moderation_case,
    escalate_safety_case,
    resolve_safety_case,
    unassign_moderation_case,
)
from .organization_service import PartnerCapability, has_capability


logger = logging.getLogger(__name__)


class SafetyReviewError(Exception):
    pass


class SafetyReviewAuthorizationError(SafetyReviewError):
    pass


class SafetyCaseConflict(SafetyReviewError):
    pass


def ensure_can_review_safety(actor):
    if not has_capability(actor, PartnerCapability.REVIEW_SAFETY):
        raise SafetyReviewAuthorizationError(
            "Platform Safety review authority is required."
        )


def get_safety_case_queryset(*, include_events=False):
    unresolved_reports = ThreadFlag.objects.filter(
        resolved_at__isnull=True,
    ).order_by("flagged_at", "id")

    queryset = (
        ModerationCase.objects.filter(
            case_type=ModerationCase.CaseType.SAFETY,
        )
        .select_related(
            "assigned_to",
            "thread",
            "thread__author",
            "thread__claim",
        )
        .prefetch_related(
            Prefetch(
                "thread__flags",
                queryset=unresolved_reports,
                to_attr="unresolved_safety_reports",
            )
        )
    )

    if include_events:
        queryset = queryset.prefetch_related(
            Prefetch(
                "events",
                queryset=(
                    ModerationEvent.objects.select_related("actor", "case").order_by(
                        "-created_at",
                        "-id",
                    )
                ),
                to_attr="recent_safety_events",
            )
        )

    return queryset


def get_safety_case_queue(*, actor, filters):
    ensure_can_review_safety(actor)

    queryset = get_safety_case_queryset().filter(
        status__in=ACTIVE_CASE_STATUSES,
    )

    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])

    if filters.get("priority"):
        queryset = queryset.filter(priority=filters["priority"])

    if filters.get("assigned") == "me":
        queryset = queryset.filter(assigned_to=actor)
    elif filters.get("assigned") == "unassigned":
        queryset = queryset.filter(assigned_to__isnull=True)

    return queryset.order_by("-created_at", "id")


def _get_locked_safety_case(case):
    try:
        return (
            ModerationCase.objects.select_for_update(of=("self",))
            .select_related("thread")
            .get(
                pk=case.pk,
                case_type=ModerationCase.CaseType.SAFETY,
            )
        )
    except ModerationCase.DoesNotExist as error:
        raise SafetyCaseConflict(
            "This Safety case is no longer available."
        ) from error


def _ensure_active_case(case):
    if case.status not in ACTIVE_CASE_STATUSES:
        raise SafetyCaseConflict(
            "This Safety case is no longer active."
        )


def _ensure_case_owner(case, actor):
    if case.assigned_to_id is None:
        raise SafetyCaseConflict(
            "Claim this Safety case before taking action."
        )

    if case.assigned_to_id != actor.pk:
        raise SafetyCaseConflict(
            "This Safety case is assigned to another moderator."
        )


def claim_safety_case(*, case, actor):
    ensure_can_review_safety(actor)

    with transaction.atomic():
        locked_case = _get_locked_safety_case(case)
        _ensure_active_case(locked_case)

        if locked_case.assigned_to_id == actor.pk:
            return locked_case

        if locked_case.assigned_to_id is not None:
            raise SafetyCaseConflict(
                "This Safety case is assigned to another moderator."
            )

        return assign_moderation_case(
            locked_case,
            assignee=actor,
            actor=actor,
        )


def release_safety_case(*, case, actor):
    ensure_can_review_safety(actor)

    with transaction.atomic():
        locked_case = _get_locked_safety_case(case)
        _ensure_active_case(locked_case)
        _ensure_case_owner(locked_case, actor)

        return unassign_moderation_case(
            locked_case,
            actor=actor,
        )


def perform_safety_case_action(*, case, actor, action, notes=""):
    ensure_can_review_safety(actor)

    if not case.thread_id:
        raise SafetyCaseConflict(
            "This Safety case no longer has reviewable thread content."
        )

    if action == "ESCALATE":
        with transaction.atomic():
            locked_case = _get_locked_safety_case(case)
            _ensure_active_case(locked_case)
            _ensure_case_owner(locked_case, actor)

            escalated_case = escalate_safety_case(
                thread=locked_case.thread,
                actor=actor,
                notes=notes,
            )

            return {
                "case": escalated_case,
                "action": action,
            }

    with transaction.atomic():
        try:
            locked_thread = Thread.objects.select_for_update().get(
                pk=case.thread_id,
            )
        except Thread.DoesNotExist as error:
            raise SafetyCaseConflict(
                "This Safety case no longer has reviewable thread content."
            ) from error

        locked_case = _get_locked_safety_case(case)
        _ensure_active_case(locked_case)
        _ensure_case_owner(locked_case, actor)

        result = resolve_safety_case(
            thread=locked_thread,
            actor=actor,
            action=action,
            notes=notes,
        )
        result["action"] = action
        return result


def schedule_safety_resolution_trust_updates(result, *, action=None):
    resolved_action = action or result.get("action")
    targets = [
        ("reporter", reporter_id)
        for reporter_id in result.get("reporter_ids", set())
    ]

    if resolved_action == "REMOVE" and result.get("author_id"):
        targets.append(("author", result["author_id"]))

    targets.extend(
        ("evidence_contributor", contributor_id)
        for contributor_id in result.get("contributor_ids", set())
    )

    case = result.get("case")
    thread = result.get("thread")
    case_id = getattr(case, "pk", None)
    thread_id = getattr(thread, "pk", None)

    def dispatch_trust_updates():
        try:
            from .tasks import recompute_user_trust_score_task
        except Exception:
            logger.exception(
                "Failed to load the post-commit Safety trust task for "
                "case_id=%s thread_id=%s action=%s.",
                case_id,
                thread_id,
                resolved_action,
            )
            return

        for target_type, user_id in targets:
            try:
                recompute_user_trust_score_task.delay(user_id)
            except Exception:
                logger.exception(
                    "Failed to enqueue post-commit Safety trust recomputation "
                    "for user_id=%s target_type=%s case_id=%s thread_id=%s "
                    "action=%s.",
                    user_id,
                    target_type,
                    case_id,
                    thread_id,
                    resolved_action,
                )

    transaction.on_commit(dispatch_trust_updates, robust=True)


def summarize_report_reasons(reports):
    counts = Counter(report.reason for report in reports)
    labels = dict(ThreadFlag.Reason.choices)

    return [
        {
            "reason": reason,
            "reason_label": labels.get(reason, reason),
            "count": count,
        }
        for reason, count in sorted(counts.items())
    ]
