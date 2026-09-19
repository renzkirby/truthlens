"""Privacy-minimal, append-only instrumentation for observed public interactions."""

from uuid import UUID

from .models import OfficialFactCheck, Organization, PublicReachEvent
from .organization_public_presence_service import is_public_partner_eligible
from .public_publication_query_service import (
    PublicPublicationNotFound,
    get_public_partner_fact_check_detail,
)


class PublicReachError(Exception):
    pass


class InvalidPublicReach(PublicReachError):
    pass


class PublicReachTargetNotFound(PublicReachError):
    pass


class PublicReachConflict(PublicReachError):
    pass


E = PublicReachEvent.EventType
S = PublicReachEvent.SourceSurface
VALID_EVENT_SURFACE_PAIRS = frozenset({
    (E.PARTNER_PROFILE_VIEW, S.PUBLIC_PARTNER_PROFILE),
    (E.PUBLICATION_VIEW, S.PUBLIC_FACT_CHECK_PAGE),
    (E.EXTENSION_PUBLICATION_IMPRESSION, S.EXTENSION_OFFICIAL_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_IMPRESSION, S.EXTENSION_RELATED_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_CLICK, S.EXTENSION_OFFICIAL_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_CLICK, S.EXTENSION_RELATED_FACT_CHECK),
})


def validate_public_reach_pair(event_type, source_surface):
    if not isinstance(event_type, str) or not isinstance(source_surface, str):
        raise InvalidPublicReach("Invalid event/surface pair.")
    if (event_type, source_surface) not in VALID_EVENT_SURFACE_PAIRS:
        raise InvalidPublicReach("Invalid event/surface pair.")


def record_public_reach_event(
    *, client_event_id, event_type, source_surface, organization, fact_check=None,
):
    """Return (event, created). Retries compare immutable event-local snapshots."""
    try:
        client_event_id = UUID(str(client_event_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise InvalidPublicReach("client_event_id must be a UUID.") from error
    validate_public_reach_pair(event_type, source_surface)
    if not isinstance(organization, Organization) or organization._state.adding:
        raise PublicReachTargetNotFound("Public target unavailable.")
    # Refresh eligibility from storage rather than trusting a stale caller instance.
    organization = Organization.objects.filter(pk=organization.pk).first()
    if organization is None or not is_public_partner_eligible(organization):
        raise PublicReachTargetNotFound("Public target unavailable.")

    publication_snapshot = ""
    if event_type == E.PARTNER_PROFILE_VIEW:
        if fact_check is not None:
            raise InvalidPublicReach("Profile views cannot specify a publication.")
    else:
        if fact_check is None:
            raise InvalidPublicReach("Publication events require a publication.")
        if not isinstance(fact_check, OfficialFactCheck) or fact_check._state.adding:
            raise PublicReachTargetNotFound("Public target unavailable.")
        fact_check = OfficialFactCheck.objects.filter(
            pk=fact_check.pk, organization=organization,
        ).first()
        if fact_check is None:
            raise PublicReachTargetNotFound("Public target unavailable.")
        try:
            get_public_partner_fact_check_detail(
                organization=organization, publication_id=fact_check.pk,
            )
        except PublicPublicationNotFound as error:
            raise PublicReachTargetNotFound("Public target unavailable.") from error
        publication_snapshot = str(fact_check.pk)

    semantics = {
        "event_type": event_type,
        "source_surface": source_surface,
        "source_organization_id_snapshot": str(organization.pk),
        "fact_check_id_snapshot": publication_snapshot,
    }
    # get_or_create uses an atomic insert and resolves a unique-key race by
    # fetching the winning row. The DB unique constraint is the concurrency gate.
    event, created = PublicReachEvent.objects.get_or_create(
        client_event_id=client_event_id,
        defaults={**semantics, "organization": organization, "fact_check": fact_check},
    )
    if any(getattr(event, field) != value for field, value in semantics.items()):
        raise PublicReachConflict("client_event_id already represents another event.")
    return event, created
