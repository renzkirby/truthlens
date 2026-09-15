"""Capability-scoped access to the trusted organization metrics baseline."""

from .organization_service import PartnerCapability, has_capability
from .verification_metrics_service import get_organization_verification_baseline


class VerificationMetricsAuthorizationError(Exception):
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

    return get_organization_verification_baseline(organization=organization)
