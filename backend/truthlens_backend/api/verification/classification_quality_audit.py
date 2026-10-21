"""Pure, no-network subject-domain quality audit over separately reviewed cases.

This module NEVER invokes an LLM, Django ORM, Celery, or a remote service.
Draft reference labels are not ground truth; only reviewer-approved cases
contribute to accuracy and potential authorization-leakage metrics.
"""
import json
import re
from pathlib import Path
from types import SimpleNamespace

from .classification_contract import validate_classification_response
from ..verification_domain_policy import DOMAIN_CODES, eligibility_reason


CORPUS_VERSION = 1
MAX_CASES = 120
MAX_FILE_BYTES = 512_000
CASE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
TAGS = frozenset({
    "single_domain", "cross_domain", "ambiguous", "location_only",
    "prompt_injection", "weak_evidence", "contradictory", "out_of_scope",
})


class ClassificationAuditError(ValueError):
    """Invalid local audit input; never surface raw claim/prediction contents."""


def _load_json(path):
    try:
        location = Path(path)
        if not location.is_file() or location.stat().st_size > MAX_FILE_BYTES:
            raise ClassificationAuditError("Missing or oversized local JSON input.")
        with location.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ClassificationAuditError("Invalid local JSON input.") from None


def _domains(domains, decision):
    if decision == "ABSTAIN":
        return type(domains) is list and domains == []
    return (
        decision == "CLASSIFY"
        and type(domains) is list
        and 1 <= len(domains) <= 3
        and all(type(domain) is str and domain in DOMAIN_CODES
                for domain in domains)
        and len(domains) == len(set(domains))
    )


