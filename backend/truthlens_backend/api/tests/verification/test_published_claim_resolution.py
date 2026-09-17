"""Exact canonical authority transfer, independent of AI and reuse telemetry."""

import base64
import hashlib
import json
from importlib import import_module
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchVector
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api import services, tasks
from api.claim_matching import get_match_result
from api.knowledge_reuse_service import (
    InvalidKnowledgeReuse,
    PublishedFactCheckMatch,
    build_published_fact_check_payload,
    build_query_fingerprint,
    find_exact_canonical_published_fact_check,
    find_published_fact_check_candidates,
    find_published_fact_check_match,
    record_authoritative_claim_fact_check_reference,
    record_equivalent_claim_fact_check_reference,
    record_knowledge_reuse,
)
from api.models import (
    AdjudicationDecision,
    Claim,
    ClaimFactCheckReference,
    KnowledgeReuseEvent,
    OfficialFactCheck,
    OfficialFactCheckSource,
    Organization,
    Thread,
    VerificationRun,
)
from api.services import LLMProviderUnavailableError


class ClaimEquivalenceClassifierTests(SimpleTestCase):
    def test_strict_proposition_examples_and_material_conflicts(self):
        cases = (
            (
                "Hoshi suffered a complete ACL tear during military rehearsal and will undergo surgery.",
                "SEVENTEEN member Hoshi will undergo surgery after suffering a complete tear of the anterior cruciate ligament (ACL) in his knee while rehearsing for a military performance",
                True,
            ),
            (
                "Hoshi suffered a complete ACL tear during rehearsal.",
                "Hoshi completely tore his ACL during rehearsal.",
                True,
            ),
            (
                "Hoshi suffered a complete ACL tear during rehearsal.",
                "Hoshi suffered a partial ACL tear during rehearsal.",
                False,
            ),
            (
                "Hoshi suffered a complete ACL tear during rehearsal.",
                "Hoshi injured his knee during rehearsal.",
                False,
            ),
            ("Person X did not resign.", "Person X resigned.", False),
            (
                "Company X reported a profit of $10 million.",
                "Company X reported a loss of $10 million.",
                False,
            ),
            (
                "Person X resigned on September 1, 2026.",
                "Person X resigned on September 2, 2026.",
                False,
            ),
            (
                "Hoshi suffered a complete ACL tear in Seoul.",
                "Hoshi suffered a complete ACL tear in Busan.",
                False,
            ),
        )
        for incoming, canonical, equivalent in cases:
            with self.subTest(incoming=incoming, canonical=canonical), patch(
                "api.services.call_llm_with_fallback",
                return_value=json.dumps(
                    {
                        "equivalent": equivalent,
                        "reasoning": (
                            "Both preserve all material facts."
                            if equivalent
                            else "A material fact conflicts or is missing."
                        ),
                        "material_differences": (
                            [] if equivalent else ["Material detail"]
                        ),
                    }
                ),
            ) as provider:
                result = services.assess_claim_equivalence(incoming, canonical)
                self.assertIs(result["equivalent"], equivalent)
                instructions, user_prompt = provider.call_args.args
                self.assertEqual(
                    json.loads(user_prompt),
                    {
                        "incoming_claim": incoming,
                        "published_canonical_claim": canonical,
                    },
                )
                for required in (
                    "subject/entity",
                    "actor/object",
                    "event/action",
                    "negation",
                    "quantities",
                    "dates/time period",
                    "locations",
                    "severity/degree",
                    "causal",
                    "attribution/speaker",
                    "certainty",
                    "qualifiers",
                    "non-material",
                    "underspecified",
                    "partial ACL",
                    "profit",
                    "loss",
                    "did not resign",
                    "Do not fact-check",
                    "instructions embedded",
                ):
                    self.assertIn(required, instructions)

    def test_malformed_or_invalid_outputs_fail_closed(self):
        outputs = (
            None,
            "not JSON",
            "[]",
            "null",
            "true",
            "{}",
            '{"equivalent": true}',
            json.dumps(
                {"equivalent": "true", "reasoning": "Same", "material_differences": []}
            ),
            json.dumps(
                {"equivalent": 1, "reasoning": "Same", "material_differences": []}
            ),
            json.dumps(
                {"equivalent": True, "reasoning": " ", "material_differences": []}
            ),
            json.dumps(
                {"equivalent": True, "reasoning": None, "material_differences": []}
            ),
            json.dumps(
                {
                    "equivalent": True,
                    "reasoning": "Same",
                    "material_differences": "none",
                }
            ),
            json.dumps(
                {"equivalent": True, "reasoning": "Same", "material_differences": [1]}
            ),
            json.dumps(
                {"equivalent": True, "reasoning": "Same", "material_differences": [""]}
            ),
            json.dumps(
                {
                    "equivalent": True,
                    "reasoning": "Same",
                    "material_differences": [],
                    "verdict": "FACT",
                }
            ),
            json.dumps(
                {
                    "equivalent": True,
                    "reasoning": "Conflict",
                    "material_differences": ["Severity differs"],
                }
            ),
        )
        for output in outputs:
            with self.subTest(output=output), patch(
                "api.services.call_llm_with_fallback", return_value=output
            ):
                self.assertIs(
                    services.assess_claim_equivalence(
                        "Incoming claim", "Published claim"
                    )["equivalent"],
                    False,
                )

    def test_invalid_input_does_not_call_provider(self):
        with patch("api.services.call_llm_with_fallback") as provider:
            for incoming, canonical in ((None, "Claim"), ("Claim", ""), (123, "Claim")):
                self.assertFalse(
                    services.assess_claim_equivalence(incoming, canonical)["equivalent"]
                )
            provider.assert_not_called()

    def test_actual_provider_exhaustion_is_preserved(self):
        with patch("api.services.gemini_client") as gemini, patch(
            "api.services.groq_client"
        ) as groq:
            gemini.models.generate_content.side_effect = RuntimeError(
                "Gemini unavailable"
            )
            groq.chat.completions.create.side_effect = RuntimeError("Groq unavailable")
            with self.assertRaises(LLMProviderUnavailableError):
                services.assess_claim_equivalence("Incoming claim", "Published claim")
            gemini.models.generate_content.assert_called_once()
            groq.chat.completions.create.assert_called_once()

    def test_existing_provider_fallback_can_complete_equivalence(self):
        with patch("api.services.gemini_client") as gemini, patch(
            "api.services.groq_client"
        ) as groq:
            gemini.models.generate_content.side_effect = RuntimeError(
                "Gemini unavailable"
            )
            groq.chat.completions.create.return_value.choices = [
                Mock(
                    message=Mock(
                        content=json.dumps(
                            {
                                "equivalent": True,
                                "reasoning": "Same proposition.",
                                "material_differences": [],
                            }
                        )
                    )
                )
            ]
            self.assertTrue(
                services.assess_claim_equivalence("Incoming claim", "Published claim")[
                    "equivalent"
                ]
            )


