"""Capability-scoped composition of trusted organization measurement services."""

from .organization_service import PartnerCapability, has_capability
from .verification_activity_metrics_service import get_organization_verification_activity
from .verification_metrics_service import get_organization_verification_baseline


class VerificationMetricsAuthorizationError(Exception):
    pass


class VerificationMetricsCompositionError(Exception):
    pass


def get_organization_verification_metrics(*, actor, organization):
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

    return {
        **baseline,
        "activity": {
            "measurement_basis": activity["measurement_basis"],
            "evidence_review": activity["evidence_review"],
            "adjudication": activity["adjudication"],
            "publication": activity["publication"],
        },
    }
