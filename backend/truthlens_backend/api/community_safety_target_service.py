"""Small target adapter for Community Safety content operations."""

from django.utils import timezone

from .models import (
    CommunitySafetyDecision,
    EvidenceSubmission,
    ModerationCase,
    Thread,
    ThreadComment,
)


class CommunitySafetyTargetError(Exception):
    pass


def target_label(target_type):
    return {
        ModerationCase.SafetyTargetType.THREAD: "discussion",
        ModerationCase.SafetyTargetType.COMMENT: "comment",
        ModerationCase.SafetyTargetType.EVIDENCE: "evidence",
    }.get(target_type, "content")


def _queryset_for_target(target_type, *, lock=False):
    if target_type == ModerationCase.SafetyTargetType.THREAD:
        queryset = Thread.objects.select_related("author", "claim")
    elif target_type == ModerationCase.SafetyTargetType.COMMENT:
        queryset = ThreadComment.objects.select_related("commenter", "thread")
    elif target_type == ModerationCase.SafetyTargetType.EVIDENCE:
        queryset = EvidenceSubmission.objects.select_related("contributor", "thread")
    else:
        raise CommunitySafetyTargetError("Unsupported Community Safety target type.")

    if lock:
        queryset = queryset.select_for_update()
    return queryset


def get_case_target(case, *, lock=False):
    target_type = case.safety_target_type

    if target_type == ModerationCase.SafetyTargetType.THREAD:
        target_id = case.thread_id
    elif target_type == ModerationCase.SafetyTargetType.COMMENT:
        target_id = case.thread_comment_id
    elif target_type == ModerationCase.SafetyTargetType.EVIDENCE:
        target_id = case.evidence_submission_id
    else:
        raise CommunitySafetyTargetError(
            "This Safety case does not have a supported Community content target."
        )

    if not target_id:
        raise CommunitySafetyTargetError(
            "This Safety case no longer has reviewable Community content."
        )

    try:
        target = _queryset_for_target(target_type, lock=lock).get(pk=target_id)
    except (Thread.DoesNotExist, ThreadComment.DoesNotExist, EvidenceSubmission.DoesNotExist) as error:
        raise CommunitySafetyTargetError(
            "This Safety case no longer has reviewable Community content."
        ) from error

    if getattr(target, "thread_id", case.thread_id) != case.thread_id:
        raise CommunitySafetyTargetError(
            "The Safety target no longer belongs to the expected discussion."
        )

    return target


def get_decision_target(decision, *, lock=False):
    target_type = decision.target_type
    try:
        target = _queryset_for_target(target_type, lock=lock).get(
            pk=decision.target_id_snapshot,
        )
    except (Thread.DoesNotExist, ThreadComment.DoesNotExist, EvidenceSubmission.DoesNotExist) as error:
        raise CommunitySafetyTargetError(
            "The Community content targeted by this decision no longer exists."
        ) from error

    if target_type == CommunitySafetyDecision.TargetType.THREAD:
        thread_id = target.pk
    else:
        thread_id = target.thread_id

    if str(thread_id) != str(decision.thread_id_snapshot):
        raise CommunitySafetyTargetError(
            "The Community content no longer matches the original Safety decision."
        )

    return target


def target_owner(target_type, target):
    if target_type == ModerationCase.SafetyTargetType.THREAD:
        return target.author
    if target_type == ModerationCase.SafetyTargetType.COMMENT:
        return target.commenter
    if target_type == ModerationCase.SafetyTargetType.EVIDENCE:
        return target.contributor
    raise CommunitySafetyTargetError("Unsupported Community Safety target type.")


