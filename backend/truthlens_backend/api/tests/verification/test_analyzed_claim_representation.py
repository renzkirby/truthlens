from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from api.models import Claim
from api.serializers import (
    ClaimDeepAnalysisSerializer,
    ClaimSerializer,
    CommunityFeedClaimSerializer,
    PublicProfileClaimSummarySerializer,
    SafetyClaimSummarySerializer,
    VerificationIntakeClaimSerializer,
)
from api.tasks import ClaimPersistenceError, persist_analyzed_claim_representation


class AnalyzedClaimRepresentationTests(TestCase):
    def test_persistence_updates_only_new_fields_and_normalizes_edges(self):
        claim = Claim.objects.create(
            context_text="Legacy context.",
            ai_verdict="FACT",
            ai_summary="Existing assessment.",
        )

        persist_analyzed_claim_representation(
            claim.pk,
            "  A precise factual proposition.  ",
            "  Original submitted wording.  ",
        )

        claim.refresh_from_db()
        self.assertEqual(claim.analyzed_claim, "A precise factual proposition.")
        self.assertEqual(claim.source_context, "Original submitted wording.")
        self.assertEqual(claim.context_text, "Legacy context.")
        self.assertEqual(claim.ai_verdict, "FACT")
        self.assertEqual(claim.ai_summary, "Existing assessment.")

    def test_out_of_scope_is_not_stored_as_analyzed_claim(self):
        claim = Claim.objects.create(context_text="Legacy context.")

        persist_analyzed_claim_representation(
            claim.pk, "OUT_OF_SCOPE", "Original submitted text."
        )

        claim.refresh_from_db()
        self.assertIsNone(claim.analyzed_claim)
        self.assertEqual(claim.source_context, "Original submitted text.")

    def test_missing_claim_keeps_legacy_no_op_behavior(self):
        claim = Claim()
        persist_analyzed_claim_representation(claim.pk, "Proposition.", "Input.")

    def test_database_failure_propagates_as_claim_persistence_error(self):
        claim = Claim.objects.create(context_text="Original.")
        with patch("api.tasks.Claim.objects.filter") as filtered:
            filtered.return_value.update.side_effect = DatabaseError("write failed")
            with self.assertRaises(ClaimPersistenceError):
                persist_analyzed_claim_representation(
                    claim.pk, "Proposition.", "Input."
                )

    def test_serializer_exposure_and_legacy_nulls(self):
        claim = Claim.objects.create(context_text="Legacy claim text.")

        ordinary = ClaimSerializer(claim).data
        detailed = ClaimDeepAnalysisSerializer(claim).data
        public = PublicProfileClaimSummarySerializer(claim).data
        feed = CommunityFeedClaimSerializer(
            claim, context={"verified_evidence_count": 0}
        ).data
        safety = SafetyClaimSummarySerializer(claim).data
        intake = VerificationIntakeClaimSerializer(claim).data

        for payload in (ordinary, detailed, public, feed, safety, intake):
            self.assertIsNone(payload["analyzed_claim"])
            self.assertEqual(payload["context_text"], "Legacy claim text.")
        self.assertNotIn("source_context", ordinary)
        self.assertNotIn("source_context", public)
        self.assertNotIn("source_context", feed)
        self.assertNotIn("source_context", safety)
        self.assertNotIn("source_context", intake)
        self.assertIn("source_context", detailed)
        self.assertIsNone(detailed["source_context"])

        claim.analyzed_claim = "Concise proposition."
        claim.source_context = "Long original material."
        claim.save(update_fields=["analyzed_claim", "source_context"])
        self.assertEqual(ClaimSerializer(claim).data["analyzed_claim"], "Concise proposition.")
        self.assertEqual(
            ClaimDeepAnalysisSerializer(claim).data["source_context"],
            "Long original material.",
        )

    def test_representation_fields_are_read_only_in_claim_serializers(self):
        claim = Claim.objects.create(context_text="Original.")
        ordinary = ClaimSerializer(
            claim,
            data={"analyzed_claim": "User replacement."},
            partial=True,
        )
        detailed = ClaimDeepAnalysisSerializer(
            claim,
            data={"source_context": "User replacement."},
            partial=True,
        )

        self.assertTrue(ordinary.is_valid(), ordinary.errors)
        self.assertTrue(detailed.is_valid(), detailed.errors)
        self.assertNotIn("analyzed_claim", ordinary.validated_data)
        self.assertNotIn("source_context", detailed.validated_data)
