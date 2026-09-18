"""Aggregate reviewer participation proven by durable accountability actor IDs."""

from .models import AccountabilityEvent
from .organization_service import PartnerCapability


class VerificationReviewerParticipationMetricsIntegrityError(Exception):
    pass


def get_organization_verification_reviewer_participation(*, organization):
    """Count distinct reviewers without reconstructing historical person identity.

    Correction review and verdict revision are substantive reviewer participation.
    Blank historical durable IDs are outside coverage, but their selected event
    semantics must still be valid. Neither actor FKs nor usernames are consulted.
    """
    actions = AccountabilityEvent.ActionType
    resources = AccountabilityEvent.ResourceType
    expected_semantics = {
        actions.EVIDENCE_VERIFIED: (
            resources.EVIDENCE_SUBMISSION, PartnerCapability.REVIEW_EVIDENCE, "evidence_review",
        ),
        actions.EVIDENCE_REJECTED: (
            resources.EVIDENCE_SUBMISSION, PartnerCapability.REVIEW_EVIDENCE, "evidence_review",
        ),
        actions.ADJUDICATION_STARTED: (
            resources.MODERATION_CASE, PartnerCapability.ADJUDICATE, "adjudication",
        ),
        actions.VERDICT_ISSUED: (
            resources.ADJUDICATION_DECISION, PartnerCapability.ADJUDICATE, "adjudication",
        ),
        actions.VERDICT_REVISED: (
            resources.ADJUDICATION_DECISION, PartnerCapability.ADJUDICATE, "adjudication",
        ),
    }
    events = AccountabilityEvent.objects.filter(
        subject_organization=organization,
        action_type__in=tuple(expected_semantics),
    ).order_by("created_at", "id").values(
        "action_type", "resource_type", "authority_scope",
        "authority_organization_id", "capability", "actor_id_snapshot", "created_at",
    )

    reviewers_by_stage = {"evidence_review": set(), "adjudication": set()}
    first_observed_at = None
    last_observed_at = None
    for event in events:
        resource_type, capability, stage = expected_semantics[event["action_type"]]
        if (
            event["resource_type"] != resource_type
            or event["authority_scope"] != AccountabilityEvent.AuthorityScope.ORGANIZATION
            or event["authority_organization_id"] != organization.pk
            or event["capability"] != capability
        ):
            raise VerificationReviewerParticipationMetricsIntegrityError(
                "Selected reviewer participation history has invalid event semantics."
            )

        actor_id = event["actor_id_snapshot"]
        if actor_id == "":
            continue
        if (
            not isinstance(actor_id, str)
            or not actor_id.strip()
            or actor_id != actor_id.strip()
        ):
            raise VerificationReviewerParticipationMetricsIntegrityError(
                "Selected reviewer participation history has an invalid durable actor ID."
            )

        reviewers_by_stage[stage].add(actor_id)
        created_at = event["created_at"]
        first_observed_at = (
            min(first_observed_at, created_at)
            if first_observed_at is not None else created_at
        )
        last_observed_at = (
            max(last_observed_at, created_at)
            if last_observed_at is not None else created_at
        )

    unique_reviewers = reviewers_by_stage["evidence_review"] | reviewers_by_stage["adjudication"]
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "ACCOUNTABILITY_EVENT",
            "identity_source": "ACTOR_ID_SNAPSHOT",
            "coverage": "DURABLE_ACTOR_ID_SNAPSHOT_EVENTS_ONLY",
            "historical_backfill": False,
            "first_observed_participation_at": first_observed_at,
            "last_observed_participation_at": last_observed_at,
        },
        "reviewer_participation": {
            "unique_reviewers": len(unique_reviewers),
            "by_stage": {
                stage: len(reviewers) for stage, reviewers in reviewers_by_stage.items()
            },
        },
    }
