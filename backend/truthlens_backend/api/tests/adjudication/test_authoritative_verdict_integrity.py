from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.adjudication_provenance import (
    AdjudicationProvenance,
    annotate_claim_authoritative_verdict,
    get_claim_adjudication_provenance,
)
from api.adjudication_service import (
    ensure_adjudication_case,
    issue_adjudication_decision,
)
from api.claim_matching import get_match_result
from api.evidence_review_service import review_evidence_submission
from api.models import (
    AdjudicationDecision,
    Claim,
    ClaimCheckHistory,
    EvidenceSubmission,
    ModerationCase,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
)
from api.serializers import ClaimSerializer
from api.tasks import _save_claim, execute_core_text_pipeline


class AuthoritativeVerdictIntegrityTests(TestCase):
    def setUp(self):
        self.reviewer = User.objects.create_user(
            username="verdict-integrity-reviewer",
            password="test-password",
        )
        self.contributor = User.objects.create_user(
            username="verdict-integrity-contributor",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Verdict Integrity Partner",
            slug="verdict-integrity-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.reviewer,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

    def _create_claim(
        self,
        context,
        *,
        ai_verdict="UNVERIFIED",
        fingerprint=None,
    ):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=context,
            ai_verdict=ai_verdict,
            ai_summary=f"Automated analysis for {context}",
            claim_fingerprint=fingerprint,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.contributor,
            caption=context,
        )
        VerificationAssignment.objects.create(
            claim=claim,
            organization=self.organization,
            claimed_by=self.reviewer,
            status=VerificationAssignment.Status.ACTIVE,
        )
        return claim, thread

    def _issue_decision(self, claim, verdict=AdjudicationDecision.Verdict.FACT):
        thread = claim.threads.first()
        if not EvidenceSubmission.objects.filter(thread__claim=claim).exists():
            EvidenceSubmission.objects.create(
                thread=thread,
                contributor=self.contributor,
                evidence_caption="Reviewed evidence for adjudication.",
                evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
                evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            )
        case = ensure_adjudication_case(
            claim=claim,
            actor=self.reviewer,
            organization=self.organization,
        )
        return issue_adjudication_decision(
            case_id=case.id,
            organization_id=self.organization.id,
            actor=self.reviewer,
            verdict=verdict,
            canonical_claim=claim.context_text,
            rationale="A human adjudicator reviewed the available evidence.",
            expected_revision=0,
        )

    def _create_evidence(self, thread, evidence_type):
        return EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.contributor,
            evidence_caption=f"Evidence: {evidence_type}",
            evidence_type=evidence_type,
        )

    @staticmethod
    def _annotated_verdict(claim):
        return annotate_claim_authoritative_verdict(
            Claim.objects.filter(pk=claim.pk)
        ).get().authoritative_final_verdict

    def test_decisive_verified_evidence_does_not_set_claim_verdict(self):
        for evidence_type in (
            EvidenceSubmission.EvidenceType.SUPPORTS,
            EvidenceSubmission.EvidenceType.CONTRADICTS,
        ):
            with self.subTest(evidence_type=evidence_type):
                claim, thread = self._create_claim(
                    f"Evidence signal isolation: {evidence_type}"
                )
                evidence = self._create_evidence(thread, evidence_type)

                evidence.evidence_status = EvidenceSubmission.EvidenceStatus.VERIFIED
                evidence.save(update_fields=["evidence_status"])

                claim.refresh_from_db()
                self.assertIsNone(claim.final_verdict)
                self.assertFalse(
                    AdjudicationDecision.objects.filter(claim=claim).exists()
                )

    def test_evidence_save_does_not_overwrite_legitimate_decision(self):
        claim, thread = self._create_claim("Preserve the human decision")
        self._issue_decision(claim, AdjudicationDecision.Verdict.FACT)
        evidence = self._create_evidence(
            thread,
            EvidenceSubmission.EvidenceType.CONTRADICTS,
        )

        evidence.evidence_status = EvidenceSubmission.EvidenceStatus.VERIFIED
        evidence.save(update_fields=["evidence_status"])

        claim.refresh_from_db()
        self.assertEqual(claim.final_verdict, AdjudicationDecision.Verdict.FACT)
        self.assertEqual(
            claim.adjudication_decisions.get(is_current=True).verdict,
            AdjudicationDecision.Verdict.FACT,
        )

    def test_locked_evidence_review_keeps_claim_undecided(self):
        claim, thread = self._create_claim("Canonical Evidence Review isolation")
        evidence = self._create_evidence(
            thread,
            EvidenceSubmission.EvidenceType.SUPPORTS,
        )
        evidence_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
        )

        review_evidence_submission(
            evidence=evidence,
            actor=self.reviewer,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            expected_status=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
            expected_case_id=evidence_case.id,
            expected_organization_id=self.organization.id,
            allow_reopen=False,
        )

        claim.refresh_from_db()
        self.assertIsNone(claim.final_verdict)
        self.assertFalse(AdjudicationDecision.objects.filter(claim=claim).exists())

    def test_exact_second_chance_match_reuses_ai_context_not_human_verdict(self):
        source, _source_thread = self._create_claim(
            "Exact matched source claim",
            ai_verdict="FAKE",
            fingerprint="txt:shared-integrity-fingerprint",
        )
        self._issue_decision(source, AdjudicationDecision.Verdict.FAKE)
        target, _target_thread = self._create_claim(
            "Exact matched target claim",
            ai_verdict=None,
            fingerprint="txt:shared-integrity-fingerprint",
        )

        with patch("api.claim_matching.find_matching_claim", return_value=source):
            execute_core_text_pipeline(target.context_text, target.id)

        source.refresh_from_db()
        target.refresh_from_db()
        self.assertNotEqual(source.id, target.id)
        self.assertEqual(target.ai_verdict, source.ai_verdict)
        self.assertEqual(target.ai_summary, source.ai_summary)
        self.assertIsNone(target.final_verdict)
        self.assertIn("prior analysis", target.score_context)

    def test_second_chance_match_preserves_target_human_decision(self):
        source, _source_thread = self._create_claim(
            "Matched automated context",
            ai_verdict="FAKE",
        )
        target, _target_thread = self._create_claim(
            "Already adjudicated target",
            ai_verdict="UNVERIFIED",
        )
        self._issue_decision(target, AdjudicationDecision.Verdict.FACT)

        with patch("api.claim_matching.find_matching_claim", return_value=source):
            execute_core_text_pipeline(target.context_text, target.id)

        target.refresh_from_db()
        self.assertEqual(target.final_verdict, AdjudicationDecision.Verdict.FACT)
        self.assertEqual(target.ai_verdict, source.ai_verdict)

    def test_pipeline_failure_does_not_clear_human_decision(self):
        claim, _thread = self._create_claim("Pipeline failure preservation")
        self._issue_decision(claim, AdjudicationDecision.Verdict.MISLEADING)

        with patch("api.claim_matching.find_matching_claim", return_value=None), patch(
            "api.tasks.clean_ocr_text",
            side_effect=RuntimeError("analysis unavailable"),
        ):
            execute_core_text_pipeline(claim.context_text, claim.id)

        claim.refresh_from_db()
        self.assertEqual(
            claim.final_verdict,
            AdjudicationDecision.Verdict.MISLEADING,
        )
        self.assertEqual(claim.ai_verdict, "UNVERIFIED")

    def test_stale_ai_save_cannot_overwrite_adjudication_cache(self):
        claim, _thread = self._create_claim(
            "Stale AI persistence isolation",
            ai_verdict="UNVERIFIED",
        )
        stale_ai_instance = Claim.objects.get(pk=claim.pk)
        self._issue_decision(claim, AdjudicationDecision.Verdict.FACT)

        with patch(
            "api.tasks.Claim.objects.get",
            return_value=stale_ai_instance,
        ), patch(
            "api.embedding_service.generate_embedding",
            return_value=None,
        ):
            _save_claim(
                claim.id,
                {
                    "verdict": "MISLEADING",
                    "summary": "New automated analysis.",
                    "reasoning": "AI-owned reasoning.",
                    "score_context": "AI-owned score context.",
                    "confidence_score": 73,
                },
                "Live Web Search",
                "Updated AI context",
                ["https://example.com/ai-source"],
            )

        claim.refresh_from_db()

        self.assertEqual(
            claim.final_verdict,
            AdjudicationDecision.Verdict.FACT,
        )
        self.assertEqual(claim.ai_verdict, "MISLEADING")
        self.assertEqual(claim.ai_summary, "New automated analysis.")
        self.assertEqual(claim.ai_reasoning, "AI-owned reasoning.")
        self.assertEqual(claim.consensus_score, 73)
        self.assertEqual(claim.score_context, "AI-owned score context.")
        self.assertEqual(claim.source_type, "Live Web Search")
        self.assertEqual(claim.context_text, "Updated AI context")
        self.assertEqual(claim.source_link, "https://example.com/ai-source")
        self.assertEqual(
            claim.top_verdict_source,
            "https://example.com/ai-source",
        )
        self.assertEqual(
            claim.ai_sources,
            ["https://example.com/ai-source"],
        )
        self.assertEqual(
            claim.verified_via,
            Claim.VerificationSource.AI_EXTENSION,
        )
        self.assertIsNotNone(claim.claim_fingerprint)

    def test_cache_only_verdict_is_not_presented_as_human_adjudication(self):
        claim, _thread = self._create_claim(
            "Unattributed compatibility cache",
            ai_verdict="MISLEADING",
        )
        Claim.objects.filter(pk=claim.pk).update(final_verdict="FAKE")
        claim.refresh_from_db()

        data = ClaimSerializer(claim).data
        match = get_match_result(claim)

        self.assertIsNone(data["final_verdict"])
        self.assertEqual(data["effective_verdict"], "MISLEADING")
        self.assertFalse(data["has_moderator_verdict"])
        self.assertIsNone(data["moderator_verdict_info"])
        self.assertEqual(
            get_claim_adjudication_provenance(claim)["status"],
            AdjudicationProvenance.UNATTRIBUTED_CACHE,
        )
        self.assertIsNone(self._annotated_verdict(claim))
        self.assertEqual(match["match_type"], "has_thread")
        self.assertEqual(match["verdict"], "MISLEADING")
        self.assertIsNone(match["final_verdict"])
        self.assertNotEqual(match["resolution_source"], "ADJUDICATION")

    def test_polling_authority_flag_ignores_cache_only_verdict(self):
        claim, _thread = self._create_claim(
            "Public polling cache isolation",
            ai_verdict="UNVERIFIED",
        )
        Claim.objects.filter(pk=claim.pk).update(final_verdict="FACT")

        response = APIClient().get(
            reverse("claim_status", kwargs={"claim_id": claim.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()["has_community_verdict"])
        self.assertIsNone(response.json()["final_verdict"])

    def test_history_verdict_filter_ignores_cache_only_value(self):
        claim, _thread = self._create_claim(
            "History filter cache isolation",
            ai_verdict="MISLEADING",
        )
        Claim.objects.filter(pk=claim.pk).update(final_verdict="FACT")
        ClaimCheckHistory.objects.create(user=self.reviewer, claim=claim)
        client = APIClient()
        client.force_authenticate(user=self.reviewer)

        cached_response = client.get(
            reverse("user_fact_check_library"),
            {"view": "history", "verdict": "FACT"},
        )
        ai_response = client.get(
            reverse("user_fact_check_library"),
            {"view": "history", "verdict": "MISLEADING"},
        )

        self.assertEqual(cached_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cached_response.data["count"], 0)
        self.assertEqual(ai_response.status_code, status.HTTP_200_OK)
        self.assertEqual(ai_response.data["count"], 1)
        self.assertEqual(ai_response.data["results"][0]["id"], str(claim.id))

    def test_thread_search_ignores_cache_only_verdict(self):
        claim, thread = self._create_claim(
            "Thread search cache isolation",
            ai_verdict="MISLEADING",
        )
        Claim.objects.filter(pk=claim.pk).update(final_verdict="FACT")
        client = APIClient()
        client.force_authenticate(user=self.reviewer)

        cached_response = client.get(
            reverse("thread-list"),
            {"search": "FACT"},
        )
        ai_response = client.get(
            reverse("thread-list"),
            {"search": "MISLEADING"},
        )

        self.assertEqual(cached_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cached_response.data["results"], [])
        self.assertEqual(ai_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in ai_response.data["results"]],
            [str(thread.id)],
        )

    def test_uncertain_legacy_decision_is_not_falsely_attributed(self):
        claim, _thread = self._create_claim(
            "Legacy provenance unavailable",
            ai_verdict="UNVERIFIED",
        )
        Claim.objects.filter(pk=claim.pk).update(final_verdict="FAKE")
        AdjudicationDecision.objects.create(
            claim=claim,
            verdict=AdjudicationDecision.Verdict.FAKE,
            canonical_claim=claim.context_text,
            rationale="Imported without a matching historical thread review.",
            decided_by=self.reviewer,
            decision_source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
        )
        claim.refresh_from_db()

        data = ClaimSerializer(claim).data

        self.assertIsNone(data["final_verdict"])
        self.assertFalse(data["has_moderator_verdict"])
        self.assertEqual(
            get_claim_adjudication_provenance(claim)["status"],
            AdjudicationProvenance.LEGACY_PROVENANCE_UNAVAILABLE,
        )
        self.assertIsNone(self._annotated_verdict(claim))

    def test_human_label_without_canonical_case_is_not_falsely_attributed(self):
        claim, _thread = self._create_claim("Incomplete human provenance")
        Claim.objects.filter(pk=claim.pk).update(final_verdict="FACT")
        AdjudicationDecision.objects.create(
            claim=claim,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim=claim.context_text,
            rationale="Record lacks the canonical adjudication case.",
            decided_by=self.reviewer,
            organization=self.organization,
        )
        claim.refresh_from_db()

        data = ClaimSerializer(claim).data

        self.assertIsNone(data["final_verdict"])
        self.assertFalse(data["has_moderator_verdict"])
        self.assertEqual(
            get_claim_adjudication_provenance(claim)["status"],
            AdjudicationProvenance.PROVENANCE_UNAVAILABLE,
        )
        self.assertIsNone(self._annotated_verdict(claim))

    def test_legacy_decision_with_reviewer_retains_historical_attribution(self):
        claim, thread = self._create_claim("Attributed legacy adjudication")
        Claim.objects.filter(pk=claim.pk).update(final_verdict="FACT")
        thread.moderator_verdict = AdjudicationDecision.Verdict.FACT
        thread.moderated_by = self.reviewer
        thread.save(update_fields=["moderator_verdict", "moderated_by"])
        AdjudicationDecision.objects.create(
            claim=claim,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim=claim.context_text,
            rationale="Imported from a moderator-authored legacy decision.",
            decided_by=self.reviewer,
            decision_source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
        )
        claim.refresh_from_db()

        data = ClaimSerializer(claim).data

        self.assertEqual(data["final_verdict"], "FACT")
        self.assertTrue(data["has_moderator_verdict"])
        self.assertEqual(
            get_claim_adjudication_provenance(claim)["status"],
            AdjudicationProvenance.LEGACY_HUMAN_REVIEW,
        )
        self.assertEqual(self._annotated_verdict(claim), "FACT")

    def test_current_decision_is_authoritative_when_cache_mismatches(self):
        claim, _thread = self._create_claim("Current decision provenance")
        result = self._issue_decision(claim, AdjudicationDecision.Verdict.FACT)
        Claim.objects.filter(pk=claim.pk).update(final_verdict="FAKE")
        claim.refresh_from_db()

        data = ClaimSerializer(claim).data

        self.assertEqual(result["decision"].verdict, "FACT")
        self.assertEqual(data["final_verdict"], "FACT")
        self.assertEqual(data["effective_verdict"], "FACT")
        self.assertTrue(data["has_moderator_verdict"])
        self.assertEqual(data["moderator_verdict_info"]["verdict"], "FACT")
        self.assertEqual(
            get_claim_adjudication_provenance(claim)["status"],
            AdjudicationProvenance.HUMAN_ADJUDICATION,
        )
        self.assertEqual(self._annotated_verdict(claim), "FACT")
