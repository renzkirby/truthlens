"""Anonymous read projections for institutionally published fact-checks."""

from .models import OfficialFactCheck
from .organization_publication_query_service import (
    evaluate_publication_lineage_integrity,
)
from .publication_snapshot_schema import (
    EDITORIAL_REVISION_SCHEMA_VERSION,
    FACTUAL_CORRECTION_SCHEMA_VERSION,
    FIRST_PUBLICATION_SCHEMA_VERSION,
    PublicationSnapshotSchemaError,
    validate_publication_snapshot,
)


class PublicPublicationQueryError(Exception):
    pass


class PublicPublicationNotFound(PublicPublicationQueryError):
    pass


SOURCE_ORIGINS = {
    "VERIFIED_EVIDENCE": "DECISION_EVIDENCE",
    "MODERATOR_ADDED": "ORGANIZATION_EDITORIAL",
    "LEGACY_IMPORT": "LEGACY_IMPORT",
}


def _organization_payload(organization):
    return {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
        "logo_url": organization.logo_url if organization.public_logo_enabled else None,
        "organization_type": organization.organization_type,
        "organization_type_label": organization.get_organization_type_display(),
    }


def _validated_payload(fact_check):
    snapshot = fact_check.publication_snapshot
    try:
        return validate_publication_snapshot(
            schema_version=snapshot.schema_version,
            payload=snapshot.payload,
        )
    except PublicationSnapshotSchemaError as error:
        raise PublicPublicationNotFound("Publication not found.") from error


def _revision_kind(fact_check):
    schema_version = fact_check.publication_snapshot.schema_version
    if schema_version == FIRST_PUBLICATION_SCHEMA_VERSION:
        return OfficialFactCheck.RevisionKind.INITIAL
    if schema_version == EDITORIAL_REVISION_SCHEMA_VERSION:
        return OfficialFactCheck.RevisionKind.EDITORIAL_REVISION
    if schema_version == FACTUAL_CORRECTION_SCHEMA_VERSION:
        return OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION
    raise PublicPublicationNotFound("Publication not found.")


def _revision_values(fact_check, payload):
    schema_version = fact_check.publication_snapshot.schema_version
    if schema_version == FIRST_PUBLICATION_SCHEMA_VERSION:
        return None
    if schema_version == EDITORIAL_REVISION_SCHEMA_VERSION:
        revision = payload["revision"]
        return {
            "kind": OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            "reason": revision["revision_reason"],
            "requested_at": revision["revision_requested_at"],
        }
    if schema_version == FACTUAL_CORRECTION_SCHEMA_VERSION:
        correction = payload["correction"]
        return {
            "kind": OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            "reason": correction["correction_reason"],
            "requested_at": correction["correction_requested_at"],
        }
    raise PublicPublicationNotFound("Publication not found.")


def _lineage_payloads(lineage):
    return [(item, _validated_payload(item)) for item in lineage]


def _collection_item(lineage):
    lineage_payloads = _lineage_payloads(lineage)
    current_payload = lineage_payloads[-1][1]
    revision_kinds = [_revision_kind(item) for item, _payload in lineage_payloads]
    return {
        "publication_id": current_payload["fact_check_id"],
        "claim_id": current_payload["claim_id"],
        "decision": {
            "canonical_claim": current_payload["canonical_claim"],
            "verdict": current_payload["verdict"],
        },
        "article": {
            "headline": current_payload["headline"],
            "summary": current_payload["summary"],
            "version": current_payload["article_version"],
            "revision_kind": revision_kinds[-1],
        },
        "published_at": current_payload["published_at"],
        "history": {
            "previous_versions_count": len(lineage_payloads) - 1,
            "has_factual_correction": (
                OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION
                in revision_kinds
            ),
        },
    }


def _source_payload(source):
    selected = source["is_editorially_selected"]
    if selected is True:
        citation_state = "CITED_IN_ARTICLE"
    elif selected is False:
        citation_state = "NOT_CITED_IN_ARTICLE"
    else:
        citation_state = "CITATION_HISTORY_UNAVAILABLE"
    return {
        "url": source["url"],
        "title": source["title"],
        "source_origin": SOURCE_ORIGINS.get(source["source_type"], "UNKNOWN"),
        "citation_state": citation_state,
    }


