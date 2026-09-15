"""Observed ordinary institutional activity from append-only accountability events."""

from .models import AccountabilityEvent


class VerificationActivityMetricsIntegrityError(Exception):
    pass


def project_organization_verification_activity_events(*, organization):
    """Validate complete selected history and project ordinary activity events.

    Correction evidence and revision/correction publications are outside ordinary
    activity. No time window is applied: malformed selected history anywhere in
    the organization's instrumentation history fails closed before returning.
    """
    actions = AccountabilityEvent.ActionType
    resources = AccountabilityEvent.ResourceType
    expected_resources = {
        actions.EVIDENCE_VERIFIED: resources.EVIDENCE_SUBMISSION,
        actions.EVIDENCE_REJECTED: resources.EVIDENCE_SUBMISSION,
        actions.ADJUDICATION_STARTED: resources.MODERATION_CASE,
        actions.VERDICT_ISSUED: resources.ADJUDICATION_DECISION,
        actions.ARTICLE_PUBLISHED: resources.OFFICIAL_FACT_CHECK,
    }
    events = AccountabilityEvent.objects.filter(
        subject_organization=organization,
        action_type__in=tuple(expected_resources),
    ).order_by("created_at", "id").values(
        "id", "action_type", "resource_type", "context", "created_at",
    )

    projected_events = []
    seen_claims = {
        actions.ADJUDICATION_STARTED: set(),
        actions.VERDICT_ISSUED: set(),
        actions.ARTICLE_PUBLISHED: set(),
    }
    for event in events:
        action = event["action_type"]
        if event["resource_type"] != expected_resources[action]:
            raise VerificationActivityMetricsIntegrityError(
                f"Event {event['id']} has an incorrect resource type for {action}."
            )
        context = event["context"]
        claim_id = context.get("claim_id") if isinstance(context, dict) else None
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise VerificationActivityMetricsIntegrityError(
                f"Event {event['id']} has a missing or blank claim_id."
            )

        if (
            action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED)
            and "correction_request_id" in context
        ):
            continue

        if action == actions.ARTICLE_PUBLISHED and context.get("revision_kind") != "INITIAL":
            raise VerificationActivityMetricsIntegrityError(
                f"Event {event['id']} is not an explicit initial publication."
            )
        if action in seen_claims:
            if claim_id in seen_claims[action]:
                raise VerificationActivityMetricsIntegrityError(
                    f"Claim {claim_id} has duplicate {action} history in this organization."
                )
            seen_claims[action].add(claim_id)

        projected_events.append({
            "action_type": action,
            "claim_id": claim_id,
            "created_at": event["created_at"],
        })

    return projected_events


def get_organization_verification_activity(*, organization):
    """Aggregate ordinary instrumented activity without historical backfill."""
    events = project_organization_verification_activity_events(organization=organization)
    actions = AccountabilityEvent.ActionType
    counts = dict.fromkeys((
        actions.EVIDENCE_VERIFIED,
        actions.EVIDENCE_REJECTED,
        actions.ADJUDICATION_STARTED,
        actions.VERDICT_ISSUED,
        actions.ARTICLE_PUBLISHED,
    ), 0)
    first_observed_at = None
    last_observed_at = None
    for event in events:
        counts[event["action_type"]] += 1
        created_at = event["created_at"]
        first_observed_at = (
            min(first_observed_at, created_at)
            if first_observed_at is not None else created_at
        )
        last_observed_at = (
            max(last_observed_at, created_at)
            if last_observed_at is not None else created_at
        )

    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "ACCOUNTABILITY_EVENT",
            "coverage": "INSTRUMENTATION_ERA_ONLY",
            "historical_backfill": False,
            "first_observed_activity_at": first_observed_at,
            "last_observed_activity_at": last_observed_at,
        },
        "evidence_review": {
            "decisions": counts[actions.EVIDENCE_VERIFIED] + counts[actions.EVIDENCE_REJECTED],
            "verified": counts[actions.EVIDENCE_VERIFIED],
            "rejected": counts[actions.EVIDENCE_REJECTED],
        },
        "adjudication": {
            "started": counts[actions.ADJUDICATION_STARTED],
            "verdicts_issued": counts[actions.VERDICT_ISSUED],
        },
        "publication": {
            "initial_published": counts[actions.ARTICLE_PUBLISHED],
        },
    }
