import uuid

from django.test import TestCase

from api.models import (
    CanonicalSource,
    Claim,
    EvidenceSource,
    VerificationEvidence,
    VerificationRun,
)
from api.verification.grouping import (
    CANONICAL_SOURCE,
    EVIDENCE_SOURCE,
    EvidenceIndependenceGroup,
    group_verification_evidence_by_source_identity,
)


class EvidenceIndependenceGroupingTests(TestCase):
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

    def test_cross_provider_shared_canonical_source_forms_one_group(self):
        canonical_source = self._canonical_source("example.com")
        gfc_source = self._evidence_source(
            "GOOGLE_FACT_CHECK",
            canonical_source=canonical_source,
        )
        tavily_source = self._evidence_source(
            "TAVILY",
            canonical_source=canonical_source,
        )
        gfc_link = self._link(gfc_source)
        tavily_link = self._link(tavily_source)

        groups = group_verification_evidence_by_source_identity(
            [gfc_link, tavily_link]
        )

        self.assertEqual(groups, [EvidenceIndependenceGroup(
            identity_kind=CANONICAL_SOURCE,
            identity_id=canonical_source.pk,
            evidence=(gfc_link, tavily_link),
        )])

    def test_distinct_canonical_sources_form_distinct_groups(self):
        first_canonical = self._canonical_source("first.example")
        second_canonical = self._canonical_source("second.example")
        first_link = self._link(self._evidence_source(
            "TAVILY",
            canonical_source=first_canonical,
        ))
        second_link = self._link(self._evidence_source(
            "TAVILY",
            canonical_source=second_canonical,
        ))

        groups = group_verification_evidence_by_source_identity(
            [first_link, second_link]
        )

        self.assertEqual(
            [(group.identity_kind, group.identity_id) for group in groups],
            [
                (CANONICAL_SOURCE, first_canonical.pk),
                (CANONICAL_SOURCE, second_canonical.pk),
            ],
        )

    def test_sources_without_canonical_identity_form_separate_fallback_groups(self):
        first_source = self._evidence_source(
            "GOOGLE_FACT_CHECK",
            publisher="Shared Publisher",
            url="https://example.com/article",
            title="Shared title",
            content="Shared content",
            raw_reference={"shared": True},
        )
        second_source = self._evidence_source(
            "TAVILY",
            publisher="Shared Publisher",
            url="https://example.com/article",
            title="Shared title",
            content="Shared content",
            raw_reference={"shared": True},
        )
        first_link = self._link(first_source)
        second_link = self._link(second_source)

        groups = group_verification_evidence_by_source_identity(
            [first_link, second_link]
        )

        self.assertEqual(
            [(group.identity_kind, group.identity_id) for group in groups],
            [
                (EVIDENCE_SOURCE, first_source.pk),
                (EVIDENCE_SOURCE, second_source.pk),
            ],
        )

    def test_canonical_and_fallback_identity_namespaces_remain_distinct(self):
        shared_uuid = uuid.uuid4()
        canonical_source = CanonicalSource.objects.create(
            id=shared_uuid,
            name="canonical.example",
            domain="canonical.example",
        )
        canonical_link = self._link(self._evidence_source(
            "TAVILY",
            canonical_source=canonical_source,
        ))
        fallback_source = self._evidence_source(
            "GOOGLE_FACT_CHECK",
            id=shared_uuid,
        )
        fallback_link = self._link(fallback_source)

        groups = group_verification_evidence_by_source_identity(
            [canonical_link, fallback_link]
        )

        self.assertEqual(
            [(group.identity_kind, group.identity_id) for group in groups],
            [
                (CANONICAL_SOURCE, shared_uuid),
                (EVIDENCE_SOURCE, shared_uuid),
            ],
        )

    def test_group_and_member_order_follow_first_seen_input_order(self):
        first_canonical = self._canonical_source("first.example")
        second_canonical = self._canonical_source("second.example")
        first_member = self._link(self._evidence_source(
            "TAVILY",
            canonical_source=first_canonical,
        ))
        second_group_member = self._link(self._evidence_source(
            "TAVILY",
            canonical_source=second_canonical,
        ))
        second_member = self._link(self._evidence_source(
            "GOOGLE_FACT_CHECK",
            canonical_source=first_canonical,
        ))

        groups = group_verification_evidence_by_source_identity(
            iter([first_member, second_group_member, second_member])
        )

        self.assertEqual(
            [group.identity_id for group in groups],
            [first_canonical.pk, second_canonical.pk],
        )
        self.assertEqual(groups[0].evidence, (first_member, second_member))
        self.assertEqual(groups[1].evidence, (second_group_member,))

    def test_duplicate_exact_link_input_is_included_once(self):
        source = self._evidence_source("TAVILY")
        link = self._link(source)
        reloaded_link = VerificationEvidence.objects.get(pk=link.pk)

        groups = group_verification_evidence_by_source_identity(
            [link, reloaded_link, link]
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].evidence, (link,))

    def test_empty_iterable_returns_empty_list(self):
        with self.assertNumQueries(0):
            self.assertEqual(
                group_verification_evidence_by_source_identity(iter(())),
                [],
            )

    def test_unsaved_link_with_uuid_is_rejected_using_model_state(self):
        source = self._evidence_source("TAVILY")
        unsaved_link = VerificationEvidence(
            verification_run=self.run,
            evidence_source=source,
        )
        self.assertIsNotNone(unsaved_link.pk)
        self.assertTrue(unsaved_link._state.adding)

        with self.assertRaisesMessage(
            ValueError,
            "Every VerificationEvidence must already be persisted.",
        ):
            group_verification_evidence_by_source_identity([unsaved_link])

    def test_links_from_multiple_verification_runs_are_rejected(self):
        other_run = VerificationRun.objects.create(claim=self.claim)
        first_link = self._link(self._evidence_source("TAVILY"))
        second_link = self._link(
            self._evidence_source("GOOGLE_FACT_CHECK"),
            run=other_run,
        )

        with self.assertRaisesMessage(
            ValueError,
            "Every VerificationEvidence must belong to the same VerificationRun.",
        ):
            group_verification_evidence_by_source_identity(
                [first_link, second_link]
            )

    def test_grouping_does_not_mutate_database_rows(self):
        canonical_source = self._canonical_source("example.com")
        source = self._evidence_source(
            "TAVILY",
            canonical_source=canonical_source,
        )
        link = self._link(source)
        models = (
            CanonicalSource,
            EvidenceSource,
            VerificationRun,
            VerificationEvidence,
        )
        before = {
            model: list(model.objects.order_by("pk").values())
            for model in models
        }

        group_verification_evidence_by_source_identity([link])

        for model in models:
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    list(model.objects.order_by("pk").values()),
                    before[model],
                )

    def test_existing_role_stance_and_scores_are_preserved(self):
        source = self._evidence_source("GOOGLE_FACT_CHECK")
        link = self._link(
            source,
            evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            stance=VerificationEvidence.Stance.REFUTES,
            relevance_score=0.9,
            directness_score=0.8,
            recency_score=0.7,
        )
        before = VerificationEvidence.objects.values().get(pk=link.pk)

        groups = group_verification_evidence_by_source_identity([link])

        grouped_link = groups[0].evidence[0]
        self.assertIs(grouped_link, link)
        self.assertEqual(
            grouped_link.evidence_role,
            VerificationEvidence.EvidenceRole.FACT_CHECK,
        )
        self.assertEqual(grouped_link.stance, VerificationEvidence.Stance.REFUTES)
        self.assertEqual(grouped_link.relevance_score, 0.9)
        self.assertEqual(grouped_link.directness_score, 0.8)
        self.assertEqual(grouped_link.recency_score, 0.7)
        self.assertEqual(
            VerificationEvidence.objects.values().get(pk=link.pk),
            before,
        )
