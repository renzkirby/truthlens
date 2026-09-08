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
