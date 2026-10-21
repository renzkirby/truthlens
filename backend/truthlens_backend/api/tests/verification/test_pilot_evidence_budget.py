"""Offline, lossless pilot-only prompt budgeting with provenance preservation."""
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from api.services import (
    LLMProviderUnavailableError,
    build_persisted_evidence_prompt,
)
from api.tasks import _render_bounded_persisted_evidence_context
from api.verification.cloudflare_pilot import PILOT_MAX_INPUT_CHARS
from api.verification.evidence_dossier import (
    ReasoningEvidenceGroup,
    ReasoningEvidenceItem,
    render_compact_reasoning_evidence_dossier,
    render_reasoning_evidence_dossier,
)


def _item(*, stance="SUPPORTS", content="Explicit sourced evidence.",
          provider="TAVILY", serial=1):
    return ReasoningEvidenceItem(
        evidence_link_id=uuid4(),
        evidence_source_id=uuid4(),
        provider=provider,
        url=f"https://example.org/item/{serial}?origin=qa",
        canonical_url=f"https://example.org/item/{serial}",
        title=f"Public source number {serial}",
        publisher=f"Publisher {serial}",
        source_type="WEB_SEARCH",
        content=content,
        published_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        evidence_role="SECONDARY",
        stance=stance,
        relevance_score=0.91,
        directness_score=0.82,
        recency_score=0.74,
    )


def _groups(content_length=100, count=12):
    items = [_item(serial=i + 1, content=("X" * content_length))
             for i in range(count)]
    return [
        ReasoningEvidenceGroup(
            identity_kind="CANONICAL_SOURCE" if i < 5 else "EVIDENCE_SOURCE",
            identity_id=uuid4(),
            evidence=tuple(items[j] for j in range(count) if j % 7 == i),
        )
        for i in range(7)
        if any(j % 7 == i for j in range(count))
    ]


