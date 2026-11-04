"""Validation and plain-text projection for persisted rich-text documents."""

from copy import deepcopy
from urllib.parse import urlparse


CURRENT_SCHEMA_VERSION = 1

PROFILE_DISCUSSION = "discussion"
PROFILE_EVIDENCE = "evidence"
PROFILE_COMMENT = "comment"
PROFILE_PUBLICATION = "publication"

_PROFILE_RULES = {
    PROFILE_DISCUSSION: {
        "nodes": {
            "doc",
            "paragraph",
            "text",
            "hardBreak",
            "bulletList",
            "orderedList",
            "listItem",
            "blockquote",
        },
        "marks": {"bold", "italic", "link"},
        "headings": set(),
        "max_text": 6000,
        "max_nodes": 600,
    },
    PROFILE_EVIDENCE: {
        "nodes": {
            "doc",
            "paragraph",
            "text",
            "hardBreak",
            "bulletList",
            "orderedList",
            "listItem",
            "blockquote",
        },
        "marks": {"bold", "italic", "link"},
        "headings": set(),
        "max_text": 6000,
        "max_nodes": 600,
    },
    PROFILE_COMMENT: {
        "nodes": {
            "doc",
            "paragraph",
            "text",
            "hardBreak",
            "bulletList",
            "listItem",
            "blockquote",
        },
        "marks": {"bold", "italic", "link"},
        "headings": set(),
        "max_text": 3000,
        "max_nodes": 350,
    },
    PROFILE_PUBLICATION: {
        "nodes": {
            "doc",
            "paragraph",
            "heading",
            "text",
            "hardBreak",
            "bulletList",
            "orderedList",
            "listItem",
            "blockquote",
        },
        "marks": {"bold", "italic", "underline", "link"},
        "headings": {2, 3},
        "max_text": 50000,
        "max_nodes": 5000,
    },
}

MAX_DEPTH = 12
MAX_LINK_LENGTH = 2000
_ALLOWED_LINK_SCHEMES = {"http", "https"}


class RichTextSchemaError(ValueError):
    """Raised when a persisted rich-text document violates the allowlist."""


def _invalid(message):
    raise RichTextSchemaError(message)


def _rules(profile):
    try:
        return _PROFILE_RULES[profile]
    except KeyError as error:
        raise RichTextSchemaError("Unsupported rich-text profile.") from error


def _validate_link_href(value):
    if not isinstance(value, str):
        _invalid("Rich-text link href must be a string.")
    href = value.strip()
    if not href or len(href) > MAX_LINK_LENGTH:
        _invalid("Rich-text link href is invalid.")
    parsed = urlparse(href)
    if parsed.scheme.lower() not in _ALLOWED_LINK_SCHEMES or not parsed.netloc:
        _invalid("Rich-text links must use an absolute http or https URL.")
    return href


def _normalize_marks(raw_marks, *, profile):
    if raw_marks is None:
        return []
    if not isinstance(raw_marks, list):
        _invalid("Rich-text marks must be a list.")

    rules = _rules(profile)
    normalized = []
    seen = set()
    for raw_mark in raw_marks:
        if not isinstance(raw_mark, dict):
            _invalid("Rich-text mark must be an object.")
        mark_type = raw_mark.get("type")
        if mark_type not in rules["marks"]:
            _invalid(f"Rich-text mark '{mark_type}' is not allowed.")
        if mark_type in seen:
            continue
        seen.add(mark_type)

        if mark_type == "link":
            attrs = raw_mark.get("attrs")
            if not isinstance(attrs, dict):
                _invalid("Rich-text link attributes are invalid.")
            normalized.append(
                {
                    "type": "link",
                    "attrs": {"href": _validate_link_href(attrs.get("href"))},
                }
            )
            continue

        if raw_mark.get("attrs") not in (None, {}):
            _invalid(f"Rich-text mark '{mark_type}' does not accept attributes.")
        normalized.append({"type": mark_type})

    return normalized


