import uuid
from urllib.parse import urlsplit

from django.db import IntegrityError, transaction

from ..models import CanonicalSource, EvidenceSource


class AmbiguousCanonicalSourceHostError(ValueError):
    """Raised when more than one CanonicalSource claims the same host."""


class CanonicalSourceHostCollisionError(ValueError):
    """Raised when a deterministic host UUID belongs to another identity."""


def _normalized_hostname(value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None

    try:
        hostname = urlsplit(value).hostname
    except ValueError:
        return None

    if not hostname:
        return None

    hostname = hostname.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname or None


def _source_hostname(evidence_source: EvidenceSource) -> str | None:
    return (
        _normalized_hostname(evidence_source.canonical_url)
        or _normalized_hostname(evidence_source.url)
    )


def canonical_source_id_for_host(hostname: str) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"truthlens:canonical-source-host:{hostname}",
    )


def _normalized_stored_domain(domain: str | None) -> str | None:
    if not isinstance(domain, str) or not domain:
        return None

    normalized = domain.lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]

    return normalized or None


def _validate_deterministic_source(
    canonical_source: CanonicalSource,
    hostname: str,
) -> CanonicalSource:
    if _normalized_stored_domain(canonical_source.domain) != hostname:
        raise CanonicalSourceHostCollisionError(
            "Deterministic CanonicalSource UUID is already assigned "
            f"to an incompatible host for {hostname}."
        )

    return canonical_source


def _get_or_create_canonical_source(hostname: str) -> CanonicalSource:
    matches = [
        canonical_source
        for canonical_source in CanonicalSource.objects.all().order_by("id")
        if _normalized_stored_domain(canonical_source.domain) == hostname
    ]
    if len(matches) > 1:
        raise AmbiguousCanonicalSourceHostError(
            f"Multiple CanonicalSource rows match host {hostname}."
        )

    if matches:
        return matches[0]

    deterministic_id = canonical_source_id_for_host(hostname)
    deterministic_source = CanonicalSource.objects.filter(
        pk=deterministic_id
    ).first()
    if deterministic_source is not None:
        return _validate_deterministic_source(deterministic_source, hostname)

    try:
        with transaction.atomic():
            return CanonicalSource.objects.create(
                id=deterministic_id,
                name=hostname,
                domain=hostname,
            )
    except IntegrityError:
        deterministic_source = CanonicalSource.objects.filter(
            pk=deterministic_id
        ).first()
        if deterministic_source is None:
            raise

        return _validate_deterministic_source(deterministic_source, hostname)


def assign_canonical_source(
    evidence_source: EvidenceSource,
) -> EvidenceSource:
    """Assign a persisted EvidenceSource its conservative observed-host identity."""
    if evidence_source._state.adding or evidence_source.pk is None:
        raise ValueError("EvidenceSource must already be persisted.")

    with transaction.atomic():
        locked_source = (
            EvidenceSource.objects.select_for_update()
            .get(pk=evidence_source.pk)
        )

        if locked_source.canonical_source_id is not None:
            return locked_source

        hostname = _source_hostname(locked_source)
        if hostname is None:
            return locked_source

        canonical_source = _get_or_create_canonical_source(hostname)
        locked_source.canonical_source = canonical_source
        locked_source.save(update_fields=["canonical_source"])

    return locked_source
