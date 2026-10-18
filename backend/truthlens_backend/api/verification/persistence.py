from collections.abc import Iterable

from django.db import transaction

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


def persist_evidence_sources(
    evidence_items: Iterable[NormalizedEvidence],
) -> list[tuple[EvidenceSource, bool]]:
    """Persist a batch while preserving single-item identity precedence."""
    evidence_items = list(evidence_items)
    if not evidence_items:
        return []

    for evidence in evidence_items:
        if not evidence.provider.strip():
            raise ValueError("Normalized evidence provider must not be blank.")

    providers = {evidence.provider for evidence in evidence_items}
    canonical_urls = {
        evidence.canonical_url
        for evidence in evidence_items
        if evidence.canonical_url
    }
    content_hashes = {
        evidence.content_hash
        for evidence in evidence_items
        if evidence.content_hash
    }

    with transaction.atomic():
        existing_by_url = {}
        if canonical_urls:
            for source in (
                EvidenceSource.objects.filter(
                    provider__in=providers,
                    canonical_url__in=canonical_urls,
                )
                .order_by("retrieved_at", "id")
            ):
                existing_by_url.setdefault(
                    (source.provider, source.canonical_url),
                    source,
                )

        existing_by_hash = {}
        if content_hashes:
            for source in (
                EvidenceSource.objects.filter(
                    provider__in=providers,
                    content_hash__in=content_hashes,
                )
                .order_by("retrieved_at", "id")
            ):
                existing_by_hash.setdefault(
                    (source.provider, source.content_hash),
                    source,
                )

        persisted = []
        for evidence in evidence_items:
            source = None
            if evidence.canonical_url:
                source = existing_by_url.get(
                    (evidence.provider, evidence.canonical_url)
                )
            if source is None and evidence.content_hash:
                source = existing_by_hash.get(
                    (evidence.provider, evidence.content_hash)
                )

            if source is not None:
                persisted.append((source, False))
                continue

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
                raw_reference=dict(evidence.raw_reference),
            )
            persisted.append((source, True))

            if source.canonical_url:
                existing_by_url.setdefault(
                    (source.provider, source.canonical_url),
                    source,
                )
            if source.content_hash:
                existing_by_hash.setdefault(
                    (source.provider, source.content_hash),
                    source,
                )

    return persisted
