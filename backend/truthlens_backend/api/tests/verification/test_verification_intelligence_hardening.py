"""Endpoint-local hardening keeps intelligence a private, passive read."""

import json
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.knowledge_reuse_service import build_query_fingerprint
from api.models import (
    AccountabilityEvent,
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    CanonicalSource,
    Claim,
    ClaimFactCheckReference,
    EvidenceSource,
    EvidenceSubmission,
    KnowledgeReuseEvent,
    ModerationCase,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OfficialFactCheckSource,
    Organization,
    OrganizationMembership,
    PublicReachEvent,
    Thread,
    UserProfile,
    VerificationAssignment,
    VerificationEvidence,
    VerificationRun,
)
from api.verification_intelligence_service import get_verification_intelligence_context
from api.views import logger


LOCKED_AUTHORITY_CONTRACT = {
    "automated_analysis": "NON_AUTHORITATIVE",
    "automated_evidence": "CONTEXT_ONLY",
    "human_evidence": "REVIEWED_INPUT_NOT_FINAL_JUDGMENT",
    "adjudication_decision": "AUTHORITATIVE_HUMAN_JUDGMENT",
    "authoritative_publication": "DURABLE_INSTITUTIONAL_KNOWLEDGE",
    "related_publications": "CONTEXT_ONLY_NO_VERDICT_TRANSFER",
}
PRIVATE_FIELDS = {
    "content", "raw_reference", "authority_score", "canonical_source",
    "canonical_source_id", "canonical_source_ids", "failure_message",
    "email", "emails", "ip", "ip_address", "request_ip", "user_agent",
    "token", "tokens", "access_token", "refresh_token", "api_key",
    "credentials", "password", "provider_payload", "private_payload",
}
ADVICE_FIELDS = {
    "recommended_verdict", "suggested_verdict", "truth_score", "decision_score",
    "confidence_to_decide", "preferred_verdict", "ranking", "recommendation",
    "verdict_recommendation", "decision_recommendation",
}


class VerificationIntelligenceHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = User.objects.create_user(
            username="hardening-lead", email="private-hardening@example.test",
        )
        self.organization = self.partner("hardening-a")
        self.other = self.partner("hardening-b")
        self.membership = OrganizationMembership.objects.create(
            user=self.actor, organization=self.organization,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="Persisted hardening claim",
            url_link="https://example.test/current-claim",
            final_verdict="FAKE", ai_verdict="FACT", ai_summary="Cached summary",
        )
        self.assignment = VerificationAssignment.objects.create(
            claim=self.claim, organization=self.organization, claimed_by=self.actor,
            claimed_at=timezone.now(), status=VerificationAssignment.Status.ACTIVE,
        )
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
            "celery.canvas.Signature.apply_async",
            "celery.app.base.Celery.send_task",
            "requests.sessions.Session.request",
            "httpx.Client.send",
            "httpx.AsyncClient.send",
            "socket.create_connection",
        ):
            self.guards.append(self.enterContext(patch(
                target, side_effect=AssertionError(f"Forbidden intelligence read: {target}"),
            )))
        # Approved helper-internal exact-canonical authority revalidation is allowed.
        # Do not guard find_exact_canonical_published_fact_check.

    def tearDown(self):
        try:
            # Also detect forbidden calls swallowed by the endpoint's 503 boundary.
            for guard in self.guards:
                guard.assert_not_called()
        finally:
            super().tearDown()

    def partner(self, slug):
        return Organization.objects.create(
            name=slug, slug=slug, public_profile_enabled=True,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    def get(self, organization=None, claim_id=None):
        url = self.url if claim_id is None else reverse(
            "verification_intelligence", kwargs={"claim_id": claim_id},
        )
        return self.client.get(url, {"organization_id": (organization or self.organization).pk})

    def project(self):
        return get_verification_intelligence_context(
            actor=self.actor, organization=self.organization, claim_id=self.claim.pk,
        )

    def assert_private_cache_policy(self, response):
        directives = {item.strip().lower() for item in response["Cache-Control"].split(",")}
        self.assertTrue({"no-store", "private", "no-cache", "must-revalidate", "max-age=0"} <= directives)
        self.assertNotIn("public", directives)
        self.assertIn("Expires", response)

    def assert_status_and_cache(self, response, expected):
        self.assertEqual(response.status_code, expected)
        self.assert_private_cache_policy(response)

    def state(self):
        # Snapshot every API model, including empty tables and sealed provenance,
        # so both row creation/deletion and changes to existing fields are detected.
        models = list(apps.get_app_config("api").get_models()) + [User]
        return {
            model._meta.label: list(model.objects.order_by("pk").values())
            for model in models
        }

    def passive_read(self, read):
        before = self.state()
        with CaptureQueriesContext(connection) as queries:
            result = read()
        self.assertEqual(self.state(), before)
        for query in queries:
            self.assertTrue(query["sql"].lstrip().upper().startswith("SELECT"), query["sql"])
        self.assertFalse(AccountabilityEvent.objects.exists())
        self.assertFalse(KnowledgeReuseEvent.objects.exists())
        self.assertFalse(PublicReachEvent.objects.exists())
        return result

    def assert_excluded_keys(self, value, forbidden):
        if isinstance(value, dict):
            self.assertFalse(forbidden.intersection(key.lower() for key in value), value.keys())
            for child in value.values():
                self.assert_excluded_keys(child, forbidden)
        elif isinstance(value, list):
            for child in value:
                self.assert_excluded_keys(child, forbidden)

    def publication(self, claim, *, headline):
        """Seed a genuinely reachable, sealed publication without invoking workflows."""
        reviewed_at = timezone.now()
        thread = Thread.objects.create(claim=claim, author=self.actor)
        evidence = EvidenceSubmission.objects.create(
            thread=thread, contributor=self.actor, evidence_status="VERIFIED",
            evidence_type="PROVIDES CONTEXT", evidence_caption="Reviewed publication input",
            evidence_url="https://example.test/publication-input",
            verified_by=self.actor, verified_at=reviewed_at,
        )
        case = ModerationCase.objects.create(
            claim=claim, organization=self.organization, case_type="ADJUDICATION",
            status="RESOLVED", resolution_code="FACT",
        )
        decision = AdjudicationDecision.objects.create(
            claim=claim, organization=self.organization, moderation_case=case,
            decided_by=self.actor, verdict="FACT",
            canonical_claim=f"Published proposition for {headline}", rationale="Human rationale",
        )
        decision_snapshot = AdjudicationDecisionEvidenceSnapshot.objects.create(
            decision=decision, claim_id=claim.pk,
            evidence_records=[{
                "id": str(evidence.pk), "thread_id": str(thread.pk),
                "evidence_status": evidence.evidence_status, "evidence_type": evidence.evidence_type,
                "evidence_caption": evidence.evidence_caption, "evidence_url": evidence.evidence_url,
                "contributor_id": str(self.actor.pk), "reviewer_id": str(self.actor.pk),
                "submitted_at": evidence.submitted_at.isoformat(), "reviewed_at": reviewed_at.isoformat(),
                "moderator_notes": evidence.moderator_notes, "rejection_reason": evidence.rejection_reason,
            }],
        )
        publication = OfficialFactCheck.objects.create(
            claim=claim, organization=self.organization, adjudication_decision=decision,
            canonical_claim=decision.canonical_claim, verdict=decision.verdict, headline=headline,
            summary="Published summary", article_body="Published article",
            publication_status="PUBLISHED", revision_kind="INITIAL", published_at=reviewed_at,
            drafted_by=self.actor, reviewed_by=self.actor, published_by=self.actor,
            submitted_for_review_at=reviewed_at, reviewed_at=reviewed_at,
        )
        OfficialFactCheckSource.objects.create(
            fact_check=publication, url="https://example.test/editorial-source",
            title="Published source", source_type="MODERATOR_ADDED",
            added_by=self.actor, is_editorially_selected=True,
        )
        OfficialFactCheckPublicationSnapshot.objects.create(
            fact_check=publication, decision_snapshot=decision_snapshot, captured_at=reviewed_at,
            payload=OfficialFactCheckPublicationSnapshot.build_payload(
                fact_check=publication, decision_snapshot=decision_snapshot,
            ),
        )
        return publication

    def populated_context(self):
        self.canonical = CanonicalSource.objects.create(name="Private normalized source identity")
        run = VerificationRun.objects.create(
            claim=self.claim, status="FAILED", failure_stage="ASSESSMENT",
            failure_code="PROVIDER_UNAVAILABLE", failure_message="PRIVATE_FAILURE_DIAGNOSTIC",
        )
        source = EvidenceSource.objects.create(
            provider="TAVILY", title="Persisted source", url="https://example.test/evidence",
            canonical_source=self.canonical, content="PRIVATE_SOURCE_CONTENT",
            raw_reference={"private": "PRIVATE_PROVIDER_PAYLOAD"}, authority_score=0.99,
        )
        VerificationEvidence.objects.create(
            verification_run=run, evidence_source=source, stance="SUPPORTS",
            evidence_role="PRIMARY", relevance_score=0.8, directness_score=0.7,
        )
        current = self.publication(self.claim, headline="Current published resolution")
        pending = EvidenceSubmission.objects.create(
            thread=Thread.objects.create(claim=self.claim, author=self.actor),
            contributor=self.actor, evidence_status="UNVERIFIED",
        )
        ModerationCase.objects.create(
            evidence_submission=pending, case_type="EVIDENCE", status="OPEN",
        )
        related = self.publication(
            Claim.objects.create(context_text="Different published proposition"),
            headline="Related published context",
        )
        ClaimFactCheckReference.objects.create(
            target_claim=self.claim, fact_check=related, relationship_kind="RELATED",
            match_method="SEMANTIC", similarity_score=0.99,
            query_fingerprint=build_query_fingerprint(self.claim.context_text),
        )
        return current, related

    def test_authenticated_success_is_private_and_never_cached(self):
        response = self.passive_read(self.get)
        self.assert_status_and_cache(response, 200)
        self.assertFalse(ClaimFactCheckReference.objects.exists())

    def test_anonymous_remains_401_and_never_cached(self):
        self.client.force_authenticate(None)
        self.assert_status_and_cache(self.passive_read(self.get), 401)

    def test_missing_and_invalid_scope_remain_validation_errors(self):
        for query in ({}, {"organization_id": "invalid"}, {"organization_id": ""}):
            with self.subTest(query=query):
                response = self.passive_read(lambda: self.client.get(self.url, query))
                self.assert_status_and_cache(response, 400)
                self.assertIn("organization_id", response.json())

    def test_absent_organization_remains_404_and_never_cached(self):
        response = self.passive_read(lambda: self.client.get(self.url, {"organization_id": uuid4()}))
        self.assert_status_and_cache(response, 404)

    def test_organization_capabilities_cannot_cross_tenants(self):
        response = self.passive_read(lambda: self.get(self.other))
        self.assert_status_and_cache(response, 403)

    def test_contributor_has_no_partner_intelligence_capability(self):
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(role="CONTRIBUTOR")
        self.assert_status_and_cache(self.passive_read(self.get), 403)

    def test_platform_safety_moderator_alone_remains_forbidden(self):
        safety = User.objects.create_user(username="hardening-safety")
        safety.profile.role = UserProfile.Role.MOD
        safety.profile.save(update_fields=["role"])
        self.client.force_authenticate(safety)
        self.assert_status_and_cache(self.passive_read(self.get), 403)

    def test_existing_qualifying_roles_retain_access(self):
        for role in ("OWNER", "ADMIN", "LEAD_VERIFIER", "MODERATOR", "RESEARCHER"):
            with self.subTest(role=role):
                OrganizationMembership.objects.filter(pk=self.membership.pk).update(role=role)
                self.assert_status_and_cache(self.passive_read(self.get), 200)

    def test_inactive_membership_revokes_access(self):
        for membership_status in ("SUSPENDED", "LEFT"):
            with self.subTest(status=membership_status):
                OrganizationMembership.objects.filter(pk=self.membership.pk).update(status=membership_status)
                self.assert_status_and_cache(self.passive_read(self.get), 403)

    def test_authorized_other_partner_cannot_see_active_work(self):
        OrganizationMembership.objects.create(
            user=self.actor, organization=self.other, role="LEAD_VERIFIER", status="ACTIVE",
        )
        response = self.passive_read(lambda: self.get(self.other))
        self.assert_status_and_cache(response, 404)
        absent = self.passive_read(lambda: self.get(self.other, claim_id=uuid4()))
        self.assert_status_and_cache(absent, 404)
        self.assertEqual(response.json(), absent.json())

    def test_nonactive_assignments_remain_not_found(self):
        for assignment_status in ("AVAILABLE", "RELEASED", "COMPLETED"):
            with self.subTest(status=assignment_status):
                VerificationAssignment.objects.filter(pk=self.assignment.pk).update(status=assignment_status)
                self.assert_status_and_cache(self.passive_read(self.get), 404)

    def test_missing_assignment_remains_not_found(self):
        self.assignment.delete()
        self.assert_status_and_cache(self.passive_read(self.get), 404)

    def test_missing_claim_remains_not_found(self):
        self.assert_status_and_cache(self.passive_read(lambda: self.get(claim_id=uuid4())), 404)

    def test_post_is_method_not_allowed_and_never_cached(self):
        response = self.passive_read(lambda: self.client.post(
            self.url, {"organization_id": str(self.organization.pk)}, format="json",
        ))
        self.assert_status_and_cache(response, 405)

    def test_unexpected_projection_failure_is_logged_bounded_503(self):
        self.populated_context()
        references_before = ClaimFactCheckReference.objects.count()
        private_diagnostic = "PRIVATE_RUNTIME_DIAGNOSTIC credential=secret database=internal"
        with self.assertLogs("api.views", level="ERROR") as logs, patch(
            "api.views.logger.exception", wraps=logger.exception,
        ) as log_exception, patch(
            "api.views.get_verification_intelligence_context",
            side_effect=RuntimeError(private_diagnostic),
        ) as projection:
            first, second = self.passive_read(lambda: (self.get(), self.get()))
        projection.assert_called_with(
            actor=self.actor, organization=self.organization, claim_id=self.claim.pk,
        )
        self.assertEqual(projection.call_count, 2)
        self.assertEqual(log_exception.call_count, 2)
        log_exception.assert_called_with("Verification intelligence projection failed.")
        self.assertTrue(any("RuntimeError" in item for item in logs.output))
        for response in (first, second):
            self.assert_status_and_cache(response, 503)
            self.assertEqual(response.json(), {
                "detail": "Verification intelligence is temporarily unavailable.",
            })
            self.assertNotIn(private_diagnostic, response.content.decode())
            self.assert_excluded_keys(response.json(), PRIVATE_FIELDS | ADVICE_FIELDS)
        self.assertEqual(ClaimFactCheckReference.objects.count(), references_before)

    def test_known_authorization_error_is_403_without_failure_logging(self):
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(role="CONTRIBUTOR")
        with self.assertNoLogs("api.views", level="ERROR"):
            response = self.passive_read(self.get)
        self.assert_status_and_cache(response, 403)
        self.assertEqual(response.json(), {
            "detail": "You do not have permission to view verification work for this organization.",
        })

    def test_known_not_found_error_is_404_without_failure_logging(self):
        VerificationAssignment.objects.filter(pk=self.assignment.pk).update(status="COMPLETED")
        with self.assertNoLogs("api.views", level="ERROR"):
            response = self.passive_read(self.get)
        self.assert_status_and_cache(response, 404)
        self.assertEqual(response.json(), {"detail": "Active verification work not found."})

    def test_repeated_successes_are_deterministic_and_leave_all_rows_unchanged(self):
        self.populated_context()
        references_before = ClaimFactCheckReference.objects.count()
        first, second, projection = self.passive_read(lambda: (self.get(), self.get(), self.project()))
        self.assert_status_and_cache(first, 200)
        self.assert_status_and_cache(second, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json(), projection)
        self.assertEqual(ClaimFactCheckReference.objects.count(), references_before)
        self.assertEqual(ModerationCase.objects.count(), 3)
        self.assertEqual(AdjudicationDecision.objects.count(), 2)

    def test_rejected_reads_create_no_events_references_or_domain_changes(self):
        denied = self.passive_read(lambda: (self.get(self.other), self.get(self.other)))
        for response in denied:
            self.assert_status_and_cache(response, 403)
        missing = self.passive_read(lambda: (self.get(claim_id=uuid4()), self.get(claim_id=uuid4())))
        for response in missing:
            self.assert_status_and_cache(response, 404)
        self.assertFalse(ClaimFactCheckReference.objects.exists())

    def test_rejected_reads_leave_populated_domain_rows_unchanged(self):
        self.populated_context()
        responses = self.passive_read(lambda: (self.get(self.other), self.get(claim_id=uuid4())))
        for response, expected in zip(responses, (403, 404)):
            self.assert_status_and_cache(response, expected)
        self.assertEqual(ClaimFactCheckReference.objects.count(), 1)

    def test_approved_exact_canonical_revalidation_remains_a_passive_read(self):
        publication = self.publication(
            Claim.objects.create(context_text="Previously published canonical proposition"),
            headline="Exact canonical prior resolution",
        )
        ClaimFactCheckReference.objects.create(
            target_claim=self.claim, fact_check=publication, relationship_kind="AUTHORITATIVE",
            match_method="EXACT_CANONICAL",
            query_fingerprint=build_query_fingerprint(publication.canonical_claim),
        )
        first, second = self.passive_read(lambda: (self.get(), self.get()))
        self.assert_status_and_cache(first, 200)
        self.assert_status_and_cache(second, 200)
        self.assertEqual(first.json(), second.json())
        knowledge = first.json()["institutional_knowledge"]
        self.assertEqual(knowledge["authoritative_resolution"]["fact_check_id"], str(publication.pk))
        self.assertEqual(knowledge["intelligence"]["authoritative"]["why_surfaced"]["code"],
                         "EXACT_CANONICAL_AUTHORITY")
        self.assertEqual(ClaimFactCheckReference.objects.count(), 1)

    def test_response_recursively_excludes_private_fields_and_values(self):
        self.populated_context()
        response = self.passive_read(self.get)
        self.assert_status_and_cache(response, 200)
        payload = response.json()
        self.assert_excluded_keys(payload, PRIVATE_FIELDS)
        serialized = json.dumps(payload)
        for value in (
            self.actor.email, str(self.canonical.pk), "PRIVATE_SOURCE_CONTENT",
            "PRIVATE_PROVIDER_PAYLOAD", "PRIVATE_FAILURE_DIAGNOSTIC",
        ):
            self.assertNotIn(value, serialized)

    def test_response_has_no_recommendation_or_verdict_advice(self):
        self.populated_context()
        response = self.passive_read(self.get)
        self.assert_status_and_cache(response, 200)
        payload = response.json()
        self.assert_excluded_keys(payload, ADVICE_FIELDS)
        self.assert_excluded_keys(payload["evidence_intelligence"], {"verdict", "evidence_verdict"})
        self.assertNotIn("final_verdict", payload["claim"])

    def test_related_intelligence_never_transfers_verdict(self):
        _, related = self.populated_context()
        response = self.passive_read(self.get)
        self.assert_status_and_cache(response, 200)
        knowledge = response.json()["institutional_knowledge"]
        self.assertEqual(len(knowledge["related_publications"]), 1)
        self.assertEqual(len(knowledge["intelligence"]["related"]), 1)
        entry = knowledge["intelligence"]["related"][0]
        self.assertEqual(entry["fact_check_id"], str(related.pk))
        self.assertEqual(entry["authority"], "CONTEXT_ONLY_NO_VERDICT_TRANSFER")
        self.assertEqual(entry["permitted_use"], "BACKGROUND_CONTEXT_ONLY")
        self.assertEqual(entry["why_surfaced"]["code"], "RELATED_SEMANTIC")
        self.assert_excluded_keys(entry, {"verdict", "summary"} | ADVICE_FIELDS)
        self.assert_excluded_keys(knowledge["related_publications"], {"verdict", "summary"})

    def test_locked_schema_and_authority_contract_are_unchanged(self):
        self.populated_context()
        response = self.passive_read(self.get)
        self.assert_status_and_cache(response, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(set(payload), {
            "schema_version", "claim", "workflow", "automated_analysis", "human_evidence",
            "adjudication", "institutional_knowledge", "evidence_intelligence",
            "authority_contract", "limitations",
        })
        self.assertEqual(payload["authority_contract"], LOCKED_AUTHORITY_CONTRACT)
        self.assertEqual(payload["automated_analysis"]["authority"], "NON_AUTHORITATIVE")
        self.assertEqual(payload["automated_analysis"]["evidence"]["authority"], "CONTEXT_ONLY")
        self.assertEqual(payload["human_evidence"]["authority"], "REVIEWED_INPUT_NOT_FINAL_JUDGMENT")
        self.assertEqual(payload["adjudication"]["authority"], "AUTHORITATIVE_HUMAN_JUDGMENT")
        self.assertIsNotNone(payload["adjudication"]["current_decision"])
        self.assertEqual(payload["institutional_knowledge"]["intelligence"]["authoritative"]["authority"],
                         "DURABLE_INSTITUTIONAL_KNOWLEDGE")

    def test_reads_with_no_persisted_intelligence_do_not_schedule_or_generate_it(self):
        first, second, projection = self.passive_read(lambda: (self.get(), self.get(), self.project()))
        self.assert_status_and_cache(first, 200)
        self.assert_status_and_cache(second, 200)
        self.assertEqual(first.json(), projection)
        self.assertEqual(first.json(), second.json())
        self.assertFalse(VerificationRun.objects.exists())
        self.assertFalse(VerificationEvidence.objects.exists())
        self.assertFalse(ClaimFactCheckReference.objects.exists())
        self.assertFalse(ModerationCase.objects.exists())
        self.assertFalse(AdjudicationDecision.objects.exists())
        for guard in self.guards:
            guard.assert_not_called()