@override_settings(APP_ENV="development", DEBUG=True)
class PilotEvidenceBudgetTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
        }))

    def _length(self, context):
        system, user = build_persisted_evidence_prompt(
            "The claim is precisely described here.", context, "NEUTRAL",
        )
        return len(system) + len(user)

    def test_compact_renderer_retains_all_values_and_source_group_boundaries(self):
        a = _item(stance="REFUTES", content="Negation: does NOT support this claim.",
                  serial=1)
        b = _item(stance="SUPPORTS", content="Independent direct support.", serial=2)
        c = _item(stance="UNKNOWN", content="Uncertain source context.", serial=3)
        b = replace(b, published_at=None, retrieved_at=None,
                    relevance_score=None, directness_score=None)
        groups = [
            ReasoningEvidenceGroup("CANONICAL_SOURCE", uuid4(), (a, b)),
            ReasoningEvidenceGroup("EVIDENCE_SOURCE", uuid4(), (c,)),
        ]
        original = render_reasoning_evidence_dossier(groups)
        compact = render_compact_reasoning_evidence_dossier(groups)
        self.assertEqual(compact, render_compact_reasoning_evidence_dossier(iter(groups)))
        self.assertLess(len(compact), len(original))
        self.assertEqual(compact.count("=== SOURCE IDENTITY GROUP "), 2)
        self.assertEqual(compact.count("--- EVIDENCE ITEM "), 3)
        self.assertIn("must not be counted as multiple independent confirmations", compact)
        self.assertIn("not guaranteed to be editorially independent", compact)
        for idx, item in enumerate((a, b, c)):
            self.assertEqual(compact.count(item.content), 1)
            self.assertIn(item.content, compact)
            # Every metadata field is present in positional JSON, even nulls.
            index = compact.index(f"--- EVIDENCE ITEM {1 if idx != 1 else 2} ---")
            # Repeated item index is scoped by SOURCE IDENTITY GROUP.
            sub = compact[index + len(f"--- EVIDENCE ITEM {1 if idx != 1 else 2} ---"):].split("\n", 2)[1]
            obj = json.loads(sub)
            self.assertEqual(len(obj), 13)
            self.assertEqual(obj[0], item.provider)
            self.assertEqual(obj[1], item.evidence_role)
            self.assertEqual(obj[2], item.stance)
            self.assertEqual(obj[3], item.publisher)
            self.assertEqual(obj[5], item.title)
            self.assertEqual(obj[6], item.url)
            self.assertEqual(obj[7], item.canonical_url)
            self.assertEqual(obj[8], item.published_at.isoformat() if item.published_at else None)
            self.assertEqual(obj[9], item.retrieved_at.isoformat() if item.retrieved_at else None)
            self.assertEqual(obj[10], item.relevance_score)
            self.assertEqual(obj[11], item.directness_score)
            self.assertEqual(obj[12], item.recency_score)
        self.assertNotIn("raw_reference", compact)

    def test_empty_unchanged_and_normal_size_uses_exact_legacy_prompt(self):
        self.assertEqual(render_compact_reasoning_evidence_dossier([]), "")
        groups = _groups(content_length=80)
        expected = render_reasoning_evidence_dossier(groups)
        with patch("api.tasks.render_compact_reasoning_evidence_dossier") as compact:
            got = _render_bounded_persisted_evidence_context(
                groups, "The claim is precisely described here.", "NEUTRAL",
            )
        self.assertEqual(got, expected)
        self.assertLess(self._length(got), PILOT_MAX_INPUT_CHARS)
        compact.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_production_unchanged_even_when_evidence_is_oversize(self):
        groups = _groups(content_length=3000)
        expected = render_reasoning_evidence_dossier(groups)
        with patch("api.tasks.render_compact_reasoning_evidence_dossier") as compact:
            got = _render_bounded_persisted_evidence_context(
                groups, "The claim is precisely described here.", "NEUTRAL",
            )
        self.assertEqual(got, expected)
        compact.assert_not_called()

    def test_compact_budget_does_not_drop_any_supports_or_refutes(self):
        chosen = None
        for content_size in range(1600, 2300, 20):
            groups = _groups(content_length=content_size)
            original = render_reasoning_evidence_dossier(groups)
            compact = render_compact_reasoning_evidence_dossier(groups)
            if self._length(original) > PILOT_MAX_INPUT_CHARS >= self._length(compact):
                chosen = groups
                break
        self.assertIsNotNone(chosen, "Expected a compressible medium-sized dossier")
        chosen[0] = replace(chosen[0], evidence=tuple(
            replace(item, stance="REFUTES") if i == 0 else item
            for i, item in enumerate(chosen[0].evidence)
        ))
        got = _render_bounded_persisted_evidence_context(
            chosen, "The claim is precisely described here.", "NEUTRAL",
        )
        self.assertLessEqual(self._length(got), PILOT_MAX_INPUT_CHARS)
        for item in (x for g in chosen for x in g.evidence):
            self.assertIn(item.content, got)
        self.assertIn("REFUTES", got)
        self.assertIn("SUPPORTS", got)

    def test_over_limit_after_lossless_compaction_fails_without_provider_call(self):
        groups = [
            ReasoningEvidenceGroup(
                identity_kind="EVIDENCE_SOURCE",
                identity_id=uuid4(),
                evidence=(_item(content="LONG SOURCE CONTENT " * 1900),),
            )
        ]
        with (
            patch("api.services.call_llm_with_fallback") as provider,
            self.assertRaises(LLMProviderUnavailableError),
        ):
            _render_bounded_persisted_evidence_context(
                groups, "The claim is precisely described here.", "NEUTRAL",
            )
        provider.assert_not_called()

    def test_pilot_flag_off_keeps_existing_renderer(self):
        groups = _groups(content_length=2900)
        expected = render_reasoning_evidence_dossier(groups)
        with (
            patch.dict(os.environ, {"ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "0"}),
            patch("api.tasks.render_compact_reasoning_evidence_dossier") as compact,
        ):
            got = _render_bounded_persisted_evidence_context(
                groups, "The claim is precisely described here.", "NEUTRAL",
            )
        self.assertEqual(got, expected)
        compact.assert_not_called()
