from collections.abc import Iterable
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


def filter_reasoning_evidence_dossier_by_role(
    evidence_groups: Iterable[ReasoningEvidenceGroup],
    evidence_role: str,
) -> list[ReasoningEvidenceGroup]:
    """Select an exact evidence role without changing group or member order."""
    filtered_groups = []

    for evidence_group in evidence_groups:
        matching_evidence = tuple(
            evidence_item
            for evidence_item in evidence_group.evidence
            if evidence_item.evidence_role == evidence_role
        )
        if matching_evidence:
            filtered_groups.append(ReasoningEvidenceGroup(
                identity_kind=evidence_group.identity_kind,
                identity_id=evidence_group.identity_id,
                evidence=matching_evidence,
            ))

    return filtered_groups


def render_reasoning_evidence_dossier(
    evidence_groups: Iterable[ReasoningEvidenceGroup],
) -> str:
    """Render persisted evidence with explicit source-identity boundaries."""
    evidence_groups = tuple(evidence_groups)
    if not evidence_groups:
        return ""

    lines = [
        "PERSISTED EVIDENCE DOSSIER",
        (
            "Items within one SOURCE IDENTITY GROUP share normalized source "
            "identity and must not be counted as multiple independent confirmations."
        ),
        (
            "Different SOURCE IDENTITY GROUPS are not guaranteed to be "
            "editorially independent."
        ),
    ]

    for group_index, evidence_group in enumerate(evidence_groups, start=1):
        lines.extend([
            "",
            f"=== SOURCE IDENTITY GROUP {group_index} ===",
            f"Identity kind: {evidence_group.identity_kind}",
        ])

        for item_index, evidence_item in enumerate(evidence_group.evidence, start=1):
            lines.extend([
                "",
                f"--- EVIDENCE ITEM {item_index} ---",
                f"Provider: {evidence_item.provider}",
            ])
            optional_fields = (
                ("Evidence role", evidence_item.evidence_role),
                ("Stance", evidence_item.stance),
                ("Publisher", evidence_item.publisher),
                ("Source type", evidence_item.source_type),
                ("Title", evidence_item.title),
                ("URL", evidence_item.url),
                ("Canonical URL", evidence_item.canonical_url),
                ("Published at", evidence_item.published_at),
                ("Retrieved at", evidence_item.retrieved_at),
                ("Relevance score", evidence_item.relevance_score),
                ("Directness score", evidence_item.directness_score),
                ("Recency score", evidence_item.recency_score),
            )
            lines.extend(
                f"{label}: {value.isoformat() if isinstance(value, datetime) else value}"
                for label, value in optional_fields
                if value is not None
            )
            if evidence_item.content is not None:
                lines.extend(["Content:", evidence_item.content])

    return "\n".join(lines)