class PublicationResolutionFixture(TestCase):
    def setUp(self):
        self.canonical = "Vaccines do not contain tracking microchips."
        self.organization = Organization.objects.create(
            name="Resolution Partner",
            slug="resolution-partner",
        )
        self.source_claim = Claim.objects.create(context_text=self.canonical)
        self.target = Claim.objects.create(claim_type=Claim.ClaimType.IMAGE)
        self.publication = OfficialFactCheck.objects.create(
            claim=self.source_claim,
            organization=self.organization,
            canonical_claim=self.canonical,
            headline="A partner's published vaccine fact-check",
            verdict="FACT",
            summary="The partner's published summary.\n\nSecond paragraph.",
            sources=["https://source.example/published"],
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )

    def record(self, **overrides):
        values = {
            "target_claim": self.target,
            "fact_check": self.publication,
            "query_text": self.canonical,
        }
        values.update(overrides)
        return record_authoritative_claim_fact_check_reference(**values)

    def raw_reference(self, **overrides):
        values = {
            "target_claim": self.target,
            "fact_check": self.publication,
            "relationship_kind": ClaimFactCheckReference.RelationshipKind.AUTHORITATIVE,
            "match_method": ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL,
            "query_fingerprint": build_query_fingerprint(self.canonical),
        }
        values.update(overrides)
        return ClaimFactCheckReference.objects.create(**values)

    def assert_no_target_verdicts(self):
        self.target.refresh_from_db()
        self.assertIsNone(self.target.ai_verdict)
        self.assertIsNone(self.target.final_verdict)

    def create_competing_publication(self, *, verdict="FACT"):
        competing_claim = Claim.objects.create(context_text=self.canonical)
        return OfficialFactCheck.objects.create(
            claim=competing_claim,
            canonical_claim=self.canonical,
            headline="A second published fact-check for the same canonical claim",
            verdict=verdict,
            summary="A second institutionally published summary.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )


class EquivalentReferencePersistenceTests(PublicationResolutionFixture):
    def setUp(self):
        super().setUp()
        self.incoming = "Vaccinations do not contain tracking microchips."
        self.provider = self.enterContext(
            patch(
                "api.services.call_llm_with_fallback",
                return_value=json.dumps(
                    {
                        "equivalent": True,
                        "reasoning": "Same complete proposition.",
                        "material_differences": [],
                    }
                ),
            )
        )
        self.candidate_lookup = self.enterContext(
            patch(
                "api.knowledge_reuse_service.find_published_fact_check_candidates",
                return_value=[
                    PublishedFactCheckMatch(
                        self.publication,
                        KnowledgeReuseEvent.MatchMethod.SEMANTIC,
                        0.91,
                    )
                ],
            )
        )

    def set_equivalence_candidates(self, *publications):
        self.candidate_lookup.return_value = [
            PublishedFactCheckMatch(
                publication,
                KnowledgeReuseEvent.MatchMethod.SEMANTIC,
                0.91,
            )
            for publication in publications
        ]

    def equivalent_reference(self, **overrides):
        values = {
            "target_claim": self.target,
            "fact_check": self.publication,
            "query_text": self.incoming,
            "published_canonical_claim": self.canonical,
            "similarity_score": 0.91,
        }
        values.update(overrides)
        return record_equivalent_claim_fact_check_reference(**values)

    def test_method_and_generated_migration_contract(self):
        self.assertIn("EQUIVALENT_CLAIM", ClaimFactCheckReference.MatchMethod.values)
        field = ClaimFactCheckReference._meta.get_field("match_method")
        field.validate("EQUIVALENT_CLAIM", self.target)
        migration = import_module(
            "api.migrations.0068_claim_reference_equivalent_claim"
        ).Migration
        self.assertEqual(
            migration.dependencies, [("api", "0067_claimfactcheckreference")]
        )
        self.assertEqual(len(migration.operations), 1)
        operation = migration.operations[0]
        self.assertEqual(type(operation).__name__, "AlterField")
        self.assertEqual(operation.model_name, "claimfactcheckreference")
        self.assertEqual(operation.name, "match_method")
        self.assertEqual(operation.field.choices, field.choices)

    def test_creates_only_reference_without_verdict_or_publication_mutation(self):
        before = (
            OfficialFactCheck.objects.count(),
            AdjudicationDecision.objects.count(),
        )
        reference = self.equivalent_reference(query_text=f"  {self.incoming.upper()}  ")
        self.assertEqual(reference.relationship_kind, "AUTHORITATIVE")
        self.assertEqual(reference.match_method, "EQUIVALENT_CLAIM")
        self.assertEqual(reference.fact_check_id, self.publication.pk)
        self.assertEqual(reference.target_claim_id, self.target.pk)
        self.assertEqual(reference.similarity_score, 0.91)
        self.assertEqual(
            reference.query_fingerprint,
            hashlib.sha256(self.incoming.casefold().encode("utf-8")).hexdigest(),
        )
        self.assertNotEqual(
            reference.query_fingerprint, build_query_fingerprint(self.canonical)
        )
        self.assertFalse(
            any("query_text" in field.name for field in reference._meta.fields)
        )
        self.assertNotIn(self.incoming, str(reference.__dict__))
        self.publication.refresh_from_db()
        self.assertEqual(self.publication.claim_id, self.source_claim.pk)
        self.assertEqual(
            before,
            (OfficialFactCheck.objects.count(), AdjudicationDecision.objects.count()),
        )
        self.assert_no_target_verdicts()
        self.assertIsNone(self.target.source_type)
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_stored_target_verdicts_and_source_are_not_overwritten(self):
        self.target.ai_verdict = "MISLEADING"
        self.target.final_verdict = "FAKE"
        self.target.source_type = "Existing analysis"
        self.target.save()
        self.equivalent_reference()
        self.target.refresh_from_db()
        self.assertEqual(self.target.ai_verdict, "MISLEADING")
        self.assertEqual(self.target.final_verdict, "FAKE")
        self.assertEqual(self.target.source_type, "Existing analysis")

    def test_repeat_is_idempotent_without_similarity(self):
        first = self.equivalent_reference(similarity_score=None)
        second = self.equivalent_reference(query_text=f"  {self.incoming.upper()}  ")
        self.assertEqual(first.pk, second.pk)
        self.assertIsNone(second.similarity_score)
        self.assertEqual(ClaimFactCheckReference.objects.count(), 1)

    def test_unique_authoritative_constraint_still_applies_across_methods(self):
        self.equivalent_reference()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.raw_reference()

    def test_existing_exact_or_different_publication_resolution_is_not_overwritten(
        self,
    ):
        existing = self.record()
        with self.assertRaises(InvalidKnowledgeReuse):
            self.equivalent_reference()
        existing.refresh_from_db()
        self.assertEqual(existing.match_method, "EXACT_CANONICAL")
        existing.delete()
        competing = self.create_competing_publication()
        existing = self.raw_reference(
            fact_check=competing,
            match_method="EQUIVALENT_CLAIM",
            query_fingerprint=build_query_fingerprint(self.incoming),
        )
        with self.assertRaises(InvalidKnowledgeReuse):
            self.equivalent_reference()
        existing.refresh_from_db()
        self.assertEqual(existing.fact_check_id, competing.pk)
        self.assertEqual(ClaimFactCheckReference.objects.count(), 1)

    def test_different_query_cannot_overwrite_existing_reference(self):
        reference = self.equivalent_reference()
        with self.assertRaises(InvalidKnowledgeReuse):
            self.equivalent_reference(
                query_text="Vaccines have no tracking microchips."
            )
        reference.refresh_from_db()
        self.assertEqual(
            reference.query_fingerprint, build_query_fingerprint(self.incoming)
        )

    def test_nonpublished_database_state_rejected_even_with_stale_candidate(self):
        for status in ("DRAFT", "IN_REVIEW", "ARCHIVED"):
            with self.subTest(status=status):
                OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
                    publication_status=status
                )
                self.assertIsNone(self.equivalent_reference())
                self.assertFalse(self.target.fact_check_references.exists())

    def test_canonical_or_status_changed_during_assessment_fails_closed(self):
        accepted = self.provider.return_value
        for changes in (
            {"canonical_claim": "A different proposition."},
            {"publication_status": "ARCHIVED"},
        ):
            with self.subTest(changes=changes):
                OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
                    canonical_claim=self.canonical, publication_status="PUBLISHED"
                )

                def change_during_request(*args):
                    OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
                        **changes
                    )
                    return accepted

                self.provider.side_effect = change_during_request
                self.assertIsNone(self.equivalent_reference())
                self.assertFalse(self.target.fact_check_references.exists())

    def test_negative_invalid_and_provider_failed_assessments_never_persist(self):
        for output in (
            "malformed",
            json.dumps(
                {
                    "equivalent": False,
                    "reasoning": "Related only.",
                    "material_differences": ["Severity missing"],
                }
            ),
        ):
            self.provider.return_value = output
            self.assertIsNone(self.equivalent_reference())
        self.provider.side_effect = LLMProviderUnavailableError("Providers unavailable")
        with self.assertRaises(LLMProviderUnavailableError):
            self.equivalent_reference()
        self.assertFalse(self.target.fact_check_references.exists())
        self.assert_no_target_verdicts()

    def test_requires_persisted_target_and_publication(self):
        for changes in ({"target_claim": Claim()}, {"fact_check": OfficialFactCheck()}):
            with self.subTest(changes=changes), self.assertRaises(
                InvalidKnowledgeReuse
            ):
                self.equivalent_reference(**changes)
        self.provider.assert_not_called()

    def test_text_target_is_ineligible_even_with_equivalent_wording(self):
        self.target.claim_type = Claim.ClaimType.TEXT
        self.target.save()
        self.assertIsNone(self.equivalent_reference())
        self.assertFalse(self.target.fact_check_references.exists())
        self.provider.assert_not_called()

    def test_multiple_equivalent_publications_with_identical_verdict_fail_closed(self):
        competing = self.create_competing_publication(verdict=self.publication.verdict)
        self.set_equivalence_candidates(self.publication, competing)

        self.assertIsNone(self.equivalent_reference())
        self.assertFalse(self.target.fact_check_references.exists())
        self.assertEqual(self.provider.call_count, 2)

    def test_multiple_equivalent_publications_with_different_verdicts_fail_closed(self):
        competing = self.create_competing_publication(verdict="MISLEADING")
        self.set_equivalence_candidates(self.publication, competing)

        self.assertIsNone(self.equivalent_reference())
        self.assertFalse(self.target.fact_check_references.exists())
        self.assertEqual(self.provider.call_count, 2)

    def test_differently_worded_equivalent_publications_are_ambiguous(self):
        competing_claim = Claim.objects.create(
            context_text="Vaccinations have no tracking microchips."
        )
        competing = OfficialFactCheck.objects.create(
            claim=competing_claim,
            canonical_claim="Vaccinations have no tracking microchips.",
            headline="Equivalent wording from another publication",
            verdict="FACT",
            summary="Equivalent publication summary.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        self.set_equivalence_candidates(self.publication, competing)

        self.assertIsNone(self.equivalent_reference())
        self.assertFalse(self.target.fact_check_references.exists())

    def test_exactly_one_equivalent_candidate_may_resolve(self):
        competing_claim = Claim.objects.create(
            context_text="Vaccines may contain tracking microchips."
        )
        competing = OfficialFactCheck.objects.create(
            claim=competing_claim,
            canonical_claim="Vaccines may contain tracking microchips.",
            headline="A related but materially different publication",
            verdict="MISLEADING",
            summary="Different proposition.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        self.set_equivalence_candidates(self.publication, competing)

        def classify(_instructions, user_prompt):
            canonical = json.loads(user_prompt)["published_canonical_claim"]
            equivalent = canonical == self.canonical
            return json.dumps(
                {
                    "equivalent": equivalent,
                    "reasoning": (
                        "Same complete proposition."
                        if equivalent
                        else "Material certainty differs."
                    ),
                    "material_differences": [] if equivalent else ["certainty"],
                }
            )

        self.provider.side_effect = classify
        reference = self.equivalent_reference()

        self.assertEqual(reference.fact_check_id, self.publication.pk)
        self.assertEqual(reference.match_method, "EQUIVALENT_CLAIM")
        self.assertEqual(self.provider.call_count, 2)

    def test_candidate_retrieval_returns_multiple_exact_headline_matches(self):
        shared_headline = "A shared publication headline for candidate retrieval"
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            headline=shared_headline
        )
        competing_claim = Claim.objects.create(context_text="Another proposition.")
        competing = OfficialFactCheck.objects.create(
            claim=competing_claim,
            canonical_claim="Another proposition about the same broad topic.",
            headline=shared_headline,
            verdict="UNVERIFIED",
            summary="Another publication.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )

        with patch(
            "api.knowledge_reuse_service.generate_embedding",
            return_value=None,
        ):
            candidates = find_published_fact_check_candidates(shared_headline)

        self.assertEqual(
            {candidate.fact_check.pk for candidate in candidates},
            {self.publication.pk, competing.pk},
        )

    def test_equivalent_reference_fingerprint_constraint_remains_sha256_only(self):
        for fingerprint in ("raw incoming text", "a" * 63, "A" * 64):
            with self.subTest(fingerprint=fingerprint), self.assertRaises(
                IntegrityError
            ), transaction.atomic():
                self.raw_reference(
                    match_method="EQUIVALENT_CLAIM", query_fingerprint=fingerprint
                )

    def test_public_result_uses_publication_with_null_target_provenance(self):
        self.equivalent_reference()
        result = get_match_result(self.target)
        self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertEqual(result["verdict"], self.publication.verdict)
        self.assertEqual(result["summary"], self.publication.summary)
        self.assertEqual(result["sources"], self.publication.sources)
        self.assertEqual(
            result["official_fact_check"],
            build_published_fact_check_payload(
                PublishedFactCheckMatch(self.publication, "EQUIVALENT_CLAIM", 0.91)
            ),
        )
        self.assertIsNone(result["ai_verdict"])
        self.assertIsNone(result["final_verdict"])
        self.assert_no_target_verdicts()

    def test_stored_ai_remains_real_and_final_requires_target_adjudication(self):
        self.target.ai_verdict = "FAKE"
        self.target.final_verdict = "MISLEADING"
        self.target.save()
        self.equivalent_reference()
        result = get_match_result(self.target)
        self.assertEqual(result["verdict"], self.publication.verdict)
        self.assertEqual(result["ai_verdict"], "FAKE")
        self.assertIsNone(result["final_verdict"])

    def test_related_semantic_full_text_and_archived_equivalence_have_no_authority(
        self,
    ):
        for method in ("SEMANTIC", "FULL_TEXT", "EQUIVALENT_CLAIM"):
            with self.subTest(method=method):
                reference = self.raw_reference(
                    relationship_kind="RELATED", match_method=method
                )
                result = get_match_result(self.target)
                self.assertIsNone(result["resolution_source"])
                self.assertIsNone(result["verdict"])
                reference.delete()
        self.equivalent_reference()
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            publication_status="ARCHIVED"
        )
        result = get_match_result(self.target)
        self.assertIsNone(result["resolution_source"])
        self.assertIsNone(result["verdict"])

    def test_publication_with_no_sources_does_not_borrow_target_ai_sources(self):
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(sources=[])
        self.target.ai_sources = ["https://ai.example/source"]
        self.target.top_verdict_source = "https://ai.example/top"
        self.target.save()
        self.equivalent_reference()
        result = get_match_result(self.target)
        self.assertEqual(result["sources"], [])
        self.assertIsNone(result["source_url"])

    def test_analytics_failure_cannot_suppress_equivalent_public_result(self):
        self.equivalent_reference()
        with patch(
            "api.claim_matching.record_knowledge_reuse",
            side_effect=RuntimeError("Analytics failed"),
        ):
            result = get_match_result(self.target, record_reuse=True)
        self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertEqual(result["verdict"], self.publication.verdict)


class ExactCanonicalLookupTests(PublicationResolutionFixture):
    def setUp(self):
        super().setUp()
        self.embedding = self.enterContext(
            patch(
                "api.knowledge_reuse_service.generate_embedding",
                side_effect=AssertionError("Authoritative lookup must not embed."),
            )
        )
        self.search_query = self.enterContext(
            patch(
                "api.knowledge_reuse_service.SearchQuery",
                side_effect=AssertionError(
                    "Authoritative lookup must not use full text."
                ),
            )
        )
        self.distance = self.enterContext(
            patch(
                "api.knowledge_reuse_service.CosineDistance",
                side_effect=AssertionError(
                    "Authoritative lookup must not rank similarity."
                ),
            )
        )

    def test_exact_canonical_returns_published_match_without_search_providers(self):
        match = find_exact_canonical_published_fact_check(self.canonical)
        self.assertEqual(match.fact_check.pk, self.publication.pk)
        self.assertEqual(
            match.match_method, ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL
        )
        self.assertEqual(match.similarity_score, 1.0)
        self.embedding.assert_not_called()
        self.search_query.assert_not_called()
        self.distance.assert_not_called()

    def test_case_insensitive_canonical_equality(self):
        match = find_exact_canonical_published_fact_check(self.canonical.upper())
        self.assertEqual(match.fact_check.pk, self.publication.pk)

    def test_existing_query_whitespace_normalization_is_used(self):
        match = find_exact_canonical_published_fact_check(
            "  Vaccines\n do  not\tcontain tracking microchips.  "
        )
        self.assertEqual(match.fact_check.pk, self.publication.pk)

    def test_headline_exact_is_not_authoritative_but_remains_vault_context(self):
        self.assertIsNone(
            find_exact_canonical_published_fact_check(self.publication.headline)
        )
        generic_match = find_published_fact_check_match(self.publication.headline)
        self.assertEqual(generic_match.fact_check.pk, self.publication.pk)
        self.assertEqual(
            generic_match.match_method, KnowledgeReuseEvent.MatchMethod.EXACT_TEXT
        )
        self.embedding.assert_not_called()

    def test_semantic_near_match_is_not_authoritative(self):
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            embedding=[1.0] + [0.0] * 383,
        )
        self.assertIsNone(
            find_exact_canonical_published_fact_check(
                "Vaccinations contain no tracking chips."
            )
        )
        self.embedding.assert_not_called()
        self.distance.assert_not_called()

    def test_full_text_only_match_is_not_authoritative(self):
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            search_vector=SearchVector("canonical_claim", "summary"),
        )
        self.assertIsNone(
            find_exact_canonical_published_fact_check("vaccines tracking microchips")
        )
        self.search_query.assert_not_called()

    def test_nonpublished_statuses_are_excluded(self):
        for status in ("DRAFT", "IN_REVIEW", "ARCHIVED"):
            with self.subTest(status=status):
                OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
                    publication_status=status
                )
                self.assertIsNone(
                    find_exact_canonical_published_fact_check(self.canonical)
                )

    def test_blank_nontext_and_insufficient_queries_return_none(self):
        for query in (None, "", " \t\n", "short", "123456789", 123):
            with self.subTest(query=query), self.assertNumQueries(0):
                self.assertIsNone(find_exact_canonical_published_fact_check(query))

    def test_punctuation_differences_do_not_transfer_authority(self):
        self.assertIsNone(
            find_exact_canonical_published_fact_check(self.canonical.rstrip("."))
        )

    def test_identical_verdict_duplicate_publications_are_ambiguous(self):
        competing = self.create_competing_publication(verdict=self.publication.verdict)
        self.assertNotEqual(competing.claim_id, self.publication.claim_id)
        self.assertIsNone(find_exact_canonical_published_fact_check(self.canonical))

    def test_differing_verdict_duplicate_publications_are_ambiguous(self):
        self.create_competing_publication(verdict="MISLEADING")
        self.assertIsNone(find_exact_canonical_published_fact_check(self.canonical))


