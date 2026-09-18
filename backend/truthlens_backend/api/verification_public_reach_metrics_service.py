"""Internal primitive counts of durable, observed public interactions."""

from .models import PublicReachEvent
from .public_reach_service import VALID_EVENT_SURFACE_PAIRS


class VerificationPublicReachMetricsIntegrityError(Exception):
    pass


def project_organization_public_reach_events(*, organization):
    """Validate selected snapshot history without consulting current relationships.

    Client event IDs are validated as recording-time identities and omitted from
    the projected measurement rows. They do not identify people or audiences.
    Authorization is the query composition layer's responsibility.
    """
    organization_id = str(organization.pk)
    rows = PublicReachEvent.objects.filter(
        source_organization_id_snapshot=organization_id,
    ).order_by("created_at", "id").values(
        "id", "client_event_id", "event_type", "source_surface",
        "source_organization_id_snapshot", "fact_check_id_snapshot", "created_at",
    )
    events = []
    for row in rows:
        event_type = row["event_type"]
        surface = row["source_surface"]
        publication_id = row["fact_check_id_snapshot"]
        is_profile = event_type == PublicReachEvent.EventType.PARTNER_PROFILE_VIEW
        if (
            not row["id"]
            or not row["client_event_id"]
            or not isinstance(event_type, str)
            or not isinstance(surface, str)
            or (event_type, surface) not in VALID_EVENT_SURFACE_PAIRS
            or row["source_organization_id_snapshot"] != organization_id
            or not isinstance(publication_id, str)
            or (is_profile and publication_id != "")
            or (not is_profile and (not publication_id.strip() or publication_id != publication_id.strip()))
            or row["created_at"] is None
        ):
            raise VerificationPublicReachMetricsIntegrityError(
                "Selected public reach history has invalid measurement fields."
            )
        events.append({
            "event_type": event_type,
            "source_surface": surface,
            "fact_check_id_snapshot": publication_id,
            "created_at": row["created_at"],
        })
    return events


def get_organization_public_reach_metrics(*, organization):
    """Count each interaction once; deduplicate only distinct publication snapshots.

    Recording-time idempotency already governs persisted events. These counts
    measure neither unique audience nor engagement or conversion rates.
    """
    events = project_organization_public_reach_events(organization=organization)
    by_type = {value: 0 for value in PublicReachEvent.EventType.values}
    by_surface = {value: 0 for value in PublicReachEvent.SourceSurface.values}
    publication_ids = set()
    extension = {
        "impressions": {"official": 0, "related": 0, "total": 0},
        "clicks": {"official": 0, "related": 0, "total": 0},
    }
    extension_types = {
        PublicReachEvent.EventType.EXTENSION_PUBLICATION_IMPRESSION: "impressions",
        PublicReachEvent.EventType.EXTENSION_PUBLICATION_CLICK: "clicks",
    }
    first_observed_at = None
    last_observed_at = None
    for event in events:
        event_type = event["event_type"]
        surface = event["source_surface"]
        by_type[event_type] += 1
        by_surface[surface] += 1
        if event["fact_check_id_snapshot"]:
            publication_ids.add(event["fact_check_id_snapshot"])
        if event_type in extension_types:
            category = (
                "official" if surface == PublicReachEvent.SourceSurface.EXTENSION_OFFICIAL_FACT_CHECK
                else "related"
            )
            extension[extension_types[event_type]][category] += 1
        created_at = event["created_at"]
        first_observed_at = (
            min(first_observed_at, created_at) if first_observed_at is not None else created_at
        )
        last_observed_at = (
            max(last_observed_at, created_at) if last_observed_at is not None else created_at
        )
    for counts in extension.values():
        counts["total"] = counts["official"] + counts["related"]
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "PUBLIC_REACH_EVENT",
            "attribution_source": "SOURCE_ORGANIZATION_ID_SNAPSHOT",
            "publication_identity_source": "FACT_CHECK_ID_SNAPSHOT",
            "coverage": "INSTRUMENTATION_ERA_ONLY",
            "historical_backfill": False,
            "unique_audience_measurement": False,
            "first_observed_interaction_at": first_observed_at,
            "last_observed_interaction_at": last_observed_at,
        },
        "observed_interactions": {
            "events": len(events),
            "by_type": by_type,
            "by_surface": by_surface,
            "distinct_publications": len(publication_ids),
        },
        "extension_publications": extension,
    }
