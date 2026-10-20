"""Auditable, non-production claim corpus and reviewer approval requirements."""
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ValidationError


CORPUS_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    / "realworld_verification_cases.json"
)
VERDICTS = frozenset({"FACT", "FAKE", "MISLEADING", "UNVERIFIED", "SATIRE"})
DOMAINS = frozenset({
    "CIVICS", "ELECTIONS", "LAW", "HEALTH", "SCIENCE", "TECHNOLOGY",
    "EDUCATION", "ECONOMY", "ENVIRONMENT", "DISASTERS", "SPORTS", "CULTURE",
})


def load_corpus(path=CORPUS_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not 20 <= len(data) <= 40:
        raise ValidationError("Corpus must contain 20-40 cases.")
    unique_ids = set()
    for case in data:
        if not isinstance(case, dict):
            raise ValidationError("Invalid case record.")
        required = {
            "id", "domain", "language", "claim", "evidence_snapshot",
            "sources", "as_of", "proposed_verdict", "review", "public_only",
        }
        if not required.issubset(case) or any(not case[k] for k in (
            "id", "claim", "evidence_snapshot", "sources",
        )):
            raise ValidationError("Incomplete source-linked case.")
        if case["id"] in unique_ids or not isinstance(case["id"], str):
            raise ValidationError("Duplicate or malformed case ID.")
        unique_ids.add(case["id"])
        if case["domain"] not in DOMAINS or case["language"] not in {"en", "fil"}:
            raise ValidationError("Unknown claim domain or language.")
        if case["proposed_verdict"] not in VERDICTS or case["public_only"] is not True:
            raise ValidationError("Invalid proposed label or nonpublic case.")
        date.fromisoformat(case["as_of"])
        if not isinstance(case["sources"], list):
            raise ValidationError("Evidence source list must be an array.")
        for source in case["sources"]:
            if not isinstance(source, dict) or not all(
                source.get(k) for k in ("title", "url", "source_date")
            ):
                raise ValidationError("Missing source provenance.")
            parsed = urlparse(source["url"])
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValidationError("Provenance must use HTTPS sources.")
            date.fromisoformat(source["source_date"])
        review = case["review"]
        if not isinstance(review, dict) or review.get("status") not in {
            "PENDING", "APPROVED", "REJECTED",
        }:
            raise ValidationError("Invalid review state.")
    return data


def reviewed_gold_verdict(case):
    """Only independent, explicit reviewer approval defines a gold label."""
    review = case["review"]
    if review["status"] != "APPROVED":
        return None
    reviewer = review.get("reviewer")
    approved_verdict = review.get("approved_verdict")
    rationale = review.get("rationale")
    reviewed_at = review.get("reviewed_at")
    if (
        not isinstance(reviewer, str) or len(reviewer.strip()) < 3
        or not isinstance(rationale, str) or len(rationale.strip()) < 20
        or approved_verdict not in VERDICTS
        or not isinstance(reviewed_at, str)
    ):
        raise ValidationError(
            "Approved case requires reviewer, gold label, dated rationale."
        )
    try:
        date.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise ValidationError("Invalid reviewed_at date.") from exc
    if review.get("source_checked") is not True:
        raise ValidationError("Approved case needs source_checked=true.")
    return approved_verdict
