"""Pure validation for sealed publication snapshot payloads."""

from datetime import datetime
import re
import uuid


FIRST_PUBLICATION_SCHEMA_VERSION = 1
EDITORIAL_REVISION_SCHEMA_VERSION = 2
CURRENT_SCHEMA_VERSION = EDITORIAL_REVISION_SCHEMA_VERSION

BASE_PAYLOAD_FIELDS = frozenset(
    {
        "claim_id",
        "fact_check_id",
        "decision_id",
        "decision_evidence_snapshot_id",
        "organization",
        "article_version",
        "published_at",
        "canonical_claim",
        "verdict",
        "headline",
        "summary",
        "article_body",
        "drafted_by",
        "drafted_at",
        "submitted_for_review_at",
        "reviewed_by",
        "reviewed_at",
        "published_by",
        "sources",
    }
)
V1_PAYLOAD_FIELDS = BASE_PAYLOAD_FIELDS
V2_PAYLOAD_FIELDS = BASE_PAYLOAD_FIELDS | {"revision"}
ORGANIZATION_FIELDS = frozenset({"id", "name", "slug"})
USER_FIELDS = frozenset({"id", "username"})
SOURCE_FIELDS = frozenset(
    {
        "id",
        "url",
        "title",
        "source_type",
        "is_editorially_selected",
        "added_by",
        "created_at",
        "legacy_evidence_submission_id",
        "lineage",
    }
)
LINEAGE_FIELDS = frozenset(
    {"id", "decision_evidence_snapshot_id", "captured_evidence_id"}
)
REVISION_FIELDS = frozenset(
    {
        "revision_kind",
        "supersedes_fact_check_id",
        "supersedes_publication_snapshot_id",
        "predecessor_article_version",
        "predecessor_published_at",
        "revision_reason",
        "revision_requested_by",
        "revision_requested_at",
    }
)

SUPPORTED_VERDICTS = frozenset(
    {"FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED"}
)
SUPPORTED_SOURCE_TYPES = frozenset(
    {"VERIFIED_EVIDENCE", "MODERATOR_ADDED", "LEGACY_IMPORT"}
)

_AUTH_USER_ID_PATTERN = re.compile(r"[1-9][0-9]*\Z")


class PublicationSnapshotSchemaError(ValueError):
    """Raised when a sealed publication payload is malformed."""


def _invalid(message):
    raise PublicationSnapshotSchemaError(message)


def _validate_uuid(value, field):
    if not isinstance(value, str):
        _invalid(f"{field} must be a UUID string.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise PublicationSnapshotSchemaError(
            f"{field} must be a UUID string."
        ) from error
    if str(parsed) != value:
        _invalid(f"{field} must use canonical UUID serialization.")


