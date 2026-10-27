"""Strict, provider-independent subject-classification response contract.

No verdict, credibility, geographic jurisdiction, or source authority can be
inferred here. Domain evidence must quote the exact persisted claim text.
An ABSTAIN is a valid result, not a provider failure.
"""
import json

from ..verification_domain_policy import DOMAIN_CODES


CLASSIFICATION_OPERATION = "investigation_classification"
MAX_CLASSIFICATION_DOMAINS = 3
MIN_QUOTE_CHARS = 4


def classification_response_error(raw, claim_text):
    """Return a bounded reason code for an invalid classifier response.

    The raw model response is intentionally not persisted. These structural
    reason codes make provider/prompt failures diagnosable without weakening
    the strict classification boundary.
    """
    if not isinstance(raw, str) or not isinstance(claim_text, str):
        return "INVALID_INPUT"
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return "MALFORMED_JSON"
    if not isinstance(payload, dict) or set(payload) != {
        "decision", "primary_subject", "domains",
    }:
        return "INVALID_TOP_LEVEL_KEYS"

    decision = payload["decision"]
    primary_subject = payload["primary_subject"]
    domains = payload["domains"]
    if not isinstance(domains, list):
        return "INVALID_DOMAINS_TYPE"
    if decision == "ABSTAIN":
        return "" if primary_subject is None and domains == [] else "INVALID_ABSTAIN_SHAPE"
    if decision != "CLASSIFY":
        return "INVALID_DECISION"
    if (
        not isinstance(primary_subject, str)
        or primary_subject not in DOMAIN_CODES
    ):
        return "INVALID_PRIMARY_SUBJECT"
    if not domains:
        return "EMPTY_DOMAINS"

    seen = set()
    for domain in domains:
        if not isinstance(domain, dict) or set(domain) != {"code", "evidence"}:
            return "INVALID_DOMAIN_OBJECT"
        code = domain["code"]
        evidence = domain["evidence"]
        if not isinstance(code, str) or code not in DOMAIN_CODES:
            return "UNKNOWN_DOMAIN"
        if code in seen:
            return "DUPLICATE_DOMAIN"
        if (
            not isinstance(evidence, str)
            or len(evidence.strip()) < MIN_QUOTE_CHARS
            or evidence.strip().casefold() not in claim_text.casefold()
        ):
            return "INVALID_EVIDENCE_QUOTE"
        seen.add(code)

    if len(domains) > MAX_CLASSIFICATION_DOMAINS:
        return "TOO_MANY_DOMAINS"
    if primary_subject not in seen:
        return "PRIMARY_NOT_IN_DOMAINS"
    return ""


def validate_classification_response(raw, claim_text):
    """Validate the complete classification JSON before accepting any LLM.

    This is a *structural and quoted-input* safety gate, not a substitute
    for empirical classification accuracy review before enforce mode.
    """
    return classification_response_error(raw, claim_text) == ""
