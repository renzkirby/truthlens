import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from tavily import TavilyClient

from ..contracts import RawEvidence


PROVIDER_NAME = "TAVILY"
EXTRACT_PROVIDER_NAME = "TAVILY_EXTRACT"
PRIMARY_SOURCE_RECOVERY_PROVIDER_RESULTS = 6

# Preserve the existing shared text/URL search preset during adapter staging.
INCLUDE_DOMAINS = (
    "pressone.ph",
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
    "fullfact.org",
    "afp.com",
)

# Keep normal retrieval bounded while ensuring institution-specific factual
# claims can surface primary evidence without waiting for the late recovery path.
# These are broad public-information authorities, not test-case URLs.
AUTHORITY_INCLUDE_DOMAINS = (
    "psa.gov.ph",
    "pagasa.dost.gov.ph",
    "bsp.gov.ph",
    "officialgazette.gov.ph",
    "deped.gov.ph",
    "dswd.gov.ph",
    "doh.gov.ph",
    "denr.gov.ph",
    "da.gov.ph",
    "nasa.gov",
    "noaa.gov",
    "who.int",
    "unesco.org",
    "un.org",
)
NORMAL_INCLUDE_DOMAINS = (*INCLUDE_DOMAINS, *AUTHORITY_INCLUDE_DOMAINS)

# Recovery search is intentionally narrower than a general open-web search.
# These roots cover major intergovernmental institutions whose official domains
# do not use a government TLD. Government/military/int TLDs are handled
# generically by _is_primary_recovery_source_url().
RECOVERY_INSTITUTIONAL_ROOT_DOMAINS = frozenset({
    "un.org",
    "who.int",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "asean.org",
    "europa.eu",
})


def _hostname_for_url(value: Any) -> str:
    cleaned = _clean_optional_text(value)
    if cleaned is None:
        return ""
    try:
        return (urlparse(cleaned).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return ""


def _is_primary_recovery_source_url(value: Any) -> bool:
    """Admit only clearly institutional primary-source domains in recovery."""
    hostname = _hostname_for_url(value)
    if not hostname:
        return False

    labels = hostname.split(".")
    if labels[-1] in {"gov", "mil", "int"}:
        return True
    # Government namespaces such as gov.ph, go.jp, gob.mx, and gouv.fr are
    # accepted only under a country-code TLD. This deliberately rejects lookalike
    # commercial hosts such as example.gov.com or fake.go.net.
    if (
        len(labels) >= 2
        and len(labels[-1]) == 2
        and labels[-2] in {"gov", "go", "gob", "gouv"}
    ):
        return True
    if hostname == "gc.ca" or hostname.endswith(".gc.ca"):
        return True
    if hostname == "admin.ch" or hostname.endswith(".admin.ch"):
        return True
    return any(
        hostname == root or hostname.endswith(f".{root}")
        for root in RECOVERY_INSTITUTIONAL_ROOT_DOMAINS
    )


def filter_primary_source_recovery_payload(
    payload: dict[str, Any],
    *,
    limit: int = 3,
) -> dict[str, Any]:
    """Keep at most a few clearly institutional results from broad recovery."""
    if not isinstance(payload, dict):
        return {}

    filtered = dict(payload)
    results = payload.get("results", [])
    if not isinstance(results, list) or limit <= 0:
        filtered["results"] = []
        return filtered

    admitted = []
    for result in results:
        if not isinstance(result, dict):
            continue
        if not _is_primary_recovery_source_url(result.get("url")):
            continue
        admitted.append(dict(result))
        if len(admitted) >= limit:
            break

    filtered["results"] = admitted
    return filtered


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


def parse_tavily_extract_response(
    payload: dict[str, Any],
    *,
    limit: int = 2,
) -> list[RawEvidence]:
    """Translate bounded Tavily Extract results into separate page evidence."""
    if limit <= 0 or not isinstance(payload, dict):
        return []

    results = payload.get("results", [])
    if not isinstance(results, list):
        return []

    evidence_items: list[RawEvidence] = []
    for result_index, result in enumerate(results):
        if not isinstance(result, dict):
            continue
        url = _clean_optional_text(result.get("url"))
        content = _clean_optional_text(
            result.get("raw_content")
            if result.get("raw_content") is not None
            else result.get("content")
        )
        if url is None or content is None:
            continue
        evidence_items.append(
            RawEvidence(
                provider=EXTRACT_PROVIDER_NAME,
                url=url,
                title=_clean_optional_text(result.get("title")),
                publisher=_clean_optional_text(result.get("publisher")),
                content=content,
                source_type="WEB_EXTRACT",
                raw_reference={"tavily_extract_result_index": result_index},
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
        primary_source_recovery: bool = False,
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

        search_kwargs = {
            "query": cleaned_query,
            "search_depth": "advanced",
            "topic": "general",
            "include_answer": True,
            "timeout": self.timeout,
        }
        if primary_source_recovery:
            # This is the only open-domain mode. Bound provider output before
            # persistence, then admit only clearly institutional primary sources.
            search_kwargs["max_results"] = max(
                limit,
                PRIMARY_SOURCE_RECOVERY_PROVIDER_RESULTS,
            )
        else:
            # Preserve the existing curated search behavior for every normal run.
            search_kwargs["include_domains"] = list(NORMAL_INCLUDE_DOMAINS)

        payload = self.client.search(**search_kwargs)
        if not isinstance(payload, dict):
            raise TypeError("Tavily search response must be a dictionary.")
        if primary_source_recovery:
            payload = filter_primary_source_recovery_payload(payload, limit=limit)

        return payload, parse_tavily_response(payload, limit=limit)

    def extract_with_payload(
        self,
        urls,
        *,
        query: str | None = None,
        limit: int = 2,
        timeout: float | None = None,
    ) -> tuple[dict[str, Any], list[RawEvidence]]:
        """Extract page text for a tiny set of already-retrieved candidate URLs."""
        if isinstance(urls, str):
            bounded_urls = [urls.strip()] if urls.strip() else []
        else:
            bounded_urls = [
                value.strip()
                for value in (urls or ())
                if isinstance(value, str) and value.strip()
            ]
        bounded_urls = bounded_urls[:limit]
        if not bounded_urls or limit <= 0:
            return {}, []

        if self.client is None:
            api_key = _clean_optional_text(self.api_key)
            if api_key is None:
                raise ValueError("TAVILY_API_KEY is required for Tavily extract.")
            self.client = TavilyClient(api_key=api_key)

        extract_timeout = self.timeout if timeout is None else timeout
        payload = self.client.extract(
            bounded_urls,
            extract_depth="basic",
            format="text",
            timeout=extract_timeout,
            **({"query": query.strip()} if isinstance(query, str) and query.strip() else {}),
        )
        if not isinstance(payload, dict):
            raise TypeError("Tavily extract response must be a dictionary.")
        return payload, parse_tavily_extract_response(payload, limit=limit)

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[RawEvidence]:
        _, evidence_items = self.search_with_payload(query, limit=limit)
        return evidence_items
