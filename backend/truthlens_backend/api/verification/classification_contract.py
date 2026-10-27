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


def validate_classification_response(raw, claim_text):
    """Validate the complete classification JSON before accepting any LLM.

    This is a *structural and quoted-input* safety gate, not a substitute
    for empirical classification accuracy review before enforce mode.
    """
    if not isinstance(raw, str) or not isinstance(claim_text, str):
        return False
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, dict) or set(payload) != {
        "decision", "primary_subject", "domains",
    }:
        return False
    decision = payload["decision"]
    primary_subject = payload["primary_subject"]
    domains = payload["domains"]
    if not isinstance(domains, list):
        return False
    if decision == "ABSTAIN":
        return primary_subject is None and domains == []
    if (
        decision != "CLASSIFY"
        or not isinstance(primary_subject, str)
        or primary_subject not in DOMAIN_CODES
        or not (1 <= len(domains) <= MAX_CLASSIFICATION_DOMAINS)
    ):
        return False
    seen = set()
    for domain in domains:
        if not isinstance(domain, dict) or set(domain) != {"code", "evidence"}:
            return False
        code = domain["code"]
        evidence = domain["evidence"]
        if not isinstance(code, str) or code not in DOMAIN_CODES or code in seen:
            return False
        if (
            not isinstance(evidence, str)
            or len(evidence.strip()) < MIN_QUOTE_CHARS
            or evidence.strip().casefold() not in claim_text.casefold()
        ):
            return False
        seen.add(code)
    return primary_subject in seen
