import logging
from collections import Counter

from django.db import transaction
from django.db.models import Prefetch

from .accountability_service import record_accountability_event
from .models import (
    AccountabilityEvent,
    ModerationCase,
    ModerationEvent,
    Thread,
    ThreadFlag,
)
from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    ModerationCaseError,
    assign_moderation_case,
    escalate_safety_case,
    resolve_safety_case,
    unassign_moderation_case,
)
from .organization_service import PartnerCapability
from .platform_identity_service import can_review_platform_safety


logger = logging.getLogger(__name__)


class SafetyReviewError(Exception):
    pass


class SafetyReviewAuthorizationError(SafetyReviewError):
    pass


class SafetyCaseConflict(SafetyReviewError):
    pass


def ensure_can_review_safety(actor):
    if not can_review_platform_safety(actor):
        raise SafetyReviewAuthorizationError(
            "Platform Safety review authority is required."
        )


def get_safety_case_queryset(*, include_events=False):
    unresolved_reports = ThreadFlag.objects.filter(
        resolved_at__isnull=True,
    ).order_by("flagged_at", "id")
    case_linked_reports = ThreadFlag.objects.order_by("flagged_at", "id")

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
            ),
            Prefetch(
                "reports",
                queryset=case_linked_reports,
                to_attr="case_linked_safety_reports",
            ),
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
            "This Safety case is assigned to another reviewer."
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
                "This Safety case is assigned to another reviewer."
            )

        claimed_case = assign_moderation_case(
            locked_case,
            assignee=actor,
            actor=actor,
        )
        record_accountability_event(
            action_type=AccountabilityEvent.ActionType.SAFETY_CASE_CLAIMED,
            resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
            resource_id=claimed_case.pk,
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            actor=actor,
            capability=PartnerCapability.REVIEW_SAFETY,
            previous_state={"assigned_to_id": None, "status": locked_case.status},
            new_state={"assigned_to_id": str(actor.pk), "status": claimed_case.status},
            context={"thread_id": str(claimed_case.thread_id)},
        )
        return claimed_case


def release_safety_case(*, case, actor):
    ensure_can_review_safety(actor)

    with transaction.atomic():
        locked_case = _get_locked_safety_case(case)
        _ensure_active_case(locked_case)
        _ensure_case_owner(locked_case, actor)
        released_case = unassign_moderation_case(
            locked_case,
            actor=actor,
        )
        record_accountability_event(
            action_type=AccountabilityEvent.ActionType.SAFETY_CASE_RELEASED,
            resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
            resource_id=released_case.pk,
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            actor=actor,
            capability=PartnerCapability.REVIEW_SAFETY,
            previous_state={
                "assigned_to_id": str(actor.pk),
                "status": locked_case.status,
            },
            new_state={"assigned_to_id": None, "status": released_case.status},
            context={"thread_id": str(released_case.thread_id)},
        )
        return released_case


