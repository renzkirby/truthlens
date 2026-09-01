from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RawEvidence:
    """
    Evidence in the shape returned by an external provider
    before TruthLens normalization.

    Examples of providers:
    - Google Fact Check
    - Tavily
    - TruthLens Vault
    """

    provider: str

    url: str | None = None
    title: str | None = None
    publisher: str | None = None
    content: str | None = None

    source_type: str | None = None

    published_at: datetime | None = None

    raw_reference: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
class NormalizedEvidence:
    """
    Provider-independent evidence representation used
    internally by the TruthLens verification pipeline.
    """

    provider: str

    url: str | None = None
    canonical_url: str | None = None

    title: str | None = None
    publisher: str | None = None

    source_type: str | None = None

    content: str | None = None
    content_hash: str | None = None

    published_at: datetime | None = None

    raw_reference: dict[str, Any] = field(
        default_factory=dict
    )