def load_classification_corpus(path):
    """Require explicit human approval and review metadata for scored cases."""
    data = _load_json(path)
    if (not isinstance(data, dict)
            or set(data) != {"schema_version", "cases"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != CORPUS_VERSION
            or type(data["cases"]) is not list
            or not 1 <= len(data["cases"]) <= MAX_CASES):
        raise ClassificationAuditError("Invalid classification corpus schema.")
    output = []
    seen = set()
    for item in data["cases"]:
        if not isinstance(item, dict) or set(item) != {
            "id", "claim_text", "tags", "draft_expected", "review",
        }:
            raise ClassificationAuditError("Invalid corpus case fields.")
        cid, claim, tags = item["id"], item["claim_text"], item["tags"]
        if (type(cid) is not str or not CASE_ID_RE.fullmatch(cid)
                or cid in seen or type(claim) is not str
                or not 20 <= len(claim.strip()) <= 2400
                or type(tags) is not list or not tags
                or any(type(t) is not str or t not in TAGS for t in tags)
                or len(tags) != len(set(tags))):
            raise ClassificationAuditError("Invalid or duplicate corpus case.")
        seen.add(cid)
        expected = item["draft_expected"]
        if (not isinstance(expected, dict)
                or set(expected) != {"decision", "domains"}
                or not _domains(expected["domains"], expected["decision"])):
            raise ClassificationAuditError("Invalid draft classification reference.")
        review = item["review"]
        if (not isinstance(review, dict)
                or set(review) != {"status", "reviewer", "notes"}
                or review["status"] not in ("PENDING", "APPROVED")
                or type(review["reviewer"]) is not str
                or type(review["notes"]) is not str
                or len(review["reviewer"]) > 120
                or len(review["notes"]) > 2000):
            raise ClassificationAuditError("Invalid classification review metadata.")
        if review["status"] == "APPROVED" and not (
            review["reviewer"].strip() and review["notes"].strip()
        ):
            raise ClassificationAuditError(
                "Approved cases require reviewer identity and notes.",
            )
        if review["status"] == "PENDING" and review["reviewer"].strip():
            # A draft may contain review-in-progress notes but no attestation.
            raise ClassificationAuditError("Pending cases cannot name an approver.")
        output.append(item)
    return output


def load_classification_predictions(path, known_ids):
    """Consume captured raw model responses; do not infer provider accuracy."""
    data = _load_json(path)
    if (not isinstance(data, dict)
            or set(data) != {"schema_version", "predictions"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != CORPUS_VERSION
            or type(data["predictions"]) is not list
            or len(data["predictions"]) > MAX_CASES):
        raise ClassificationAuditError("Invalid prediction file schema.")
    output = {}
    for item in data["predictions"]:
        if (not isinstance(item, dict)
                or set(item) != {"case_id", "raw_response"}
                or type(item["case_id"]) is not str
                or item["case_id"] not in known_ids
                or item["case_id"] in output
                or type(item["raw_response"]) is not str
                or len(item["raw_response"]) > 8000):
            raise ClassificationAuditError("Invalid or duplicate prediction case.")
        output[item["case_id"]] = item["raw_response"]
    return output


def summarize_classification_corpus(cases):
    coverage = {key: 0 for key in sorted(TAGS)}
    supported = {code: 0 for code in sorted(DOMAIN_CODES)}
    approved = 0
    for item in cases:
        for tag in item["tags"]:
            coverage[tag] += 1
        for code in item["draft_expected"]["domains"]:
            supported[code] += 1
        approved += item["review"]["status"] == "APPROVED"
    return {
        "cases": len(cases),
        "approved": approved,
        "pending": len(cases) - approved,
        "tag_counts": coverage,
        "draft_domain_counts": supported,
    }


def score_classification_predictions(cases, predictions):
    """Descriptive, not an automatic enforcement/rollout approval.

    A potential scope leak exists when the model CLASSIFY domains would
    authorize at least one specialization set that the reviewed reference
    would not. The predicted set itself is the counterexample whenever
    a reviewer-required domain has been omitted.
    """
    approved = [item for item in cases if item["review"]["status"] == "APPROVED"]
    counts = {
        "approved": len(approved), "predicted": 0, "missing": 0,
        "invalid_json_or_quotes": 0, "exact_matches": 0,
        "safe_abstentions": 0, "wrong_domains": 0,
        "overclassified_abstentions": 0, "missed_classifications": 0,
        "potential_scope_leaks": 0,
    }
    ids_by_problem = {key: [] for key in (
        "missing", "invalid_json_or_quotes", "wrong_domains",
        "overclassified_abstentions", "missed_classifications",
        "potential_scope_leaks",
    )}
    for item in approved:
        cid = item["id"]
        raw = predictions.get(cid)
        if raw is None:
            counts["missing"] += 1
            ids_by_problem["missing"].append(cid)
            continue
        counts["predicted"] += 1
        if not validate_classification_response(raw, item["claim_text"]):
            counts["invalid_json_or_quotes"] += 1
            ids_by_problem["invalid_json_or_quotes"].append(cid)
            continue
        parsed = json.loads(raw)
        predicted = sorted(tag["code"] for tag in parsed["domains"])
        reference = item["draft_expected"]
        expected = sorted(reference["domains"])
        if (parsed["decision"] == reference["decision"]
                and predicted == expected):
            counts["exact_matches"] += 1
            if parsed["decision"] == "ABSTAIN":
                counts["safe_abstentions"] += 1
            continue
        if parsed["decision"] == "ABSTAIN":
            counts["missed_classifications"] += 1
            ids_by_problem["missed_classifications"].append(cid)
            continue
        if reference["decision"] == "ABSTAIN":
            counts["overclassified_abstentions"] += 1
            ids_by_problem["overclassified_abstentions"].append(cid)
        else:
            counts["wrong_domains"] += 1
            ids_by_problem["wrong_domains"].append(cid)

        # Diagnostic only: the candidate must never substitute for an
        # authoritative classification in actual partner permission checks.
        specialization = sorted(predicted)
        candidate_allowed = eligibility_reason(
            classification=SimpleNamespace(domains=predicted),
            specializations=specialization,
        ) is None
        reviewer_allows = (
            reference["decision"] == "CLASSIFY"
            and eligibility_reason(
                classification=SimpleNamespace(domains=expected),
                specializations=specialization,
            ) is None
        )
        if candidate_allowed and not reviewer_allows:
            counts["potential_scope_leaks"] += 1
            ids_by_problem["potential_scope_leaks"].append(cid)
    counts["coverage_complete"] = counts["missing"] == 0 and bool(approved)
    counts["exact_match_rate"] = (
        round(counts["exact_matches"] / counts["approved"], 4)
        if counts["approved"] and counts["coverage_complete"] else None
    )
    counts["problems_by_case_id"] = ids_by_problem
    counts["eligible_for_automatic_enforcement"] = False
    return counts
