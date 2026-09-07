import os
from datetime import datetime, timezone
from typing import Any

from tavily import TavilyClient

from ..contracts import RawEvidence


PROVIDER_NAME = "TAVILY"

# Preserve the existing shared text/URL search preset during adapter staging.
INCLUDE_DOMAINS = (
    "gmanetwork.com",
    "rappler.com",
    "philstar.com",
    "inquirer.net",
    "news.abs-cbn.com",
    "manilabulletin.com",
    "bworldonline.com",
    "pna.gov.ph",
    "verafiles.org",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "cnn.com",
    "aljazeera.com",
    "nytimes.com",
    "theguardian.com",
    "snopes.com",
    "politifact.com",
    "factcheck.org",
    "afp.com",
)


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _parse_provider_datetime(value: Any) -> datetime | None:
    cleaned = _clean_optional_text(value)
    if cleaned is None:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_tavily_response(
    payload: dict[str, Any],
    *,
    limit: int = 5,
) -> list[RawEvidence]:
    """Translate source results without modifying the provider payload."""
    if limit <= 0:
        return []

    results = payload.get("results", [])
    if not isinstance(results, list):
        return []

    evidence_items: list[RawEvidence] = []
    for result_index, result in enumerate(results):
        if not isinstance(result, dict):
            continue

        url = _clean_optional_text(result.get("url"))
        content = _clean_optional_text(result.get("content"))
        if url is None and content is None:
            continue

        evidence_items.append(
            RawEvidence(
                provider=PROVIDER_NAME,
                url=url,
                title=_clean_optional_text(result.get("title")),
                publisher=_clean_optional_text(result.get("publisher")),
                content=content,
                source_type="WEB_SEARCH",
                published_at=_parse_provider_datetime(result.get("published_date")),
                raw_reference={"tavily_result_index": result_index},
            )
        )
        if len(evidence_items) >= limit:
            break

    return evidence_items


class TavilyProvider:
    """Retrieve source evidence only; runtime evaluation remains caller-owned."""

    provider_name = PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 12.0,
        client=None,
    ):
        self.api_key = (
            os.environ.get("TAVILY_API_KEY") if api_key is None else api_key
        )
        self.timeout = timeout
        self.client = client

    def search_with_payload(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> tuple[dict[str, Any], list[RawEvidence]]:
        """Search once and retain the exact SDK payload for future runtime use."""
        cleaned_query = query.strip()
        if not cleaned_query or limit <= 0:
            return {}, []

        if self.client is None:
            api_key = _clean_optional_text(self.api_key)
            if api_key is None:
                raise ValueError("TAVILY_API_KEY is required for Tavily search.")
            self.client = TavilyClient(api_key=api_key)

        # limit bounds parsed evidence only; retain existing request result count.
        payload = self.client.search(
            query=cleaned_query,
            search_depth="advanced",
            topic="general",
            include_answer=True,
            include_domains=list(INCLUDE_DOMAINS),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise TypeError("Tavily search response must be a dictionary.")

        return payload, parse_tavily_response(payload, limit=limit)

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[RawEvidence]:
        _, evidence_items = self.search_with_payload(query, limit=limit)
        return evidence_items
