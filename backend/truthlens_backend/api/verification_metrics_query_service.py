"""Capability-scoped composition of trusted organization measurement services."""

from .organization_service import PartnerCapability, has_capability
from .verification_activity_metrics_service import get_organization_verification_activity
from .verification_metrics_service import get_organization_verification_baseline
from .verification_activity_trends_service import (
    VerificationActivityTrendInputError,
    get_organization_verification_activity_trend,
)


class VerificationMetricsAuthorizationError(Exception):
    pass


class VerificationMetricsCompositionError(Exception):
    pass


def get_organization_verification_metrics(
    *, actor, organization, created_after=None, created_before=None,
):
    if not (
        has_capability(
            actor,
            PartnerCapability.MANAGE_ORGANIZATION,
            organization=organization,
        )
        or has_capability(
            actor,
            PartnerCapability.CLAIM_VERIFICATION_WORK,
            organization=organization,
        )
    ):
        raise VerificationMetricsAuthorizationError(
            "You do not have permission to view this organization's verification metrics."
        )

    if (created_after is None) != (created_before is None):
        raise VerificationActivityTrendInputError(
            "created_after and created_before must be supplied together."
        )

    baseline = get_organization_verification_baseline(organization=organization)
    activity = get_organization_verification_activity(organization=organization)
    organization_id = str(organization.pk)
    if (
        baseline.get("organization_id") != organization_id
        or activity.get("organization_id") != organization_id
    ):
        raise VerificationMetricsCompositionError(
            "Measurement service organization identity is missing or mismatched."
        )

    metrics = {
        **baseline,
        "activity": {
            "measurement_basis": activity["measurement_basis"],
            "evidence_review": activity["evidence_review"],
            "adjudication": activity["adjudication"],
            "publication": activity["publication"],
        },
    }
    if created_after is not None and created_before is not None:
        trend = get_organization_verification_activity_trend(
            organization=organization,
            created_after=created_after,
            created_before=created_before,
        )
        if trend.get("organization_id") != organization_id:
            raise VerificationMetricsCompositionError(
                "Trend service organization identity is missing or mismatched."
            )
        metrics["trend"] = {
            "measurement_basis": trend["measurement_basis"],
            "totals": trend["totals"],
            "daily": trend["daily"],
        }
    return metrics
