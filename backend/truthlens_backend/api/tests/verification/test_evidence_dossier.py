import uuid
from dataclasses import FrozenInstanceError, fields
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from api.models import (
    CanonicalSource,
    Claim,
    EvidenceSource,
    VerificationEvidence,
    VerificationRun,
)
from api.verification.evidence_dossier import (
    ReasoningEvidenceGroup,
    ReasoningEvidenceItem,
    filter_reasoning_evidence_dossier_by_role,
    load_reasoning_evidence_dossier_for_run,
    render_reasoning_evidence_dossier,
)
from api.verification.grouping import (
    CANONICAL_SOURCE,
    EVIDENCE_SOURCE,
    EvidenceIndependenceGroup,
)


class ReasoningEvidenceDossierTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(context_text="Example claim.")
        self.run = VerificationRun.objects.create(claim=self.claim)

    def _canonical_source(self, domain):
        return CanonicalSource.objects.create(name=domain, domain=domain)

    def _evidence_source(self, provider, *, canonical_source=None, **fields):
        return EvidenceSource.objects.create(
            provider=provider,
            canonical_source=canonical_source,
            **fields,
        )

    def _link(self, evidence_source, **fields):
        return VerificationEvidence.objects.create(
            verification_run=self.run,
            evidence_source=evidence_source,
            **fields,
        )

    def _reasoning_item(self, *, evidence_role, content, provider="TAVILY"):
        return ReasoningEvidenceItem(
            evidence_link_id=uuid.uuid4(),
            evidence_source_id=uuid.uuid4(),
            provider=provider,
            url="https://example.com/evidence",
            canonical_url="https://example.com/evidence",
            title="Evidence title",
            publisher="Evidence Publisher",
            source_type="WEB_SEARCH",
            content=content,
            published_at=None,
            retrieved_at=timezone.now(),
            evidence_role=evidence_role,
            stance=VerificationEvidence.Stance.UNKNOWN,
            relevance_score=None,
            directness_score=None,
            recency_score=None,
        )

    def test_empty_persisted_run_returns_empty_list(self):
        self.assertEqual(load_reasoning_evidence_dossier_for_run(self.run), [])

    def test_unsaved_run_propagates_evidence_bundle_validation_error(self):
        unsaved_run = VerificationRun(claim=self.claim)
        self.assertIsNotNone(unsaved_run.pk)
        self.assertTrue(unsaved_run._state.adding)

        with self.assertRaisesMessage(
            ValueError,
            "VerificationRun must already be persisted.",
        ):
            load_reasoning_evidence_dossier_for_run(unsaved_run)

    def test_shared_canonical_source_becomes_one_provider_neutral_group(self):
        canonical_source = self._canonical_source("example.com")
        gfc_link = self._link(self._evidence_source(
            "GOOGLE_FACT_CHECK",
            canonical_source=canonical_source,
        ))
        tavily_link = self._link(self._evidence_source(
            "TAVILY",
            canonical_source=canonical_source,
        ))

        dossier = load_reasoning_evidence_dossier_for_run(self.run)

        self.assertEqual(len(dossier), 1)
        self.assertEqual(dossier[0].identity_kind, CANONICAL_SOURCE)
        self.assertEqual(dossier[0].identity_id, canonical_source.pk)
        self.assertEqual(
            {item.evidence_link_id for item in dossier[0].evidence},
            {gfc_link.pk, tavily_link.pk},
        )
        self.assertEqual(
            {item.provider for item in dossier[0].evidence},
            {"GOOGLE_FACT_CHECK", "TAVILY"},
        )

    def test_null_canonical_sources_remain_separate_fallback_groups(self):
        first_source = self._evidence_source(
            "GOOGLE_FACT_CHECK",
            publisher="Shared Publisher",
            url="https://example.com/article",
        )
        second_source = self._evidence_source(
            "TAVILY",
            publisher="Shared Publisher",
            url="https://example.com/article",
        )
        self._link(first_source)
        self._link(second_source)

        dossier = load_reasoning_evidence_dossier_for_run(self.run)

        self.assertEqual(
            {(group.identity_kind, group.identity_id) for group in dossier},
            {
                (EVIDENCE_SOURCE, first_source.pk),
                (EVIDENCE_SOURCE, second_source.pk),
            },
        )
        self.assertTrue(all(len(group.evidence) == 1 for group in dossier))

    def test_group_and_member_order_from_evidence_bundle_is_preserved(self):
        first_canonical = self._canonical_source("first.example")
        second_canonical = self._canonical_source("second.example")
        later_first_group_link = self._link(
            self._evidence_source("TAVILY", canonical_source=first_canonical),
            id=uuid.UUID(int=1),
        )
        first_second_group_link = self._link(
            self._evidence_source("TAVILY", canonical_source=second_canonical),
            id=uuid.UUID(int=2),
        )
        first_first_group_link = self._link(
            self._evidence_source(
                "GOOGLE_FACT_CHECK",
                canonical_source=first_canonical,
            ),
            id=uuid.UUID(int=3),
        )
        second_first_group_link = self._link(
            self._evidence_source("TAVILY", canonical_source=first_canonical),
            id=uuid.UUID(int=4),
        )
        first_seen_at = timezone.now()
        VerificationEvidence.objects.filter(
            pk__in=(
                first_second_group_link.pk,
                first_first_group_link.pk,
                second_first_group_link.pk,
            )
        ).update(created_at=first_seen_at)
        VerificationEvidence.objects.filter(
            pk=later_first_group_link.pk
        ).update(created_at=first_seen_at + timedelta(seconds=1))

        dossier = load_reasoning_evidence_dossier_for_run(self.run)

        self.assertEqual(
            [group.identity_id for group in dossier],
            [second_canonical.pk, first_canonical.pk],
        )
        self.assertEqual(
            [item.evidence_link_id for item in dossier[0].evidence],
            [first_second_group_link.pk],
        )
        self.assertEqual(
            [item.evidence_link_id for item in dossier[1].evidence],
            [
                first_first_group_link.pk,
                second_first_group_link.pk,
                later_first_group_link.pk,
            ],
        )

    def test_source_and_link_fields_are_copied_exactly_without_raw_reference(self):
        published_at = timezone.now() - timedelta(days=2)
        content = "Exact evidence content.\n" + ("No truncation or rewrite. " * 100)
        source = self._evidence_source(
            "Provider-With-Original-Case",
            url="https://example.com/original?tracking=1",
            canonical_url="https://example.com/original",
            title="  Original title spacing  ",
            publisher="Original Publisher",
            source_type="FACT_CHECK",
            content=content,
            published_at=published_at,
            raw_reference={"private_provider_detail": "not exposed"},
        )
        link = self._link(
            source,
            evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            stance=VerificationEvidence.Stance.REFUTES,
            relevance_score=0.91,
            directness_score=0.82,
            recency_score=0.73,
        )

        item = load_reasoning_evidence_dossier_for_run(self.run)[0].evidence[0]

        self.assertEqual(item.evidence_link_id, link.pk)
        self.assertEqual(item.evidence_source_id, source.pk)
        self.assertEqual(item.provider, source.provider)
        self.assertEqual(item.url, source.url)
        self.assertEqual(item.canonical_url, source.canonical_url)
        self.assertEqual(item.title, source.title)
        self.assertEqual(item.publisher, source.publisher)
        self.assertEqual(item.source_type, source.source_type)
        self.assertEqual(item.content, content)
        self.assertEqual(item.published_at, source.published_at)
        self.assertEqual(item.retrieved_at, source.retrieved_at)
        self.assertEqual(item.evidence_role, link.evidence_role)
        self.assertEqual(item.stance, link.stance)
        self.assertEqual(item.relevance_score, link.relevance_score)
        self.assertEqual(item.directness_score, link.directness_score)
        self.assertEqual(item.recency_score, link.recency_score)
        self.assertNotIn("raw_reference", {field.name for field in fields(item)})
        self.assertFalse(hasattr(item, "raw_reference"))

    def test_unknown_null_and_missing_fields_are_preserved(self):
        link = self._link(
            self._evidence_source(
                "TAVILY",
                url=None,
                canonical_url=None,
                title=None,
                publisher=None,
                source_type=None,
                content=None,
                published_at=None,
            ),
            evidence_role=None,
            stance=VerificationEvidence.Stance.UNKNOWN,
            relevance_score=None,
            directness_score=None,
            recency_score=None,
        )

        item = load_reasoning_evidence_dossier_for_run(self.run)[0].evidence[0]

        self.assertEqual(item.evidence_link_id, link.pk)
        self.assertIsNone(item.url)
        self.assertIsNone(item.canonical_url)
        self.assertIsNone(item.title)
        self.assertIsNone(item.publisher)
        self.assertIsNone(item.source_type)
        self.assertIsNone(item.content)
        self.assertIsNone(item.published_at)
        self.assertIsNone(item.evidence_role)
        self.assertEqual(item.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(item.relevance_score)
        self.assertIsNone(item.directness_score)
        self.assertIsNone(item.recency_score)

    def test_returned_item_and_group_dataclasses_are_immutable(self):
        self._link(self._evidence_source("TAVILY"))
        group = load_reasoning_evidence_dossier_for_run(self.run)[0]
        item = group.evidence[0]

        with self.assertRaises(FrozenInstanceError):
            item.provider = "CHANGED"
        with self.assertRaises(FrozenInstanceError):
            group.identity_kind = "CHANGED"

    def test_helper_delegates_to_evidence_bundle_without_its_own_query(self):
        source = self._evidence_source("TAVILY", content="Persisted content")
        created_link = self._link(source)
        link = VerificationEvidence.objects.select_related("evidence_source").get(
            pk=created_link.pk
        )
        grouped_evidence = [EvidenceIndependenceGroup(
            identity_kind=EVIDENCE_SOURCE,
            identity_id=source.pk,
            evidence=(link,),
        )]

        with patch(
            "api.verification.evidence_dossier.load_grouped_evidence_for_run",
            return_value=grouped_evidence,
        ) as load_grouped:
            with self.assertNumQueries(0):
                dossier = load_reasoning_evidence_dossier_for_run(self.run)

        load_grouped.assert_called_once_with(self.run)
        self.assertEqual(dossier[0].identity_kind, EVIDENCE_SOURCE)
        self.assertEqual(dossier[0].identity_id, source.pk)
        self.assertEqual(dossier[0].evidence[0].evidence_link_id, link.pk)

    def test_helper_does_not_mutate_database_rows(self):
        canonical_source = self._canonical_source("example.com")
        source = self._evidence_source(
            "TAVILY",
            canonical_source=canonical_source,
            content="Persisted evidence",
        )
        self._link(
            source,
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
        )
        models = (
            Claim,
            CanonicalSource,
            EvidenceSource,
            VerificationRun,
            VerificationEvidence,
        )
        before = {
            model: list(model.objects.order_by("pk").values())
            for model in models
        }

        load_reasoning_evidence_dossier_for_run(self.run)

        for model in models:
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    list(model.objects.order_by("pk").values()),
                    before[model],
                )

    def test_role_filter_preserves_order_and_does_not_mutate_input(self):
        first_match = self._reasoning_item(
            evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            content="First match",
        )
        nonmatch = self._reasoning_item(
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
            content="Nonmatch",
        )
        second_match = self._reasoning_item(
            evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            content="Second match",
            provider="GOOGLE_FACT_CHECK",
        )
        removed_group_item = self._reasoning_item(
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
            content="Removed group",
        )
        original_groups = (
            ReasoningEvidenceGroup(
                identity_kind=CANONICAL_SOURCE,
                identity_id=uuid.uuid4(),
                evidence=(first_match, nonmatch, second_match),
            ),
            ReasoningEvidenceGroup(
                identity_kind=EVIDENCE_SOURCE,
                identity_id=uuid.uuid4(),
                evidence=(removed_group_item,),
            ),
        )

        with self.assertNumQueries(0):
            filtered = filter_reasoning_evidence_dossier_by_role(
                original_groups,
                VerificationEvidence.EvidenceRole.FACT_CHECK,
            )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].identity_kind, original_groups[0].identity_kind)
        self.assertEqual(filtered[0].identity_id, original_groups[0].identity_id)
        self.assertEqual(filtered[0].evidence, (first_match, second_match))
        self.assertEqual(
            original_groups[0].evidence,
            (first_match, nonmatch, second_match),
        )
        self.assertEqual(original_groups[1].evidence, (removed_group_item,))

    def test_empty_dossier_renders_as_empty_string(self):
        with self.assertNumQueries(0):
            self.assertEqual(render_reasoning_evidence_dossier(iter(())), "")

    def test_renderer_is_deterministic_and_preserves_boundaries_and_content(self):
        first_content = "Exact first content.\nDo not rewrite this line."
        second_content = "Exact second content."
        first_item = self._reasoning_item(
            evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            content=first_content,
            provider="GOOGLE_FACT_CHECK",
        )
        second_item = self._reasoning_item(
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
            content=second_content,
        )
        groups = (
            ReasoningEvidenceGroup(
                identity_kind=CANONICAL_SOURCE,
                identity_id=uuid.uuid4(),
                evidence=(first_item,),
            ),
            ReasoningEvidenceGroup(
                identity_kind=EVIDENCE_SOURCE,
                identity_id=uuid.uuid4(),
                evidence=(second_item,),
            ),
        )

        with self.assertNumQueries(0):
            first_render = render_reasoning_evidence_dossier(groups)
            second_render = render_reasoning_evidence_dossier(iter(groups))

        self.assertEqual(first_render, second_render)
        self.assertLess(
            first_render.index("=== SOURCE IDENTITY GROUP 1 ==="),
            first_render.index("=== SOURCE IDENTITY GROUP 2 ==="),
        )
        self.assertIn("--- EVIDENCE ITEM 1 ---", first_render)
        self.assertIn(first_content, first_render)
        self.assertIn(second_content, first_render)
        self.assertNotIn("raw_reference", first_render)
        self.assertIn(
            "must not be counted as multiple independent confirmations",
            first_render,
        )
        self.assertIn(
            "not guaranteed to be editorially independent",
            first_render,
        )