def _normalize_node(raw_node, *, profile, depth, counters):
    if depth > MAX_DEPTH:
        _invalid("Rich-text document is nested too deeply.")
    if not isinstance(raw_node, dict):
        _invalid("Rich-text node must be an object.")

    rules = _rules(profile)
    node_type = raw_node.get("type")
    if node_type not in rules["nodes"]:
        _invalid(f"Rich-text node '{node_type}' is not allowed.")

    counters["nodes"] += 1
    if counters["nodes"] > rules["max_nodes"]:
        _invalid("Rich-text document contains too many nodes.")

    if node_type == "text":
        text = raw_node.get("text")
        if not isinstance(text, str):
            _invalid("Rich-text text nodes require string content.")
        counters["text"] += len(text)
        if counters["text"] > rules["max_text"]:
            _invalid("Rich-text document exceeds the text limit.")
        normalized = {"type": "text", "text": text}
        marks = _normalize_marks(raw_node.get("marks"), profile=profile)
        if marks:
            normalized["marks"] = marks
        unsupported = set(raw_node) - {"type", "text", "marks"}
        if unsupported:
            _invalid("Rich-text text node contains unsupported fields.")
        return normalized

    if node_type == "hardBreak":
        if set(raw_node) - {"type"}:
            _invalid("Rich-text hard break contains unsupported fields.")
        return {"type": "hardBreak"}

    normalized = {"type": node_type}

    if node_type == "heading":
        attrs = raw_node.get("attrs")
        if not isinstance(attrs, dict):
            _invalid("Rich-text heading attributes are invalid.")
        level = attrs.get("level")
        if level not in rules["headings"]:
            _invalid("Only level 2 and level 3 headings are allowed.")
        normalized["attrs"] = {"level": level}
    elif node_type == "orderedList":
        attrs = raw_node.get("attrs")
        start = 1
        if attrs is not None:
            if not isinstance(attrs, dict):
                _invalid("Rich-text ordered-list attributes are invalid.")
            raw_start = attrs.get("start", 1)
            if isinstance(raw_start, bool) or not isinstance(raw_start, int):
                _invalid("Rich-text ordered-list start value is invalid.")
            if raw_start < 1 or raw_start > 1000:
                _invalid("Rich-text ordered-list start value is invalid.")
            start = raw_start
        normalized["attrs"] = {"start": start}
    elif raw_node.get("attrs") not in (None, {}):
        _invalid(f"Rich-text node '{node_type}' does not accept attributes.")

    raw_content = raw_node.get("content")
    if raw_content is None:
        raw_content = []
    if not isinstance(raw_content, list):
        _invalid("Rich-text node content must be a list.")

    normalized_content = [
        _normalize_node(
            child,
            profile=profile,
            depth=depth + 1,
            counters=counters,
        )
        for child in raw_content
    ]

    if node_type == "doc":
        if not normalized_content:
            normalized_content = [{"type": "paragraph"}]
        if any(
            child["type"] not in {
                "paragraph",
                "heading",
                "bulletList",
                "orderedList",
                "blockquote",
            }
            for child in normalized_content
        ):
            _invalid("Rich-text document contains an invalid top-level node.")
    elif node_type in {"paragraph", "heading"}:
        if any(child["type"] not in {"text", "hardBreak"} for child in normalized_content):
            _invalid(f"Rich-text {node_type} contains an invalid child node.")
    elif node_type in {"bulletList", "orderedList"}:
        if not normalized_content or any(
            child["type"] != "listItem" for child in normalized_content
        ):
            _invalid("Rich-text list contains an invalid child node.")
    elif node_type == "listItem":
        if not normalized_content or normalized_content[0]["type"] != "paragraph":
            _invalid("Rich-text list item must begin with a paragraph.")
        if any(
            child["type"] not in {"paragraph", "bulletList", "orderedList"}
            for child in normalized_content
        ):
            _invalid("Rich-text list item contains an invalid child node.")
    elif node_type == "blockquote":
        if not normalized_content or any(
            child["type"] not in {"paragraph", "bulletList", "orderedList"}
            for child in normalized_content
        ):
            _invalid("Rich-text blockquote contains an invalid child node.")

    if normalized_content:
        normalized["content"] = normalized_content

    unsupported = set(raw_node) - {"type", "attrs", "content"}
    if unsupported:
        _invalid(f"Rich-text node '{node_type}' contains unsupported fields.")

    return normalized


