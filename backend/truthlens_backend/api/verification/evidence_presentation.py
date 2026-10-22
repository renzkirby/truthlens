"""Read-only public source previews from persisted evidence for URL reports.

This projection never changes the evidence used by the evaluator. A displayed
link is not an independent confirmation, a verdict, or a new evidence source.
"""
from urllib.parse import urlsplit

from ..models import VerificationRun
from .evidence_dossier import (
    filter_reasoning_evidence_dossier_by_role,
    load_reasoning_evidence_dossier_for_run,
)


def _safe_source_link(value):
    if not isinstance(value, str):
        return None
    url = value.strip()
    try:
        parsed = urlsplit(url)
        if (parsed.scheme.lower() not in ("http", "https")
                or not parsed.hostname or parsed.username or parsed.password):
            return None
    except ValueError:
        return None
    return url


def persisted_evidence_source_previews(
    run: VerificationRun, evidence_role: str,
) -> list[dict]:
    """One card per distinct safe URL in the exact evaluated evidence role.

    The full persisted dossier remains unchanged, including repeated source
    URLs and contrary evidence. Order follows the persisted identity groups.
    """
    groups = filter_reasoning_evidence_dossier_by_role(
        load_reasoning_evidence_dossier_for_run(run), evidence_role,
    )
    seen = set()
    previews = []
    for group in groups:
        for item in group.evidence:
            url = _safe_source_link(item.url) or _safe_source_link(
                item.canonical_url
            )
            if not url:
                continue
            parts = urlsplit(url)
            key = (
                parts.scheme.lower(), parts.hostname.lower(),
                parts.path.rstrip("/"), parts.query,
            )
            if key in seen:
                continue
            seen.add(key)
            content = item.content if isinstance(item.content, str) else ""
            title = item.title or item.publisher or "Evidence source"
            previews.append({
                "url": url,
                "title": title.strip() or "Evidence source",
                "snippet": content[:250] + ("…" if len(content) > 250 else ""),
                "provenance": "PERSISTED_EVIDENCE",
            })
    return previews