def target_excerpt(target_type, target):
    if target_type == ModerationCase.SafetyTargetType.THREAD:
        value = (target.caption or "").strip()
        if not value and target.claim_id:
            value = (target.claim.context_text or "").strip()
    elif target_type == ModerationCase.SafetyTargetType.COMMENT:
        value = (target.comment_text or "").strip()
    elif target_type == ModerationCase.SafetyTargetType.EVIDENCE:
        value = (target.evidence_caption or "").strip()
        if not value:
            value = (target.evidence_url or "").strip()
    else:
        raise CommunitySafetyTargetError("Unsupported Community Safety target type.")

    return " ".join(value.split())[:500]


def target_is_removed(target_type, target):
    if target_type == ModerationCase.SafetyTargetType.THREAD:
        return target.status == Thread.Status.REJECTED
    if target_type in {
        ModerationCase.SafetyTargetType.COMMENT,
        ModerationCase.SafetyTargetType.EVIDENCE,
    }:
        return target.safety_removed_at is not None
    return False


def target_state(target_type, target):
    if target_type == ModerationCase.SafetyTargetType.THREAD:
        return {
            "target_type": target_type,
            "target_id": str(target.pk),
            "thread_status": target.status,
        }

    return {
        "target_type": target_type,
        "target_id": str(target.pk),
        "safety_removed": bool(target.safety_removed_at),
    }


def remove_target(*, target_type, target, actor, notes="", removed_at=None):
    removed_at = removed_at or timezone.now()

    if target_is_removed(target_type, target):
        raise CommunitySafetyTargetError(
            f"The {target_label(target_type)} is already removed from Community circulation."
        )

    if target_type == ModerationCase.SafetyTargetType.THREAD:
        snapshot = {
            "pre_removal_thread_status": target.status,
            "pre_removal_moderated_by": target.moderated_by,
            "pre_removal_moderated_at": target.moderated_at,
            "pre_removal_moderator_notes": target.moderator_notes,
        }
        target.moderated_by = actor
        target.moderated_at = removed_at
        target.moderator_notes = notes or target.moderator_notes
        target.status = Thread.Status.REJECTED
        target.save(
            update_fields=[
                "moderated_by",
                "moderated_at",
                "moderator_notes",
                "status",
            ]
        )
        return snapshot

    if target_type in {
        ModerationCase.SafetyTargetType.COMMENT,
        ModerationCase.SafetyTargetType.EVIDENCE,
    }:
        target.safety_removed_at = removed_at
        target.safety_removed_by = actor
        target.save(
            update_fields=[
                "safety_removed_at",
                "safety_removed_by",
            ]
        )
        return {
            "pre_removal_thread_status": None,
            "pre_removal_moderated_by": None,
            "pre_removal_moderated_at": None,
            "pre_removal_moderator_notes": None,
        }

    raise CommunitySafetyTargetError("Unsupported Community Safety target type.")


def restore_target(*, decision, target):
    target_type = decision.target_type

    if target_type == CommunitySafetyDecision.TargetType.THREAD:
        if decision.pre_removal_thread_status not in {
            Thread.Status.PENDING,
            Thread.Status.OPEN,
            Thread.Status.CLOSED,
        }:
            raise CommunitySafetyTargetError(
                "The original discussion state cannot be restored safely."
            )

        target.status = decision.pre_removal_thread_status
        target.moderated_by_id = decision.pre_removal_moderated_by_id
        target.moderated_at = decision.pre_removal_moderated_at
        target.moderator_notes = decision.pre_removal_moderator_notes
        target.save(
            update_fields=[
                "status",
                "moderated_by",
                "moderated_at",
                "moderator_notes",
            ]
        )
        return

    if target_type in {
        CommunitySafetyDecision.TargetType.COMMENT,
        CommunitySafetyDecision.TargetType.EVIDENCE,
    }:
        if target.safety_removed_at is None:
            raise CommunitySafetyTargetError(
                f"The {target_label(target_type)} is no longer in the removed state."
            )
        target.safety_removed_at = None
        target.safety_removed_by = None
        target.save(
            update_fields=[
                "safety_removed_at",
                "safety_removed_by",
            ]
        )
        return

    raise CommunitySafetyTargetError("Unsupported Community Safety target type.")
