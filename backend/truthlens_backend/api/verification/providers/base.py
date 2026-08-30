from typing import Protocol

from ..contracts import RawEvidence


class EvidenceProvider(Protocol):
    """
    Contract implemented by all automated evidence providers.

    Providers retrieve evidence only.
    They do not decide the final TruthLens verdict.
    """

    provider_name: str

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[RawEvidence]:
        ...