class AuthoritativeReferencePersistenceTests(PublicationResolutionFixture):
    def test_creates_only_authoritative_exact_canonical_reference(self):
        reference = self.record()
        self.assertEqual(reference.target_claim_id, self.target.pk)
        self.assertEqual(reference.fact_check_id, self.publication.pk)
        self.assertEqual(reference.relationship_kind, "AUTHORITATIVE")
        self.assertEqual(reference.match_method, "EXACT_CANONICAL")
        self.assertEqual(reference.similarity_score, 1.0)
        self.assertIsNotNone(reference.created_at)

    def test_repeat_is_idempotent_including_case_and_whitespace(self):
        first = self.record()
        second = self.record(query_text=f"  {self.canonical.upper()}  ")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ClaimFactCheckReference.objects.count(), 1)
        self.assertEqual(KnowledgeReuseEvent.objects.count(), 1)

    def test_never_copies_publication_relationship_or_creates_human_work(self):
        before_publications = OfficialFactCheck.objects.count()
        before_decisions = AdjudicationDecision.objects.count()
        self.record()
        self.publication.refresh_from_db()
        self.assertEqual(self.publication.claim_id, self.source_claim.pk)
        self.assertEqual(OfficialFactCheck.objects.count(), before_publications)
        self.assertEqual(AdjudicationDecision.objects.count(), before_decisions)
        self.assert_no_target_verdicts()
        self.assertFalse(self.target.official_fact_checks.exists())

    def test_existing_target_ai_and_final_caches_are_not_overwritten(self):
        self.target.ai_verdict = "MISLEADING"
        self.target.final_verdict = "FAKE"
        self.target.source_type = "Existing analysis"
        self.target.save()
        self.record()
        self.target.refresh_from_db()
        self.assertEqual(self.target.ai_verdict, "MISLEADING")
        self.assertEqual(self.target.final_verdict, "FAKE")
        self.assertEqual(self.target.source_type, "Existing analysis")

    def test_only_normalized_sha256_is_stored_without_query_text(self):
        reference = self.record(query_text=f"  {self.canonical.upper()}  ")
        expected = hashlib.sha256(self.canonical.casefold().encode("utf-8")).hexdigest()
        self.assertEqual(reference.query_fingerprint, expected)
        self.assertNotIn("query_text", {field.name for field in reference._meta.fields})
        self.assertNotIn(self.canonical, reference.__dict__.values())
        event = KnowledgeReuseEvent.objects.get()
        self.assertEqual(event.query_fingerprint, expected)
        self.assertNotIn(self.canonical, str(event.metadata))

    def test_recorder_rechecks_status_in_database_not_stale_object(self):
        for status in ("DRAFT", "IN_REVIEW", "ARCHIVED"):
            with self.subTest(status=status):
                OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
                    publication_status=status
                )
                self.assertIsNone(self.record())
        self.assertFalse(ClaimFactCheckReference.objects.exists())

    def test_recorder_rechecks_canonical_not_headline_or_trusted_caller(self):
        self.assertIsNone(self.record(query_text=self.publication.headline))
        self.assertIsNone(
            self.record(query_text="Vaccines contain tracking microchips.")
        )
        self.assertFalse(ClaimFactCheckReference.objects.exists())

    def test_blank_query_and_unsaved_objects_are_rejected(self):
        for overrides in (
            {"query_text": " "},
            {"query_text": "short"},
            {"target_claim": Claim()},
            {"fact_check": OfficialFactCheck()},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(
                InvalidKnowledgeReuse
            ):
                self.record(**overrides)
        self.assertFalse(ClaimFactCheckReference.objects.exists())

    def test_analytics_exception_cannot_prevent_reference_or_result(self):
        with patch(
            "api.knowledge_reuse_service.record_knowledge_reuse",
            side_effect=RuntimeError("Telemetry failed"),
        ):
            reference = self.record()
        self.assertTrue(
            ClaimFactCheckReference.objects.filter(pk=reference.pk).exists()
        )
        self.assertEqual(
            get_match_result(self.target)["resolution_source"], "OFFICIAL_FACT_CHECK"
        )

    def test_real_analytics_database_error_is_isolated_by_savepoint(self):
        def failing_analytics(**kwargs):
            self.raw_reference(query_fingerprint="raw query must not be persisted")

        with transaction.atomic():
            with patch(
                "api.knowledge_reuse_service.record_knowledge_reuse",
                side_effect=failing_analytics,
            ):
                reference = self.record()
            self.assertTrue(
                ClaimFactCheckReference.objects.filter(pk=reference.pk).exists()
            )
            self.assertEqual(get_match_result(self.target)["verdict"], "FACT")

    def test_recorder_refuses_caller_selected_publication_when_exact_set_is_ambiguous(
        self,
    ):
        competing = self.create_competing_publication(verdict="MISLEADING")
        self.assertIsNone(self.record())
        self.assertIsNone(self.record(fact_check=competing))
        self.assertFalse(ClaimFactCheckReference.objects.exists())

    def test_database_prevents_second_authoritative_resolution_for_target(self):
        self.record()
        other = self.create_competing_publication(verdict="FACT")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.raw_reference(fact_check=other)
        self.assertIsNone(self.record(fact_check=other))
        self.assertEqual(ClaimFactCheckReference.objects.count(), 1)

    def test_database_rejects_raw_query_fingerprint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.raw_reference(query_fingerprint=self.canonical)
        self.assertFalse(ClaimFactCheckReference.objects.exists())

    def test_target_deletion_cascades_but_publication_is_protected(self):
        reference = self.record()
        with self.assertRaises(ProtectedError):
            self.publication.delete()
        self.target.delete()
        self.assertFalse(
            ClaimFactCheckReference.objects.filter(pk=reference.pk).exists()
        )
        self.assertTrue(
            OfficialFactCheck.objects.filter(pk=self.publication.pk).exists()
        )


class PublishedReferenceResultTests(PublicationResolutionFixture):
    def test_exact_reference_uses_publication_content_and_target_provenance(self):
        self.record()
        result = get_match_result(self.target)
        self.assertEqual(result["claim_id"], str(self.target.pk))
        self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertEqual(result["verdict"], self.publication.verdict)
        self.assertEqual(result["summary"], self.publication.summary)
        self.assertEqual(result["sources"], self.publication.sources)
        self.assertIsNone(result["ai_verdict"])
        self.assertIsNone(result["final_verdict"])
        payload = build_published_fact_check_payload(
            PublishedFactCheckMatch(
                fact_check=self.publication,
                match_method="EXACT_CANONICAL",
                similarity_score=1.0,
            )
        )
        self.assertEqual(result["official_fact_check"], payload)
        self.assertEqual(payload["claim_id"], str(self.source_claim.pk))
        self.assert_no_target_verdicts()

    def test_stored_ai_is_exposed_without_fabricating_target_adjudication(self):
        self.target.ai_verdict = "FAKE"
        self.target.save()
        self.record()
        result = get_match_result(self.target)
        self.assertEqual(result["verdict"], "FACT")
        self.assertEqual(result["ai_verdict"], "FAKE")
        self.assertIsNone(result["final_verdict"])

    def test_related_exact_reference_never_transfers_verdict(self):
        self.raw_reference(relationship_kind="RELATED")
        result = get_match_result(self.target)
        self.assertIsNone(result["resolution_source"])
        self.assertIsNone(result["verdict"])
        self.assertIsNone(result["official_fact_check"])

    def test_other_match_methods_never_transfer_authority_even_if_labelled_authoritative(
        self,
    ):
        for method in ("EXACT_HEADLINE", "SEMANTIC", "FULL_TEXT"):
            with self.subTest(method=method):
                reference = self.raw_reference(match_method=method)
                result = get_match_result(self.target)
                self.assertIsNone(result["resolution_source"])
                self.assertIsNone(result["verdict"])
                reference.delete()

    def test_referenced_nonpublished_article_never_transfers_verdict(self):
        self.record()
        for status in ("DRAFT", "IN_REVIEW", "ARCHIVED"):
            with self.subTest(status=status):
                OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
                    publication_status=status
                )
                result = get_match_result(self.target)
                self.assertIsNone(result["resolution_source"])
                self.assertIsNone(result["verdict"])
                self.assertIsNone(result["official_fact_check"])

    def test_invalid_fingerprint_and_changed_canonical_fail_closed(self):
        self.raw_reference(
            query_fingerprint=build_query_fingerprint("A different factual claim.")
        )
        self.assertIsNone(get_match_result(self.target)["resolution_source"])
        ClaimFactCheckReference.objects.all().delete()
        self.record()
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            canonical_claim="Another canonical claim."
        )
        self.assertIsNone(get_match_result(self.target)["resolution_source"])

    def test_reference_fails_closed_if_exact_publication_becomes_ambiguous(self):
        self.record()
        self.create_competing_publication(verdict="MISLEADING")
        result = get_match_result(self.target)
        self.assertIsNone(result["resolution_source"])
        self.assertIsNone(result["official_fact_check"])

    def test_publication_sources_do_not_fall_back_to_target_ai_when_empty(self):
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(sources=[])
        self.target.ai_sources = ["https://unrelated.example/ai"]
        self.target.source_link = "https://unrelated.example/original"
        self.target.top_verdict_source = "https://unrelated.example/top"
        self.target.save()
        self.record()
        result = get_match_result(self.target)
        self.assertEqual(result["sources"], [])
        self.assertIsNone(result["source_url"])

    def test_normalized_publication_sources_remain_payload_source_of_truth(self):
        OfficialFactCheckSource.objects.create(
            fact_check=self.publication,
            url="https://normalized.example/evidence",
            title="Reviewed source",
        )
        self.record()
        result = get_match_result(self.target)
        self.assertEqual(result["sources"], ["https://normalized.example/evidence"])
        self.assertEqual(
            result["official_fact_check"]["sources"][0]["title"], "Reviewed source"
        )

    def test_directly_associated_publication_contract_is_unchanged(self):
        result = get_match_result(self.source_claim)
        expected = build_published_fact_check_payload(
            PublishedFactCheckMatch(
                fact_check=self.publication,
                match_method=KnowledgeReuseEvent.MatchMethod.CLAIM_CACHE,
            )
        )
        self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertEqual(result["official_fact_check"], expected)
        self.assertEqual(result["verdict"], "FACT")
        self.assertIsNone(result["ai_verdict"])
        self.assertIsNone(result["final_verdict"])
        self.assertFalse(ClaimFactCheckReference.objects.exists())

    def test_analytics_failure_cannot_suppress_returned_publication_result(self):
        self.record()
        with patch(
            "api.claim_matching.record_knowledge_reuse",
            side_effect=RuntimeError("Analytics failed"),
        ):
            result = get_match_result(self.target, record_reuse=True)
        self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")

    def test_response_analytics_database_failure_keeps_caller_transaction_usable(self):
        self.record()

        def failing_analytics(**kwargs):
            self.raw_reference()

        with transaction.atomic():
            with patch(
                "api.claim_matching.record_knowledge_reuse",
                side_effect=failing_analytics,
            ):
                result = get_match_result(self.target, record_reuse=True)
            self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")
            self.assertTrue(self.target.fact_check_references.exists())


