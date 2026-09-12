from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..models import VerificationEvidence, VerificationRun
from .evidence_bundle import load_grouped_evidence_for_run


@dataclass(frozen=True, slots=True)
class ReasoningEvidenceItem:
    evidence_link_id: UUID
    evidence_source_id: UUID
    provider: str
    url: str | None
    canonical_url: str | None
    title: str | None
    publisher: str | None
    source_type: str | None
    content: str | None
    published_at: datetime | None
    retrieved_at: datetime | None
    evidence_role: str | None
    stance: str
    relevance_score: float | None
    directness_score: float | None
    recency_score: float | None


@dataclass(frozen=True, slots=True)
class ReasoningEvidenceGroup:
    identity_kind: str
    identity_id: UUID
    evidence: tuple[ReasoningEvidenceItem, ...]


def _reasoning_evidence_item(
    evidence_link: VerificationEvidence,
) -> ReasoningEvidenceItem:
    evidence_source = evidence_link.evidence_source
    return ReasoningEvidenceItem(
        evidence_link_id=evidence_link.pk,
        evidence_source_id=evidence_source.pk,
        provider=evidence_source.provider,
        url=evidence_source.url,
        canonical_url=evidence_source.canonical_url,
        title=evidence_source.title,
        publisher=evidence_source.publisher,
        source_type=evidence_source.source_type,
        content=evidence_source.content,
        published_at=evidence_source.published_at,
        retrieved_at=evidence_source.retrieved_at,
        evidence_role=evidence_link.evidence_role,
        stance=evidence_link.stance,
        relevance_score=evidence_link.relevance_score,
        directness_score=evidence_link.directness_score,
        recency_score=evidence_link.recency_score,
    )


def load_reasoning_evidence_dossier_for_run(
    verification_run: VerificationRun,
) -> list[ReasoningEvidenceGroup]:
    """Load a deterministic reasoning dossier from persisted grouped evidence."""
    evidence_groups = load_grouped_evidence_for_run(verification_run)

    return [
        ReasoningEvidenceGroup(
            identity_kind=evidence_group.identity_kind,
            identity_id=evidence_group.identity_id,
            evidence=tuple(
                _reasoning_evidence_item(evidence_link)
                for evidence_link in evidence_group.evidence
            ),
        )
        for evidence_group in evidence_groups
    ]
