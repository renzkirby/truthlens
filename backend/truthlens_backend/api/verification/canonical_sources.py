import uuid
from collections.abc import Iterable
from urllib.parse import urlsplit

from django.db import IntegrityError, transaction
from django.db.models import Q

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
    matches = list(
        CanonicalSource.objects.filter(
            Q(domain__iexact=hostname)
            | Q(domain__iexact=f"www.{hostname}")
        ).order_by("id")
    )
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
    return assign_canonical_sources([evidence_source])[0]


def assign_canonical_sources(
    evidence_sources: Iterable[EvidenceSource],
) -> list[EvidenceSource]:
    """Assign observed-host identities to a persisted source batch."""
    sources = []
    source_ids = set()
    for source in evidence_sources:
        if source._state.adding or source.pk is None:
            raise ValueError("EvidenceSource must already be persisted.")
        if source.pk not in source_ids:
            source_ids.add(source.pk)
            sources.append(source)

    if not sources:
        return []

    with transaction.atomic():
        locked_by_id = {
            source.pk: source
            for source in (
                EvidenceSource.objects.select_for_update()
                .filter(pk__in=source_ids)
            )
        }
        if len(locked_by_id) != len(source_ids):
            raise EvidenceSource.DoesNotExist(
                "Every EvidenceSource must already be persisted."
            )

        locked_sources = [locked_by_id[source.pk] for source in sources]
        hostnames = {
            hostname
            for source in locked_sources
            if source.canonical_source_id is None
            for hostname in [_source_hostname(source)]
            if hostname is not None
        }
        if not hostnames:
            return locked_sources

        domain_filter = Q()
        for hostname in hostnames:
            domain_filter |= Q(domain__iexact=hostname)
            domain_filter |= Q(domain__iexact=f"www.{hostname}")

        matches_by_host = {hostname: [] for hostname in hostnames}
        for canonical_source in (
            CanonicalSource.objects.filter(domain_filter).order_by("id")
        ):
            normalized_domain = _normalized_stored_domain(canonical_source.domain)
            if normalized_domain in matches_by_host:
                matches_by_host[normalized_domain].append(canonical_source)

        canonical_by_host = {}
        unresolved_hosts = []
        for hostname in sorted(hostnames):
            matches = matches_by_host[hostname]
            if len(matches) > 1:
                raise AmbiguousCanonicalSourceHostError(
                    f"Multiple CanonicalSource rows match host {hostname}."
                )
            if matches:
                canonical_by_host[hostname] = matches[0]
            else:
                unresolved_hosts.append(hostname)

        deterministic_ids = {
            hostname: canonical_source_id_for_host(hostname)
            for hostname in unresolved_hosts
        }
        deterministic_sources = {
            source.pk: source
            for source in CanonicalSource.objects.filter(
                pk__in=deterministic_ids.values()
            )
        }

        for hostname in unresolved_hosts:
            deterministic_id = deterministic_ids[hostname]
            canonical_source = deterministic_sources.get(deterministic_id)
            if canonical_source is not None:
                canonical_by_host[hostname] = _validate_deterministic_source(
                    canonical_source,
                    hostname,
                )
                continue

            try:
                with transaction.atomic():
                    canonical_source = CanonicalSource.objects.create(
                        id=deterministic_id,
                        name=hostname,
                        domain=hostname,
                    )
            except IntegrityError:
                canonical_source = CanonicalSource.objects.filter(
                    pk=deterministic_id
                ).first()
                if canonical_source is None:
                    raise
                canonical_source = _validate_deterministic_source(
                    canonical_source,
                    hostname,
                )
            canonical_by_host[hostname] = canonical_source

        changed_sources = []
        for source in locked_sources:
            if source.canonical_source_id is not None:
                continue
            hostname = _source_hostname(source)
            if hostname is None:
                continue
            source.canonical_source = canonical_by_host[hostname]
            changed_sources.append(source)

        if changed_sources:
            EvidenceSource.objects.bulk_update(
                changed_sources,
                ["canonical_source"],
            )

    return locked_sources
