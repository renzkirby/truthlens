"""Pure validation for prepared factual-correction proposal payloads."""

from datetime import datetime
import re
import uuid
from urllib.parse import urlsplit

from .evidence_snapshot_schema import (
    CURRENT_SCHEMA_VERSION as EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)


CURRENT_SCHEMA_VERSION = 1

PAYLOAD_FIELDS = frozenset(
    {
        "proposal_id",
        "proposal_version",
        "correction_request_id",
        "claim_id",
        "correction_case_id",
        "organization",
        "predecessor",
        "decision",
        "evidence_basis",
        "verification_run",
        "article",
        "sources",
        "approval",
    }
)
IDENTITY_FIELDS = frozenset({"id", "name", "slug"})
ACTOR_FIELDS = frozenset({"id", "username"})
# For editorial sources, editorial_actor is the accountable approving
# adjudicator, not necessarily the person who originally found the URL.
PREDECESSOR_FIELDS = frozenset(
    {
        "decision_id",
        "decision_revision",
        "fact_check_id",
        "fact_check_version",
        "publication_snapshot_id",
        "publication_snapshot_schema_version",
        "published_at",
    }
)
DECISION_FIELDS = frozenset({"verdict", "canonical_claim", "rationale"})
EVIDENCE_BASIS_FIELDS = frozenset({"schema_version", "items"})
EVIDENCE_ITEM_FIELDS = frozenset(
    {"review_event_id", "evidence_case_id", "correction_case_id", "record"}
)
VERIFICATION_RUN_FIELDS = frozenset(
    {
        "id",
        "claim_id",
        "status",
        "pipeline_version",
        "triggered_by_id",
        "started_at",
        "completed_at",
        "created_at",
    }
)
ARTICLE_FIELDS = frozenset({"headline", "summary", "article_body"})
SOURCE_FIELDS = frozenset(
    {"url", "provenance", "evidence", "editorial_actor"}
)
SOURCE_EVIDENCE_FIELDS = frozenset({"evidence_id", "review_event_id"})
APPROVAL_FIELDS = frozenset({"actor", "prepared_at"})

VERDICTS = frozenset({"FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED"})
SOURCE_PROVENANCE = frozenset({"CORRECTION_REVIEW_EVIDENCE", "EDITORIAL"})
_AUTH_USER_ID_PATTERN = re.compile(r"[1-9][0-9]*\Z")


class FactualCorrectionProposalSchemaError(ValueError):
    """Raised when a prepared correction proposal payload is malformed."""


def _fail(message):
    raise FactualCorrectionProposalSchemaError(message)


def _dict(value, fields, name):
    if not isinstance(value, dict) or set(value) != fields:
        _fail(f"The prepared proposal has an invalid {name} field set.")
    return value


def _uuid(value, name):
    if not isinstance(value, str):
        _fail(f"The prepared proposal has an invalid {name}.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise FactualCorrectionProposalSchemaError(
            f"The prepared proposal has an invalid {name}."
        ) from error
    if str(parsed) != value:
        _fail(f"The prepared proposal has an invalid {name}.")
    return value


def _positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(f"The prepared proposal has an invalid {name}.")
    return value


def _timestamp(value, name, *, nullable=False):
    if value is None and nullable:
        return value
    if not isinstance(value, str) or "T" not in value:
        _fail(f"The prepared proposal has an invalid {name}.")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise FactualCorrectionProposalSchemaError(
            f"The prepared proposal has an invalid {name}."
        ) from error
    return value


def _nonblank(value, name, *, max_length=None):
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or (max_length is not None and len(value) > max_length)
    ):
        _fail(f"The prepared proposal has invalid {name}.")
    return value


def _url(value):
    value = _nonblank(value, "source URL", max_length=2000)
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as error:
        raise FactualCorrectionProposalSchemaError(
            "The prepared proposal has an invalid source URL."
        ) from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or any(character.isspace() for character in value)
    ):
        _fail("The prepared proposal has an invalid source URL.")
    return value


