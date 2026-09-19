"""Explain persisted publication provenance without retrieval or authority changes."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.knowledge_reuse_service import (
    build_published_fact_check_payload,
    build_query_fingerprint,
    get_published_fact_check_resolution_for_claim,
    get_related_published_fact_check_payloads,
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
    VerificationAssignment,
    VerificationEvidence,
    VerificationRun,
)
from api.verification_intelligence_service import (
    VerificationIntelligenceAuthorizationError,
    VerificationIntelligenceNotFound,
    _build_prior_knowledge_intelligence,
    get_verification_intelligence_context,
)


class PriorInstitutionalKnowledgeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = User.objects.create_user(username="prior-knowledge-lead")
        self.organization = Organization.objects.create(
            name="Prior Knowledge Partner", slug="prior-knowledge-partner",
            public_profile_enabled=True,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.membership = OrganizationMembership.objects.create(
            user=self.actor, organization=self.organization,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="Current claim with no inferred authority",
            final_verdict="FAKE", ai_verdict="FACT", consensus_score=1.0,
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
            "api.knowledge_reuse_service.find_published_fact_check_candidates",
            "api.knowledge_reuse_service.find_published_fact_check_match",
            "api.knowledge_reuse_service.find_unique_equivalent_published_fact_check_match",
            "api.knowledge_reuse_service.generate_embedding",
            "api.embedding_service.generate_embedding",
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
            "requests.sessions.Session.request",
            "httpx.Client.send",
            "httpx.AsyncClient.send",
        ):
            self.guards.append(self.enterContext(patch(
                target, side_effect=AssertionError(f"Forbidden prior-knowledge call: {target}"),
            )))
        # Do not guard find_exact_canonical_published_fact_check: the approved
        # resolution helper must perform its real internal authority revalidation.

    def tearDown(self):
        try:
            for guard in self.guards:
                guard.assert_not_called()
        finally:
            super().tearDown()

    def project(self, **overrides):
        values = {"actor": self.actor, "organization": self.organization,
                  "claim_id": self.claim.pk}
        values.update(overrides)
        return get_verification_intelligence_context(**values)

    def knowledge(self):
        return self.project()["institutional_knowledge"]

    def get(self, organization=None):
        return self.client.get(self.url, {
            "organization_id": (organization or self.organization).pk,
        })

    def publication(self, **overrides):
        values = {
            "claim": Claim.objects.create(context_text="Previously published institutional proposition"),
            "organization": self.organization,
            "canonical_claim": "Previously published institutional proposition",
            "headline": "Prior institutional publication", "verdict": "MISLEADING",
            "summary": "Published institutional summary",
            "publication_status": OfficialFactCheck.PublicationStatus.PUBLISHED,
            "published_at": timezone.now(),
        }
        values.update(overrides)
        return OfficialFactCheck.objects.create(**values)

    def reference(self, publication, **overrides):
        values = {
            "target_claim": self.claim, "fact_check": publication,
            "relationship_kind": "AUTHORITATIVE", "match_method": "EXACT_CANONICAL",
            "query_fingerprint": build_query_fingerprint(publication.canonical_claim),
        }
        values.update(overrides)
        return ClaimFactCheckReference.objects.create(**values)

    def allow_public_detail(self):
        # Only article reachability is mocked; relationship filtering, authority
        # resolution, exact-canonical revalidation, and payload builders stay real.
        def detail(*, organization, publication_id):
            publication = OfficialFactCheck.objects.get(pk=publication_id)
            return {
                "selected_publication_id": str(publication.pk),
                "organization": {"name": organization.name, "slug": organization.slug},
                "article": {"headline": publication.headline},
                "published_at": publication.published_at.isoformat(),
            }
        return self.enterContext(patch(
            "api.knowledge_reuse_service.get_public_partner_fact_check_detail",
            side_effect=detail,
        ))

    def codes(self, intelligence):
        return [item["code"] for item in intelligence["limitations"]]

    def test_no_prior_knowledge_ignores_claim_cache_and_ai(self):
        knowledge = self.knowledge()
        intelligence = knowledge["intelligence"]
        self.assertEqual(intelligence["basis"], "PERSISTED_INSTITUTIONAL_PROVENANCE")
        self.assertEqual(intelligence["state"], "NO_PRIOR_INSTITUTIONAL_KNOWLEDGE")
        self.assertEqual(intelligence["summary"], {
            "authoritative_resolution_available": False,
            "related_publication_count": 0, "prior_knowledge_available": False,
        })
        self.assertIsNone(intelligence["authoritative"])
        self.assertEqual(intelligence["related"], [])
        self.assertEqual(self.codes(intelligence), ["NO_PRIOR_INSTITUTIONAL_KNOWLEDGE"])

    def test_related_only_state_and_limitations(self):
        self.reference(self.publication(), relationship_kind="RELATED", match_method="SEMANTIC")
        self.allow_public_detail()
        intelligence = self.knowledge()["intelligence"]
        self.assertEqual(intelligence["state"], "RELATED_CONTEXT_ONLY")
        self.assertEqual(intelligence["summary"], {
            "authoritative_resolution_available": False,
            "related_publication_count": 1, "prior_knowledge_available": True,
        })
        self.assertIsNone(intelligence["authoritative"])
        self.assertEqual(self.codes(intelligence), [
            "NO_AUTHORITATIVE_RESOLUTION", "RELATED_PUBLICATIONS_CONTEXT_ONLY",
        ])

    def test_direct_published_record_supplies_authority(self):
        publication = self.publication(claim=self.claim)
        knowledge = self.knowledge()
        intelligence = knowledge["intelligence"]
        self.assertEqual(intelligence["state"], "AUTHORITATIVE_RESOLUTION")
        self.assertEqual(intelligence["authoritative"], {
            "authority": "DURABLE_INSTITUTIONAL_KNOWLEDGE",
            "fact_check_id": str(publication.pk), "match_method": "CLAIM_CACHE",
            "why_surfaced": {
                "code": "DIRECT_PUBLISHED_CLAIM",
                "detail": "The current claim has a current published institutional fact-check. "
                          "Authority comes from that published institutional record.",
            },
            "permitted_use": "AUTHORITATIVE_RESOLUTION",
        })
        self.assertEqual(knowledge["authoritative_resolution"]["verdict"], "MISLEADING")
        self.assertEqual(intelligence["limitations"], [])
        self.assertEqual(intelligence["summary"], {
            "authoritative_resolution_available": True,
            "related_publication_count": 0, "prior_knowledge_available": True,
        })

    def test_direct_publication_with_related_context(self):
        self.publication(claim=self.claim)
        self.reference(self.publication(canonical_claim="Another contextual proposition"),
                       relationship_kind="RELATED", match_method="FULL_TEXT")
        self.allow_public_detail()
        intelligence = self.knowledge()["intelligence"]
        self.assertEqual(intelligence["state"], "AUTHORITATIVE_WITH_RELATED_CONTEXT")
        self.assertEqual(intelligence["summary"]["related_publication_count"], 1)
        self.assertEqual(self.codes(intelligence), ["RELATED_PUBLICATIONS_CONTEXT_ONLY"])

    def test_exact_canonical_durable_authority_uses_real_revalidation(self):
        publication = self.publication()
        self.reference(publication)
        knowledge = self.knowledge()
        authoritative = knowledge["intelligence"]["authoritative"]
        self.assertEqual(authoritative["why_surfaced"]["code"], "EXACT_CANONICAL_AUTHORITY")
        self.assertIn("durable contract", authoritative["why_surfaced"]["detail"])
        self.assertEqual(authoritative["fact_check_id"], str(publication.pk))
        self.assertEqual(knowledge["intelligence"]["state"], "AUTHORITATIVE_RESOLUTION")

    def test_exact_canonical_ambiguity_still_fails_closed(self):
        publication = self.publication()
        self.reference(publication)
        self.publication(verdict="FACT")
        knowledge = self.knowledge()
        self.assertIsNone(knowledge["authoritative_resolution"])
        self.assertIsNone(knowledge["intelligence"]["authoritative"])
        self.assertEqual(knowledge["intelligence"]["state"], "NO_PRIOR_INSTITUTIONAL_KNOWLEDGE")

    def test_exact_canonical_invalid_fingerprint_still_fails_closed(self):
        self.reference(self.publication(), query_fingerprint=build_query_fingerprint("Different proposition"))
        self.assertIsNone(self.knowledge()["intelligence"]["authoritative"])

    def test_equivalent_claim_explains_stored_authority_not_score(self):
        publication = self.publication()
        reference = self.reference(publication, match_method="EQUIVALENT_CLAIM", similarity_score=0.01)
        intelligence = self.knowledge()["intelligence"]
        authoritative = intelligence["authoritative"]
        self.assertEqual(authoritative["why_surfaced"]["code"], "EQUIVALENT_CLAIM_AUTHORITY")
        self.assertIn("published institutional record supplies the verdict",
                      authoritative["why_surfaced"]["detail"])
        self.assertIn("similarity score alone does not supply authority",
                      authoritative["why_surfaced"]["detail"])
        ClaimFactCheckReference.objects.filter(pk=reference.pk).update(similarity_score=1.0)
        self.assertEqual(self.knowledge()["intelligence"], intelligence)

    def test_non_authoritative_methods_cannot_resolve_despite_high_score(self):
        reference = self.reference(self.publication(), match_method="SEMANTIC", similarity_score=1.0)
        for method in ("SEMANTIC", "FULL_TEXT", "EXACT_HEADLINE"):
            with self.subTest(method=method):
                ClaimFactCheckReference.objects.filter(pk=reference.pk).update(match_method=method)
                knowledge = self.knowledge()
                self.assertIsNone(knowledge["authoritative_resolution"])
                self.assertIsNone(knowledge["intelligence"]["authoritative"])

    def test_all_related_methods_are_context_only_and_verdict_free(self):
        publication = self.publication()
        reference = self.reference(publication, relationship_kind="RELATED")
        self.allow_public_detail()
        for method, code, warning in (
            ("EXACT_CANONICAL", "RELATED_EXACT_CANONICAL", "Exact canonical text"),
            ("EXACT_HEADLINE", "RELATED_EXACT_HEADLINE", "Headline equality"),
            ("SEMANTIC", "RELATED_SEMANTIC", "Semantic similarity does not establish proposition equivalence"),
            ("FULL_TEXT", "RELATED_FULL_TEXT", "Full-text relevance does not establish proposition equivalence"),
        ):
            with self.subTest(method=method):
                ClaimFactCheckReference.objects.filter(pk=reference.pk).update(match_method=method)
                knowledge = self.knowledge()
                intelligence = knowledge["intelligence"]
                entry = intelligence["related"][0]
                self.assertEqual(intelligence["state"], "RELATED_CONTEXT_ONLY")
                self.assertIsNone(intelligence["authoritative"])
                self.assertEqual(entry["authority"], "CONTEXT_ONLY_NO_VERDICT_TRANSFER")
                self.assertEqual(entry["permitted_use"], "BACKGROUND_CONTEXT_ONLY")
                self.assertEqual(entry["why_surfaced"]["code"], code)
                self.assertIn(warning, entry["why_surfaced"]["detail"])
                self.assertIn("does not transfer", entry["why_surfaced"]["detail"])
                self.assertNotIn("verdict", entry)
                self.assertNotIn("summary", entry)
                self.assertNotIn("state", entry)
                for key in ("fact_check_id", "headline", "published_at", "organization", "match_method"):
                    self.assertEqual(entry[key], knowledge["related_publications"][0][key])

    def test_related_maximum_three_and_original_payloads_preserved(self):
        for index in range(5):
            publication = self.publication(canonical_claim=f"Distinct contextual proposition {index}")
            reference = self.reference(publication, relationship_kind="RELATED", match_method="FULL_TEXT")
            ClaimFactCheckReference.objects.filter(pk=reference.pk).update(
                created_at=timezone.now() + timedelta(days=index),
            )
        self.allow_public_detail()
        expected = get_related_published_fact_check_payloads(self.claim, limit=3)
        knowledge = self.knowledge()
        self.assertEqual(knowledge["related_publications"], expected)
        intelligence = knowledge["intelligence"]
        self.assertEqual(intelligence["summary"]["related_publication_count"], 3)
        self.assertEqual([item["fact_check_id"] for item in intelligence["related"]],
                         [item["fact_check_id"] for item in expected])

    def test_existing_authoritative_payload_preserved_for_all_supported_methods(self):
        publication = self.publication()
        reference = self.reference(publication)
        for method in ("EXACT_CANONICAL", "EQUIVALENT_CLAIM", "CLAIM_CACHE"):
            with self.subTest(method=method):
                if method == "CLAIM_CACHE":
                    publication = self.publication(claim=self.claim,
                                                   canonical_claim="Direct publication proposition")
                else:
                    ClaimFactCheckReference.objects.filter(pk=reference.pk).update(match_method=method)
                expected = build_published_fact_check_payload(
                    get_published_fact_check_resolution_for_claim(self.claim),
                )
                self.assertEqual(self.knowledge()["authoritative_resolution"], expected)
                self.assertEqual(expected["match_method"], method)

    def test_hidden_publication_statuses_do_not_supply_intelligence(self):
        publication = self.publication()
        self.reference(publication)
        for status in ("DRAFT", "IN_REVIEW", "ARCHIVED"):
            OfficialFactCheck.objects.filter(pk=publication.pk).update(publication_status=status)
            self.assertEqual(self.knowledge()["intelligence"]["state"], "NO_PRIOR_INSTITUTIONAL_KNOWLEDGE")

    def test_repeated_projection_and_gets_are_deterministic_and_read_only(self):
        self.reference(self.publication())
        self.reference(self.publication(canonical_claim="A related proposition"),
                       relationship_kind="RELATED", match_method="SEMANTIC")
        self.allow_public_detail()
        models = (
            Claim, VerificationAssignment, VerificationRun, VerificationEvidence, EvidenceSource,
            EvidenceSubmission, ModerationCase, AdjudicationDecision, OfficialFactCheck,
            ClaimFactCheckReference, KnowledgeReuseEvent, PublicReachEvent,
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
        self.assertEqual(state(), before)
        for query in queries:
            self.assertTrue(query["sql"].lstrip().upper().startswith("SELECT"), query["sql"])
        self.assertEqual(ClaimFactCheckReference.objects.count(), 2)
        self.assertFalse(KnowledgeReuseEvent.objects.exists())
        self.assertFalse(PublicReachEvent.objects.exists())

    def test_organization_authorization_and_active_scope_preserved(self):
        other = Organization.objects.create(name="Other intelligence partner", slug="other-intelligence")
        self.assertEqual(self.get(other).status_code, 403)
        with self.assertRaises(VerificationIntelligenceAuthorizationError):
            self.project(organization=other)
        OrganizationMembership.objects.create(user=self.actor, organization=other, role="OWNER", status="ACTIVE")
        self.assertEqual(self.get(other).status_code, 404)
        with self.assertRaises(VerificationIntelligenceNotFound):
            self.project(organization=other)
        VerificationAssignment.objects.filter(pk=self.assignment.pk).update(status="COMPLETED")
        self.assertEqual(self.get().status_code, 404)
        with self.assertRaises(VerificationIntelligenceNotFound):
            self.project()

    def test_contributor_still_has_no_access(self):
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(role="CONTRIBUTOR")
        self.assertEqual(self.get().status_code, 403)


class PriorKnowledgeExplanationBuilderTests(SimpleTestCase):
    """Payload-only tests forbid database access, including enrichment queries."""

    def related(self, method="SEMANTIC"):
        return {
            "fact_check_id": str(uuid4()), "headline": "Context headline",
            "published_at": "2026-09-18T00:00:00+00:00", "match_method": method,
            "organization": {"name": "Public partner", "slug": "public-partner",
                             "public_profile_available": True},
        }

    def test_unsupported_authoritative_method_fails_closed_without_changing_payload(self):
        for method in ("SEMANTIC", "FULL_TEXT", "EXACT_HEADLINE", "UNKNOWN", None):
            with self.subTest(method=method):
                resolution = {"fact_check_id": str(uuid4()), "match_method": method,
                              "verdict": "FACT", "similarity_score": 1.0}
                before = deepcopy(resolution)
                intelligence = _build_prior_knowledge_intelligence(resolution, [])
                self.assertIsNone(intelligence["authoritative"])
                self.assertEqual(intelligence["limitations"], [{
                    "code": "UNSUPPORTED_AUTHORITATIVE_MATCH_METHOD",
                    "detail": "The authoritative payload's match method has no supported explanation.",
                }])
                self.assertEqual(resolution, before)
                # State/availability report approved helper output, not a new
                # authority determination at the explanation layer.
                self.assertEqual(intelligence["state"], "AUTHORITATIVE_RESOLUTION")

    def test_unknown_related_method_is_omitted_from_explanations_only(self):
        publications = [self.related("UNKNOWN"), self.related(), self.related(None)]
        before = deepcopy(publications)
        intelligence = _build_prior_knowledge_intelligence(None, publications)
        self.assertEqual(intelligence["state"], "RELATED_CONTEXT_ONLY")
        self.assertIsNone(intelligence["authoritative"])
        self.assertEqual(intelligence["summary"]["related_publication_count"], 3)
        self.assertEqual(len(intelligence["related"]), 1)
        self.assertEqual([item["code"] for item in intelligence["limitations"]], [
            "NO_AUTHORITATIVE_RESOLUTION", "RELATED_PUBLICATIONS_CONTEXT_ONLY",
            "UNSUPPORTED_RELATED_MATCH_METHOD",
        ])
        self.assertEqual(publications, before)

    def test_builder_ignores_scores_ai_and_extra_related_fields(self):
        publication = self.related()
        publication.update(verdict="FACT", summary="Must not transfer", similarity_score=1.0,
                           source_count=100, ai_verdict="FACT", final_verdict="FACT")
        intelligence = _build_prior_knowledge_intelligence(None, [publication])
        entry = intelligence["related"][0]
        self.assertEqual(set(entry), {
            "authority", "fact_check_id", "headline", "published_at", "organization",
            "match_method", "why_surfaced", "permitted_use",
        })
        self.assertEqual(entry["authority"], "CONTEXT_ONLY_NO_VERDICT_TRANSFER")
        self.assertEqual(intelligence["state"], "RELATED_CONTEXT_ONLY")

    def test_builder_is_deterministic_and_does_not_mutate_inputs(self):
        resolution = {"fact_check_id": str(uuid4()), "match_method": "EQUIVALENT_CLAIM"}
        publications = [self.related("EXACT_CANONICAL"), self.related("FULL_TEXT")]
        before = deepcopy((resolution, publications))
        self.assertEqual(_build_prior_knowledge_intelligence(resolution, publications),
                         _build_prior_knowledge_intelligence(resolution, publications))
        self.assertEqual((resolution, publications), before)
