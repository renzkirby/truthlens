from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Claim, EvidenceSubmission, Thread
from api.serializers import (
    ClaimDeepAnalysisSerializer,
    ClaimSerializer,
    CommunityFeedClaimSerializer,
    EvidenceSubmissionSerializer,
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


class ClaimAnalysisAccessTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            context_text="Legacy claim context.",
            analyzed_claim="Concise analyzed proposition.",
            source_context="Original submitted material.",
        )
        self.url = reverse("claim_analysis", kwargs={"claim_id": self.claim.pk})
        self.client = APIClient()

    def test_anonymous_request_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_request_includes_detailed_representation(self):
        user = get_user_model().objects.create_user(
            username="analysis_reader", password="test-password"
        )
        self.client.force_authenticate(user=user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["analyzed_claim"], self.claim.analyzed_claim)
        self.assertEqual(response.data["source_context"], self.claim.source_context)
        self.assertNotIn("source_context", ClaimSerializer(self.claim).data)
        self.assertNotIn(
            "source_context", PublicProfileClaimSummarySerializer(self.claim).data
        )
        feed = CommunityFeedClaimSerializer(
            self.claim, context={"verified_evidence_count": 0}
        ).data
        self.assertNotIn("source_context", feed)


class CompactClaimContractTests(TestCase):
    def test_evidence_thread_claim_includes_type_without_source_context(self):
        user = get_user_model().objects.create_user(username="evidence_author")
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="Historical source material.",
            analyzed_claim="Concise analyzed proposition.",
            source_context="Full extracted source material.",
        )
        thread = Thread.objects.create(claim=claim, author=user)
        evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=user,
            evidence_caption="Submitted evidence.",
        )

        payload = EvidenceSubmissionSerializer().get_thread(evidence)["claim"]

        self.assertEqual(payload["claim_type"], Claim.ClaimType.URL)
        self.assertEqual(payload["analyzed_claim"], claim.analyzed_claim)
        self.assertNotIn("source_context", payload)