def _lineage_item(fact_check, payload, current_id):
    revision = _revision_values(fact_check, payload)
    return {
        "publication_id": payload["fact_check_id"],
        "version": payload["article_version"],
        "revision_kind": _revision_kind(fact_check),
        "headline": payload["headline"],
        "canonical_claim": payload["canonical_claim"],
        "verdict": payload["verdict"],
        "published_at": payload["published_at"],
        "history_state": "CURRENT" if fact_check.id == current_id else "SUPERSEDED",
        "revision_reason": revision["reason"] if revision is not None else None,
    }


def _detail_payload(*, organization, selected, current, lineage):
    lineage_payloads = _lineage_payloads(lineage)
    selected_index = next(
        index
        for index, (item, _payload) in enumerate(lineage_payloads)
        if item.id == selected.id
    )
    selected_item, selected_payload = lineage_payloads[selected_index]
    revision = _revision_values(selected_item, selected_payload)
    if revision is not None:
        predecessor, predecessor_payload = lineage_payloads[selected_index - 1]
        revision = {
            **revision,
            "predecessor": {
                "publication_id": predecessor_payload["fact_check_id"],
                "version": predecessor_payload["article_version"],
            },
        }
    return {
        "selected_publication_id": selected_payload["fact_check_id"],
        "current_publication_id": str(current.id),
        "history_state": "CURRENT" if selected.id == current.id else "SUPERSEDED",
        "organization": _organization_payload(organization),
        "claim_id": selected_payload["claim_id"],
        "decision": {
            "canonical_claim": selected_payload["canonical_claim"],
            "verdict": selected_payload["verdict"],
        },
        "article": {
            "headline": selected_payload["headline"],
            "summary": selected_payload["summary"],
            "article_body": selected_payload["article_body"],
            "version": selected_payload["article_version"],
            "revision_kind": _revision_kind(selected_item),
        },
        "published_at": selected_payload["published_at"],
        "revision": revision,
        "sources": [_source_payload(source) for source in selected_payload["sources"]],
        "lineage": [
            _lineage_item(item, payload, current.id)
            for item, payload in lineage_payloads
        ],
    }


def _current_candidates(organization):
    return OfficialFactCheck.objects.filter(
        organization=organization,
        claim__isnull=False,
        adjudication_decision__isnull=False,
        publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
        published_at__isnull=False,
        publication_snapshot__isnull=False,
    ).only("id", "claim_id", "published_at")


def list_public_partner_fact_checks(*, organization, limit=20, offset=0):
    candidates = list(_current_candidates(organization).order_by("-published_at", "id"))
    evaluations = evaluate_publication_lineage_integrity(
        organization=organization,
        current_publications=candidates,
    )
    eligible = [
        evaluations[candidate.id]
        for candidate in candidates
        if evaluations[candidate.id]["lineage_valid"]
        and evaluations[candidate.id]["all_records_sealed"]
    ]
    count = len(eligible)
    page = eligible[offset : offset + limit]
    return {
        "count": count,
        "limit": limit,
        "offset": offset,
        "organization": _organization_payload(organization),
        "results": [
            _collection_item(evaluation["lineage"]) for evaluation in page
        ],
    }


def get_public_partner_fact_check_detail(*, organization, publication_id):
    selected = (
        OfficialFactCheck.objects.filter(
            organization=organization,
            id=publication_id,
            claim__isnull=False,
            adjudication_decision__isnull=False,
            publication_status__in={
                OfficialFactCheck.PublicationStatus.PUBLISHED,
                OfficialFactCheck.PublicationStatus.ARCHIVED,
            },
            published_at__isnull=False,
            publication_snapshot__isnull=False,
        )
        .only("id", "claim_id")
        .first()
    )
    if selected is None:
        raise PublicPublicationNotFound("Publication not found.")

    currents = list(
        _current_candidates(organization).filter(claim_id=selected.claim_id)[:2]
    )
    if len(currents) != 1:
        raise PublicPublicationNotFound("Publication not found.")
    current_stub = currents[0]
    evaluation = evaluate_publication_lineage_integrity(
        organization=organization,
        current_publications=[current_stub],
    )[current_stub.id]
    if not evaluation["lineage_valid"] or not evaluation["all_records_sealed"]:
        raise PublicPublicationNotFound("Publication not found.")

    lineage_by_id = {item.id: item for item in evaluation["lineage"]}
    selected = lineage_by_id.get(selected.id)
    if selected is None:
        raise PublicPublicationNotFound("Publication not found.")
    return _detail_payload(
        organization=organization,
        selected=selected,
        current=evaluation["current"],
        lineage=evaluation["lineage"],
    )