class PublishedClaimPipelineTests(PublicationResolutionFixture):
    def setUp(self):
        super().setUp()
        self.cleaned = {
            "cleaned_claim": self.canonical,
            "search_query": "vaccines microchips",
            "article_stance": "NEUTRAL",
        }
        self.ai_result = {
            "verdict": "FAKE",
            "summary": "An independently evaluated claim.",
            "confidence_score": 85,
        }
        self.extract_image = self._patch(
            "api.tasks.extract_text_from_image", return_value="Raw OCR text"
        )
        self.clean_ocr = self._patch(
            "api.tasks.clean_ocr_text", return_value=self.cleaned
        )
        response = Mock(status_code=200)
        response.json.return_value = {"results": [{"raw_content": "Raw URL article"}]}
        self._patch("api.tasks.requests.post", return_value=response)
        self._patch("api.tasks.clean_extracted_text", return_value="Clean article text")
        self.extract_query = self._patch(
            "api.tasks.extract_search_query", return_value=self.cleaned
        )
        self.find_matching_claim = self._patch(
            "api.claim_matching.find_matching_claim",
            return_value=None,
        )
        self.vault = self._patch("api.tasks.search_official_vault", return_value=None)
        self.authority_candidates = self._patch(
            "api.knowledge_reuse_service.find_published_fact_check_candidates",
            return_value=[],
        )
        self.image_gfc = self._patch(
            "api.tasks.evaluate_image_claim_with_gfc", return_value=self.ai_result
        )
        self.image_tavily = self._patch(
            "api.tasks.evaluate_image_claim_with_tavily", return_value=self.ai_result
        )
        self.url_gfc = self._patch(
            "api.tasks.evaluate_url_claim_with_gfc", return_value=self.ai_result
        )
        self.url_tavily = self._patch(
            "api.tasks.evaluate_url_claim_with_tavily", return_value=self.ai_result
        )
        self.persisted_eval = self._patch(
            "api.tasks.evaluate_claim_with_persisted_evidence",
            return_value=self.ai_result,
        )
        self.gfc_retrieval = self._patch(
            "api.tasks._retrieve_and_ingest_gfc",
            return_value={
                "claims": [
                    {
                        "text": "External fact-check",
                        "claimReview": [{"url": "https://external.example/fact-check"}],
                    }
                ]
            },
        )
        self.tavily_retrieval = self._patch(
            "api.tasks._retrieve_and_ingest_tavily", return_value={"results": []}
        )
        self._patch("api.tasks.is_fact_check_relevant", return_value=True)
        self._patch(
            "api.tasks.load_reasoning_evidence_dossier_for_run",
            return_value=["Persisted dossier"],
        )
        self._patch(
            "api.tasks.filter_reasoning_evidence_dossier_by_role",
            return_value=["Selected evidence"],
        )
        self._patch(
            "api.tasks.render_reasoning_evidence_dossier",
            return_value="Persisted evidence context",
        )
        self._patch("api.tasks._assess_and_persist_reasoning_evidence")
        self.embedding = self._patch(
            "api.embedding_service.generate_embedding", return_value=None
        )
        self.vault_embedding = self._patch(
            "api.knowledge_reuse_service.generate_embedding", return_value=None
        )
        self.llm = self._patch("api.services.call_llm_with_fallback")
        self._patch("api.tasks._log_stage")
        self.save_claim = self._patch("api.tasks._save_claim", wraps=tasks._save_claim)

    def _patch(self, target, **kwargs):
        return self.enterContext(patch(target, **kwargs))

    def image(self):
        tasks.snippet_fact_check_process.run(
            "image-hash",
            self.target.pk,
            base64_string=base64.b64encode(b"image fixture").decode("ascii"),
        )

    def url(self):
        self.target.claim_type = Claim.ClaimType.URL
        self.target.url_link = "https://article.example/claim"
        self.target.save()
        tasks.url_fact_check_process.run(self.target.url_link, self.target.pk)

    def cached_ai_claim(self, *, verdict="MISLEADING"):
        return Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            ai_verdict=verdict,
            ai_summary="Cached AI analysis summary.",
            consensus_score=77,
            source_type="Cached AI",
            source_link="https://cache.example/source",
            top_verdict_source="https://cache.example/top",
            ai_sources=["https://cache.example/source"],
            is_ai_generated=False,
            score_context="Cached score context",
        )

    def assert_exact_bypass(self):
        for mocked in (
            self.vault,
            self.image_gfc,
            self.image_tavily,
            self.url_gfc,
            self.url_tavily,
            self.persisted_eval,
            self.gfc_retrieval,
            self.tavily_retrieval,
            self.save_claim,
            self.embedding,
            self.vault_embedding,
            self.llm,
        ):
            mocked.assert_not_called()
        reference = self.target.fact_check_references.get()
        self.assertEqual(reference.fact_check_id, self.publication.pk)
        self.assertEqual(reference.relationship_kind, "AUTHORITATIVE")
        self.assertEqual(reference.match_method, "EXACT_CANONICAL")
        run = self.target.verification_runs.get()
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.failure_code)
        self.assert_no_target_verdicts()
        self.assertEqual(self.target.context_text, self.cleaned["cleaned_claim"])
        self.assertIsNone(self.target.source_type)

    def semantic_context(self):
        self.cleaned["cleaned_claim"] = "Vaccines contain tracking microchips."
        self.vault.return_value = build_published_fact_check_payload(
            PublishedFactCheckMatch(
                fact_check=self.publication,
                match_method="SEMANTIC",
                similarity_score=0.91,
            )
        )

    def assert_ai_path(self, evaluator):
        evaluator.assert_called_once()
        self.vault.assert_called_once_with(
            self.cleaned["cleaned_claim"], target_claim=self.target
        )
        self.save_claim.assert_called_once()
        self.assertFalse(self.target.fact_check_references.exists())
        self.target.refresh_from_db()
        self.assertEqual(self.target.ai_verdict, self.ai_result["verdict"])
        self.assertIsNone(self.target.final_verdict)
        self.assertEqual(
            self.target.verification_runs.get().status, VerificationRun.Status.COMPLETED
        )

    def test_image_raw_ocr_exact_canonical_bypasses_claim_gate_and_evaluators(self):
        self.extract_image.return_value = self.canonical
        self.clean_ocr.side_effect = AssertionError(
            "Raw OCR exact authority must bypass the LLM ClaimGate."
        )

        self.image()

        self.assert_exact_bypass()
        self.clean_ocr.assert_not_called()
        self.target.refresh_from_db()
        self.assertEqual(self.target.context_text, self.canonical)

    def test_image_raw_ocr_ambiguous_exact_falls_through_to_claim_gate(self):
        self.create_competing_publication(verdict="MISLEADING")
        self.extract_image.return_value = self.canonical
        self.cleaned["cleaned_claim"] = "A related but non-exact factual claim."
        self.vault.return_value = build_published_fact_check_payload(
            PublishedFactCheckMatch(
                fact_check=self.publication,
                match_method="SEMANTIC",
                similarity_score=0.91,
            )
        )

        self.image()

        self.clean_ocr.assert_called_once_with(self.canonical)
        self.assert_ai_path(self.image_gfc)

    def test_image_exact_canonical_bypasses_evaluators_and_completes_run(self):
        self.image()
        self.assert_exact_bypass()
        self.clean_ocr.assert_called_once_with("Raw OCR text")

    def test_url_exact_canonical_bypasses_evaluators_and_completes_run(self):
        self.url()
        self.assert_exact_bypass()
        self.extract_query.assert_called_once_with(
            "Clean article text", self.target.url_link
        )

    def test_image_exact_publication_beats_second_chance_ai_cache(self):
        cached = self.cached_ai_claim(verdict="FAKE")
        self.find_matching_claim.return_value = cached

        self.image()

        self.assert_exact_bypass()
        self.target.refresh_from_db()
        self.assertIsNone(self.target.ai_verdict)
        self.assertIsNone(self.target.ai_summary)
        self.assertIsNone(self.target.score_context)

    def test_image_second_chance_ai_cache_is_preserved_without_exact_publication(self):
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
        )
        cached = self.cached_ai_claim(verdict="MISLEADING")
        self.find_matching_claim.return_value = cached

        self.image()

        self.target.refresh_from_db()
        self.assertEqual(self.target.ai_verdict, cached.ai_verdict)
        self.assertEqual(self.target.ai_summary, cached.ai_summary)
        self.assertEqual(self.target.consensus_score, cached.consensus_score)
        self.assertEqual(self.target.source_type, cached.source_type)
        self.assertEqual(
            self.target.score_context,
            "This result was matched from a prior analysis of the same claim.",
        )
        self.assertFalse(self.target.fact_check_references.exists())
        # B.1B checks for published equivalence before falling back to the
        # legacy second-chance AI cache. With the publication archived the
        # Vault returns no authoritative candidate, then cached AI reuse wins.
        self.vault.assert_called_once_with(
            self.cleaned["cleaned_claim"],
            target_claim=self.target,
        )
        self.save_claim.assert_not_called()
        self.assertEqual(
            self.target.verification_runs.get().status,
            VerificationRun.Status.COMPLETED,
        )

    def test_image_exact_publication_beats_satire_shortcut(self):
        self.cleaned["article_stance"] = "SATIRE"
        self.image()
        self.assert_exact_bypass()

    def test_url_exact_publication_beats_satire_shortcut(self):
        self.cleaned["article_stance"] = "SATIRE"
        self.url()
        self.assert_exact_bypass()

    def test_ambiguous_exact_publications_fall_through_to_ai_vault_path(self):
        self.create_competing_publication(verdict="MISLEADING")
        self.vault.return_value = build_published_fact_check_payload(
            PublishedFactCheckMatch(
                fact_check=self.publication,
                match_method="EXACT_TEXT",
                similarity_score=1.0,
            )
        )

        self.image()

        self.assert_ai_path(self.image_gfc)

    def test_image_semantic_match_retains_existing_ai_vault_path(self):
        self.semantic_context()
        self.image()
        self.assert_ai_path(self.image_gfc)

    def test_url_semantic_match_retains_existing_ai_vault_path(self):
        self.semantic_context()
        self.url()
        self.assert_ai_path(self.url_gfc)

    def test_image_headline_exact_retains_ai_evaluation(self):
        self.cleaned["cleaned_claim"] = self.publication.headline
        self.vault.return_value = build_published_fact_check_payload(
            PublishedFactCheckMatch(
                fact_check=self.publication,
                match_method="EXACT_TEXT",
                similarity_score=1.0,
            )
        )
        self.image()
        self.assert_ai_path(self.image_gfc)

    def test_image_full_text_match_retains_ai_evaluation(self):
        self.cleaned["cleaned_claim"] = "vaccines tracking microchips"
        self.vault.return_value = build_published_fact_check_payload(
            PublishedFactCheckMatch(
                fact_check=self.publication,
                match_method="FULL_TEXT",
                similarity_score=None,
            )
        )
        self.image()
        self.assert_ai_path(self.image_gfc)

    def test_url_nonexact_without_vault_retains_gfc_evidence_evaluator(self):
        self.cleaned["cleaned_claim"] = "An unrelated public factual claim."
        self.url()
        self.assert_ai_path(self.persisted_eval)
        self.gfc_retrieval.assert_called_once()

    def test_shared_text_pipeline_does_not_gain_unrequested_authority_transfer(self):
        self.target.claim_type = Claim.ClaimType.TEXT
        self.target.save()
        tasks.execute_core_text_pipeline("Submitted text", self.target.pk)
        self.assert_ai_path(self.persisted_eval)

    def test_exact_resolution_survives_analytics_failure_in_image_pipeline(self):
        with patch(
            "api.knowledge_reuse_service.record_knowledge_reuse",
            side_effect=RuntimeError("Analytics failed"),
        ):
            self.image()
        self.assert_exact_bypass()

    def test_exact_unverified_publication_completes_without_ai_abstention(self):
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            verdict="UNVERIFIED"
        )
        self.url()
        self.assert_exact_bypass()
        self.assertEqual(get_match_result(self.target)["verdict"], "UNVERIFIED")

    def assert_provider_failure_integrity(self, error):
        run = self.target.verification_runs.get()
        self.assertEqual(run.status, VerificationRun.Status.FAILED)
        self.assertEqual(run.failure_stage, "final_evaluator")
        self.assertEqual(run.failure_code, "LLM_UNAVAILABLE")
        self.assertEqual(run.failure_message, str(error))
        self.assert_no_target_verdicts()
        self.assertIsNone(self.target.consensus_score)
        self.assertFalse(self.target.fact_check_references.exists())
        self.save_claim.assert_not_called()
        self.tavily_retrieval.assert_not_called()

    def test_image_nonexact_provider_exhaustion_preserves_failure_integrity(self):
        self.semantic_context()
        self.image_gfc.side_effect = services.evaluate_image_claim_with_gfc
        error = LLMProviderUnavailableError(
            "No configured LLM provider successfully completed this request."
        )
        self.llm.side_effect = error
        with self.assertRaises(LLMProviderUnavailableError) as raised:
            self.image()
        self.assertIs(raised.exception, error)
        self.assert_provider_failure_integrity(error)

    def test_url_nonexact_provider_exhaustion_preserves_failure_integrity(self):
        self.cleaned["cleaned_claim"] = "An unrelated public factual claim."
        error = LLMProviderUnavailableError(
            "No configured LLM provider successfully completed this request."
        )
        self.persisted_eval.side_effect = error
        with self.assertRaises(LLMProviderUnavailableError) as raised:
            self.url()
        self.assertIs(raised.exception, error)
        self.assert_provider_failure_integrity(error)

    def test_lookup_failure_fails_run_without_fabricating_ai_analysis(self):
        with patch(
            "api.tasks.find_exact_canonical_published_fact_check",
            side_effect=RuntimeError("Lookup failed"),
        ):
            with self.assertRaises(tasks.ClaimPersistenceError):
                self.image()
        self.assert_no_target_verdicts()
        self.save_claim.assert_not_called()
        self.vault.assert_not_called()
        self.assertEqual(
            self.target.verification_runs.get().failure_stage, "claim_persistence"
        )

    def test_reference_persistence_failure_does_not_fabricate_ai_result(self):
        with patch(
            "api.tasks.record_authoritative_claim_fact_check_reference",
            side_effect=RuntimeError("Storage failed"),
        ):
            with self.assertRaises(tasks.ClaimPersistenceError):
                self.image()
        self.assert_no_target_verdicts()
        self.save_claim.assert_not_called()
        self.assertFalse(self.target.fact_check_references.exists())
        self.assertEqual(
            self.target.verification_runs.get().failure_stage, "claim_persistence"
        )

    def test_context_save_failure_rolls_back_reference_and_fails_run(self):
        original_save = Claim.save

        def fail_context_save(claim, *args, **kwargs):
            if kwargs.get("update_fields") == ["context_text", "last_updated"]:
                raise RuntimeError("Context storage failed")
            return original_save(claim, *args, **kwargs)

        with patch.object(Claim, "save", new=fail_context_save):
            with self.assertRaises(tasks.ClaimPersistenceError):
                self.image()
        self.assert_no_target_verdicts()
        self.assertFalse(self.target.fact_check_references.exists())
        self.assertFalse(KnowledgeReuseEvent.objects.exists())
        self.assertEqual(
            self.target.verification_runs.get().failure_stage, "claim_persistence"
        )

    def equivalent_context(self, *, method="SEMANTIC", equivalent=True):
        self.cleaned["cleaned_claim"] = (
            "Vaccinations do not contain tracking microchips."
        )
        candidate = PublishedFactCheckMatch(
            self.publication,
            method,
            0.91 if method == "SEMANTIC" else 1.0,
        )
        self.vault.return_value = build_published_fact_check_payload(candidate)
        self.authority_candidates.return_value = [candidate]
        self.llm.return_value = json.dumps(
            {
                "equivalent": equivalent,
                "reasoning": (
                    "Same complete proposition."
                    if equivalent
                    else "Material detail differs."
                ),
                "material_differences": [] if equivalent else ["Material detail"],
            }
        )

    def assert_equivalent_bypass(self):
        for evaluator in (
            self.image_gfc,
            self.image_tavily,
            self.url_gfc,
            self.url_tavily,
            self.persisted_eval,
            self.gfc_retrieval,
            self.tavily_retrieval,
            self.save_claim,
        ):
            evaluator.assert_not_called()
        self.vault.assert_called_once_with(
            self.cleaned["cleaned_claim"], target_claim=self.target
        )
        reference = self.target.fact_check_references.get()
        self.assertEqual(reference.relationship_kind, "AUTHORITATIVE")
        self.assertEqual(reference.match_method, "EQUIVALENT_CLAIM")
        self.assertEqual(reference.fact_check_id, self.publication.pk)
        self.assertEqual(
            reference.query_fingerprint,
            build_query_fingerprint(self.cleaned["cleaned_claim"]),
        )
        run = self.target.verification_runs.get()
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.failure_code)
        self.assert_no_target_verdicts()
        self.assertEqual(self.target.context_text, self.cleaned["cleaned_claim"])
        self.assertIsNone(self.target.source_type)
        result = get_match_result(self.target)
        self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertEqual(result["verdict"], self.publication.verdict)
        self.assertEqual(result["summary"], self.publication.summary)
        self.assertIsNone(result["ai_verdict"])
        self.assertIsNone(result["final_verdict"])

    def test_image_equivalent_semantic_candidate_bypasses_all_factual_evaluators(self):
        self.equivalent_context()
        self.image()
        self.assert_equivalent_bypass()
        self.llm.assert_called_once()
        self.assertEqual(
            json.loads(self.llm.call_args.args[1]),
            {
                "incoming_claim": self.cleaned["cleaned_claim"],
                "published_canonical_claim": self.canonical,
            },
        )

    def test_url_equivalent_semantic_candidate_completes_via_publication(self):
        self.equivalent_context()
        self.url()
        self.assert_equivalent_bypass()
        self.extract_query.assert_called_once_with(
            "Clean article text", self.target.url_link
        )
        self.llm.assert_called_once()

    def test_image_headline_candidate_still_requires_equivalence_gate(self):
        self.equivalent_context(method="EXACT_TEXT")
        self.cleaned["cleaned_claim"] = self.publication.headline
        self.image()
        self.assert_equivalent_bypass()
        self.llm.assert_called_once()
        self.assertEqual(
            json.loads(self.llm.call_args.args[1])["incoming_claim"],
            self.publication.headline,
        )

    def test_exact_cleaned_image_resolution_never_requests_equivalence(self):
        with patch(
            "api.services.assess_claim_equivalence",
            side_effect=AssertionError("Exact wins"),
        ) as gate:
            self.image()
        self.assert_exact_bypass()
        gate.assert_not_called()

    def test_exact_raw_image_resolution_never_requests_equivalence(self):
        self.extract_image.return_value = self.canonical
        with patch(
            "api.services.assess_claim_equivalence",
            side_effect=AssertionError("Exact wins"),
        ) as gate:
            self.image()
        self.assert_exact_bypass()
        self.clean_ocr.assert_not_called()
        gate.assert_not_called()

    def test_exact_url_resolution_never_requests_equivalence(self):
        with patch(
            "api.services.assess_claim_equivalence",
            side_effect=AssertionError("Exact wins"),
        ) as gate:
            self.url()
        self.assert_exact_bypass()
        gate.assert_not_called()

    def test_image_equivalent_candidate_beats_second_chance_ai_cache(self):
        self.equivalent_context()
        cached = self.cached_ai_claim(verdict="FAKE")
        self.find_matching_claim.return_value = cached

        self.image()

        self.assert_equivalent_bypass()
        self.target.refresh_from_db()
        self.assertIsNone(self.target.ai_verdict)
        self.assertIsNone(self.target.ai_summary)
        self.assertIsNone(self.target.score_context)

    def test_image_non_equivalent_candidate_preserves_second_chance_ai_cache(self):
        self.equivalent_context(equivalent=False)
        cached = self.cached_ai_claim(verdict="MISLEADING")
        self.find_matching_claim.return_value = cached

        self.image()

        self.target.refresh_from_db()
        self.assertEqual(self.target.ai_verdict, cached.ai_verdict)
        self.assertEqual(self.target.ai_summary, cached.ai_summary)
        self.assertEqual(
            self.target.score_context,
            "This result was matched from a prior analysis of the same claim.",
        )
        self.assertFalse(self.target.fact_check_references.exists())
        self.vault.assert_called_once_with(
            self.cleaned["cleaned_claim"], target_claim=self.target
        )
        self.llm.assert_called_once()
        self.image_gfc.assert_not_called()

    def test_image_equivalent_candidate_beats_satire_shortcut(self):
        self.equivalent_context()
        self.cleaned["article_stance"] = "SATIRE"

        self.image()

        self.assert_equivalent_bypass()

    def test_image_non_equivalent_satire_preserves_existing_satire_behavior(self):
        self.equivalent_context(equivalent=False)
        self.cleaned["article_stance"] = "SATIRE"

        self.image()

        self.target.refresh_from_db()
        self.assertEqual(self.target.ai_verdict, "SATIRE")
        self.assertEqual(self.target.source_type, "Satire Detection")
        self.assertFalse(self.target.fact_check_references.exists())
        self.vault.assert_called_once_with(
            self.cleaned["cleaned_claim"], target_claim=self.target
        )
        self.llm.assert_called_once()
        self.image_gfc.assert_not_called()

    def test_url_equivalent_candidate_beats_satire_shortcut(self):
        self.equivalent_context()
        self.cleaned["article_stance"] = "SATIRE"

        self.url()

        self.assert_equivalent_bypass()

    def test_url_non_equivalent_satire_preserves_existing_satire_behavior(self):
        self.equivalent_context(equivalent=False)
        self.cleaned["article_stance"] = "SATIRE"

        self.url()

        self.target.refresh_from_db()
        self.assertEqual(self.target.ai_verdict, "SATIRE")
        self.assertEqual(self.target.source_type, "Satire Detection")
        self.assertFalse(self.target.fact_check_references.exists())
        self.vault.assert_called_once_with(
            self.cleaned["cleaned_claim"], target_claim=self.target
        )
        self.llm.assert_called_once()
        self.url_gfc.assert_not_called()

    def test_multiple_equivalent_vault_candidates_fall_through_without_authority(self):
        self.equivalent_context()
        competing_claim = Claim.objects.create(
            context_text="Vaccinations have no tracking microchips."
        )
        competing = OfficialFactCheck.objects.create(
            claim=competing_claim,
            canonical_claim="Vaccinations have no tracking microchips.",
            headline="Another equivalent institutional publication",
            verdict="FACT",
            summary="Another published summary.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        self.authority_candidates.return_value = [
            PublishedFactCheckMatch(
                self.publication,
                KnowledgeReuseEvent.MatchMethod.SEMANTIC,
                0.91,
            ),
            PublishedFactCheckMatch(
                competing,
                KnowledgeReuseEvent.MatchMethod.SEMANTIC,
                0.90,
            ),
        ]

        self.image()

        self.assert_ai_path(self.image_gfc)
        self.assertEqual(self.llm.call_count, 2)
        self.assertFalse(self.target.fact_check_references.exists())

    def test_image_complete_partial_conflict_keeps_vault_ai_evaluator(self):
        canonical = "Hoshi suffered a complete ACL tear during rehearsal."
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            canonical_claim=canonical
        )
        self.publication.canonical_claim = canonical
        self.equivalent_context(equivalent=False)
        self.cleaned["cleaned_claim"] = (
            "Hoshi suffered a partial ACL tear during rehearsal."
        )
        self.image()
        self.assert_ai_path(self.image_gfc)
        self.llm.assert_called_once()
        self.assertEqual(
            json.loads(self.llm.call_args.args[1])["published_canonical_claim"],
            canonical,
        )

    def test_image_underspecified_related_candidate_keeps_vault_ai_evaluator(self):
        canonical = "Hoshi suffered a complete ACL tear during rehearsal."
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            canonical_claim=canonical
        )
        self.publication.canonical_claim = canonical
        self.equivalent_context(equivalent=False)
        self.cleaned["cleaned_claim"] = "Hoshi injured his knee during rehearsal."
        self.image()
        self.assert_ai_path(self.image_gfc)
        self.llm.assert_called_once()

    def test_url_non_equivalent_candidate_keeps_existing_vault_ai_path(self):
        self.equivalent_context(equivalent=False)
        self.url()
        self.assert_ai_path(self.url_gfc)
        self.llm.assert_called_once()

    def test_image_invalid_equivalence_output_keeps_existing_ai_path(self):
        self.equivalent_context()
        self.llm.return_value = '{"equivalent": true}'
        self.image()
        self.assert_ai_path(self.image_gfc)

    def test_image_equivalence_provider_exhaustion_has_no_authority_or_verdict_copy(
        self,
    ):
        self.equivalent_context()
        error = LLMProviderUnavailableError(
            "No equivalence provider completed this request."
        )
        self.llm.side_effect = error
        with self.assertRaises(LLMProviderUnavailableError) as raised:
            self.image()
        self.assertIs(raised.exception, error)
        self.assert_provider_failure_integrity(error)
        self.image_gfc.assert_not_called()
        self.image_tavily.assert_not_called()
        self.persisted_eval.assert_not_called()

    def test_url_equivalence_provider_exhaustion_has_no_authority_or_verdict_copy(self):
        self.equivalent_context()
        error = LLMProviderUnavailableError(
            "No equivalence provider completed this request."
        )
        self.llm.side_effect = error
        with self.assertRaises(LLMProviderUnavailableError) as raised:
            self.url()
        self.assertIs(raised.exception, error)
        self.assert_provider_failure_integrity(error)
        self.url_gfc.assert_not_called()
        self.url_tavily.assert_not_called()
        self.persisted_eval.assert_not_called()

    def test_text_vault_candidate_never_runs_equivalence_or_gains_authority(self):
        self.equivalent_context()
        self.target.claim_type = Claim.ClaimType.TEXT
        self.target.save()
        tasks.execute_core_text_pipeline("Submitted text", self.target.pk)
        self.assert_ai_path(self.image_gfc)
        self.llm.assert_not_called()

    def test_vault_analytics_failure_does_not_suppress_equivalent_resolution(self):
        self.equivalent_context()
        self.vault.side_effect = services.search_official_vault
        with patch(
            "api.knowledge_reuse_service.find_published_fact_check_match",
            return_value=PublishedFactCheckMatch(
                self.publication,
                "SEMANTIC",
                0.91,
            ),
        ), patch(
            "api.knowledge_reuse_service.record_knowledge_reuse",
            side_effect=RuntimeError("Analytics failed"),
        ):
            self.image()
        self.assert_equivalent_bypass()

    def test_equivalent_context_failure_rolls_back_reference(self):
        self.equivalent_context()
        original_save = Claim.save

        def fail_context_save(claim, *args, **kwargs):
            if kwargs.get("update_fields") == ["context_text", "last_updated"]:
                raise RuntimeError("Context storage failed")
            return original_save(claim, *args, **kwargs)

        with patch.object(Claim, "save", new=fail_context_save):
            with self.assertRaises(tasks.ClaimPersistenceError):
                self.image()
        self.assertFalse(self.target.fact_check_references.exists())
        self.assert_no_target_verdicts()
        self.image_gfc.assert_not_called()
        self.assertEqual(
            self.target.verification_runs.get().failure_stage, "claim_persistence"
        )


