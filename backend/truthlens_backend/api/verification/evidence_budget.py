"""Deterministic, execution-only evidence budgeting. Never writes evidence.

Estimates include chat framing headroom; they are not provider-exact counts.
The local soft allowance is deliberately below the observed 8K Groq TPM tier,
and is not an organization-wide rate limiter.
"""
import json
import math
import os
import re
from dataclasses import replace
from functools import lru_cache

import tiktoken


HARD_PROMPT_TOKENS = 6000
ASSESSMENT_PROMPT_TARGET = 3200
ASSESSMENT_REQUEST_TARGET = 4800
FINAL_PROMPT_TARGET = 3600
# Initial tuning allowance for final JSON plus model reasoning output.
FINAL_EVALUATION_OUTPUT_TOKENS = 1536
MIN_SOFT_PROMPT_TARGET = 1800
LOCAL_GROQ_SOFT_TOKENS = 5800
USAGE_WINDOW_SECONDS = 60
PROMPT_MARGIN = 1.15
CHAT_FRAMING_TOKENS = 96
ASSESSMENT_CONTENT_TOKENS = 650
RICH_CONTENT_TOKENS = 700
SMALL_CONTENT_TOKENS = 180
MIN_CONTENT_TOKENS = 48
# Each result contains only an opaque key, stance and two numeric scores.
# Allow 96 tokens per object (including generous JSON whitespace headroom),
# plus shared framing/reasoning headroom; do not budget prose per item.
ASSESSMENT_OUTPUT_BASE = 384
ASSESSMENT_OUTPUT_PER_ITEM = 96
CONTRADICTION_MIN_SCORE = 0.70
CONTRADICTION_SCORE_TOLERANCE = 0.10
OMISSION_MARKER = "\n[... evidence omitted for request budget ...]\n"


class LLMRequestBudgetExceededError(RuntimeError):
    """Even a minimum valid evidence request cannot fit its safe budget."""


@lru_cache(maxsize=8)
def _encoding(model):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        # GPT-OSS uses the o200k family; unknown overrides use a conservative
        # cross-encoding count below rather than assuming their tokenizer.
        return tiktoken.get_encoding("o200k_base")


def token_count(text):
    model = os.environ.get("GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"
    count = len(_encoding(model).encode(text, disallowed_special=()))
    if model != "openai/gpt-oss-120b":
        count = max(count, len(tiktoken.get_encoding("cl100k_base").encode(
            text, disallowed_special=(),
        )))
    return count


def estimate_prompt_tokens(system, user):
    return math.ceil((token_count(system) + token_count(user)
                      + CHAT_FRAMING_TOKENS) * PROMPT_MARGIN)


def validate_request_budget(system, user, hard_limit=None):
    estimate = estimate_prompt_tokens(system, user)
    if estimate > (HARD_PROMPT_TOKENS if hard_limit is None else hard_limit):
        raise LLMRequestBudgetExceededError(
            "Minimum evidence request exceeds the configured prompt capacity."
        )
    return estimate


def bounded_content(content, allowance):
    """Keep both ends on whitespace boundaries without changing stored text.

    Character slicing avoids splitting UTF-8/token bytes in Tagalog/Taglish.
    Binary search and a final recount account for marker and boundary costs.
    """
    if not isinstance(content, str) or token_count(content) <= allowance:
        return content

    def excerpt(size):
        head = content[:size]
        tail = content[-size:] if size else ""
        if size < len(content):
            if re.search(r"\s", head):
                head = re.sub(r"\S+$", "", head).rstrip()
            if re.search(r"\s", tail):
                tail = re.sub(r"^\S+", "", tail).lstrip()
        return head + OMISSION_MARKER + tail

    low, high = 0, len(content) // 2
    best = OMISSION_MARKER
    while low <= high:
        middle = (low + high) // 2
        candidate = excerpt(middle)
        if token_count(candidate) <= allowance:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def assessment_prompt(claim_text, items):
    return "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps(
        {"claim_text": claim_text, "evidence_items": items}, ensure_ascii=False,
    )


def assessment_output_limit(count):
    return ASSESSMENT_OUTPUT_BASE + ASSESSMENT_OUTPUT_PER_ITEM * count


def assessment_request_fits(system, claim_text, items):
    estimate = estimate_prompt_tokens(system, assessment_prompt(claim_text, items))
    return (estimate <= min(ASSESSMENT_PROMPT_TARGET, HARD_PROMPT_TOKENS)
            and estimate + assessment_output_limit(len(items)) <= ASSESSMENT_REQUEST_TARGET)


