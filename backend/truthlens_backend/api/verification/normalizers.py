import hashlib
import re
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

from .contracts import (
    NormalizedEvidence,
    RawEvidence,
)


TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def normalize_text(value: str | None) -> str | None:
    """
    Normalize provider text without changing its meaning.

    - strips leading/trailing whitespace
    - collapses repeated internal whitespace
    - preserves case and punctuation
    """

    if value is None:
        return None

    normalized = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return normalized or None


def canonicalize_url(url: str | None) -> str | None:
    """
    Produce a stable form of an evidence URL.

    Removes:
    - fragments
    - common tracking query parameters

    Normalizes:
    - scheme and hostname to lowercase
    - default ports
    - trailing root slash
    """

    if not url:
        return None

    candidate = url.strip()

    if not candidate:
        return None

    parsed = urlsplit(candidate)

    scheme = parsed.scheme.lower()
    hostname = (
        parsed.hostname.lower()
        if parsed.hostname
        else ""
    )

    if not scheme or not hostname:
        return candidate

    port = parsed.port

    if (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        port = None

    netloc = hostname

    if port is not None:
        netloc = f"{hostname}:{port}"

    query_items = [
        (key, value)
        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )
        if key.lower() not in TRACKING_QUERY_PARAMS
    ]

    query = urlencode(query_items)

    path = parsed.path or "/"

    if path == "/":
        path = ""

    return urlunsplit(
        (
            scheme,
            netloc,
            path,
            query,
            "",
        )
    )


def compute_content_hash(
    content: str | None,
) -> str | None:
    """
    Generate a SHA-256 hash from normalized evidence content.
    """

    normalized_content = normalize_text(content)

    if normalized_content is None:
        return None

    return hashlib.sha256(
        normalized_content.encode("utf-8")
    ).hexdigest()


def normalize_evidence(
    evidence: RawEvidence,
) -> NormalizedEvidence:
    """
    Convert provider-specific RawEvidence into TruthLens'
    provider-independent evidence representation.
    """

    content = normalize_text(
        evidence.content
    )

    return NormalizedEvidence(
        provider=evidence.provider.strip().upper(),
        url=(
            evidence.url.strip()
            if evidence.url
            else None
        ),
        canonical_url=canonicalize_url(
            evidence.url
        ),
        title=normalize_text(
            evidence.title
        ),
        publisher=normalize_text(
            evidence.publisher
        ),
        source_type=(
            evidence.source_type.strip().upper()
            if evidence.source_type
            else None
        ),
        content=content,
        content_hash=compute_content_hash(
            content
        ),
        published_at=evidence.published_at,
        raw_reference=dict(
            evidence.raw_reference
        ),
    )