class PublishedResolutionPollingTests(PublicationResolutionFixture):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()

    def poll(self, claim=None):
        response = self.client.get(
            reverse("claim_status", kwargs={"claim_id": (claim or self.target).pk})
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_exact_reference_with_null_ai_verdict_returns_completed_institutional_result(
        self,
    ):
        self.record()
        result = self.poll()
        self.assertEqual(result["verdict"], self.publication.verdict)
        self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertEqual(
            result["official_fact_check"]["fact_check_id"], str(self.publication.pk)
        )
        self.assertIsNone(result["ai_verdict"])
        self.assertIsNone(result["final_verdict"])

    def test_equivalent_reference_with_null_ai_returns_completed_institutional_result(
        self,
    ):
        with patch(
            "api.knowledge_reuse_service.find_published_fact_check_candidates",
            return_value=[
                PublishedFactCheckMatch(
                    self.publication,
                    KnowledgeReuseEvent.MatchMethod.SEMANTIC,
                    0.91,
                )
            ],
        ), patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(
                {
                    "equivalent": True,
                    "reasoning": "Same complete proposition.",
                    "material_differences": [],
                }
            ),
        ):
            record_equivalent_claim_fact_check_reference(
                target_claim=self.target,
                fact_check=self.publication,
                query_text="Vaccinations do not contain tracking microchips.",
                published_canonical_claim=self.canonical,
                similarity_score=0.91,
            )
        result = self.poll()
        self.assertEqual(result["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertEqual(result["verdict"], self.publication.verdict)
        self.assertEqual(result["summary"], self.publication.summary)
        self.assertEqual(
            result["official_fact_check"]["match_method"], "EQUIVALENT_CLAIM"
        )
        self.assertIsNone(result["ai_verdict"])
        self.assertIsNone(result["final_verdict"])

    def test_unresolved_claim_with_null_ai_verdict_remains_pending(self):
        self.assertEqual(self.poll(), {"verdict": "PENDING"})

    def test_direct_publication_with_null_ai_verdict_is_completed(self):
        self.assertEqual(
            self.poll(self.source_claim)["resolution_source"], "OFFICIAL_FACT_CHECK"
        )

    def test_related_and_wrong_method_references_remain_pending(self):
        for overrides in (
            {"relationship_kind": "RELATED"},
            {"match_method": "EXACT_HEADLINE"},
            {"match_method": "SEMANTIC"},
            {"match_method": "FULL_TEXT"},
        ):
            with self.subTest(overrides=overrides):
                reference = self.raw_reference(**overrides)
                self.assertEqual(self.poll(), {"verdict": "PENDING"})
                reference.delete()

    def test_archived_publication_does_not_bypass_pending(self):
        self.record()
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(
            publication_status="ARCHIVED"
        )
        self.assertEqual(self.poll(), {"verdict": "PENDING"})

    def test_thread_and_reuse_event_do_not_bypass_pending(self):
        actor = User.objects.create_user(username="resolution-thread-user")
        Thread.objects.create(claim=self.target, author=actor)
        record_knowledge_reuse(
            fact_check=self.publication,
            target_claim=self.target,
            reuse_type=KnowledgeReuseEvent.ReuseType.VERIFICATION_CONTEXT,
            match_method=KnowledgeReuseEvent.MatchMethod.EXACT_TEXT,
            query_text=self.canonical,
        )
        self.assertEqual(self.poll(), {"verdict": "PENDING"})

    def test_existing_ai_polling_result_is_preserved(self):
        self.target.ai_verdict = "MISLEADING"
        self.target.ai_summary = "An AI analysis summary."
        self.target.save()
        result = self.poll()
        self.assertEqual(result["resolution_source"], "AI")
        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["summary"], self.target.ai_summary)