def pack_assessment_requests(system, claim_text, items):
    """Maximal contiguous packs, with stable opaque keys and no metadata.

    Each pack consumes as many compact representations as fit both the prompt
    target and the prompt-plus-completion target. Neither is a shared TPM limit.
    """
    packs, current = [], []
    for item in items:
        compact = {"key": item["key"], "evidence_content": bounded_content(
            item["evidence_content"], ASSESSMENT_CONTENT_TOKENS,
        )}
        if current and not assessment_request_fits(system, claim_text, current + [compact]):
            packs.append(current)
            current = []
        allowance = ASSESSMENT_CONTENT_TOKENS
        while not assessment_request_fits(
            system, claim_text, [compact],
        ) and allowance > MIN_CONTENT_TOKENS:
            allowance = max(MIN_CONTENT_TOKENS, allowance // 2)
            compact["evidence_content"] = bounded_content(
                item["evidence_content"], allowance,
            )
        validate_request_budget(system, assessment_prompt(claim_text, [compact]))
        if not assessment_request_fits(system, claim_text, [compact]):
            raise LLMRequestBudgetExceededError(
                "Minimum assessment prompt and completion exceed the assessment budget."
            )
        current.append(compact)
    if current:
        packs.append(current)
    return packs


def soft_final_target(recent_groq_tokens):
    return min(FINAL_PROMPT_TARGET, max(
        MIN_SOFT_PROMPT_TARGET,
        LOCAL_GROQ_SOFT_TOKENS - recent_groq_tokens - FINAL_EVALUATION_OUTPUT_TOKENS,
    ))


def _scored(item):
    return item.relevance_score is not None and item.directness_score is not None


def _rank(entry):
    index, _, item = entry
    # None remains unavailable, never relevance zero. Stable input breaks ties.
    return ((0, -item.relevance_score, -item.directness_score, index)
            if _scored(item) else (1, 0, 0, index))


def _unique_entries(groups):
    seen_ids, seen_urls, seen_content = set(), set(), set()
    entries = []
    for index, (group, item) in enumerate(
        (group, item) for group in groups for item in group.evidence
    ):
        entries.append((index, group, item))
    unique = []
    for entry in sorted(entries, key=_rank):
        item = entry[2]
        content = " ".join((item.content or "").split())
        if (item.evidence_source_id in seen_ids
                or (item.canonical_url and item.canonical_url in seen_urls)
                or (content and content in seen_content)):
            continue
        seen_ids.add(item.evidence_source_id)
        if item.canonical_url:
            seen_urls.add(item.canonical_url)
        if content:
            seen_content.add(content)
        unique.append(entry)
    return unique


def _groups_for(entries):
    groups, positions = [], {}
    for _, group, item in entries:
        key = (group.identity_kind, group.identity_id)
        if key not in positions:
            positions[key] = len(groups)
            groups.append(replace(group, evidence=()))
        position = positions[key]
        groups[position] = replace(
            groups[position], evidence=groups[position].evidence + (item,),
        )
    return groups


def competitively_strong(opposing, selected):
    """Stance cannot rescue weak quality; compare both dimensions independently."""
    material_stance = {"REFUTES": "SUPPORTS", "SUPPORTS": "REFUTES"}.get(opposing.stance)
    scored = [item for item in selected
              if _scored(item) and material_stance is not None and item.stance == material_stance]
    return bool(scored and _scored(opposing) and all(
        getattr(opposing, field) >= max(
            CONTRADICTION_MIN_SCORE,
            min(getattr(item, field) for item in scored)
            - CONTRADICTION_SCORE_TOLERANCE,
        ) for field in ("relevance_score", "directness_score")
    ))


def bounded_reasoning_dossier(groups, prompt_builder, recent_groq_tokens=0):
    """Return complete rendered blocks and safe metrics, without DB mutations.

    prompt_builder renders the actual system and complete user prompt, so claim,
    stance, instructions, wrappers and metadata all consume the same budget.
    """
    from .evidence_dossier import render_reasoning_evidence_dossier

    groups = list(groups)
    entries = _unique_entries(groups)
    target = min(soft_final_target(recent_groq_tokens), HARD_PROMPT_TOKENS)

    def render(selected):
        return render_reasoning_evidence_dossier(_groups_for(selected))

    def estimate(selected):
        return estimate_prompt_tokens(*prompt_builder(render(selected)))

    selected = []

    def append_if_fits(entry, limit):
        index, group, item = entry
        for allowance in (RICH_CONTENT_TOKENS, SMALL_CONTENT_TOKENS,
                          MIN_CONTENT_TOKENS):
            compact = (index, group, replace(
                item, content=bounded_content(item.content, allowance),
            ))
            if estimate(selected + [compact]) <= limit:
                selected.append(compact)
                return True
        return False

    # Prefer assessed source representatives first. Reserve only one minimum
    # unavailable block's incremental cost, rather than alternating whole pools.
    first, rest, seen = [], [], set()
    for entry in entries:
        key = (entry[1].identity_kind, entry[1].identity_id)
        if key in seen:
            rest.append(entry)
        else:
            first.append(entry)
            seen.add(key)
    scored = [entry for entry in first if _scored(entry[2])]
    unknown = [entry for entry in first + rest if not _scored(entry[2])]
    fallback = None
    reserve = 0
    if scored:
        for index, source_group, item in unknown:
            compact = (index, source_group, replace(
                item, content=bounded_content(item.content, MIN_CONTENT_TOKENS),
            ))
            if estimate([compact]) <= target:
                fallback = compact
                reserve = max(0, estimate([compact]) - estimate([]))
                break
    for entry in scored:
        append_if_fits(entry, target - reserve)
    if scored and not selected:
        # A conservative reserve must not displace all assessed evidence.
        # Try the true minimum pair before spending the full target on one side.
        for index, source_group, item in scored:
            compact = (index, source_group, replace(
                item, content=bounded_content(item.content, MIN_CONTENT_TOKENS),
            ))
            if fallback is not None and estimate([compact, fallback]) <= target:
                selected.append(compact)
                break
        if not selected:
            for entry in scored:
                if append_if_fits(entry, target):
                    break
    if fallback is not None:
        # Prefer an unrepresented existing identity when a minimum block fits.
        represented = {(e[1].identity_kind, e[1].identity_id) for e in selected}
        alternatives = sorted(unknown, key=lambda e: (
            (e[1].identity_kind, e[1].identity_id) in represented, e[0],
        ))
        for index, source_group, item in alternatives:
            compact = (index, source_group, replace(
                item, content=bounded_content(item.content, MIN_CONTENT_TOKENS),
            ))
            if estimate(selected + [compact]) <= target:
                selected.append(compact)
                break
    # Retry assessed candidates against the full remaining allowance, then
    # unavailable source representatives and members in persisted order.
    for entry in scored + [e for e in rest if _scored(e[2])] + unknown:
        if entry[0] not in {value[0] for value in selected}:
            append_if_fits(entry, target)

    # A minimum dossier must also respect the effective run-aware target.
    if entries and not selected:
        for entry in entries:
            if append_if_fits(entry, target):
                break
        if not selected:
            raise LLMRequestBudgetExceededError(
                "No complete minimum evidence block fits the effective final target."
            )

    stances = {entry[2].stance for entry in selected
               if _scored(entry[2]) and entry[2].stance in {"SUPPORTS", "REFUTES"}}
    if len(stances) == 1:
        opposite = "REFUTES" if "SUPPORTS" in stances else "SUPPORTS"
        candidates = [entry for entry in entries
                      if entry[2].stance == opposite
                      and entry[0] not in {value[0] for value in selected}
                      and competitively_strong(entry[2], [e[2] for e in selected])]
        if candidates:
            opposing = candidates[0]
            # First try compacting every selected block, then evict weakest
            # items. Keep a strongest original item alongside the contradiction.
            selected = [(i, g, replace(item, content=bounded_content(
                item.content, SMALL_CONTENT_TOKENS,
            ))) for i, g, item in selected]
            selected.sort(key=_rank)
            protected = next(e[0] for e in selected if e[2].stance in stances)
            while not append_if_fits(opposing, target):
                if len(selected) > 1:
                    removable = next(index for index in range(len(selected) - 1, -1, -1)
                                     if selected[index][0] != protected)
                    selected.pop(removable)
                else:
                    # Compact both sides before declaring safe capacity
                    # unavailable. The hard ceiling is never a larger target.
                    selected = [(i, g, replace(item, content=bounded_content(
                        item.content, MIN_CONTENT_TOKENS,
                    ))) for i, g, item in selected]
                    if not append_if_fits(opposing, target):
                        raise LLMRequestBudgetExceededError(
                            "Material contradiction cannot fit minimum evidence request."
                        )
                    break

    dossier = render(selected)
    estimate_final = validate_request_budget(*prompt_builder(dossier), hard_limit=target)
    return dossier, {
        "reasoning_candidates": sum(len(g.evidence) for g in groups),
        "reasoning_selected": len(selected),
        "reasoning_groups": len(_groups_for(selected)),
        "recent_groq_tokens": recent_groq_tokens,
        "final_prompt_tokens_est": estimate_final,
        "final_prompt_budget": target,
    }
