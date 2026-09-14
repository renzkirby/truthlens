import math
import uuid
from dataclasses import asdict
from unittest.mock import patch

from django.test import TestCase

from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification.evidence_assessment import EvidenceAssessment
from api.verification.evidence_dossier import ReasoningEvidenceItem
from api.verification.evidence_enrichment import persist_evidence_assessment


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