def perform_safety_case_action(
    *,
    case,
    actor,
    action,
    notes="",
    violation_code="",
    confirmed_report_ids=None,
):
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
            previous_status = locked_case.status

            escalated_case = escalate_safety_case(
                thread=locked_case.thread,
                actor=actor,
                notes=notes,
            )

            if previous_status != ModerationCase.Status.ESCALATED:
                record_accountability_event(
                    action_type=AccountabilityEvent.ActionType.SAFETY_CASE_ESCALATED,
                    resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
                    resource_id=escalated_case.pk,
                    authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
                    actor=actor,
                    capability=PartnerCapability.REVIEW_SAFETY,
                    previous_state={"status": previous_status},
                    new_state={"status": escalated_case.status},
                    reason_code="NEEDS_FURTHER_REVIEW",
                    notes=notes,
                    context={"thread_id": str(escalated_case.thread_id)},
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
        previous_case_status = locked_case.status
        previous_thread_status = locked_thread.status

        try:
            result = resolve_safety_case(
                thread=locked_thread,
                actor=actor,
                action=action,
                notes=notes,
                violation_code=violation_code,
                confirmed_report_ids=confirmed_report_ids,
            )
        except ModerationCaseError as error:
            raise SafetyCaseConflict(str(error)) from error

        result["action"] = action
        resolved_case = result["case"]
        resolved_thread = result["thread"]
        decision = result.get("decision")
        action_type = (
            AccountabilityEvent.ActionType.SAFETY_CONTENT_REMOVED
            if action == "REMOVE"
            else AccountabilityEvent.ActionType.SAFETY_DISMISSED
        )
        context = {
            "thread_id": str(resolved_thread.pk),
            "decision_id": str(decision.pk) if decision else None,
            "confirmed_report_count": len(
                result.get("confirmed_reporter_ids", set())
            ),
        }
        if decision:
            context.update(
                {
                    "violation_code": decision.violation_code or None,
                    "policy_version": decision.policy_version,
                }
            )
        record_accountability_event(
            action_type=action_type,
            resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
            resource_id=resolved_case.pk,
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            actor=actor,
            capability=PartnerCapability.REVIEW_SAFETY,
            previous_state={
                "case_status": previous_case_status,
                "thread_status": previous_thread_status,
            },
            new_state={
                "case_status": resolved_case.status,
                "thread_status": resolved_thread.status,
            },
            reason_code=action,
            notes=notes,
            context=context,
        )
        return result


def schedule_safety_resolution_notifications(result):
    decision = result.get("decision")
    if decision is None:
        return

    report_outcomes = tuple(result.get("report_outcomes", ()))
    author_id = result.get("author_id")

    def deliver():
        try:
            from .notification_service import (
                Target,
                Type,
                create_notification_once,
            )
        except Exception:
            logger.exception(
                "Failed to load Community moderation notification service "
                "for decision_id=%s.",
                decision.pk,
            )
            return

        if decision.action == "REMOVE" and author_id:
            try:
                create_notification_once(
                    recipient_id=author_id,
                    notification_type=Type.COMMUNITY_MODERATION_OUTCOME,
                    target_type=Target.MODERATION_OUTCOME,
                    target_id=decision.pk,
                    dedupe_key=f"community-safety:{decision.pk}:author",
                    title="Your discussion was removed",
                    message=(
                        "Platform Safety found "
                        f"{decision.violation_label_snapshot}. "
                        "Open the moderation outcome to review the reason and policy."
                    ),
                )
            except Exception:
                logger.exception(
                    "Failed Community moderation author notification "
                    "for decision_id=%s user_id=%s.",
                    decision.pk,
                    author_id,
                )

        for report in report_outcomes:
            reporter_id = report["reporter_id"]
            outcome = report["outcome"]
            if outcome == "CONFIRMED":
                title = "Your report was confirmed"
                message = (
                    "Platform Safety removed the reported content and confirmed "
                    "that your report identified the policy issue. This report "
                    "counts toward your Community reputation."
                )
            elif outcome == "NOT_CONFIRMED":
                title = "The content you reported was removed"
                message = (
                    "Platform Safety removed the content for a Community Guidelines "
                    "violation, but your report was not confirmed for Community reputation."
                )
            else:
                title = "Your report was reviewed"
                message = (
                    "Platform Safety did not find a Community Guidelines violation. "
                    "Your Community reputation was not changed."
                )

            try:
                create_notification_once(
                    recipient_id=reporter_id,
                    notification_type=Type.COMMUNITY_MODERATION_OUTCOME,
                    target_type=Target.MODERATION_OUTCOME,
                    target_id=decision.pk,
                    dedupe_key=(
                        f"community-safety:{decision.pk}:report:{report['report_id']}"
                    ),
                    title=title,
                    message=message,
                )
            except Exception:
                logger.exception(
                    "Failed Community moderation reporter notification "
                    "for decision_id=%s report_id=%s user_id=%s.",
                    decision.pk,
                    report["report_id"],
                    reporter_id,
                )

    transaction.on_commit(deliver, robust=True)


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

    # The same account can legitimately appear in more than one affected role
    # (for example reporter and evidence contributor). Recompute each user only
    # once per committed Safety resolution.
    deduped_targets = []
    seen_user_ids = set()
    for target_type, user_id in targets:
        if user_id in seen_user_ids:
            continue
        seen_user_ids.add(user_id)
        deduped_targets.append((target_type, user_id))
    targets = deduped_targets

    case = result.get("case")
    thread = result.get("thread")
    case_id = getattr(case, "pk", None)
    thread_id = getattr(thread, "pk", None)

    def refresh_trust_scores():
        try:
            from .trust_service import recompute_user_trust_score
        except Exception:
            logger.exception(
                "Failed to load post-commit Safety Trust recomputation "
                "service for case_id=%s thread_id=%s action=%s.",
                case_id,
                thread_id,
                resolved_action,
            )
            return

        for target_type, user_id in targets:
            try:
                recompute_user_trust_score(user_id)
            except Exception:
                logger.exception(
                    "Failed post-commit Safety Trust recomputation for "
                    "user_id=%s target_type=%s case_id=%s thread_id=%s "
                    "action=%s.",
                    user_id,
                    target_type,
                    case_id,
                    thread_id,
                    resolved_action,
                )

    transaction.on_commit(refresh_trust_scores, robust=True)


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
