"""Deterministic, conservative context selection from extracted URL Markdown.

Only intact input text is selected; no new factual proposition is inferred.
When extraction contains only navigation, return empty so URL processing
can abstain before any claim-gate or retrieval calls.
"""
import re

MAX_URL_CLAIM_CONTEXT_CHARS = 3000

# Explicit website-section headings, never an English-language word filter
# applied to article prose.
_NAV_SECTIONS = frozenset({
    "menu", "navigation", "site navigation", "press contacts", "contact us",
    "shop and learn", "account", "apple store", "for business",
    "for education", "for healthcare", "for government", "apple values",
    "about apple", "footer", "follow us", "social media", "quick links",
    "related links", "privacy", "legal", "cookie preferences",
    "newsletter", "subscribe", "explore", "search",
})
_PREFIXED_NAV_SECTIONS = frozenset({
    "press contacts", "shop and learn", "apple store", "for business",
    "for education", "for healthcare", "for government", "apple values",
    "about apple", "quick links", "site navigation", "related links",
})
_HEADER = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.+?)\s*$")
_INLINE_HEADER = re.compile(r"[ \t]+(?=#{1,6}[ \t]+\S)")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_DATE = re.compile(
    r"(?i)^(?:published|updated|date)\s*[:\-]\s*\S|"
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)[ \t]+\d{1,2}\b"
)
_SENTENCE_END = re.compile(r"[.!?][\"'”’)]?(?:\s|$)")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'“‘A-Z0-9])")


def _readable_line(line):
    line = _IMAGE.sub("", line)
    line = _LINK.sub(r"\1", line)
    line = re.sub(r"^[ \t]*(?:[-*+][ \t]+|\d+[.)][ \t]+)", "", line)
    return line.strip()


def _prose_candidate(text):
    return (
        len(text) >= 10
        and len(text.split()) >= 3
        and bool(_SENTENCE_END.search(text))
    )


def _navigation_heading(heading):
    value = heading.casefold().strip(" :—-")
    return value in _NAV_SECTIONS or any(
        value.startswith(prefix + " ") for prefix in _PREFIXED_NAV_SECTIONS
    )


def _append_complete_passage(selected, passage, limit):
    used = len("\n\n".join(selected))
    sep = 2 if selected else 0
    if used + sep + len(passage) <= limit:
        selected.append(passage)
        return
    available = limit - used - sep
    if available <= 0:
        return
    # Avoid cutting a claim in the middle of a sentence, date or qualifier.
    complete = []
    for sentence in _SENTENCE_SPLIT.split(passage):
        candidate = " ".join((*complete, sentence))
        if len(candidate) > available:
            break
        complete.append(sentence)
    if complete and _prose_candidate(" ".join(complete)):
        selected.append(" ".join(complete))


def clean_url_article_context(raw_content: str | None) -> str:
    """Select article-looking passages with title/date and original modality.

    Navigation-only extractions return "", not a guessed article claim.
    The original URL remains separately attached to its Claim record.
    """
    if not isinstance(raw_content, str) or not raw_content.strip():
        return ""
    raw = raw_content.replace("\r\n", "\n").replace("\r", "\n")
    # Tavily sometimes places multiple Markdown headings on one line.
    raw = _INLINE_HEADER.sub("\n", raw)
    title = None
    published_date = None
    passages = []
    in_navigation = False
    navigation_seen = False
    pending = []

    def flush_paragraph():
        if pending:
            passage = " ".join(pending)
            if _prose_candidate(passage):
                passages.append(passage)
            pending.clear()

    for line in raw.split("\n"):
        heading_match = _HEADER.match(line)
        if heading_match:
            flush_paragraph()
            heading = _readable_line(heading_match.group(2))
            in_navigation = _navigation_heading(heading)
            if in_navigation:
                navigation_seen = True
                continue
            if not heading:
                continue
            if title is None:
                title = heading
            elif published_date is None and _DATE.match(heading):
                published_date = heading
            elif _prose_candidate(heading):
                passages.append(heading)
            continue
        if in_navigation:
            continue
        readable = _readable_line(line)
        if not readable:
            flush_paragraph()
            continue
        if _DATE.match(readable) and published_date is None:
            flush_paragraph()
            published_date = readable
            continue
        # A group of links is often a navigation list. One in-prose
        # citation link is retained with its visible words unchanged.
        if len(_LINK.findall(line)) >= 3:
            flush_paragraph()
            navigation_seen = True
            continue
        pending.append(readable)
        if _prose_candidate(readable):
            flush_paragraph()
    flush_paragraph()

    if not passages:
        # Standalone brief URL posts can contain only one headline.
        # But navigation-dominated pages cannot substantiate a headline.
        if navigation_seen or not title or not _prose_candidate(title):
            return ""
        passages.append(title)
        title = None

    selected = []
    if title:
        selected.append(title)
    if published_date:
        selected.append(published_date)
    for passage in passages:
        _append_complete_passage(selected, passage, MAX_URL_CLAIM_CONTEXT_CHARS)
        if len("\n\n".join(selected)) >= MAX_URL_CLAIM_CONTEXT_CHARS:
            break
    if not any(_prose_candidate(part) for part in selected):
        return ""
    return "\n\n".join(selected)
