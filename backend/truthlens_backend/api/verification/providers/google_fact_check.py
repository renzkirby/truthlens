import os
from datetime import datetime, timezone
from typing import Any

import requests

from ..contracts import RawEvidence


GOOGLE_FACT_CHECK_ENDPOINT = (
    "https://factchecktools.googleapis.com/"
    "v1alpha1/claims:search"
)

PROVIDER_NAME = "GOOGLE_FACT_CHECK"


def _clean_optional_text(
    value: Any,
) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    return cleaned or None


def _parse_provider_datetime(
    value: Any,
) -> datetime | None:
    """
    Parse Google Fact Check RFC3339-style timestamps.

    Invalid or missing provider dates are treated as absent rather
    than causing evidence ingestion to fail.
    """

    cleaned = _clean_optional_text(value)

    if cleaned is None:
        return None

    try:
        parsed = datetime.fromisoformat(
            cleaned.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


def _build_review_content(
    *,
    claim_text: str | None,
    claimant: str | None,
    review_title: str | None,
    textual_rating: str | None,
    publisher_name: str | None,
) -> str | None:
    """
    Build deterministic evidence text from the structured
    fact-check metadata returned by Google.

    Google Fact Check provides review metadata rather than the full
    article body, so the normalized evidence contains the facts that
    the provider explicitly returned.
    """

    parts: list[str] = []

    if claim_text:
        parts.append(
            f"Claim reviewed: {claim_text}"
        )

    if claimant:
        parts.append(
            f"Claimant: {claimant}"
        )

    if textual_rating:
        parts.append(
            f"Rating: {textual_rating}"
        )

    if review_title:
        parts.append(
            f"Review title: {review_title}"
        )

    if publisher_name:
        parts.append(
            f"Publisher: {publisher_name}"
        )

    if not parts:
        return None

    return "\n".join(parts)


def parse_google_fact_check_response(
    payload: dict[str, Any],
    *,
    limit: int = 5,
) -> list[RawEvidence]:
    """
    Convert a Google Fact Check Tools response into TruthLens'
    provider-independent RawEvidence contract.

    Each claim review becomes one evidence item because each review
    may represent a separate fact-checking publication.
    """

    if limit <= 0:
        return []

    claims = payload.get("claims", [])

    if not isinstance(claims, list):
        return []

    evidence_items: list[RawEvidence] = []

    for claim_index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue

        claim_text = _clean_optional_text(
            claim.get("text")
        )

        claimant = _clean_optional_text(
            claim.get("claimant")
        )

        reviews = claim.get(
            "claimReview",
            [],
        )

        if not isinstance(reviews, list):
            continue

        for review_index, review in enumerate(
            reviews
        ):
            if not isinstance(review, dict):
                continue

            publisher = review.get(
                "publisher",
                {},
            )

            if not isinstance(publisher, dict):
                publisher = {}

            review_url = _clean_optional_text(
                review.get("url")
            )

            review_title = _clean_optional_text(
                review.get("title")
            )

            textual_rating = (
                _clean_optional_text(
                    review.get("textualRating")
                )
            )

            publisher_name = (
                _clean_optional_text(
                    publisher.get("name")
                )
            )

            if not any(
                (
                    review_url,
                    review_title,
                    textual_rating,
                    publisher_name,
                )
            ):
                continue

            review_date = (
                _parse_provider_datetime(
                    review.get("reviewDate")
                )
            )

            evidence_items.append(
                RawEvidence(
                    provider=PROVIDER_NAME,
                    url=review_url,
                    title=review_title,
                    publisher=publisher_name,
                    content=_build_review_content(
                        claim_text=claim_text,
                        claimant=claimant,
                        review_title=review_title,
                        textual_rating=textual_rating,
                        publisher_name=publisher_name,
                    ),
                    source_type="FACT_CHECK",
                    published_at=review_date,
                    raw_reference={
                        "gfc_claim_index": (
                            claim_index
                        ),
                        "gfc_review_index": (
                            review_index
                        ),
                    },
                )
            )

            if len(evidence_items) >= limit:
                return evidence_items

    return evidence_items


class GoogleFactCheckProvider:
    """
    Google Fact Check Tools implementation of EvidenceProvider.

    This class retrieves and translates evidence only. It does not
    determine the final TruthLens verdict.
    """

    provider_name = PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 12.0,
        http_client=None,
    ):
        self.api_key = (
            os.environ.get(
                "FACT_CHECK_API_KEY"
            )
            if api_key is None
            else api_key
        )

        self.timeout = timeout

        self.http_client = (
            http_client
            or requests
        )

    def search_with_payload(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> tuple[
        dict[str, Any],
        list[RawEvidence],
    ]:
        """
        Retrieve Google Fact Check data once and return both the
        original provider payload and parsed TruthLens evidence.

        The original payload is retained for compatibility with the
        existing runtime relevance and LLM evaluation logic.
        """

        cleaned_query = query.strip()

        if not cleaned_query or limit <= 0:
            return {}, []

        if not self.api_key:
            raise ValueError(
                "FACT_CHECK_API_KEY is required "
                "for Google Fact Check search."
            )

        response = self.http_client.get(
            GOOGLE_FACT_CHECK_ENDPOINT,
            params={
                "query": cleaned_query[:200],
                "key": self.api_key,
            },
            timeout=self.timeout,
        )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            return {}, []

        evidence_items = (
            parse_google_fact_check_response(
                payload,
                limit=limit,
            )
        )

        return payload, evidence_items

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[RawEvidence]:
        _, evidence_items = (
            self.search_with_payload(
                query,
                limit=limit,
            )
        )

        return evidence_items