def validate_rich_text_document(value, *, profile):
    """Validate an envelope and return a normalized copy safe to persist."""

    if not isinstance(value, dict):
        _invalid("Rich-text content must be an object.")
    if set(value) != {"schema_version", "doc"}:
        _invalid("Rich-text content has unsupported envelope fields.")
    schema_version = value.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != CURRENT_SCHEMA_VERSION
    ):
        _invalid("Rich-text schema version is not supported.")

    counters = {"nodes": 0, "text": 0}
    doc = _normalize_node(
        value.get("doc"),
        profile=profile,
        depth=0,
        counters=counters,
    )
    if doc["type"] != "doc":
        _invalid("Rich-text root node must be a document.")

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "doc": doc,
    }


def _inline_plain(node):
    parts = []
    for child in node.get("content", []):
        if child["type"] == "text":
            parts.append(child.get("text", ""))
        elif child["type"] == "hardBreak":
            parts.append("\n")
    return "".join(parts)


def _list_item_plain(node, *, ordered, number):
    lines = []
    for index, child in enumerate(node.get("content", [])):
        if child["type"] == "paragraph":
            prefix = ""
            if index == 0:
                prefix = f"{number}. " if ordered else "- "
            lines.append(prefix + _inline_plain(child))
        elif child["type"] in {"bulletList", "orderedList"}:
            nested = _block_plain(child)
            if nested:
                lines.extend(f"  {line}" for line in nested.splitlines())
    return "\n".join(line.rstrip() for line in lines if line.strip())


def _block_plain(node):
    node_type = node["type"]
    if node_type in {"paragraph", "heading"}:
        return _inline_plain(node)
    if node_type == "blockquote":
        lines = []
        for child in node.get("content", []):
            value = _block_plain(child)
            lines.extend(f"> {line}" for line in value.splitlines() if line.strip())
        return "\n".join(lines)
    if node_type in {"bulletList", "orderedList"}:
        ordered = node_type == "orderedList"
        start = node.get("attrs", {}).get("start", 1)
        return "\n".join(
            _list_item_plain(
                item,
                ordered=ordered,
                number=start + index,
            )
            for index, item in enumerate(node.get("content", []))
        )
    if node_type == "listItem":
        return _list_item_plain(node, ordered=False, number=1)
    if node_type == "hardBreak":
        return "\n"
    if node_type == "text":
        return node.get("text", "")
    return ""


def rich_text_to_plain(value, *, profile):
    """Return the deterministic compatibility/search projection."""

    normalized = validate_rich_text_document(value, profile=profile)
    blocks = []
    for node in normalized["doc"].get("content", []):
        value = _block_plain(node).strip()
        if value:
            blocks.append(value)
    return "\n\n".join(blocks).strip()


def normalize_rich_text_with_plain(value, *, profile):
    normalized = validate_rich_text_document(value, profile=profile)
    return normalized, rich_text_to_plain(normalized, profile=profile)


def plain_text_to_rich_text(value):
    """Convert legacy plain text to a minimal rich-text envelope."""

    text = "" if value is None else str(value)
    paragraphs = []
    for raw_paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
        lines = raw_paragraph.split("\n")
        content = []
        for index, line in enumerate(lines):
            if index:
                content.append({"type": "hardBreak"})
            if line:
                content.append({"type": "text", "text": line})
        paragraph = {"type": "paragraph"}
        if content:
            paragraph["content"] = content
        paragraphs.append(paragraph)
    if not paragraphs:
        paragraphs = [{"type": "paragraph"}]
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "doc": {"type": "doc", "content": paragraphs},
    }


def clone_rich_text(value):
    return deepcopy(value) if value is not None else None
