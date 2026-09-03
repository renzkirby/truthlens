from collections.abc import Iterable

from django.db import transaction

from ..models import EvidenceSource
from .contracts import RawEvidence
from .normalizers import normalize_evidence
from .persistence import persist_evidence_source
from .providers.base import EvidenceProvider


def ingest_raw_evidence(
    raw_evidence_items: Iterable[RawEvidence],
) -> list[EvidenceSource]:
    """
    Normalize and persist evidence that has already been retrieved.

    This allows runtime callers to retain provider-specific response
    data without performing the external provider request twice.
    """

    persisted_sources: list[EvidenceSource] = []
    seen_source_ids: set[object] = set()

    with transaction.atomic():
        for raw_evidence in raw_evidence_items:
            normalized_evidence = normalize_evidence(
                raw_evidence
            )

            evidence_source, _ = (
                persist_evidence_source(
                    normalized_evidence
                )
            )

            if evidence_source.pk in seen_source_ids:
                continue

            seen_source_ids.add(
                evidence_source.pk
            )

            persisted_sources.append(
                evidence_source
            )

    return persisted_sources


def ingest_provider_evidence(
    provider: EvidenceProvider,
    query: str,
    *,
    limit: int = 5,
) -> list[EvidenceSource]:
    """
    Retrieve evidence from a provider, normalize it, and persist it.
    """

    if limit <= 0:
        return []

    raw_evidence_items = provider.search(
        query,
        limit=limit,
    )

    return ingest_raw_evidence(
        raw_evidence_items
    )
