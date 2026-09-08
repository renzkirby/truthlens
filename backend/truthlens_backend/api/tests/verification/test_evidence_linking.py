from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification.linking import link_evidence_sources_to_run


class EvidenceLinkingTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(context_text="Example claim.")
        self.run = VerificationRun.objects.create(claim=self.claim)
        self.first = EvidenceSource.objects.create(
            provider="GOOGLE_FACT_CHECK", url="https://example.com/first",
            title="First source", authority_score=0.8,
        )
        self.second = EvidenceSource.objects.create(
            provider="GOOGLE_FACT_CHECK", url="https://example.com/second",
        )

    def _link(self, sources, **kwargs):
        return link_evidence_sources_to_run(
            self.run, sources,
            evidence_role=kwargs.get("evidence_role", VerificationEvidence.EvidenceRole.FACT_CHECK),
        )

    def test_one_source_creates_one_link(self):
        links = self._link([self.first])
        self.assertEqual(len(links), 1)
        self.assertEqual(VerificationEvidence.objects.count(), 1)
        self.assertEqual(links[0].verification_run_id, self.run.pk)
        self.assertEqual(links[0].evidence_source_id, self.first.pk)

    def test_multiple_sources_return_in_first_seen_order(self):
        existing = self._link([self.first])[0]
        links = self._link(iter([self.second, self.first]))
        self.assertEqual([link.evidence_source_id for link in links], [self.second.pk, self.first.pk])
        self.assertEqual(links[1].pk, existing.pk)
        self.assertEqual(VerificationEvidence.objects.count(), 2)

    def test_duplicate_input_returns_one_link_per_source(self):
        reloaded = EvidenceSource.objects.get(pk=self.first.pk)
        links = self._link([self.first, self.second, reloaded, self.second])
        self.assertEqual([link.evidence_source_id for link in links], [self.first.pk, self.second.pk])
        self.assertEqual(VerificationEvidence.objects.count(), 2)

    def test_repeated_calls_reuse_links(self):
        first_links = self._link([self.first, self.second])
        repeated = self._link([self.first, self.second])
        self.assertEqual([link.pk for link in repeated], [link.pk for link in first_links])
        self.assertEqual(VerificationEvidence.objects.count(), 2)

    def test_same_source_links_independently_to_different_runs(self):
        first_link = self._link([self.first])[0]
        other_run = VerificationRun.objects.create(claim=self.claim)
        second_link = link_evidence_sources_to_run(
            other_run, [self.first], evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
        )[0]
        self.assertNotEqual(first_link.pk, second_link.pk)
        self.assertEqual(second_link.verification_run_id, other_run.pk)
        self.assertEqual(second_link.evidence_source_id, self.first.pk)
        self.assertEqual(second_link.evidence_role, VerificationEvidence.EvidenceRole.SECONDARY)
        self.assertEqual(VerificationEvidence.objects.count(), 2)

    def test_existing_enriched_link_is_not_overwritten(self):
        existing = VerificationEvidence.objects.create(
            verification_run=self.run, evidence_source=self.first,
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
            stance=VerificationEvidence.Stance.REFUTES,
            relevance_score=0.9, directness_score=0.8, recency_score=0.7,
        )
        before = VerificationEvidence.objects.values().get(pk=existing.pk)
        links = self._link([self.first])
        self.assertEqual(links[0].pk, existing.pk)
        self.assertEqual(VerificationEvidence.objects.values().get(pk=existing.pk), before)
        self.assertEqual(VerificationEvidence.objects.count(), 1)

    def test_new_fact_check_links_keep_default_stance_and_null_scores(self):
        link = self._link([self.first])[0]
        link.refresh_from_db()
        self.assertEqual(link.evidence_role, VerificationEvidence.EvidenceRole.FACT_CHECK)
        self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(link.relevance_score)
        self.assertIsNone(link.directness_score)
        self.assertIsNone(link.recency_score)

    def test_linking_does_not_require_a_particular_run_status(self):
        for status in VerificationRun.Status.values:
            with self.subTest(status=status):
                run = VerificationRun.objects.create(claim=self.claim, status=status)
                links = link_evidence_sources_to_run(
                    run, [self.first], evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
                )
                self.assertEqual(len(links), 1)
                run.refresh_from_db()
                self.assertEqual(run.status, status)

    def test_linking_does_not_mutate_sources_or_run(self):
        source_before = list(EvidenceSource.objects.order_by("pk").values())
        run_before = VerificationRun.objects.values().get(pk=self.run.pk)
        self._link([self.first, self.second])
        self.assertEqual(list(EvidenceSource.objects.order_by("pk").values()), source_before)
        self.assertEqual(VerificationRun.objects.values().get(pk=self.run.pk), run_before)

    def test_empty_input_returns_empty_list_without_writes(self):
        with self.assertNumQueries(0):
            self.assertEqual(self._link(iter([])), [])
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_unsaved_run_with_uuid_is_rejected(self):
        unsaved = VerificationRun(claim=self.claim)
        self.assertIsNotNone(unsaved.pk)
        self.assertTrue(unsaved._state.adding)
        with self.assertRaisesMessage(ValueError, "VerificationRun must already be persisted"):
            link_evidence_sources_to_run(
                unsaved, [self.first], evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            )
        self.assertEqual(VerificationRun.objects.count(), 1)
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_unsaved_sources_with_uuid_are_rejected_before_writes(self):
        for unsaved in (
            EvidenceSource(provider="GOOGLE_FACT_CHECK"),
            EvidenceSource(id=self.first.pk, provider="GOOGLE_FACT_CHECK"),
        ):
            with self.subTest(pk=unsaved.pk):
                self.assertIsNotNone(unsaved.pk)
                self.assertTrue(unsaved._state.adding)
                with self.assertRaisesMessage(ValueError, "Every EvidenceSource must already be persisted"):
                    self._link([self.first, unsaved])
                self.assertEqual(VerificationEvidence.objects.count(), 0)
                self.assertEqual(EvidenceSource.objects.count(), 2)

    def test_invalid_evidence_role_is_rejected(self):
        for role in (None, "", "INVALID", "fact_check"):
            with self.subTest(role=role):
                with self.assertRaisesMessage(ValueError, "Invalid VerificationEvidence evidence_role"):
                    self._link([self.first], evidence_role=role)
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_batch_failure_rolls_back_new_links_and_preserves_existing_links(self):
        other_source = EvidenceSource.objects.create(provider="GOOGLE_FACT_CHECK")
        existing = self._link([other_source])[0]
        before = VerificationEvidence.objects.values().get(pk=existing.pk)
        get_or_create = VerificationEvidence.objects.get_or_create

        def fail_second_source(**kwargs):
            if kwargs["evidence_source"].pk == self.second.pk:
                raise IntegrityError("Simulated second link failure")
            return get_or_create(**kwargs)

        with patch(
            "api.verification.linking.VerificationEvidence.objects.get_or_create",
            side_effect=fail_second_source,
        ):
            with self.assertRaisesMessage(IntegrityError, "Simulated second link failure"):
                self._link([other_source, self.first, self.second])

        self.assertEqual(list(VerificationEvidence.objects.values()), [before])
