"""Persisted evidence review support preserves human authority and performs no writes."""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.adjudication_service import is_claim_ready_for_adjudication
from api.knowledge_reuse_service import (
    build_published_fact_check_payload,
    get_published_fact_check_resolution_for_claim,
    get_related_published_fact_check_payloads,
)
from api.models import (
    AdjudicationDecision,
    CanonicalSource,
    Claim,
    ClaimFactCheckReference,
    EvidenceSource,
    EvidenceSubmission,
    KnowledgeReuseEvent,
    ModerationCase,
    OfficialFactCheck,
    Organization,
    OrganizationMembership,
    PublicReachEvent,
    Thread,
    UserProfile,
    VerificationAssignment,
    VerificationEvidence,
    VerificationRun,
)
from api.verification_intelligence_service import (
    VerificationIntelligenceAuthorizationError,
    VerificationIntelligenceNotFound,
    _build_evidence_intelligence,
    _build_prior_knowledge_intelligence,
    get_verification_intelligence_context,
)


class EvidenceIntelligenceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = User.objects.create_user(username="evidence-intelligence-lead")
        self.organization = Organization.objects.create(
            name="Evidence Intelligence Partner", slug="evidence-intelligence-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.membership = OrganizationMembership.objects.create(
            user=self.actor, organization=self.organization,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.claim = Claim.objects.create(context_text="Persisted evidence claim")
        self.assignment = VerificationAssignment.objects.create(
            claim=self.claim, organization=self.organization, claimed_by=self.actor,
            claimed_at=timezone.now(), status=VerificationAssignment.Status.ACTIVE,
        )
        self.thread = Thread.objects.create(claim=self.claim, author=self.actor)
        self.client = APIClient()
        self.client.force_authenticate(self.actor)
        self.url = reverse("verification_intelligence", kwargs={"claim_id": self.claim.pk})
        self.guards = []
        for target in (
            "api.services.call_llm_with_fallback",
            "api.services.assess_claim_equivalence",
            "api.services.search_official_vault",
            "api.services.gemini_client.models.generate_content",
            "api.services.groq_client.chat.completions.create",
            "api.verification.evidence_assessment.call_llm_with_fallback",
            "api.verification.evidence_assessment.assess_reasoning_evidence_against_claim",
            "api.verification.evidence_assessment.assess_reasoning_evidence_batch_against_claim",
            "api.verification.evidence_enrichment.persist_evidence_assessment",
            "api.embedding_service.generate_embedding",
            "api.knowledge_reuse_service.generate_embedding",
            "api.knowledge_reuse_service.find_published_fact_check_candidates",
            "api.knowledge_reuse_service.find_published_fact_check_match",
            "api.knowledge_reuse_service.find_unique_equivalent_published_fact_check_match",
            "api.knowledge_reuse_service.index_published_fact_check",
            "api.knowledge_reuse_service.record_knowledge_reuse",
            "api.knowledge_reuse_service.record_authoritative_claim_fact_check_reference",
            "api.knowledge_reuse_service.record_equivalent_claim_fact_check_reference",
            "api.knowledge_reuse_service.record_related_claim_fact_check_reference",
            "api.verification.providers.tavily.TavilyProvider.search",
            "api.verification.providers.tavily.TavilyProvider.search_with_payload",
            "api.verification.providers.google_fact_check.GoogleFactCheckProvider.search",
            "api.verification.providers.google_fact_check.GoogleFactCheckProvider.search_with_payload",
            "api.ocr_service.extract_text_from_image",
            "api.ocr_adapter.extract_text_with_provider_adapter",
            "api.models.Claim.compute_final_verdict",
            "celery.app.task.Task.apply_async",
            "requests.sessions.Session.request",
            "httpx.Client.send",
            "httpx.AsyncClient.send",
        ):
            self.guards.append(self.enterContext(patch(
                target, side_effect=AssertionError(f"Forbidden evidence-intelligence call: {target}"),
            )))

    def tearDown(self):
        try:
            for guard in self.guards:
                guard.assert_not_called()
        finally:
            super().tearDown()

    def project(self, **overrides):
        values = {"actor": self.actor, "organization": self.organization, "claim_id": self.claim.pk}
        values.update(overrides)
        return get_verification_intelligence_context(**values)

    def intelligence(self):
        return self.project()["evidence_intelligence"]

    def get(self, organization=None):
        return self.client.get(self.url, {"organization_id": (organization or self.organization).pk})

    def make_run(self, status="COMPLETED", **fields):
        return VerificationRun.objects.create(claim=self.claim, status=status, **fields)

    def automated(self, run, *, canonical=None, source=None, **fields):
        source = source or EvidenceSource.objects.create(
            provider="TAVILY", title="Persisted evidence source",
            url="https://example.test/evidence", canonical_source=canonical,
        )
        return VerificationEvidence.objects.create(verification_run=run, evidence_source=source, **fields)

    def human(self, status="UNVERIFIED", **fields):
        return EvidenceSubmission.objects.create(
            thread=self.thread, contributor=self.actor, evidence_status=status, **fields,
        )

    def case(self, evidence, status="OPEN"):
        return ModerationCase.objects.create(
            case_type="EVIDENCE", evidence_submission=evidence, status=status,
        )

    def readiness(self, intelligence):
        return intelligence["human"]["evidence_side_adjudication_readiness"]

    def question_codes(self, intelligence):
        return [item["code"] for item in intelligence["unresolved_questions"]]

    def limitation_codes(self, intelligence):
        return [item["code"] for item in intelligence["limitations"]]

    def test_no_evidence_state_and_no_human_blocker(self):
        result = self.intelligence()
        self.assertEqual(result["basis"], "PERSISTED_EVIDENCE_STATE")
        self.assertEqual(result["authority"], "NON_AUTHORITATIVE_REVIEW_SUPPORT")
        self.assertEqual(result["state"], "NO_EVIDENCE")
        self.assertEqual(result["automated"]["total"], 0)
        self.assertIsNone(result["automated"]["verification_run_id"])
        self.assertIsNone(result["automated"]["run_status"])
        self.assertEqual(self.readiness(result), {
            "ready": False, "basis": "CURRENT_HUMAN_EVIDENCE_REVIEW_STATE",
            "blocking_codes": ["NO_HUMAN_EVIDENCE"],
        })
        self.assertEqual(self.question_codes(result), ["NO_HUMAN_EVIDENCE"])
        self.assertEqual(self.limitation_codes(result), ["NO_EVIDENCE"])

    def test_automated_only_state_does_not_supply_human_readiness(self):
        run = self.make_run()
        self.automated(run)
        result = self.intelligence()
        self.assertEqual(result["state"], "AUTOMATED_CONTEXT_ONLY")
        self.assertEqual(result["automated"]["authority"], "CONTEXT_ONLY")
        self.assertEqual(result["automated"]["verification_run_id"], str(run.pk))
        self.assertEqual(self.readiness(result)["blocking_codes"], ["NO_HUMAN_EVIDENCE"])
        self.assertEqual(self.limitation_codes(result), [
            "AUTOMATED_EVIDENCE_CONTEXT_ONLY", "SOURCE_IDENTITY_NOT_EDITORIAL_INDEPENDENCE",
        ])

    def test_human_pending_state_has_priority_over_automated_presence(self):
        self.human()
        self.assertEqual(self.intelligence()["state"], "HUMAN_REVIEW_PENDING")
        self.automated(self.make_run())
        result = self.intelligence()
        self.assertEqual(result["state"], "HUMAN_REVIEW_PENDING")
        self.assertEqual(self.readiness(result)["blocking_codes"], ["UNREVIEWED_HUMAN_EVIDENCE"])
        self.assertIn("HUMAN_EVIDENCE_PENDING_REVIEW", self.question_codes(result))

    def test_human_review_complete_without_automated(self):
        self.human("VERIFIED")
        result = self.intelligence()
        self.assertEqual(result["state"], "HUMAN_REVIEW_COMPLETE")
        self.assertEqual(result["human"]["authority"], "REVIEWED_INPUT_NOT_FINAL_JUDGMENT")
        self.assertTrue(self.readiness(result)["ready"])
        self.assertEqual(self.readiness(result)["blocking_codes"], [])
        self.assertEqual(result["unresolved_questions"], [])
        self.assertEqual(self.limitation_codes(result), ["HUMAN_EVIDENCE_NOT_FINAL_JUDGMENT"])

    def test_human_complete_with_automated_context(self):
        self.human("VERIFIED")
        self.automated(self.make_run())
        self.assertEqual(self.intelligence()["state"], "HUMAN_REVIEW_COMPLETE_WITH_AUTOMATED_CONTEXT")

    def test_active_case_blocks_even_when_submissions_are_reviewed(self):
        self.case(self.human("VERIFIED"))
        result = self.intelligence()
        self.assertEqual(result["state"], "HUMAN_REVIEW_PENDING")
        self.assertEqual(self.readiness(result)["blocking_codes"], ["ACTIVE_EVIDENCE_CASES"])
        self.assertEqual(self.question_codes(result), ["ACTIVE_EVIDENCE_CASES"])

    def test_blocker_and_question_order_for_unreviewed_with_active_case(self):
        self.case(self.human())
        result = self.intelligence()
        self.assertEqual(self.readiness(result)["blocking_codes"], [
            "UNREVIEWED_HUMAN_EVIDENCE", "ACTIVE_EVIDENCE_CASES",
        ])
        self.assertEqual(self.question_codes(result), ["HUMAN_EVIDENCE_PENDING_REVIEW", "ACTIVE_EVIDENCE_CASES"])

    def test_all_rejected_is_ready_under_existing_readiness_rules(self):
        self.human("REJECTED")
        self.human("REJECTED")
        result = self.intelligence()
        self.assertTrue(self.readiness(result)["ready"])
        self.assertTrue(is_claim_ready_for_adjudication(self.claim))
        self.assertEqual(result["human"]["reviewed"], 2)
        self.assertEqual(result["human"]["verified"], 0)
        self.assertEqual(result["state"], "HUMAN_REVIEW_COMPLETE")

    def test_readiness_agrees_with_existing_helper_across_case_states(self):
        case = self.case(self.human("VERIFIED"))
        for status in ModerationCase.Status.values:
            with self.subTest(status=status):
                ModerationCase.objects.filter(pk=case.pk).update(status=status)
                result = self.intelligence()
                self.assertEqual(self.readiness(result)["ready"], is_claim_ready_for_adjudication(self.claim))
                self.assertEqual(result["human"]["active_evidence_cases"],
                                 int(status in {"OPEN", "IN_REVIEW", "ESCALATED", "REOPENED"}))

    def test_reviewed_counts_verified_plus_rejected_only(self):
        self.human("VERIFIED")
        self.human("VERIFIED")
        self.human("REJECTED")
        self.human()
        human = self.intelligence()["human"]
        self.assertEqual({key: human[key] for key in (
            "total", "reviewed", "verified", "rejected", "unreviewed",
        )}, {"total": 4, "reviewed": 3, "verified": 2, "rejected": 1, "unreviewed": 1})

    def test_verified_submission_types_exclude_other_review_statuses(self):
        for evidence_type in EvidenceSubmission.EvidenceType.values:
            self.human("VERIFIED", evidence_type=evidence_type)
            self.human("REJECTED", evidence_type=evidence_type)
            self.human("UNVERIFIED", evidence_type=evidence_type)
        self.assertEqual(self.intelligence()["human"]["verified_submission_type_counts"], {
            "SUPPORTS_CLAIM": 1, "CONTRADICTS_CLAIM": 1, "PROVIDES_CONTEXT": 1,
            "SOURCE_VERIFICATION": 1, "UNSPECIFIED": 0,
        })

    def test_null_blank_and_unexpected_verified_types_are_unspecified(self):
        for evidence_type in (None, "", "UNEXPECTED"):
            self.human("VERIFIED", evidence_type=evidence_type)
        self.assertEqual(self.intelligence()["human"]["verified_submission_type_counts"]["UNSPECIFIED"], 3)

    def test_evidence_verdict_does_not_affect_intelligence(self):
        item = self.human("VERIFIED", evidence_verdict="FACT")
        before = self.intelligence()
        EvidenceSubmission.objects.filter(pk=item.pk).update(evidence_verdict="FAKE")
        self.assertEqual(self.intelligence(), before)

    def test_assessment_completeness_all_persisted_combinations(self):
        run = self.make_run()
        for stance, relevance, directness, expected in (
            ("SUPPORTS", 0.0, 0.0, "fully_assessed"),
            ("CONTEXT", 0.5, 0.5, "fully_assessed"),
            ("REFUTES", None, 0.5, "partially_assessed"),
            ("SUPPORTS", 0.5, None, "partially_assessed"),
            ("CONTEXT", None, None, "partially_assessed"),
            ("UNKNOWN", 0.5, 0.5, "partially_assessed"),
            ("UNKNOWN", None, 0.5, "partially_assessed"),
            ("UNKNOWN", 0.5, None, "partially_assessed"),
            ("UNKNOWN", None, None, "unassessed"),
        ):
            with self.subTest(stance=stance, relevance=relevance, directness=directness):
                item = self.automated(run, stance=stance, relevance_score=relevance, directness_score=directness)
                result = _build_evidence_intelligence(
                    run=run, automated_evidence_links=[item], human_evidence=[], active_evidence_cases=0,
                )
                self.assertEqual(result["automated"]["assessment"], {
                    key: int(key == expected) for key in ("fully_assessed", "partially_assessed", "unassessed")
                })

    def test_recency_does_not_affect_assessment_completeness(self):
        run = self.make_run()
        full = self.automated(run, stance="SUPPORTS", relevance_score=0.8, directness_score=0.8)
        unassessed = self.automated(run)
        before = self.intelligence()
        VerificationEvidence.objects.filter(pk__in=[full.pk, unassessed.pk]).update(recency_score=1.0)
        self.assertEqual(self.intelligence(), before)

    def test_exact_stance_and_role_counts_including_unspecified(self):
        run = self.make_run()
        for stance, role in (
            ("SUPPORTS", "PRIMARY"), ("REFUTES", "SECONDARY"),
            ("CONTEXT", "FACT_CHECK"), ("UNKNOWN", "CONTEXTUAL"),
            ("SUPPORTS", None), ("UNKNOWN", ""), ("UNKNOWN", "UNEXPECTED"),
        ):
            self.automated(run, stance=stance, evidence_role=role)
        automated = self.intelligence()["automated"]
        self.assertEqual(automated["stance_counts"], {"SUPPORTS": 2, "REFUTES": 1, "CONTEXT": 1, "UNKNOWN": 3})
        self.assertEqual(automated["role_counts"], {
            "PRIMARY": 1, "SECONDARY": 1, "FACT_CHECK": 1, "CONTEXTUAL": 1, "UNSPECIFIED": 3,
        })

    def test_only_latest_run_contributes(self):
        old = self.make_run()
        canonical = CanonicalSource.objects.create(name="Older shared identity")
        self.automated(old, canonical=canonical, stance="SUPPORTS", relevance_score=1.0, directness_score=1.0)
        self.automated(old, canonical=canonical, stance="REFUTES")
        latest = self.make_run("FAILED")
        VerificationRun.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
        self.automated(latest, stance="CONTEXT", evidence_role="CONTEXTUAL")
        result = self.intelligence()
        self.assertEqual(result["automated"]["verification_run_id"], str(latest.pk))
        self.assertEqual(result["automated"]["total"], 1)
        self.assertEqual(result["automated"]["assessment"]["fully_assessed"], 0)
        self.assertEqual(result["automated"]["stance_counts"], {"SUPPORTS": 0, "REFUTES": 0, "CONTEXT": 1, "UNKNOWN": 0})
        self.assertEqual(result["automated"]["source_identity"]["shared_group_count"], 0)
        self.assertNotIn("CONFLICTING_AUTOMATED_STANCES", self.question_codes(result))

    def test_empty_latest_run_does_not_reuse_older_evidence(self):
        old = self.make_run()
        self.automated(old)
        self.make_run()
        VerificationRun.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self.intelligence()["state"], "NO_EVIDENCE")

    def test_canonical_shared_identity_and_fallback_group_counts(self):
        run = self.make_run()
        first = CanonicalSource.objects.create(name="Shared normalized identity")
        second = CanonicalSource.objects.create(name="Another normalized identity")
        for _ in range(3):
            self.automated(run, canonical=first)
        for _ in range(2):
            self.automated(run, canonical=second)
        self.automated(run)
        self.automated(run)
        result = self.intelligence()
        self.assertEqual(result["automated"]["source_identity"], {
            "group_count": 4, "shared_group_count": 2, "items_in_shared_groups": 5,
        })
        self.assertIn("SHARED_AUTOMATED_SOURCE_IDENTITY", self.question_codes(result))
        detail = next(item["detail"] for item in result["limitations"]
                      if item["code"] == "SOURCE_IDENTITY_NOT_EDITORIAL_INDEPENDENCE")
        self.assertIn("different groups are not proof of editorial independence or corroboration", detail)
        self.assertIn("must not be counted as multiple independent confirmations", detail)

    def test_same_canonical_source_is_one_shared_group(self):
        run = self.make_run()
        canonical = CanonicalSource.objects.create(name="One shared source identity")
        self.automated(run, canonical=canonical)
        self.automated(run, canonical=canonical)
        self.assertEqual(self.intelligence()["automated"]["source_identity"], {
            "group_count": 1, "shared_group_count": 1, "items_in_shared_groups": 2,
        })

    def test_conflicting_automated_signals_are_nonblocking_questions_only(self):
        run = self.make_run()
        self.automated(run, stance="SUPPORTS")
        self.automated(run, stance="REFUTES")
        result = self.intelligence()
        question = next(item for item in result["unresolved_questions"]
                        if item["code"] == "CONFLICTING_AUTOMATED_STANCES")
        self.assertFalse(question["blocking"])
        self.assertEqual(question["basis"], "LATEST_VERIFICATION_RUN")
        self.assertNotIn("verdict", result)

    def test_reviewed_type_tension_requires_both_types_to_be_verified(self):
        self.human("VERIFIED", evidence_type="SUPPORTS CLAIM")
        contradicts = self.human("REJECTED", evidence_type="CONTRADICTS CLAIM")
        self.assertNotIn("REVIEWED_SUBMISSION_TYPE_TENSION", self.question_codes(self.intelligence()))
        EvidenceSubmission.objects.filter(pk=contradicts.pk).update(evidence_status="VERIFIED")
        result = self.intelligence()
        self.assertTrue(self.readiness(result)["ready"])
        self.assertIn("REVIEWED_SUBMISSION_TYPE_TENSION", self.question_codes(result))

    def test_all_static_question_templates_and_order(self):
        self.case(self.human())
        self.human("VERIFIED", evidence_type="SUPPORTS CLAIM")
        self.human("VERIFIED", evidence_type="CONTRADICTS CLAIM")
        run = self.make_run()
        canonical = CanonicalSource.objects.create(name="Shared question identity")
        self.automated(run, canonical=canonical, stance="SUPPORTS")
        self.automated(run, canonical=canonical, stance="REFUTES")
        self.assertEqual(self.intelligence()["unresolved_questions"], [
            {"code": "HUMAN_EVIDENCE_PENDING_REVIEW", "question": "Which submitted evidence items still require human review?",
             "basis": "CURRENT_HUMAN_EVIDENCE_REVIEW_STATE", "blocking": True},
            {"code": "ACTIVE_EVIDENCE_CASES", "question": "Which active evidence-review cases must be resolved before the evidence side is adjudication-ready?",
             "basis": "CURRENT_HUMAN_EVIDENCE_REVIEW_STATE", "blocking": True},
            {"code": "AUTOMATED_EVIDENCE_ASSESSMENT_GAPS", "question": "Which persisted automated evidence items still lack a complete claim-relationship assessment?",
             "basis": "LATEST_VERIFICATION_RUN", "blocking": False},
            {"code": "SHARED_AUTOMATED_SOURCE_IDENTITY", "question": "Are multiple automated evidence items from the same source identity being treated as independent corroboration?",
             "basis": "PERSISTED_SOURCE_IDENTITY_GROUPING", "blocking": False},
            {"code": "CONFLICTING_AUTOMATED_STANCES", "question": "How should the human reviewer evaluate persisted automated evidence that includes both supporting and refuting signals?",
             "basis": "LATEST_VERIFICATION_RUN", "blocking": False},
            {"code": "REVIEWED_SUBMISSION_TYPE_TENSION", "question": "How should the adjudicator evaluate verified submissions labeled as both supporting and contradicting the claim?",
             "basis": "CURRENT_HUMAN_EVIDENCE_REVIEW_STATE", "blocking": False},
        ])

    def test_no_human_question_template_precedes_automated_gaps(self):
        self.automated(self.make_run())
        result = self.intelligence()
        self.assertEqual(result["unresolved_questions"][0], {
            "code": "NO_HUMAN_EVIDENCE",
            "question": "What human-submitted evidence should be gathered and reviewed before adjudication?",
            "basis": "CURRENT_HUMAN_EVIDENCE_REVIEW_STATE", "blocking": True,
        })
        self.assertEqual(self.question_codes(result), ["NO_HUMAN_EVIDENCE", "AUTOMATED_EVIDENCE_ASSESSMENT_GAPS"])

    def test_cached_ai_and_final_verdict_do_not_change_evidence_intelligence(self):
        self.human("VERIFIED")
        self.automated(self.make_run(), stance="SUPPORTS")
        before = self.intelligence()
        Claim.objects.filter(pk=self.claim.pk).update(
            ai_verdict="FAKE", final_verdict="FACT", consensus_score=1.0,
            ai_summary="Cached summary", ai_reasoning="Cached reasoning",
        )
        self.assertEqual(self.intelligence(), before)

    def test_noncompleted_runs_warn_without_blocking_human_readiness(self):
        self.human("REJECTED")
        run = self.make_run()
        for status in ("PENDING", "RUNNING", "FAILED", "ABSTAINED", "CANCELLED"):
            with self.subTest(status=status):
                VerificationRun.objects.filter(pk=run.pk).update(status=status, failure_message="Private diagnostic")
                result = self.intelligence()
                self.assertEqual(result["automated"]["run_status"], status)
                self.assertTrue(self.readiness(result)["ready"])
                self.assertIn("AUTOMATED_RUN_NOT_COMPLETED", self.limitation_codes(result))
                self.assertNotIn("Private diagnostic", json.dumps(result))
                self.assertNotIn("failure_message", json.dumps(result))

    def test_assessed_items_emit_non_authoritative_assessment_limitation(self):
        run = self.make_run()
        item = self.automated(run, stance="SUPPORTS", relevance_score=0.8, directness_score=0.8)
        self.assertIn("AUTOMATED_ASSESSMENTS_NON_AUTHORITATIVE", self.limitation_codes(self.intelligence()))
        VerificationEvidence.objects.filter(pk=item.pk).update(directness_score=None)
        self.assertIn("AUTOMATED_ASSESSMENTS_NON_AUTHORITATIVE", self.limitation_codes(self.intelligence()))
        VerificationEvidence.objects.filter(pk=item.pk).update(stance="UNKNOWN", relevance_score=None)
        self.assertNotIn("AUTOMATED_ASSESSMENTS_NON_AUTHORITATIVE", self.limitation_codes(self.intelligence()))

    def test_fully_assessed_context_has_no_gap_question_or_run_warning(self):
        self.human("VERIFIED")
        self.automated(self.make_run(), stance="CONTEXT", relevance_score=0.0, directness_score=0.0)
        result = self.intelligence()
        self.assertEqual(result["unresolved_questions"], [])
        self.assertEqual(self.limitation_codes(result), [
            "AUTOMATED_EVIDENCE_CONTEXT_ONLY", "AUTOMATED_ASSESSMENTS_NON_AUTHORITATIVE",
            "SOURCE_IDENTITY_NOT_EDITORIAL_INDEPENDENCE", "HUMAN_EVIDENCE_NOT_FINAL_JUDGMENT",
        ])

    def test_failed_run_without_evidence_has_no_evidence_state(self):
        self.make_run("FAILED", failure_message="Private failure")
        result = self.intelligence()
        self.assertEqual(result["state"], "NO_EVIDENCE")
        self.assertEqual(self.limitation_codes(result), ["NO_EVIDENCE", "AUTOMATED_RUN_NOT_COMPLETED"])
        self.assertFalse(self.readiness(result)["ready"])

    def test_adjudication_and_publication_do_not_change_evidence_intelligence(self):
        self.human("REJECTED")
        before = self.intelligence()
        case = ModerationCase.objects.create(
            claim=self.claim, organization=self.organization, case_type="ADJUDICATION",
            status="RESOLVED", resolution_code="FACT",
        )
        decision = AdjudicationDecision.objects.create(
            claim=self.claim, organization=self.organization, moderation_case=case,
            decided_by=self.actor, verdict="FACT", rationale="Human decision",
        )
        OfficialFactCheck.objects.create(
            claim=self.claim, organization=self.organization, adjudication_decision=decision,
            canonical_claim="Published institutional claim", headline="Institutional headline",
            verdict="FACT", summary="Institutional summary", publication_status="PUBLISHED",
            published_at=timezone.now(),
        )
        self.assertEqual(self.intelligence(), before)

    def test_new_block_has_no_verdict_or_private_source_fields(self):
        canonical = CanonicalSource.objects.create(name="Private canonical identity")
        source = EvidenceSource.objects.create(
            provider="TAVILY", canonical_source=canonical, content="Private content",
            raw_reference={"private": "payload"}, authority_score=1.0,
        )
        self.automated(self.make_run(), source=source, stance="REFUTES")
        self.human("VERIFIED", evidence_verdict="FACT")
        result = self.intelligence()
        forbidden_keys = {"verdict", "content", "raw_reference", "authority_score", "canonical_source_id"}
        def check_keys(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden_keys.intersection(value))
                for child in value.values():
                    check_keys(child)
            elif isinstance(value, list):
                for child in value:
                    check_keys(child)
        check_keys(result)
        for private in (str(canonical.pk), str(source.pk), "Private content", "payload"):
            self.assertNotIn(private, json.dumps(result))

    def test_existing_automated_evidence_payload_unchanged(self):
        run = self.make_run()
        item = self.automated(run, stance="SUPPORTS", evidence_role="PRIMARY",
                              relevance_score=0.8, directness_score=0.7, recency_score=0.6)
        source = item.evidence_source
        self.assertEqual(self.project()["automated_analysis"]["evidence"], {
            "authority": "CONTEXT_ONLY", "basis": "LATEST_VERIFICATION_RUN",
            "verification_run_id": str(run.pk), "count": 1,
            "items": [{
                "id": str(item.pk), "evidence_role": "PRIMARY", "stance": "SUPPORTS",
                "relevance_score": 0.8, "directness_score": 0.7, "recency_score": 0.6,
                "created_at": item.created_at.isoformat(),
                "source": {
                    "id": str(source.pk), "provider": source.provider, "title": source.title,
                    "publisher": source.publisher, "source_type": source.source_type,
                    "url": source.url, "canonical_url": source.canonical_url,
                    "published_at": None, "retrieved_at": source.retrieved_at.isoformat(),
                },
            }],
        })

    def test_existing_human_evidence_payload_unchanged(self):
        reviewed_at = timezone.now()
        item = self.human("VERIFIED", verified_by=self.actor, verified_at=reviewed_at,
                          evidence_type="SUPPORTS CLAIM", evidence_caption="Caption",
                          evidence_url="https://example.test/human", moderator_notes="Review notes")
        self.assertEqual(self.project()["human_evidence"], {
            "authority": "REVIEWED_INPUT_NOT_FINAL_JUDGMENT", "basis": "CURRENT_EVIDENCE_RECORDS",
            "counts": {"total": 1, "verified": 1, "rejected": 0, "unreviewed": 0, "active_evidence_cases": 0},
            "items": [{
                "id": str(item.pk), "thread_id": str(self.thread.pk), "evidence_caption": "Caption",
                "evidence_url": "https://example.test/human", "evidence_type": "SUPPORTS CLAIM",
                "evidence_status": "VERIFIED", "moderator_notes": "Review notes", "rejection_reason": None,
                "submitted_at": item.submitted_at.isoformat(), "reviewed_at": reviewed_at.isoformat(),
                "contributor": {"id": self.actor.pk, "username": self.actor.username},
                "reviewed_by": {"id": self.actor.pk, "username": self.actor.username},
            }],
        })

    def test_existing_institutional_knowledge_intelligence_unchanged(self):
        OfficialFactCheck.objects.create(
            claim=self.claim, organization=self.organization,
            canonical_claim="Published institutional proposition", headline="Published headline",
            verdict="FACT", summary="Published summary", publication_status="PUBLISHED",
            published_at=timezone.now(),
        )
        resolution = build_published_fact_check_payload(get_published_fact_check_resolution_for_claim(self.claim))
        related = get_related_published_fact_check_payloads(self.claim, limit=3)
        expected = {"authoritative_resolution": resolution, "related_publications": related,
                    "intelligence": _build_prior_knowledge_intelligence(resolution, related)}
        self.assertEqual(self.project()["institutional_knowledge"], expected)

    def test_loaded_builder_does_not_query_and_evidence_is_loaded_once(self):
        run = self.make_run()
        canonical = CanonicalSource.objects.create(name="Query-free grouping")
        self.automated(run, canonical=canonical)
        self.automated(run, canonical=canonical)
        links = list(VerificationEvidence.objects.filter(verification_run=run).select_related("evidence_source"))
        with self.assertNumQueries(0):
            _build_evidence_intelligence(run=run, automated_evidence_links=links,
                                         human_evidence=[], active_evidence_cases=0)
        with CaptureQueriesContext(connection) as queries:
            self.project()
        evidence_queries = [item for item in queries if 'FROM "api_verificationevidence"' in item["sql"]]
        self.assertEqual(len(evidence_queries), 1)
        self.assertFalse(any('FROM "api_canonicalsource"' in item["sql"] for item in queries))

    def test_authorization_and_cross_organization_scoping_unchanged(self):
        other = Organization.objects.create(name="Other evidence partner", slug="other-evidence-partner")
        self.assertEqual(self.get(other).status_code, 403)
        with self.assertRaises(VerificationIntelligenceAuthorizationError):
            self.project(organization=other)
        OrganizationMembership.objects.create(user=self.actor, organization=other, role="OWNER", status="ACTIVE")
        self.assertEqual(self.get(other).status_code, 404)
        with self.assertRaises(VerificationIntelligenceNotFound):
            self.project(organization=other)
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(role="CONTRIBUTOR")
        self.assertEqual(self.get().status_code, 403)
        safety = User.objects.create_user(username="evidence-intelligence-safety")
        safety.profile.role = UserProfile.Role.MOD
        safety.profile.save(update_fields=["role"])
        self.client.force_authenticate(safety)
        self.assertEqual(self.get().status_code, 403)

    def test_active_assignment_still_required(self):
        for status in ("AVAILABLE", "RELEASED", "COMPLETED"):
            VerificationAssignment.objects.filter(pk=self.assignment.pk).update(status=status)
            self.assertEqual(self.get().status_code, 404)
            with self.assertRaises(VerificationIntelligenceNotFound):
                self.project()

    def test_repeated_reads_are_deterministic_select_only_and_create_no_cases(self):
        self.automated(self.make_run(), stance="SUPPORTS")
        self.human("VERIFIED", evidence_type="SUPPORTS CLAIM")
        models = (
            Claim, VerificationAssignment, VerificationRun, VerificationEvidence, EvidenceSource,
            EvidenceSubmission, ModerationCase, AdjudicationDecision, OfficialFactCheck,
            ClaimFactCheckReference, KnowledgeReuseEvent, PublicReachEvent, CanonicalSource,
        )
        def state():
            return {model.__name__: list(model.objects.order_by("pk").values()) for model in models}
        before = state()
        with CaptureQueriesContext(connection) as queries:
            first, second = self.project(), self.project()
            first_get, second_get = self.get(), self.get()
        self.assertEqual(first, second)
        self.assertEqual(first_get.status_code, 200)
        self.assertEqual(second_get.status_code, 200)
        self.assertEqual(first_get.json(), first)
        self.assertEqual(second_get.json(), first)
        self.assertEqual(first["schema_version"], "1.0")
        self.assertEqual(state(), before)
        for query in queries:
            self.assertTrue(query["sql"].lstrip().upper().startswith("SELECT"), query["sql"])
        self.assertFalse(ModerationCase.objects.exists())
        self.assertFalse(AdjudicationDecision.objects.exists())
        self.assertFalse(ClaimFactCheckReference.objects.exists())
        self.assertFalse(KnowledgeReuseEvent.objects.exists())
        self.assertFalse(PublicReachEvent.objects.exists())
