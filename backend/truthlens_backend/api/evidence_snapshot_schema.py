"""Pure validation for decision-time evidence snapshot payloads."""

from datetime import datetime
import re
import uuid


CURRENT_SCHEMA_VERSION = 1

EVIDENCE_RECORD_FIELDS = frozenset(
    {
        "id",
        "thread_id",
        "evidence_status",
        "evidence_type",
        "evidence_caption",
        "evidence_url",
        "contributor_id",
        "reviewer_id",
        "submitted_at",
        "reviewed_at",
        "moderator_notes",
        "rejection_reason",
    }
)

REVIEWED_EVIDENCE_STATUSES = frozenset({"VERIFIED", "REJECTED"})

_NULLABLE_TEXT_FIELDS = (
    "evidence_type",
    "evidence_caption",
    "evidence_url",
    "moderator_notes",
    "rejection_reason",
)
_AUTH_USER_ID_PATTERN = re.compile(r"[1-9][0-9]*\Z")


class EvidenceSnapshotSchemaError(ValueError):
    """Raised when a decision-time evidence snapshot is malformed."""


def _record_error(index, message):
    return EvidenceSnapshotSchemaError(
        f"Evidence snapshot record {index} {message}"
    )


def _validate_uuid(value, *, index, field):
    if not isinstance(value, str):
        raise _record_error(index, f"has an invalid {field}.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise _record_error(index, f"has an invalid {field}.") from error
    if str(parsed) != value:
        raise _record_error(index, f"has an invalid {field}.")
    return parsed


def _validate_auth_user_id(value, *, index, field, nullable):
    if value is None and nullable:
        return
    if (
        not isinstance(value, str)
        or _AUTH_USER_ID_PATTERN.fullmatch(value) is None
    ):
        raise _record_error(index, f"has an invalid {field}.")


def _validate_timestamp(value, *, index, field, nullable):
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise _record_error(index, f"has an invalid {field}.")
    if "T" not in value:
        raise _record_error(index, f"has an invalid {field}.")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise _record_error(index, f"has an invalid {field}.") from error


def validate_evidence_snapshot(*, schema_version, evidence_records):
    """Validate and return a supported decision evidence record list.

    This function deliberately performs no database access. Invalid or missing
    evidence URLs are valid recorded values; source inclusion is a separate
    publication concern.
    """

    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != CURRENT_SCHEMA_VERSION
    ):
        raise EvidenceSnapshotSchemaError(
            "The evidence snapshot schema is not supported."
        )
    if not isinstance(evidence_records, list) or not evidence_records:
        raise EvidenceSnapshotSchemaError(
            "The evidence snapshot must contain evidence records."
        )

    evidence_ids = set()
    for index, record in enumerate(evidence_records):
        if (
            not isinstance(record, dict)
            or set(record) != EVIDENCE_RECORD_FIELDS
        ):
            raise _record_error(index, "has an invalid field set.")

        evidence_id = _validate_uuid(
            record["id"],
            index=index,
            field="evidence ID",
        )
        if evidence_id in evidence_ids:
            raise _record_error(index, "duplicates an evidence ID.")
        evidence_ids.add(evidence_id)

        _validate_uuid(
            record["thread_id"],
            index=index,
            field="thread ID",
        )
        _validate_auth_user_id(
            record["contributor_id"],
            index=index,
            field="contributor ID",
            nullable=False,
        )
        _validate_auth_user_id(
            record["reviewer_id"],
            index=index,
            field="reviewer ID",
            nullable=True,
        )

        if (
            not isinstance(record["evidence_status"], str)
            or record["evidence_status"] not in REVIEWED_EVIDENCE_STATUSES
        ):
            raise _record_error(index, "has an unsupported evidence status.")

        for field in _NULLABLE_TEXT_FIELDS:
            value = record[field]
            if value is not None and not isinstance(value, str):
                raise _record_error(index, f"has an invalid {field}.")

        _validate_timestamp(
            record["submitted_at"],
            index=index,
            field="submission timestamp",
            nullable=True,
        )
        _validate_timestamp(
            record["reviewed_at"],
            index=index,
            field="review timestamp",
            nullable=True,
        )

    return evidence_records