def _actor(value, name):
    actor = _dict(value, ACTOR_FIELDS, name)
    if (
        not isinstance(actor["id"], str)
        or _AUTH_USER_ID_PATTERN.fullmatch(actor["id"]) is None
    ):
        _fail(f"The prepared proposal has an invalid {name} ID.")
    _nonblank(actor["username"], f"{name} username")
    return actor


def validate_factual_correction_proposal(*, schema_version, payload):
    """Validate and return one supported, fully sealed proposal payload."""

    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != CURRENT_SCHEMA_VERSION
    ):
        _fail("The prepared proposal schema is not supported.")
    payload = _dict(payload, PAYLOAD_FIELDS, "payload")

    proposal_id = _uuid(payload["proposal_id"], "proposal ID")
    request_id = _uuid(payload["correction_request_id"], "request ID")
    claim_id = _uuid(payload["claim_id"], "claim ID")
    correction_case_id = _uuid(payload["correction_case_id"], "correction case ID")
    _positive_integer(payload["proposal_version"], "proposal version")

    organization = _dict(payload["organization"], IDENTITY_FIELDS, "organization")
    _uuid(organization["id"], "organization ID")
    _nonblank(organization["name"], "organization name")
    _nonblank(organization["slug"], "organization slug")

    predecessor = _dict(payload["predecessor"], PREDECESSOR_FIELDS, "predecessor")
    for field in ("decision_id", "fact_check_id", "publication_snapshot_id"):
        _uuid(predecessor[field], f"predecessor {field}")
    _positive_integer(predecessor["decision_revision"], "decision revision")
    _positive_integer(predecessor["fact_check_version"], "fact-check version")
    _positive_integer(
        predecessor["publication_snapshot_schema_version"],
        "publication snapshot schema version",
    )
    _timestamp(predecessor["published_at"], "predecessor publication timestamp")

    decision = _dict(payload["decision"], DECISION_FIELDS, "decision")
    if not isinstance(decision["verdict"], str) or decision["verdict"] not in VERDICTS:
        _fail("The prepared proposal has an invalid verdict.")
    _nonblank(decision["canonical_claim"], "canonical claim")
    _nonblank(decision["rationale"], "rationale")

    article = _dict(payload["article"], ARTICLE_FIELDS, "article")
    _nonblank(article["headline"], "headline", max_length=300)
    _nonblank(article["summary"], "summary")
    _nonblank(article["article_body"], "article body")

    basis = _dict(payload["evidence_basis"], EVIDENCE_BASIS_FIELDS, "evidence basis")
    if (
        isinstance(basis["schema_version"], bool)
        or not isinstance(basis["schema_version"], int)
        or basis["schema_version"] != EVIDENCE_SNAPSHOT_SCHEMA_VERSION
    ):
        _fail("The prepared proposal has an unsupported evidence schema.")
    if not isinstance(basis["items"], list) or not basis["items"]:
        _fail("The prepared proposal must contain reviewed evidence.")
    evidence_ids = set()
    event_records = {}
    for item in basis["items"]:
        item = _dict(item, EVIDENCE_ITEM_FIELDS, "evidence item")
        event_id = _uuid(item["review_event_id"], "review event ID")
        evidence_case_id = _uuid(item["evidence_case_id"], "evidence case ID")
        if item["correction_case_id"] != correction_case_id:
            _fail("The prepared proposal has mismatched correction-case provenance.")
        try:
            records = validate_evidence_snapshot(
                schema_version=basis["schema_version"],
                evidence_records=[item["record"]],
            )
        except (EvidenceSnapshotSchemaError, TypeError) as error:
            raise FactualCorrectionProposalSchemaError(
                "The prepared proposal contains an invalid evidence record."
            ) from error
        evidence_id = records[0]["id"]
        if evidence_id in evidence_ids or event_id in event_records:
            _fail("The prepared proposal contains duplicate evidence provenance.")
        evidence_ids.add(evidence_id)
        event_records[event_id] = records[0]
        if not evidence_case_id:
            _fail("The prepared proposal has invalid Evidence-case provenance.")

    sources = payload["sources"]
    if not isinstance(sources, list) or not sources:
        _fail("The prepared proposal must contain at least one source.")
    source_urls = set()
    editorial_actors = []
    for source in sources:
        source = _dict(source, SOURCE_FIELDS, "source")
        url = _url(source["url"])
        if url in source_urls:
            _fail("The prepared proposal contains a duplicate source URL.")
        source_urls.add(url)
        if (
            not isinstance(source["provenance"], str)
            or source["provenance"] not in SOURCE_PROVENANCE
        ):
            _fail("The prepared proposal has invalid source provenance.")
        lineage = source["evidence"]
        if not isinstance(lineage, list):
            _fail("The prepared proposal has invalid source lineage.")
        if source["provenance"] == "EDITORIAL" and lineage:
            _fail("An editorial source cannot claim evidence lineage.")
        if source["provenance"] == "CORRECTION_REVIEW_EVIDENCE" and not lineage:
            _fail("A reviewed-evidence source must retain its lineage.")
        if source["provenance"] == "EDITORIAL":
            editorial_actors.append(
                _actor(source["editorial_actor"], "editorial source actor")
            )
        elif source["editorial_actor"] is not None:
            _fail("A reviewed-evidence source cannot claim editorial attribution.")
        seen_lineage = set()
        for link in lineage:
            link = _dict(link, SOURCE_EVIDENCE_FIELDS, "source lineage")
            evidence_id = _uuid(link["evidence_id"], "source evidence ID")
            event_id = _uuid(link["review_event_id"], "source review event ID")
            pair = (evidence_id, event_id)
            if (
                pair in seen_lineage
                or evidence_id not in evidence_ids
                or event_id not in event_records
                or event_records[event_id]["id"] != evidence_id
                or event_records[event_id]["evidence_status"] != "VERIFIED"
                or event_records[event_id]["evidence_url"] != url
            ):
                _fail("The prepared proposal has invalid source lineage.")
            seen_lineage.add(pair)

    verification_run = payload["verification_run"]
    if verification_run is not None:
        verification_run = _dict(
            verification_run,
            VERIFICATION_RUN_FIELDS,
            "verification run",
        )
        _uuid(verification_run["id"], "verification-run ID")
        if verification_run["claim_id"] != claim_id:
            _fail("The prepared proposal has mismatched verification-run provenance.")
        if verification_run["status"] != "COMPLETED":
            _fail("The prepared proposal has a non-completed verification run.")
        _nonblank(verification_run["pipeline_version"], "pipeline version")
        triggered_by_id = verification_run["triggered_by_id"]
        if triggered_by_id is not None and (
            not isinstance(triggered_by_id, str)
            or _AUTH_USER_ID_PATTERN.fullmatch(triggered_by_id) is None
        ):
            _fail("The prepared proposal has an invalid verification-run actor.")
        _timestamp(verification_run["started_at"], "run start timestamp", nullable=True)
        _timestamp(verification_run["completed_at"], "run completion timestamp")
        _timestamp(verification_run["created_at"], "run creation timestamp")

    approval = _dict(payload["approval"], APPROVAL_FIELDS, "approval")
    approval_actor = _actor(approval["actor"], "approving actor")
    if any(actor != approval_actor for actor in editorial_actors):
        _fail("Editorial sources do not match the approving actor attribution.")
    _timestamp(approval["prepared_at"], "preparation timestamp")

    # Keep these locals deliberately exercised by validation and visible to
    # readers auditing the identity boundary.
    if not proposal_id or not request_id:
        _fail("The prepared proposal has invalid durable identities.")
    return payload
