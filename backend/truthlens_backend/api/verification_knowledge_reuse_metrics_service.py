"""Internal metrics for observed material reuse of published knowledge."""

import math

from .models import KnowledgeReuseEvent


class VerificationKnowledgeReuseMetricsIntegrityError(Exception):
    pass


def project_organization_knowledge_reuse_events(*, organization):
    """Return validated measurement rows attributed by the durable source snapshot.

    Blank historical source snapshots are outside coverage. Current relationships
    must never reconstruct attribution or target identity. Read only measurement
    fields; metadata, query fingerprints and actor identities are not consulted.
    """
    organization_id = str(organization.pk)
    rows = KnowledgeReuseEvent.objects.filter(
        source_organization_id_snapshot=organization_id,
    ).order_by("created_at", "id").values(
        "id", "fact_check_id", "reuse_type", "match_method",
        "source_organization_id_snapshot", "target_claim_id_snapshot",
        "similarity_score", "created_at",
    )
    events = []
    for row in rows:
        target_id = row["target_claim_id_snapshot"]
        score = row["similarity_score"]
        try:
            valid_score = score is None or (math.isfinite(score) and 0 <= score <= 1)
        except (TypeError, ValueError, OverflowError):
            valid_score = False
        if (
            not row["id"]
            or not row["fact_check_id"]
            or row["reuse_type"] not in KnowledgeReuseEvent.ReuseType.values
            or row["match_method"] not in KnowledgeReuseEvent.MatchMethod.values
            or row["source_organization_id_snapshot"] != organization_id
            or not isinstance(target_id, str)
            or (target_id != "" and (not target_id.strip() or target_id != target_id.strip()))
            or not valid_score
            or row["created_at"] is None
        ):
            raise VerificationKnowledgeReuseMetricsIntegrityError(
                "Selected knowledge reuse history has invalid measurement fields."
            )
        events.append(row)
    return events


def get_organization_knowledge_reuse_metrics(*, organization):
    """Count every observed event; only explicitly distinct metrics deduplicate.

    Repeat claim reuse means a USER_RESPONSE served with CLAIM_CACHE. These
    observations do not estimate users, requests, work avoided or hours saved.
    Authorization belongs to the later API composition layer.
    """
    events = project_organization_knowledge_reuse_events(organization=organization)
    by_type = {value: 0 for value in KnowledgeReuseEvent.ReuseType.values}
    by_method = {value: 0 for value in KnowledgeReuseEvent.MatchMethod.values}
    publication_ids = set()
    target_ids = set()
    cached_target_ids = set()
    cached_responses = 0
    first_observed_at = None
    last_observed_at = None
    for event in events:
        by_type[event["reuse_type"]] += 1
        by_method[event["match_method"]] += 1
        publication_ids.add(event["fact_check_id"])
        target_id = event["target_claim_id_snapshot"]
        if target_id:
            target_ids.add(target_id)
        if (
            event["reuse_type"] == KnowledgeReuseEvent.ReuseType.USER_RESPONSE
            and event["match_method"] == KnowledgeReuseEvent.MatchMethod.CLAIM_CACHE
        ):
            cached_responses += 1
            if target_id:
                cached_target_ids.add(target_id)
        created_at = event["created_at"]
        first_observed_at = (
            min(first_observed_at, created_at) if first_observed_at is not None else created_at
        )
        last_observed_at = (
            max(last_observed_at, created_at) if last_observed_at is not None else created_at
        )
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "KNOWLEDGE_REUSE_EVENT",
            "attribution_source": "SOURCE_ORGANIZATION_ID_SNAPSHOT",
            "target_identity_source": "TARGET_CLAIM_ID_SNAPSHOT",
            "coverage": "ATTRIBUTED_INSTRUMENTATION_ERA_ONLY",
            "historical_backfill": False,
            "historical_unattributed_rows_excluded": True,
            "first_observed_reuse_at": first_observed_at,
            "last_observed_reuse_at": last_observed_at,
        },
        "material_reuse": {
            "events": len(events),
            "by_type": by_type,
            "by_match_method": by_method,
            "distinct_publications": len(publication_ids),
            "distinct_target_claims": len(target_ids),
        },
        "repeat_claim_reuse": {
            "cached_published_responses": cached_responses,
            "distinct_cached_claims": len(cached_target_ids),
        },
    }
