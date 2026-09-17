from collections.abc import Iterable

from django.db import transaction

from ..models import EvidenceSource, VerificationEvidence, VerificationRun


def link_evidence_sources_to_run(
    verification_run: VerificationRun,
    evidence_sources: Iterable[EvidenceSource],
    *,
    evidence_role: str,
) -> list[VerificationEvidence]:
    """Create or reuse links without changing sources, runs, or existing links."""
    if verification_run._state.adding or verification_run.pk is None:
        raise ValueError("VerificationRun must already be persisted.")
    if evidence_role not in VerificationEvidence.EvidenceRole.values:
        raise ValueError("Invalid VerificationEvidence evidence_role.")

    sources = []
    seen_source_ids = set()
    for source in evidence_sources:
        # UUID defaults allocate primary keys even for unsaved model instances.
        if source._state.adding or source.pk is None:
            raise ValueError("Every EvidenceSource must already be persisted.")
        if source.pk not in seen_source_ids:
            seen_source_ids.add(source.pk)
            sources.append(source)

    if not sources:
        return []

    links = []
    with transaction.atomic():
        # Serialize linking batches for this run without changing its lifecycle.
        locked_run = VerificationRun.objects.select_for_update().get(
            pk=verification_run.pk
        )
        for source in sources:
            link, _ = VerificationEvidence.objects.get_or_create(
                verification_run=locked_run,
                evidence_source=source,
                defaults={"evidence_role": evidence_role},
            )
            links.append(link)

    return links


def record_retrieval_provenance(
    verification_links: Iterable[VerificationEvidence],
    *,
    provider: str,
    query: str,
    query_index: int,
) -> list[VerificationEvidence]:
    """Append one normalized discovery record to persisted run/source links."""
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be a non-empty string.")
    normalized_provider = provider.strip()

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    normalized_query = " ".join(query.split())

    if (
        isinstance(query_index, bool)
        or not isinstance(query_index, int)
        or query_index < 0
    ):
        raise ValueError("query_index must be a non-negative integer.")

    links = []
    seen_link_ids = set()
    for link in verification_links:
        if not isinstance(link, VerificationEvidence):
            raise ValueError("Every link must be a VerificationEvidence instance.")
        # UUID defaults allocate primary keys even for unsaved model instances.
        if link._state.adding or link.pk is None:
            raise ValueError("Every VerificationEvidence must already be persisted.")
        if link.pk not in seen_link_ids:
            seen_link_ids.add(link.pk)
            links.append(link)

    if not links:
        return []

    provenance_entry = {
        "provider": normalized_provider,
        "query": normalized_query,
        "query_index": query_index,
    }
    link_ids = [link.pk for link in links]

    with transaction.atomic():
        locked_links_by_id = {
            link.pk: link
            for link in VerificationEvidence.objects.select_for_update()
            .filter(pk__in=link_ids)
            .order_by("pk")
        }
        if len(locked_links_by_id) != len(link_ids):
            raise ValueError("Every VerificationEvidence must already be persisted.")

        locked_links = [locked_links_by_id[link_id] for link_id in link_ids]
        changed_links = []
        for link in locked_links:
            existing_provenance = link.retrieval_provenance
            if not isinstance(existing_provenance, list):
                raise ValueError("retrieval_provenance must be a list.")
            if provenance_entry not in existing_provenance:
                link.retrieval_provenance = [
                    *existing_provenance,
                    provenance_entry,
                ]
                changed_links.append(link)

        if changed_links:
            VerificationEvidence.objects.bulk_update(
                changed_links,
                ["retrieval_provenance"],
            )

    return locked_links
