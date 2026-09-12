from ..models import VerificationEvidence, VerificationRun
from .grouping import (
    EvidenceIndependenceGroup,
    group_verification_evidence_by_source_identity,
)


def load_grouped_evidence_for_run(
    verification_run: VerificationRun,
) -> list[EvidenceIndependenceGroup]:
    """Load and group one persisted verification run's evidence links."""
    if verification_run._state.adding or verification_run.pk is None:
        raise ValueError("VerificationRun must already be persisted.")

    evidence_links = (
        VerificationEvidence.objects.filter(verification_run=verification_run)
        .select_related(
            "evidence_source",
            "evidence_source__canonical_source",
        )
        .order_by("created_at", "pk")
    )

    return group_verification_evidence_by_source_identity(evidence_links)
