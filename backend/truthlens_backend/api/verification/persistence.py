from ..models import EvidenceSource
from .contracts import NormalizedEvidence


def _find_existing_evidence_source(
    evidence: NormalizedEvidence,
) -> EvidenceSource | None:
    """
    Find an already persisted source using stable evidence identity.

    Identity is provider-scoped because separate providers may carry
    different provenance and provider-specific references for the same
    underlying webpage.
    """

    if evidence.canonical_url:
        existing = (
            EvidenceSource.objects
            .filter(
                provider=evidence.provider,
                canonical_url=evidence.canonical_url,
            )
            .order_by("retrieved_at", "id")
            .first()
        )

        if existing is not None:
            return existing

    if evidence.content_hash:
        existing = (
            EvidenceSource.objects
            .filter(
                provider=evidence.provider,
                content_hash=evidence.content_hash,
            )
            .order_by("retrieved_at", "id")
            .first()
        )

        if existing is not None:
            return existing

    return None


def persist_evidence_source(
    evidence: NormalizedEvidence,
) -> tuple[EvidenceSource, bool]:
    """
    Persist normalized evidence as an EvidenceSource.

    Returns:
        (evidence_source, created)

    Existing matching records are reused without being overwritten.
    """

    if not evidence.provider.strip():
        raise ValueError(
            "Normalized evidence provider must not be blank."
        )

    existing = _find_existing_evidence_source(
        evidence
    )

    if existing is not None:
        return existing, False

    source = EvidenceSource.objects.create(
        provider=evidence.provider,
        url=evidence.url,
        canonical_url=evidence.canonical_url,
        title=evidence.title,
        publisher=evidence.publisher,
        source_type=evidence.source_type,
        content=evidence.content,
        content_hash=evidence.content_hash,
        published_at=evidence.published_at,
        raw_reference=dict(
            evidence.raw_reference
        ),
    )

    return source, True