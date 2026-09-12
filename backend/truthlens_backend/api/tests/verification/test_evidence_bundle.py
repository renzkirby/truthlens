import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from api.models import (
    CanonicalSource,
    Claim,
    EvidenceSource,
    VerificationEvidence,
    VerificationRun,
)
from api.verification.evidence_bundle import load_grouped_evidence_for_run
from api.verification.grouping import CANONICAL_SOURCE, EVIDENCE_SOURCE


class PersistedEvidenceBundleTests(TestCase):
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

    def _link(self, evidence_source, *, run=None, **fields):
        return VerificationEvidence.objects.create(
            verification_run=run or self.run,
            evidence_source=evidence_source,
            **fields,
        )

    def test_unsaved_run_with_uuid_is_rejected_using_model_state(self):
        unsaved_run = VerificationRun(claim=self.claim)
        self.assertIsNotNone(unsaved_run.pk)
        self.assertTrue(unsaved_run._state.adding)

        with self.assertRaisesMessage(
            ValueError,
            "VerificationRun must already be persisted.",
        ):
            load_grouped_evidence_for_run(unsaved_run)

    def test_empty_persisted_run_returns_empty_list_in_one_query(self):
        with self.assertNumQueries(1):
            groups = load_grouped_evidence_for_run(self.run)

        self.assertEqual(groups, [])

    def test_evidence_from_another_run_is_excluded(self):
        included_link = self._link(self._evidence_source("TAVILY"))
        other_run = VerificationRun.objects.create(claim=self.claim)
        self._link(
            self._evidence_source("GOOGLE_FACT_CHECK"),
            run=other_run,
        )

        groups = load_grouped_evidence_for_run(self.run)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].evidence, (included_link,))

    def test_cross_provider_shared_canonical_source_forms_one_group(self):
        canonical_source = self._canonical_source("example.com")
        gfc_link = self._link(self._evidence_source(
            "GOOGLE_FACT_CHECK",
            canonical_source=canonical_source,
        ))
        tavily_link = self._link(self._evidence_source(
            "TAVILY",
            canonical_source=canonical_source,
        ))

        groups = load_grouped_evidence_for_run(self.run)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].identity_kind, CANONICAL_SOURCE)
        self.assertEqual(groups[0].identity_id, canonical_source.pk)
        self.assertEqual(set(groups[0].evidence), {gfc_link, tavily_link})

    def test_null_canonical_sources_form_separate_fallback_groups(self):
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

        groups = load_grouped_evidence_for_run(self.run)

        self.assertEqual(
            {(group.identity_kind, group.identity_id) for group in groups},
            {
                (EVIDENCE_SOURCE, first_source.pk),
                (EVIDENCE_SOURCE, second_source.pk),
            },
        )
        self.assertTrue(all(len(group.evidence) == 1 for group in groups))

    def test_ordering_uses_created_at_then_pk_for_groups_and_members(self):
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

        groups = load_grouped_evidence_for_run(self.run)

        self.assertEqual(
            [group.identity_id for group in groups],
            [second_canonical.pk, first_canonical.pk],
        )
        self.assertEqual(
            [link.pk for link in groups[0].evidence],
            [first_second_group_link.pk],
        )
        self.assertEqual(
            [link.pk for link in groups[1].evidence],
            [
                first_first_group_link.pk,
                second_first_group_link.pk,
                later_first_group_link.pk,
            ],
        )

    def test_relationships_are_eager_loaded_without_n_plus_one_queries(self):
        canonical_source = self._canonical_source("example.com")
        first_link = self._link(self._evidence_source(
            "GOOGLE_FACT_CHECK",
            canonical_source=canonical_source,
        ))
        second_link = self._link(self._evidence_source(
            "TAVILY",
            canonical_source=canonical_source,
        ))

        with self.assertNumQueries(1):
            groups = load_grouped_evidence_for_run(self.run)
            loaded_links = groups[0].evidence
            self.assertEqual(
                [link.evidence_source.canonical_source.domain for link in loaded_links],
                ["example.com", "example.com"],
            )

        self.assertEqual(set(loaded_links), {first_link, second_link})

    def test_roles_stances_and_scores_are_preserved_without_filtering(self):
        unknown_link = self._link(
            self._evidence_source("TAVILY"),
            evidence_role=None,
            stance=VerificationEvidence.Stance.UNKNOWN,
        )
        scored_link = self._link(
            self._evidence_source("GOOGLE_FACT_CHECK"),
            evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            stance=VerificationEvidence.Stance.REFUTES,
            relevance_score=0.9,
            directness_score=0.8,
            recency_score=0.7,
        )

        groups = load_grouped_evidence_for_run(self.run)
        links_by_id = {
            link.pk: link
            for group in groups
            for link in group.evidence
        }

        self.assertEqual(set(links_by_id), {unknown_link.pk, scored_link.pk})
        loaded_unknown = links_by_id[unknown_link.pk]
        self.assertIsNone(loaded_unknown.evidence_role)
        self.assertEqual(loaded_unknown.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(loaded_unknown.relevance_score)
        self.assertIsNone(loaded_unknown.directness_score)
        self.assertIsNone(loaded_unknown.recency_score)
        loaded_scored = links_by_id[scored_link.pk]
        self.assertEqual(
            loaded_scored.evidence_role,
            VerificationEvidence.EvidenceRole.FACT_CHECK,
        )
        self.assertEqual(loaded_scored.stance, VerificationEvidence.Stance.REFUTES)
        self.assertEqual(loaded_scored.relevance_score, 0.9)
        self.assertEqual(loaded_scored.directness_score, 0.8)
        self.assertEqual(loaded_scored.recency_score, 0.7)

    def test_helper_does_not_mutate_database_rows(self):
        canonical_source = self._canonical_source("example.com")
        source = self._evidence_source(
            "TAVILY",
            canonical_source=canonical_source,
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

        load_grouped_evidence_for_run(self.run)

        for model in models:
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    list(model.objects.order_by("pk").values()),
                    before[model],
                )
