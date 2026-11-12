"""Privacy-safe read projection for Community moderation outcomes."""

from .community_policy import get_community_violation
from .models import CommunitySafetyDecision, FlagResolutionLog


class CommunityModerationOutcomeNotFound(Exception):
    pass


def get_community_moderation_outcome(*, actor, decision_id):
    decision = (
        CommunitySafetyDecision.objects
        .select_related("thread_author")
        .filter(pk=decision_id)
        .first()
    )
    if decision is None:
        raise CommunityModerationOutcomeNotFound()

    role = None
    report_log = None
    if decision.thread_author_id == actor.id:
        role = "AUTHOR"
    else:
        report_log = (
            FlagResolutionLog.objects
            .filter(
                safety_decision=decision,
                flagged_by=actor,
            )
            .order_by("-resolved_at", "-id")
            .first()
        )
        if report_log is not None:
            role = "REPORTER"

    if role is None:
        raise CommunityModerationOutcomeNotFound()

    violation = get_community_violation(decision.violation_code)
    payload = {
        "id": str(decision.id),
        "role": role,
        "action": decision.action,
        "policy": {
            "title": decision.policy_title_snapshot,
            "version": decision.policy_version,
            "violation_code": decision.violation_code or None,
            "violation_title": (
                decision.violation_label_snapshot
                or (violation["title"] if violation else None)
            ),
        },
        "rationale": decision.rationale,
        "decided_at": decision.decided_at,
    }

    if role == "AUTHOR":
        payload["content"] = {
            "thread_id": str(decision.thread_id_snapshot),
            "excerpt": decision.content_excerpt_snapshot,
            "author_username": decision.author_username_snapshot,
        }
    else:
        payload["report"] = {
            "reason": report_log.reason,
            "reason_label": report_log.get_reason_display(),
            "notes": report_log.notes or "",
            "flagged_at": report_log.flagged_at,
            "outcome": report_log.report_outcome,
            "outcome_label": report_log.get_report_outcome_display(),
            "counts_toward_reputation": bool(report_log.is_valid_report),
        }

    return payload
