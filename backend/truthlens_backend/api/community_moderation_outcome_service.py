"""Privacy-safe read projection for Community moderation outcomes."""

from .community_policy import get_community_violation
from .models import (
    CommunityReportOutcome,
    CommunitySafetyDecision,
    CommunitySafetyReconsideration,
)


class CommunityModerationOutcomeNotFound(Exception):
    pass


def get_community_moderation_outcome(*, actor, decision_id):
    decision = (
        CommunitySafetyDecision.objects
        .select_related("content_owner", "moderation_case", "reconsideration")
        .filter(pk=decision_id)
        .first()
    )
    if decision is None:
        raise CommunityModerationOutcomeNotFound()

    role = None
    report_log = None
    if decision.content_owner_id == actor.id:
        role = "AUTHOR"
    else:
        report_log = (
            CommunityReportOutcome.objects
            .filter(
                safety_decision=decision,
                reporter=actor,
            )
            .order_by("-resolved_at", "-id")
            .first()
        )
        if report_log is not None:
            role = "REPORTER"

    if role is None:
        raise CommunityModerationOutcomeNotFound()

    violation = get_community_violation(decision.violation_code)
    reconsideration = getattr(decision, "reconsideration", None)
    reconsideration_reversed = bool(
        reconsideration
        and reconsideration.outcome
        == CommunitySafetyReconsideration.Outcome.REVERSED
    )

    payload = {
        "id": str(decision.id),
        "role": role,
        "action": decision.action,
        "target": {
            "type": decision.target_type,
            "id": str(decision.target_id_snapshot),
            "thread_id": str(decision.thread_id_snapshot),
        },
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
        "reconsideration": (
            {
                "status": "RESOLVED" if reconsideration.outcome else "SUBMITTED",
                "outcome": reconsideration.outcome or None,
                "resolution_rationale": reconsideration.resolution_rationale,
                "submitted_at": reconsideration.submitted_at,
                "resolved_at": reconsideration.resolved_at,
                "content_restored": reconsideration_reversed,
            }
            if reconsideration
            else None
        ),
    }

    if role == "AUTHOR":
        payload["content"] = {
            "thread_id": str(decision.thread_id_snapshot),
            "target_id": str(decision.target_id_snapshot),
            "target_type": decision.target_type,
            "excerpt": decision.content_excerpt_snapshot,
            "owner_username": decision.owner_username_snapshot,
        }
        if reconsideration:
            payload["reconsideration"]["request_statement"] = (
                reconsideration.request_statement
            )

        from .community_safety_reconsideration_service import (
            can_request_reconsideration,
        )

        payload["can_request_reconsideration"] = can_request_reconsideration(
            decision=decision,
            actor=actor,
        )
    else:
        payload["report"] = {
            "reason": report_log.reason,
            "reason_label": report_log.get_reason_display(),
            "notes": report_log.notes or "",
            "reported_at": report_log.reported_at,
            "outcome": report_log.report_outcome,
            "outcome_label": report_log.get_report_outcome_display(),
            "counts_toward_reputation": bool(
                report_log.is_valid_report and not reconsideration_reversed
            ),
        }

    return payload
