"""Current organization verification state from persisted operational records."""

from django.db.models import Q

from .models import (
    FactualCorrectionRequest,
    OfficialFactCheck,
    VerificationAssignment,
)


def get_organization_verification_current_state(*, organization):
    """Return aggregate current state for one organization without side effects."""

    published_fact_checks = (
        OfficialFactCheck.objects.filter(
            organization=organization,
            claim__isnull=False,
            adjudication_decision__isnull=False,
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        .values("claim_id")
        .distinct()
        .count()
    )
    active_corrections = FactualCorrectionRequest.objects.filter(
        organization=organization,
        status=FactualCorrectionRequest.Status.ACTIVE,
    ).count()
    active_investigations = VerificationAssignment.objects.filter(
        organization=organization,
        status=VerificationAssignment.Status.ACTIVE,
    ).count()
    open_publication_work = (
        OfficialFactCheck.objects.filter(
            organization=organization,
            claim__isnull=False,
            adjudication_decision__isnull=False,
            publication_status__in=(
                OfficialFactCheck.PublicationStatus.DRAFT,
                OfficialFactCheck.PublicationStatus.IN_REVIEW,
            ),
        )
        .filter(
            (
                Q(
                    revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
                    supersedes__isnull=True,
                )
                | Q(revision_kind__isnull=True, supersedes__isnull=True)
            )
            | Q(
                revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
                supersedes__isnull=False,
            )
        )
        .values("claim_id")
        .distinct()
        .count()
    )

    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "PERSISTED_OPERATIONAL_RECORDS",
            "coverage": "CURRENT_STATE",
        },
        "published_fact_checks": {
            "distinct_claims": published_fact_checks,
        },
        "factual_corrections": {
            "active_requests": active_corrections,
        },
        "investigations": {
            "active_assignments": active_investigations,
        },
        "publication_work": {
            "distinct_claims": open_publication_work,
        },
    }
