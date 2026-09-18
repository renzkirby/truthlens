"""Persisted intelligence context: scoped authority and strictly read-only access."""

import json
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.knowledge_reuse_service import (
    build_published_fact_check_payload,
    build_query_fingerprint,
    get_published_fact_check_resolution_for_claim,
)
from api.models import (
    AdjudicationDecision,
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
    AUTHORITY_CONTRACT,
    VerificationIntelligenceAuthorizationError,
    VerificationIntelligenceNotFound,
    get_verification_intelligence_context,
)


class VerificationIntelligenceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = User.objects.create_user(username="intelligence-lead")
        self.organization = self.partner("intelligence-a")
        self.other = self.partner("intelligence-b")
        self.membership = OrganizationMembership.objects.create(
            user=self.actor,
            organization=self.organization,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="Persisted claim context",
            url_link="https://example.test/claim",
            source_link="https://example.test/source",
            media_url="https://example.test/media",
            final_verdict="FAKE",
            ai_verdict="UNVERIFIED",
            ai_summary="Cached summary",
            ai_reasoning="Cached reasoning",
            consensus_score=0.4,
            score_context="Cached score context",
            source_type="AUTOMATED",
            is_ai_generated=True,
        )
        self.assignment = VerificationAssignment.objects.create(
            claim=self.claim,
            organization=self.organization,
            claimed_by=self.actor,
            claimed_at=timezone.now(),
            status=VerificationAssignment.Status.ACTIVE,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.actor)
        self.url = reverse(
            "verification_intelligence", kwargs={"claim_id": self.claim.pk}
        )
        self.guards = []
        for target in (
            "api.services.call_llm_with_fallback",
            "api.services.assess_claim_equivalence",
            "api.services.gemini_client.models.generate_content",
            "api.services.groq_client.chat.completions.create",
            "api.verification.providers.tavily.TavilyProvider.search_with_payload",
            "api.verification.providers.tavily.TavilyProvider.search",
            "api.verification.providers.google_fact_check.GoogleFactCheckProvider.search_with_payload",
            "api.verification.providers.google_fact_check.GoogleFactCheckProvider.search",
            "api.ocr_service.extract_text_from_image",
            "api.ocr_adapter.extract_text_with_provider_adapter",
            "api.embedding_service.generate_embedding",
            "api.knowledge_reuse_service.generate_embedding",
            "api.knowledge_reuse_service.find_published_fact_check_candidates",
            "api.knowledge_reuse_service.find_published_fact_check_match",
            "api.knowledge_reuse_service.index_published_fact_check",
            "api.knowledge_reuse_service.record_knowledge_reuse",
            "api.knowledge_reuse_service.record_authoritative_claim_fact_check_reference",
            "api.knowledge_reuse_service.record_equivalent_claim_fact_check_reference",
            "api.knowledge_reuse_service.record_related_claim_fact_check_reference",
            "api.models.Claim.compute_final_verdict",
            "requests.sessions.Session.request",
            "httpx.Client.send",
            "httpx.AsyncClient.send",
        ):
            self.guards.append(
                self.enterContext(
                    patch(
                        target,
                        side_effect=AssertionError(
                            f"Forbidden read-projection call: {target}"
                        ),
                    )
                )
            )

    def partner(self, slug):
        return Organization.objects.create(
            name=slug,
            slug=slug,
            public_profile_enabled=True,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    def project(self, **overrides):
        kwargs = {
            "actor": self.actor,
            "organization": self.organization,
            "claim_id": self.claim.pk,
        }
        kwargs.update(overrides)
        return get_verification_intelligence_context(**kwargs)

    def get(self, **scope):
        return self.client.get(
            self.url, scope or {"organization_id": self.organization.pk}
        )

    def codes(self, result):
        return [item["code"] for item in result["limitations"]]

    def make_run(self, status="COMPLETED", **fields):
        return VerificationRun.objects.create(claim=self.claim, status=status, **fields)

    def human_evidence(self, status="UNVERIFIED", **fields):
        thread = Thread.objects.create(claim=self.claim, author=self.actor)
        return EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.actor,
            evidence_status=status,
            **fields,
        )

    def decision(self, organization=None, case_organization=None, **fields):
        organization = organization or self.organization
        case = ModerationCase.objects.create(
            claim=self.claim,
            organization=case_organization or organization,
            case_type=ModerationCase.CaseType.ADJUDICATION,
            status=ModerationCase.Status.RESOLVED,
            resolution_code="FACT",
        )
        return AdjudicationDecision.objects.create(
            claim=self.claim,
            organization=organization,
            moderation_case=case,
            decided_by=self.actor,
            verdict="FACT",
            canonical_claim="Human canonical claim",
            rationale="Human rationale",
            **fields,
        )

    def publication(self, **fields):
        values = {
            "claim": Claim.objects.create(
                context_text="Canonical published proposition"
            ),
            "organization": self.organization,
            "canonical_claim": "Canonical published proposition",
            "headline": "Published headline",
            "verdict": "FACT",
            "summary": "Published summary",
            "publication_status": OfficialFactCheck.PublicationStatus.PUBLISHED,
            "published_at": timezone.now(),
        }
        values.update(fields)
        return OfficialFactCheck.objects.create(**values)

    def reference(self, publication, **fields):
        values = {
            "target_claim": self.claim,
            "fact_check": publication,
            "relationship_kind": "AUTHORITATIVE",
            "match_method": "EXACT_CANONICAL",
            "query_fingerprint": build_query_fingerprint(publication.canonical_claim),
        }
        values.update(fields)
        return ClaimFactCheckReference.objects.create(**values)

    def test_unauthenticated_endpoint(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.get().status_code, 401)

    def test_missing_invalid_and_absent_scope(self):
        self.assertEqual(self.client.get(self.url).status_code, 400)
        self.assertEqual(self.get(organization_id="invalid").status_code, 400)
        self.assertEqual(self.get(organization_id=uuid4()).status_code, 404)

    def test_contributor_is_forbidden(self):
        self.membership.role = OrganizationMembership.Role.CONTRIBUTOR
        self.membership.save(update_fields=["role"])
        self.assertEqual(self.get().status_code, 403)
        with self.assertRaises(VerificationIntelligenceAuthorizationError):
            self.project()

    def test_platform_safety_alone_is_forbidden(self):
        safety = User.objects.create_user(username="intelligence-safety")
        safety.profile.role = UserProfile.Role.MOD
        safety.profile.save(update_fields=["role"])
        self.client.force_authenticate(safety)
        self.assertEqual(self.get().status_code, 403)

    def test_capability_does_not_cross_organization_scope(self):
        self.assertEqual(self.get(organization_id=self.other.pk).status_code, 403)
        with self.assertRaises(VerificationIntelligenceAuthorizationError):
            self.project(organization=self.other)

    def test_authorized_other_organization_cannot_see_assignment(self):
        OrganizationMembership.objects.create(
            user=self.actor,
            organization=self.other,
            role="LEAD_VERIFIER",
            status="ACTIVE",
        )
        self.assertEqual(self.get(organization_id=self.other.pk).status_code, 404)
        with self.assertRaises(VerificationIntelligenceNotFound):
            self.project(organization=self.other)

    def test_active_assignment_is_required(self):
        for assignment_status in ("AVAILABLE", "RELEASED", "COMPLETED"):
            with self.subTest(status=assignment_status):
                VerificationAssignment.objects.filter(pk=self.assignment.pk).update(
                    status=assignment_status,
                )
                self.assertEqual(self.get().status_code, 404)
        VerificationAssignment.objects.filter(pk=self.assignment.pk).delete()
        self.assertEqual(self.get().status_code, 404)
        with self.assertRaises(VerificationIntelligenceNotFound):
            self.project(claim_id=uuid4())

    def test_all_workload_roles_are_allowed(self):
        for role in ("OWNER", "ADMIN", "LEAD_VERIFIER", "MODERATOR", "RESEARCHER"):
            with self.subTest(role=role):
                OrganizationMembership.objects.filter(pk=self.membership.pk).update(
                    role=role
                )
                self.assertEqual(self.get().status_code, 200)

    def test_inactive_membership_revokes_access(self):
        for status in ("SUSPENDED", "LEFT"):
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(
                status=status
            )
            self.assertEqual(self.get().status_code, 403)
        with self.assertRaises(VerificationIntelligenceAuthorizationError):
            self.project(actor=AnonymousUser())
        with self.assertRaises(VerificationIntelligenceAuthorizationError):
            self.project(organization=None)

    def test_response_shape_claim_and_authority_contract(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "claim",
                "workflow",
                "automated_analysis",
                "human_evidence",
                "adjudication",
                "institutional_knowledge",
                "authority_contract",
                "limitations",
            },
        )
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["authority_contract"], AUTHORITY_CONTRACT)
        self.assertEqual(
            set(result["claim"]),
            {
                "id",
                "claim_type",
                "context_text",
                "url_link",
                "source_link",
                "media_url",
                "last_updated",
            },
        )
        self.assertEqual(result["claim"]["context_text"], self.claim.context_text)
        self.assertNotIn("final_verdict", json.dumps(result))
        self.assertIsNone(result["adjudication"]["current_decision"])
        self.assertEqual(
            result["workflow"]["assignment"]["claimed_by"],
            {"id": self.actor.pk, "username": self.actor.username},
        )

    def test_cached_analysis_is_non_authoritative(self):
        block = self.project()["automated_analysis"]
        self.assertEqual(block["authority"], "NON_AUTHORITATIVE")
        snapshot = block["claim_snapshot"]
        self.assertEqual(snapshot["basis"], "CLAIM_CACHED_AUTOMATED_ANALYSIS")
        for name in (
            "ai_verdict",
            "ai_summary",
            "ai_reasoning",
            "consensus_score",
            "score_context",
            "source_type",
            "is_ai_generated",
        ):
            self.assertEqual(snapshot[name], getattr(self.claim, name))

    def test_no_run_has_empty_evidence_and_limitation(self):
        result = self.project()
        self.assertIsNone(result["automated_analysis"]["latest_run"])
        self.assertEqual(
            result["automated_analysis"]["evidence"],
            {
                "authority": "CONTEXT_ONLY",
                "basis": "LATEST_VERIFICATION_RUN",
                "verification_run_id": None,
                "count": 0,
                "items": [],
            },
        )
        self.assertEqual(
            self.codes(result),
            [
                "NO_VERIFICATION_RUN",
                "NO_CURRENT_ADJUDICATION",
                "NO_AUTHORITATIVE_PUBLICATION",
            ],
        )

    def test_latest_completed_run_and_timestamp_tie_are_deterministic(self):
        older = self.make_run(id=UUID(int=3))
        selected = self.make_run(
            id=UUID(int=1),
            pipeline_version="persisted-version",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        timestamp = timezone.now()
        VerificationRun.objects.filter(pk__in=[older.pk, selected.pk]).update(
            created_at=timestamp
        )
        result = self.project()
        latest = result["automated_analysis"]["latest_run"]
        self.assertEqual(latest["id"], str(selected.pk))
        self.assertEqual(latest["pipeline_version"], "persisted-version")
        self.assertEqual(latest["created_at"], timestamp.isoformat())
        self.assertNotIn("LATEST_RUN_NOT_COMPLETED", self.codes(result))
        self.assertEqual(self.project(), result)

    def test_latest_noncompleted_run_not_previous_success_is_projected(self):
        self.make_run()
        for index, status in enumerate(
            ("FAILED", "ABSTAINED", "PENDING", "RUNNING", "CANCELLED")
        ):
            with self.subTest(status=status):
                run = self.make_run(
                    status,
                    failure_stage="OCR",
                    failure_code="PROVIDER_UNAVAILABLE",
                    failure_message="Private provider diagnostic",
                )
                VerificationRun.objects.filter(pk=run.pk).update(
                    created_at=timezone.now() + timedelta(days=index + 1),
                )
                result = self.project()
                latest = result["automated_analysis"]["latest_run"]
                self.assertEqual(latest["status"], status)
                self.assertEqual(latest["failure_stage"], "OCR")
                self.assertEqual(latest["failure_code"], "PROVIDER_UNAVAILABLE")
                self.assertNotIn("failure_message", json.dumps(result))
                self.assertNotIn("Private provider diagnostic", json.dumps(result))
                self.assertIn("LATEST_RUN_NOT_COMPLETED", self.codes(result))

    def test_automated_evidence_only_latest_run_and_safe_source_fields(self):
        old, latest = self.make_run(), self.make_run()
        VerificationRun.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        source = EvidenceSource.objects.create(
            provider="TAVILY",
            title="Persisted source",
            publisher="Publisher",
            url="https://example.test/evidence",
            canonical_url="https://example.test/canonical",
            content="Private full content",
            raw_reference={"secret": "payload"},
            authority_score=0.9,
        )
        VerificationEvidence.objects.create(
            verification_run=old, evidence_source=source
        )
        item = VerificationEvidence.objects.create(
            verification_run=latest,
            evidence_source=source,
            stance="REFUTES",
            evidence_role="PRIMARY",
            relevance_score=0.8,
            directness_score=0.5,
            recency_score=0.2,
        )
        block = self.project()["automated_analysis"]["evidence"]
        self.assertEqual(block["verification_run_id"], str(latest.pk))
        self.assertEqual(block["count"], 1)
        self.assertEqual(block["items"][0]["id"], str(item.pk))
        self.assertEqual(block["items"][0]["stance"], "REFUTES")
        self.assertEqual(
            set(block["items"][0]["source"]),
            {
                "id",
                "provider",
                "title",
                "publisher",
                "source_type",
                "url",
                "canonical_url",
                "published_at",
                "retrieved_at",
            },
        )
        for private in ("content", "raw_reference", "authority_score"):
            self.assertNotIn(private, block["items"][0]["source"])

    def test_human_evidence_counts_and_review_context(self):
        reviewed_at = timezone.now()
        verified = self.human_evidence(
            "VERIFIED",
            verified_by=self.actor,
            verified_at=reviewed_at,
            moderator_notes="Reviewed notes",
            evidence_caption="Caption",
        )
        self.human_evidence(
            "REJECTED",
            verified_by=self.actor,
            verified_at=reviewed_at,
            rejection_reason="IRRELEVANT",
        )
        unreviewed = self.human_evidence()
        ModerationCase.objects.create(
            case_type="EVIDENCE",
            evidence_submission=unreviewed,
            status="OPEN",
        )
        ModerationCase.objects.create(
            case_type="EVIDENCE",
            evidence_submission=verified,
            status="RESOLVED",
        )
        ModerationCase.objects.create(
            case_type="SAFETY", thread=verified.thread, status="OPEN"
        )
        unrelated_claim = Claim.objects.create()
        unrelated_thread = Thread.objects.create(
            claim=unrelated_claim, author=self.actor
        )
        unrelated = EvidenceSubmission.objects.create(
            thread=unrelated_thread, contributor=self.actor
        )
        ModerationCase.objects.create(
            case_type="EVIDENCE", evidence_submission=unrelated, status="OPEN"
        )
        block = self.project()["human_evidence"]
        self.assertEqual(block["authority"], "REVIEWED_INPUT_NOT_FINAL_JUDGMENT")
        self.assertEqual(block["basis"], "CURRENT_EVIDENCE_RECORDS")
        self.assertEqual(
            block["counts"],
            {
                "total": 3,
                "verified": 1,
                "rejected": 1,
                "unreviewed": 1,
                "active_evidence_cases": 1,
            },
        )
        item = next(item for item in block["items"] if item["id"] == str(verified.pk))
        self.assertEqual(item["reviewed_at"], reviewed_at.isoformat())
        self.assertEqual(
            item["reviewed_by"], {"id": self.actor.pk, "username": self.actor.username}
        )
        self.assertEqual(item["moderator_notes"], "Reviewed notes")
        self.assertNotIn("evidence_verdict", item)
        pending = next(
            item for item in block["items"] if item["id"] == str(unreviewed.pk)
        )
        self.assertIsNone(pending["reviewed_at"])
        self.assertIsNone(pending["reviewed_by"])
        self.assertEqual(
            [item["id"] for item in block["items"]],
            [
                str(item.pk)
                for item in EvidenceSubmission.objects.filter(
                    thread__claim=self.claim,
                ).order_by("submitted_at", "id")
            ],
        )

    def test_active_evidence_case_statuses(self):
        evidence = self.human_evidence()
        case = ModerationCase.objects.create(
            case_type="EVIDENCE", evidence_submission=evidence
        )
        for status in ModerationCase.Status.values:
            ModerationCase.objects.filter(pk=case.pk).update(status=status)
            expected = int(status in {"OPEN", "IN_REVIEW", "ESCALATED", "REOPENED"})
            self.assertEqual(
                self.project()["human_evidence"]["counts"]["active_evidence_cases"],
                expected,
            )

    def test_current_attributable_decision(self):
        run = self.make_run()
        decision = self.decision(verification_run=run)
        result = self.project()
        block = result["adjudication"]
        self.assertEqual(block["authority"], "AUTHORITATIVE_HUMAN_JUDGMENT")
        current = block["current_decision"]
        self.assertEqual(current["id"], str(decision.pk))
        self.assertEqual(current["verdict"], "FACT")
        self.assertEqual(current["organization_id"], str(self.organization.pk))
        self.assertEqual(current["verification_run_id"], str(run.pk))
        self.assertEqual(
            current["provenance"],
            {"status": "HUMAN_ADJUDICATION", "is_attributable": True},
        )
        self.assertNotIn("NO_CURRENT_ADJUDICATION", self.codes(result))
        self.assertEqual(
            result["workflow"]["adjudication_case"]["id"],
            str(decision.moderation_case_id),
        )

    def test_missing_and_unattributable_decisions_are_null(self):
        self.assertIsNone(self.project()["adjudication"]["current_decision"])
        decision = self.decision()
        ModerationCase.objects.filter(pk=decision.moderation_case_id).update(
            status="OPEN"
        )
        result = self.project()
        self.assertIsNone(result["adjudication"]["current_decision"])
        self.assertIn("NO_CURRENT_ADJUDICATION", self.codes(result))

    def test_cross_organization_decision_and_case_are_hidden(self):
        decision = self.decision(organization=self.other)
        result = self.project()
        self.assertIsNone(result["adjudication"]["current_decision"])
        self.assertIsNone(result["workflow"]["adjudication_case"])
        self.assertNotIn("Human rationale", json.dumps(result))
        AdjudicationDecision.objects.filter(pk=decision.pk).update(
            organization=self.organization
        )
        self.assertIsNone(self.project()["adjudication"]["current_decision"])

    def test_noncurrent_history_is_not_exposed(self):
        self.decision(is_current=False)
        result = self.project()
        self.assertIsNone(result["adjudication"]["current_decision"])
        self.assertNotIn("Human rationale", json.dumps(result))

    def test_legacy_decision_uses_existing_historical_provenance(self):
        decision = AdjudicationDecision.objects.create(
            claim=self.claim,
            organization=self.organization,
            decided_by=self.actor,
            verdict="FACT",
            decision_source="LEGACY_MIGRATION",
        )
        self.assertIsNone(self.project()["adjudication"]["current_decision"])
        Thread.objects.create(
            claim=self.claim,
            author=self.actor,
            moderated_by=self.actor,
            moderator_verdict="FACT",
        )
        current = self.project()["adjudication"]["current_decision"]
        self.assertEqual(current["id"], str(decision.pk))
        self.assertEqual(
            current["provenance"],
            {"status": "LEGACY_HUMAN_REVIEW", "is_attributable": True},
        )

    def test_user_summaries_do_not_expose_account_information(self):
        self.human_evidence("VERIFIED", verified_by=self.actor)
        self.decision()
        result = self.project()
        summaries = [
            result["workflow"]["assignment"]["claimed_by"],
            result["adjudication"]["current_decision"]["decided_by"],
            result["human_evidence"]["items"][0]["contributor"],
            result["human_evidence"]["items"][0]["reviewed_by"],
        ]
        for summary in summaries:
            self.assertEqual(set(summary), {"id", "username"})

    def test_workflow_case_is_scoped_to_claim_and_organization(self):
        own = ModerationCase.objects.create(
            claim=self.claim, organization=self.organization, case_type="ADJUDICATION"
        )
        ModerationCase.objects.create(
            claim=self.claim,
            organization=self.other,
            case_type="ADJUDICATION",
            status="RESOLVED",
        )
        ModerationCase.objects.create(
            claim=Claim.objects.create(),
            organization=self.organization,
            case_type="ADJUDICATION",
        )
        self.assertEqual(
            self.project()["workflow"]["adjudication_case"]["id"], str(own.pk)
        )

    def test_authoritative_resolution_uses_durable_helper(self):
        publication = self.publication()
        reference = self.reference(publication)
        expected = build_published_fact_check_payload(
            get_published_fact_check_resolution_for_claim(self.claim)
        )
        result = self.project()
        self.assertEqual(
            result["institutional_knowledge"]["authoritative_resolution"], expected
        )
        self.assertEqual(expected["verdict"], "FACT")
        self.assertNotIn("NO_AUTHORITATIVE_PUBLICATION", self.codes(result))
        self.assertEqual(ClaimFactCheckReference.objects.count(), 1)
        self.assertTrue(
            ClaimFactCheckReference.objects.filter(pk=reference.pk).exists()
        )
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_invalid_durable_authority_does_not_transfer_verdict(self):
        publication = self.publication()
        reference = self.reference(publication, query_fingerprint="0" * 64)
        self.assertIsNone(
            self.project()["institutional_knowledge"]["authoritative_resolution"]
        )
        ClaimFactCheckReference.objects.filter(pk=reference.pk).update(
            query_fingerprint=build_query_fingerprint(publication.canonical_claim),
            match_method="SEMANTIC",
        )
        self.assertIsNone(
            self.project()["institutional_knowledge"]["authoritative_resolution"]
        )

    def test_related_publications_keep_existing_context_only_contract(self):
        publications = [
            self.publication(canonical_claim=f"Related proposition {index}")
            for index in range(4)
        ]
        for publication in publications:
            self.reference(
                publication, relationship_kind="RELATED", match_method="SEMANTIC"
            )

        # Isolate public article reachability; durable reference lookup and payload
        # construction remain real, including eligibility and the limit of three.
        def public_detail(*, organization, publication_id):
            publication = OfficialFactCheck.objects.get(pk=publication_id)
            return {
                "selected_publication_id": str(publication_id),
                "organization": {"name": organization.name, "slug": organization.slug},
                "article": {"headline": publication.headline},
                "published_at": publication.published_at.isoformat(),
            }

        with patch(
            "api.knowledge_reuse_service.get_public_partner_fact_check_detail",
            side_effect=public_detail,
        ):
            result = self.project()
        knowledge = result["institutional_knowledge"]
        self.assertIsNone(knowledge["authoritative_resolution"])
        self.assertEqual(len(knowledge["related_publications"]), 3)
        for item in knowledge["related_publications"]:
            self.assertNotIn("verdict", item)
            self.assertNotIn("summary", item)
        self.assertEqual(
            result["authority_contract"]["related_publications"],
            "CONTEXT_ONLY_NO_VERDICT_TRANSFER",
        )
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_repeated_gets_are_select_only_and_leave_state_unchanged(self):
        self.make_run("FAILED", failure_message="Private diagnostic")
        self.human_evidence("VERIFIED", verified_by=self.actor)
        self.decision()
        self.reference(self.publication())
        models = (
            Claim,
            VerificationAssignment,
            VerificationRun,
            VerificationEvidence,
            EvidenceSource,
            EvidenceSubmission,
            ModerationCase,
            AdjudicationDecision,
            OfficialFactCheck,
            ClaimFactCheckReference,
            KnowledgeReuseEvent,
            PublicReachEvent,
        )

        def state():
            return {
                model.__name__: list(model.objects.order_by("pk").values())
                for model in models
            }

        before = state()
        with CaptureQueriesContext(connection) as queries:
            first, second = self.get(), self.get()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(state(), before)
        for query in queries:
            self.assertTrue(
                query["sql"].lstrip().upper().startswith("SELECT"), query["sql"]
            )
        self.assertFalse(KnowledgeReuseEvent.objects.exists())
        self.assertEqual(ClaimFactCheckReference.objects.count(), 1)
        for guard in self.guards:
            guard.assert_not_called()

    def test_no_run_read_does_not_create_references_or_accounting(self):
        self.project()
        self.assertEqual(self.get().status_code, 200)
        self.assertFalse(ClaimFactCheckReference.objects.exists())
        self.assertFalse(KnowledgeReuseEvent.objects.exists())
        self.assertFalse(PublicReachEvent.objects.exists())
        self.assertFalse(VerificationRun.objects.exists())
        for guard in self.guards:
            guard.assert_not_called()