def _validate_timestamp(value, field, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or "T" not in value:
        _invalid(f"{field} must be an ISO-8601 datetime or null.")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise PublicationSnapshotSchemaError(
            f"{field} must be an ISO-8601 datetime or null."
        ) from error


def _validate_user(value, field):
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != USER_FIELDS:
        _invalid(f"{field} has an invalid user identity.")
    if (
        not isinstance(value["id"], str)
        or _AUTH_USER_ID_PATTERN.fullmatch(value["id"]) is None
        or not isinstance(value["username"], str)
    ):
        _invalid(f"{field} has an invalid user identity.")


def _validate_base_payload(payload, *, expected_fields):
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        _invalid("The publication snapshot has an invalid field set.")

    for field in (
        "claim_id",
        "fact_check_id",
        "decision_id",
        "decision_evidence_snapshot_id",
    ):
        _validate_uuid(payload[field], field)

    organization = payload["organization"]
    if not isinstance(organization, dict) or set(organization) != ORGANIZATION_FIELDS:
        _invalid("organization has an invalid identity.")
    _validate_uuid(organization["id"], "organization.id")
    if not isinstance(organization["name"], str) or not isinstance(
        organization["slug"], str
    ):
        _invalid("organization has an invalid identity.")

    if (
        isinstance(payload["article_version"], bool)
        or not isinstance(payload["article_version"], int)
        or payload["article_version"] < 1
    ):
        _invalid("article_version must be a positive integer.")

    for field in ("canonical_claim", "headline", "summary", "article_body"):
        if not isinstance(payload[field], str):
            _invalid(f"{field} must be a string.")
    if (
        not isinstance(payload["verdict"], str)
        or payload["verdict"] not in SUPPORTED_VERDICTS
    ):
        _invalid("verdict is not supported by this snapshot schema.")

    _validate_user(payload["drafted_by"], "drafted_by")
    _validate_user(payload["reviewed_by"], "reviewed_by")
    _validate_user(payload["published_by"], "published_by")
    _validate_timestamp(payload["published_at"], "published_at")
    _validate_timestamp(payload["drafted_at"], "drafted_at", nullable=True)
    _validate_timestamp(
        payload["submitted_for_review_at"],
        "submitted_for_review_at",
        nullable=True,
    )
    _validate_timestamp(payload["reviewed_at"], "reviewed_at", nullable=True)

    sources = payload["sources"]
    if not isinstance(sources, list) or not sources:
        _invalid("sources must be a non-empty list.")
    source_ids = set()
    lineage_ids = set()
    for source_index, source in enumerate(sources):
        prefix = f"sources[{source_index}]"
        if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
            _invalid(f"{prefix} has an invalid field set.")
        _validate_uuid(source["id"], f"{prefix}.id")
        if source["id"] in source_ids:
            _invalid(f"{prefix}.id is duplicated.")
        source_ids.add(source["id"])
        if not isinstance(source["url"], str):
            _invalid(f"{prefix}.url must be a string.")
        if source["title"] is not None and not isinstance(source["title"], str):
            _invalid(f"{prefix}.title must be a string or null.")
        if (
            not isinstance(source["source_type"], str)
            or source["source_type"] not in SUPPORTED_SOURCE_TYPES
        ):
            _invalid(f"{prefix}.source_type is not supported.")
        if source["is_editorially_selected"] is not None and not isinstance(
            source["is_editorially_selected"], bool
        ):
            _invalid(f"{prefix}.is_editorially_selected is invalid.")
        _validate_user(source["added_by"], f"{prefix}.added_by")
        _validate_timestamp(source["created_at"], f"{prefix}.created_at")
        legacy_id = source["legacy_evidence_submission_id"]
        if legacy_id is not None:
            _validate_uuid(legacy_id, f"{prefix}.legacy_evidence_submission_id")

        lineage = source["lineage"]
        if not isinstance(lineage, list):
            _invalid(f"{prefix}.lineage must be a list.")
        captured_ids = set()
        for link_index, link in enumerate(lineage):
            link_prefix = f"{prefix}.lineage[{link_index}]"
            if not isinstance(link, dict) or set(link) != LINEAGE_FIELDS:
                _invalid(f"{link_prefix} has an invalid field set.")
            for field in LINEAGE_FIELDS:
                _validate_uuid(link[field], f"{link_prefix}.{field}")
            if link["id"] in lineage_ids:
                _invalid(f"{link_prefix}.id is duplicated.")
            lineage_ids.add(link["id"])
            if link["captured_evidence_id"] in captured_ids:
                _invalid(f"{link_prefix}.captured_evidence_id is duplicated.")
            captured_ids.add(link["captured_evidence_id"])


def _validate_v1(payload):
    _validate_base_payload(payload, expected_fields=V1_PAYLOAD_FIELDS)


def _validate_v2(payload):
    _validate_base_payload(payload, expected_fields=V2_PAYLOAD_FIELDS)

    revision = payload["revision"]
    if not isinstance(revision, dict) or set(revision) != REVISION_FIELDS:
        _invalid("revision has an invalid field set.")
    if revision["revision_kind"] != "EDITORIAL_REVISION":
        _invalid("revision.revision_kind is not supported.")
    _validate_uuid(
        revision["supersedes_fact_check_id"],
        "revision.supersedes_fact_check_id",
    )
    _validate_uuid(
        revision["supersedes_publication_snapshot_id"],
        "revision.supersedes_publication_snapshot_id",
    )
    predecessor_version = revision["predecessor_article_version"]
    if (
        isinstance(predecessor_version, bool)
        or not isinstance(predecessor_version, int)
        or predecessor_version < 1
    ):
        _invalid("revision.predecessor_article_version must be positive.")
    if payload["article_version"] <= predecessor_version:
        _invalid("article_version must follow the predecessor version.")
    if payload["fact_check_id"] == revision["supersedes_fact_check_id"]:
        _invalid("An editorial revision cannot supersede itself.")
    _validate_timestamp(
        revision["predecessor_published_at"],
        "revision.predecessor_published_at",
    )
    reason = revision["revision_reason"]
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or reason != reason.strip()
        or len(reason) > 2000
    ):
        _invalid("revision.revision_reason is invalid.")
    if revision["revision_requested_by"] is None:
        _invalid("revision.revision_requested_by is required.")
    _validate_user(
        revision["revision_requested_by"],
        "revision.revision_requested_by",
    )
    _validate_timestamp(
        revision["revision_requested_at"],
        "revision.revision_requested_at",
    )


def validate_publication_snapshot(*, schema_version, payload):
    """Validate a sealed publication payload without database access."""

    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        _invalid("The publication snapshot schema is not supported.")

    validators = {
        FIRST_PUBLICATION_SCHEMA_VERSION: _validate_v1,
        EDITORIAL_REVISION_SCHEMA_VERSION: _validate_v2,
    }
    validator = validators.get(schema_version)
    if validator is None:
        _invalid("The publication snapshot schema is not supported.")
    validator(payload)
    return payload
