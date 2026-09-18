from statistics import mean, median

from .models import AccountabilityEvent


class VerificationMetricsIntegrityError(Exception):
    pass


def project_organization_assignment_lifecycles(*, organization):
    """Project assignment attempts exclusively from organization-subject events.

    Shared intake is excluded. Each assignment resource identifies one attempt;
    incomplete or conflicting lifecycle history fails closed without row repair.
    """
    actions = AccountabilityEvent.ActionType
    lifecycle_actions = (
        actions.VERIFICATION_ASSIGNMENT_CLAIMED,
        actions.VERIFICATION_ASSIGNMENT_RELEASED,
        actions.VERIFICATION_ASSIGNMENT_COMPLETED,
    )
    events = AccountabilityEvent.objects.filter(
        resource_type=AccountabilityEvent.ResourceType.VERIFICATION_ASSIGNMENT,
        action_type__in=lifecycle_actions,
        subject_organization=organization,
    ).order_by("resource_id", "created_at", "id").values(
        "resource_id", "action_type", "context", "created_at",
    )

    histories = {}
    for event in events:
        histories.setdefault(event["resource_id"], []).append(event)

    attempts = []
    for assignment_id, history in histories.items():
        by_action = {action: [] for action in lifecycle_actions}
        claim_id = None
        for event in history:
            context = event["context"]
            event_claim_id = context.get("claim_id") if isinstance(context, dict) else None
            if not isinstance(event_claim_id, str) or not event_claim_id.strip():
                raise VerificationMetricsIntegrityError(
                    f"Assignment {assignment_id} has a missing or blank claim_id."
                )
            if claim_id is not None and event_claim_id != claim_id:
                raise VerificationMetricsIntegrityError(
                    f"Assignment {assignment_id} has inconsistent claim_id values."
                )
            claim_id = event_claim_id
            by_action[event["action_type"]].append(event)

        claimed = by_action[actions.VERIFICATION_ASSIGNMENT_CLAIMED]
        released = by_action[actions.VERIFICATION_ASSIGNMENT_RELEASED]
        completed = by_action[actions.VERIFICATION_ASSIGNMENT_COMPLETED]
        if len(claimed) != 1:
            raise VerificationMetricsIntegrityError(
                f"Assignment {assignment_id} must have exactly one claimed event."
            )
        if len(released) > 1 or len(completed) > 1:
            raise VerificationMetricsIntegrityError(
                f"Assignment {assignment_id} has duplicate terminal events."
            )
        if released and completed:
            raise VerificationMetricsIntegrityError(
                f"Assignment {assignment_id} has both released and completed events."
            )

        claimed_at = claimed[0]["created_at"]
        terminal = released or completed
        terminal_at = terminal[0]["created_at"] if terminal else None
        if terminal_at is not None and terminal_at < claimed_at:
            raise VerificationMetricsIntegrityError(
                f"Assignment {assignment_id} has a terminal event before its claim."
            )
        attempts.append({
            "assignment_id": assignment_id,
            "claim_id": claim_id,
            "organization_id": str(organization.pk),
            "status": "RELEASED" if released else "COMPLETED" if completed else "ACTIVE",
            "claimed_at": claimed_at,
            "terminal_at": terminal_at,
            "duration_seconds": (
                (terminal_at - claimed_at).total_seconds()
                if terminal_at is not None else None
            ),
        })

    return sorted(attempts, key=lambda attempt: (
        attempt["claimed_at"], attempt["assignment_id"],
    ))


def get_organization_verification_baseline(*, organization):
    """Aggregate observed operational attempts from the trusted projection.

    Coverage begins with recorded organization activity, without historical
    backfill. Reliability uses terminal outcomes; turnaround uses completions.
    """
    lifecycles = project_organization_assignment_lifecycles(organization=organization)
    counts = {"ACTIVE": 0, "RELEASED": 0, "COMPLETED": 0}
    claimed_times = []
    completed_durations = []
    for attempt in lifecycles:
        counts[attempt["status"]] += 1
        claimed_times.append(attempt["claimed_at"])
        if attempt["status"] == "COMPLETED":
            completed_durations.append(attempt["duration_seconds"])

    terminal = counts["RELEASED"] + counts["COMPLETED"]
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "ACCOUNTABILITY_EVENT",
            "coverage": "INSTRUMENTATION_ERA_ONLY",
            "historical_backfill": False,
            "first_observed_claimed_at": min(claimed_times) if claimed_times else None,
            "last_observed_claimed_at": max(claimed_times) if claimed_times else None,
        },
        "attempts": {
            "claimed": len(lifecycles),
            "active": counts["ACTIVE"],
            "released": counts["RELEASED"],
            "completed": counts["COMPLETED"],
            "terminal": terminal,
        },
        "reliability": {
            "terminal_completion_rate": counts["COMPLETED"] / terminal if terminal else None,
            "terminal_release_rate": counts["RELEASED"] / terminal if terminal else None,
        },
        "completed_turnaround": {
            "count": len(completed_durations),
            "average_seconds": float(mean(completed_durations)) if completed_durations else None,
            "median_seconds": float(median(completed_durations)) if completed_durations else None,
            "minimum_seconds": float(min(completed_durations)) if completed_durations else None,
            "maximum_seconds": float(max(completed_durations)) if completed_durations else None,
        },
    }
