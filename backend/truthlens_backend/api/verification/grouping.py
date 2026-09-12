from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from ..models import VerificationEvidence


CANONICAL_SOURCE = "CANONICAL_SOURCE"
EVIDENCE_SOURCE = "EVIDENCE_SOURCE"


@dataclass(frozen=True, slots=True)
class EvidenceIndependenceGroup:
    identity_kind: str
    identity_id: UUID
    evidence: tuple[VerificationEvidence, ...]


def group_verification_evidence_by_source_identity(
    evidence_links: Iterable[VerificationEvidence],
) -> list[EvidenceIndependenceGroup]:
    """Group persisted evidence links by explicit source identity."""
    grouped_links: dict[
        tuple[str, UUID],
        list[VerificationEvidence],
    ] = {}
    seen_link_ids: set[UUID] = set()
    verification_run_id: UUID | None = None

    for evidence_link in evidence_links:
        if evidence_link._state.adding or evidence_link.pk is None:
            raise ValueError("Every VerificationEvidence must already be persisted.")

        if verification_run_id is None:
            verification_run_id = evidence_link.verification_run_id
        elif evidence_link.verification_run_id != verification_run_id:
            raise ValueError(
                "Every VerificationEvidence must belong to the same VerificationRun."
            )

        if evidence_link.pk in seen_link_ids:
            continue
        seen_link_ids.add(evidence_link.pk)

        canonical_source_id = evidence_link.evidence_source.canonical_source_id
        if canonical_source_id is not None:
            identity = (CANONICAL_SOURCE, canonical_source_id)
        else:
            identity = (EVIDENCE_SOURCE, evidence_link.evidence_source_id)

        grouped_links.setdefault(identity, []).append(evidence_link)

    return [
        EvidenceIndependenceGroup(
            identity_kind=identity_kind,
            identity_id=identity_id,
            evidence=tuple(group_links),
        )
        for (identity_kind, identity_id), group_links in grouped_links.items()
    ]
