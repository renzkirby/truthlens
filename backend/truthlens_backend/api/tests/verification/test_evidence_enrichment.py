import math
import uuid
from dataclasses import asdict
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification.evidence_assessment import EvidenceAssessment
from api.verification.evidence_dossier import ReasoningEvidenceItem
from api.verification.evidence_enrichment import (
    persist_evidence_assessment,
    persist_evidence_assessments_batch,
)


class EvidenceAssessmentPersistenceTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(context_text="Example claim.")
        self.run = VerificationRun.objects.create(claim=self.claim)
        self.source = EvidenceSource.objects.create(
            provider="TAVILY",
            content="Persisted evidence.",
        )
        self.link = VerificationEvidence.objects.create(
            verification_run=self.run,
            evidence_source=self.source,
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
        )
        self.evidence_item = self._item()

    def _item(self, link=None, **overrides):
        link = link or self.link
        values = {
            "evidence_link_id": link.pk,
            "evidence_source_id": link.evidence_source_id,
            "provider": link.evidence_source.provider,
            "url": link.evidence_source.url,
            "canonical_url": link.evidence_source.canonical_url,
            "title": link.evidence_source.title,
            "publisher": link.evidence_source.publisher,
            "source_type": link.evidence_source.source_type,
            "content": link.evidence_source.content,
            "published_at": link.evidence_source.published_at,
            "retrieved_at": link.evidence_source.retrieved_at,
            "evidence_role": link.evidence_role,
            "stance": link.stance,
            "relevance_score": link.relevance_score,
            "directness_score": link.directness_score,
            "recency_score": link.recency_score,
        }
        values.update(overrides)
        return ReasoningEvidenceItem(**values)

    def _assessment(self, **overrides):
        values = {
            "stance": VerificationEvidence.Stance.SUPPORTS,
            "relevance_score": 0.8,
            "directness_score": 0.7,
        }
        values.update(overrides)
        return EvidenceAssessment(**values)

    def _persist_and_refresh(self, assessment=None, evidence_item=None):
        persisted = persist_evidence_assessment(
            evidence_item or self.evidence_item,
            assessment or self._assessment(),
        )
        self.link.refresh_from_db()
        return persisted

    def _link_values(self, link=None):
        link = link or self.link
        return VerificationEvidence.objects.values().get(pk=link.pk)

    def _assert_invalid_without_write(self, assessment):
        before = self._link_values()
        with self.assertRaises(ValueError):
            persist_evidence_assessment(self.evidence_item, assessment)
        self.assertEqual(self._link_values(), before)

    def test_supports_assessment_persists_all_three_fields(self):
        self.assertTrue(self._persist_and_refresh())
        self.assertEqual(self.link.stance, VerificationEvidence.Stance.SUPPORTS)
        self.assertEqual(self.link.relevance_score, 0.8)
        self.assertEqual(self.link.directness_score, 0.7)

    def test_refutes_assessment_persists(self):
        self.assertTrue(self._persist_and_refresh(self._assessment(stance="REFUTES")))
        self.assertEqual(self.link.stance, VerificationEvidence.Stance.REFUTES)

    def test_context_assessment_persists(self):
        self.assertTrue(self._persist_and_refresh(self._assessment(stance="CONTEXT")))
        self.assertEqual(self.link.stance, VerificationEvidence.Stance.CONTEXT)

    def test_unknown_with_numeric_scores_persists(self):
        assessment = self._assessment(
            stance="UNKNOWN",
            relevance_score=0.4,
            directness_score=0.2,
        )
        self.assertTrue(self._persist_and_refresh(assessment))
        self.assertEqual(self.link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertEqual(self.link.relevance_score, 0.4)
        self.assertEqual(self.link.directness_score, 0.2)

    def test_zero_scores_persist_as_real_values(self):
        assessment = self._assessment(relevance_score=0, directness_score=0.0)
        self.assertTrue(self._persist_and_refresh(assessment))
        self.assertEqual(self.link.relevance_score, 0.0)
        self.assertEqual(self.link.directness_score, 0.0)
        self.assertIsInstance(self.link.relevance_score, float)
        self.assertIsInstance(self.link.directness_score, float)

    def test_one_scores_persist_as_real_values(self):
        assessment = self._assessment(relevance_score=1, directness_score=1.0)
        self.assertTrue(self._persist_and_refresh(assessment))
        self.assertEqual(self.link.relevance_score, 1.0)
        self.assertEqual(self.link.directness_score, 1.0)

    def test_exact_unavailable_assessment_returns_false_without_write(self):
        before = self._link_values()
        assessment = EvidenceAssessment(
            stance=VerificationEvidence.Stance.UNKNOWN,
            relevance_score=None,
            directness_score=None,
        )
        self.assertFalse(persist_evidence_assessment(self.evidence_item, assessment))
        self.assertEqual(self._link_values(), before)

    def test_invalid_stance_raises_value_error_without_write(self):
        self._assert_invalid_without_write(self._assessment(stance="FACT"))

    def test_negative_score_is_rejected(self):
        self._assert_invalid_without_write(self._assessment(relevance_score=-0.01))

    def test_score_above_one_is_rejected_without_clamping(self):
        self._assert_invalid_without_write(self._assessment(directness_score=1.01))

    def test_numeric_string_is_rejected(self):
        self._assert_invalid_without_write(self._assessment(relevance_score="0.8"))

    def test_boolean_score_is_rejected(self):
        for field_name in ("relevance_score", "directness_score"):
            with self.subTest(field_name=field_name):
                self._assert_invalid_without_write(
                    self._assessment(**{field_name: True})
                )

    def test_none_in_only_one_score_is_rejected(self):
        for field_name in ("relevance_score", "directness_score"):
            with self.subTest(field_name=field_name):
                self._assert_invalid_without_write(
                    self._assessment(**{field_name: None})
                )

    def test_none_in_both_scores_with_assessed_stance_is_rejected(self):
        self._assert_invalid_without_write(
            self._assessment(relevance_score=None, directness_score=None)
        )

    def test_nan_and_infinities_are_rejected(self):
        for invalid_score in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid_score=invalid_score):
                self._assert_invalid_without_write(
                    self._assessment(relevance_score=invalid_score)
                )

    def test_existing_non_unknown_stance_is_never_overwritten(self):
        VerificationEvidence.objects.filter(pk=self.link.pk).update(
            stance=VerificationEvidence.Stance.REFUTES
        )
        before = self._link_values()
        self.assertFalse(persist_evidence_assessment(
            self.evidence_item,
            self._assessment(),
        ))
        self.assertEqual(self._link_values(), before)

    def test_existing_unknown_with_numeric_scores_is_never_overwritten(self):
        VerificationEvidence.objects.filter(pk=self.link.pk).update(
            relevance_score=0.3,
            directness_score=0.2,
        )
        before = self._link_values()
        self.assertFalse(persist_evidence_assessment(
            self.evidence_item,
            self._assessment(),
        ))
        self.assertEqual(self._link_values(), before)

    def test_partially_enriched_existing_state_is_never_overwritten(self):
        VerificationEvidence.objects.filter(pk=self.link.pk).update(
            relevance_score=0.3,
            directness_score=None,
        )
        before = self._link_values()
        self.assertFalse(persist_evidence_assessment(
            self.evidence_item,
            self._assessment(),
        ))
        self.assertEqual(self._link_values(), before)

    def test_recency_score_is_preserved(self):
        VerificationEvidence.objects.filter(pk=self.link.pk).update(recency_score=0.6)
        self.assertTrue(self._persist_and_refresh())
        self.assertEqual(self.link.recency_score, 0.6)

    def test_evidence_role_is_preserved(self):
        original_role = self.link.evidence_role
        self.assertTrue(self._persist_and_refresh())
        self.assertEqual(self.link.evidence_role, original_role)

    def test_verification_run_and_evidence_source_are_preserved(self):
        original_run_id = self.link.verification_run_id
        original_source_id = self.link.evidence_source_id
        self.assertTrue(self._persist_and_refresh())
        self.assertEqual(self.link.verification_run_id, original_run_id)
        self.assertEqual(self.link.evidence_source_id, original_source_id)

    def test_source_id_mismatch_raises_value_error_without_write(self):
        before = self._link_values()
        mismatched_item = self._item(evidence_source_id=uuid.uuid4())
        with self.assertRaises(ValueError):
            persist_evidence_assessment(mismatched_item, self._assessment())
        self.assertEqual(self._link_values(), before)

    def test_nonexistent_evidence_link_id_propagates_does_not_exist(self):
        missing_item = self._item(evidence_link_id=uuid.uuid4())
        with self.assertRaises(VerificationEvidence.DoesNotExist):
            persist_evidence_assessment(missing_item, self._assessment())

    def test_unrelated_verification_evidence_rows_are_untouched(self):
        unrelated_source = EvidenceSource.objects.create(provider="GOOGLE_FACT_CHECK")
        unrelated_link = VerificationEvidence.objects.create(
            verification_run=self.run,
            evidence_source=unrelated_source,
            evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            recency_score=0.9,
        )
        before = self._link_values(unrelated_link)
        self.assertTrue(self._persist_and_refresh())
        self.assertEqual(self._link_values(unrelated_link), before)

    def test_evidence_item_is_not_mutated(self):
        before = asdict(self.evidence_item)
        self.assertTrue(self._persist_and_refresh())
        self.assertEqual(asdict(self.evidence_item), before)

    def test_assessment_object_is_not_mutated(self):
        assessment = self._assessment()
        before = asdict(assessment)
        self.assertTrue(self._persist_and_refresh(assessment))
        self.assertEqual(asdict(assessment), before)

    def test_persistence_does_not_call_assessor_or_llm(self):
        with (
            patch(
                "api.verification.evidence_assessment."
                "assess_reasoning_evidence_against_claim"
            ) as assess,
            patch("api.services.call_llm_with_fallback") as call_llm,
        ):
            self.assertTrue(self._persist_and_refresh())
        assess.assert_not_called()
        call_llm.assert_not_called()


class BatchEvidenceAssessmentPersistenceTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(context_text="Batch persistence claim.")
        self.run = VerificationRun.objects.create(claim=self.claim)

    def _link(self, index, **overrides):
        source = EvidenceSource.objects.create(
            provider="TAVILY",
            canonical_url=f"https://example.com/batch-{index}",
            content=f"Batch evidence {index}.",
        )
        values = {
            "verification_run": self.run,
            "evidence_source": source,
            "evidence_role": VerificationEvidence.EvidenceRole.SECONDARY,
            "recency_score": 0.25,
            "retrieval_provenance": [{"provider": "TAVILY", "rank": index}],
        }
        values.update(overrides)
        return VerificationEvidence.objects.create(**values)

    def _item(self, link, **overrides):
        values = {
            "evidence_link_id": link.pk,
            "evidence_source_id": link.evidence_source_id,
            "provider": link.evidence_source.provider,
            "url": link.evidence_source.url,
            "canonical_url": link.evidence_source.canonical_url,
            "title": link.evidence_source.title,
            "publisher": link.evidence_source.publisher,
            "source_type": link.evidence_source.source_type,
            "content": link.evidence_source.content,
            "published_at": link.evidence_source.published_at,
            "retrieved_at": link.evidence_source.retrieved_at,
            "evidence_role": link.evidence_role,
            "stance": link.stance,
            "relevance_score": link.relevance_score,
            "directness_score": link.directness_score,
            "recency_score": link.recency_score,
        }
        values.update(overrides)
        return ReasoningEvidenceItem(**values)

    def _assessment(self, index=0, **overrides):
        values = {
            "stance": VerificationEvidence.Stance.SUPPORTS,
            "relevance_score": 0.8 - (index * 0.1),
            "directness_score": 0.7 - (index * 0.1),
        }
        values.update(overrides)
        return EvidenceAssessment(**values)

    def test_multiple_valid_assessments_use_one_lock_and_one_bulk_update(self):
        links = [self._link(index) for index in range(3)]
        items = [self._item(link) for link in links]
        assessments = [self._assessment(index) for index in range(3)]
        original_values = [
            {
                "verification_run_id": link.verification_run_id,
                "evidence_source_id": link.evidence_source_id,
                "evidence_role": link.evidence_role,
                "recency_score": link.recency_score,
                "retrieval_provenance": link.retrieval_provenance,
                "created_at": link.created_at,
            }
            for link in links
        ]
        manager = VerificationEvidence.objects

        with (
            patch.object(
                manager,
                "select_for_update",
                wraps=manager.select_for_update,
            ) as select_for_update,
            patch.object(
                manager,
                "bulk_update",
                wraps=manager.bulk_update,
            ) as bulk_update,
        ):
            outcomes = persist_evidence_assessments_batch(items, assessments)

        self.assertEqual([outcome.persisted for outcome in outcomes], [True] * 3)
        self.assertEqual([outcome.error for outcome in outcomes], [None] * 3)
        select_for_update.assert_called_once_with()
        bulk_update.assert_called_once()
        updated_rows, = bulk_update.call_args.args
        self.assertEqual({row.pk for row in updated_rows}, {link.pk for link in links})
        self.assertEqual(
            bulk_update.call_args.kwargs["fields"],
            ["stance", "relevance_score", "directness_score"],
        )

        for link, assessment, original in zip(links, assessments, original_values):
            link.refresh_from_db()
            self.assertEqual(link.stance, assessment.stance)
            self.assertEqual(link.relevance_score, assessment.relevance_score)
            self.assertEqual(link.directness_score, assessment.directness_score)
            for field_name, value in original.items():
                self.assertEqual(getattr(link, field_name), value)

    def test_unavailable_invalid_missing_and_mismatch_are_isolated_in_order(self):
        links = [self._link(index) for index in range(4)]
        missing_item = self._item(
            links[2],
            evidence_link_id=uuid.uuid4(),
        )
        mismatched_item = self._item(
            links[3],
            evidence_source_id=uuid.uuid4(),
        )
        items = [
            self._item(links[0]),
            self._item(links[1]),
            missing_item,
            mismatched_item,
            self._item(links[2]),
        ]
        assessments = [
            EvidenceAssessment(
                stance=VerificationEvidence.Stance.UNKNOWN,
                relevance_score=None,
                directness_score=None,
            ),
            self._assessment(relevance_score="invalid"),
            self._assessment(),
            self._assessment(),
            self._assessment(stance=VerificationEvidence.Stance.REFUTES),
        ]

        outcomes = persist_evidence_assessments_batch(items, assessments)

        self.assertEqual(
            [outcome.persisted for outcome in outcomes],
            [False, False, False, False, True],
        )
        self.assertIsNone(outcomes[0].error)
        self.assertIsInstance(outcomes[1].error, ValueError)
        self.assertIsInstance(outcomes[2].error, VerificationEvidence.DoesNotExist)
        self.assertIsInstance(outcomes[3].error, ValueError)
        self.assertIsNone(outcomes[4].error)
        for link in (links[0], links[1], links[3]):
            link.refresh_from_db()
            self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
            self.assertIsNone(link.relevance_score)
            self.assertIsNone(link.directness_score)
        links[2].refresh_from_db()
        self.assertEqual(links[2].stance, VerificationEvidence.Stance.REFUTES)

    def test_existing_and_partially_assessed_rows_are_not_overwritten(self):
        assessed = self._link(
            1,
            stance=VerificationEvidence.Stance.CONTEXT,
            relevance_score=0.4,
            directness_score=0.3,
        )
        partial = self._link(2, directness_score=0.2)
        pristine = self._link(3)
        before = {
            link.pk: VerificationEvidence.objects.values().get(pk=link.pk)
            for link in (assessed, partial)
        }

        outcomes = persist_evidence_assessments_batch(
            [self._item(link) for link in (assessed, partial, pristine)],
            [self._assessment()] * 3,
        )

        self.assertEqual(
            [outcome.persisted for outcome in outcomes],
            [False, False, True],
        )
        self.assertEqual(
            VerificationEvidence.objects.values().get(pk=assessed.pk),
            before[assessed.pk],
        )
        self.assertEqual(
            VerificationEvidence.objects.values().get(pk=partial.pk),
            before[partial.pk],
        )

    def test_valid_batch_uses_a_constant_bounded_number_of_queries(self):
        links = [self._link(index) for index in range(5)]
        items = [self._item(link) for link in links]
        assessments = [self._assessment(index) for index in range(5)]
        table_name = VerificationEvidence._meta.db_table.upper()

        with CaptureQueriesContext(connection) as queries:
            outcomes = persist_evidence_assessments_batch(items, assessments)

        statements = [query["sql"].upper() for query in queries]
        evidence_selects = [
            sql for sql in statements
            if sql.lstrip().startswith("SELECT") and table_name in sql
        ]
        evidence_updates = [
            sql for sql in statements
            if sql.lstrip().startswith("UPDATE") and table_name in sql
        ]
        self.assertEqual([outcome.persisted for outcome in outcomes], [True] * 5)
        self.assertEqual(len(evidence_selects), 1)
        self.assertEqual(len(evidence_updates), 1)
        self.assertLessEqual(len(statements), 4)
