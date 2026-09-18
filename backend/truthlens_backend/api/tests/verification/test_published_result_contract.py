from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from api.knowledge_reuse_service import (
    InvalidKnowledgeReuse,
    PublishedFactCheckMatch,
    build_published_fact_check_payload,
    build_related_published_fact_check_payload,
)
from api.models import (
    ClaimFactCheckReference,
    KnowledgeReuseEvent,
    OfficialFactCheck,
    Organization,
)
from api.organization_public_presence_service import is_public_partner_eligible
from api.public_publication_query_service import PublicPublicationNotFound


class PublishedResultContractTests(SimpleTestCase):
    """Payload-only checks: no workflow mutation or reuse instrumentation."""

    def setUp(self):
        self.organization = Organization(
            id=uuid4(),
            name="Partner-authored verification",
            slug="public-partner",
            public_profile_enabled=True,
            public_logo_enabled=True,
            logo_url="https://partner.example/logo.png",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.source = SimpleNamespace(
            url="https://source.example/report",
            title="Primary source",
            source_type="MODERATOR_ADDED",
        )
        # The builder consumes publication fields, not live adjudication rows.
        self.publication = SimpleNamespace(
            id=uuid4(),
            claim_id=uuid4(),
            canonical_claim="Canonical published claim",
            headline="Partner publication headline",
            verdict="MISLEADING",
            summary="The publishing partner's own summary.\nSecond paragraph.",
            version=3,
            revision_kind=OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            organization=self.organization,
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            published_at=datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
            source_items=Mock(),
            sources=[],
        )
        self.publication.source_items.all.return_value = [self.source]
        self.match = PublishedFactCheckMatch(
            fact_check=self.publication,
            match_method=KnowledgeReuseEvent.MatchMethod.SEMANTIC,
            similarity_score=0.923456789,
        )
        self.public_detail = {
            "selected_publication_id": str(self.publication.id),
            "organization": {
                "name": self.organization.name,
                "slug": self.organization.slug,
            },
            "article": {
                "headline": self.publication.headline,
            },
            "published_at": self.publication.published_at.isoformat(),
        }
        self.public_detail_lookup = self.enterContext(
            patch(
                "api.knowledge_reuse_service.get_public_partner_fact_check_detail",
                return_value=self.public_detail,
            )
        )

    def build(self):
        return build_published_fact_check_payload(self.match)

    def test_exact_contract_preserves_all_publication_and_match_fields(self):
        self.assertEqual(
            self.build(),
            {
                "fact_check_id": str(self.publication.id),
                "claim_id": str(self.publication.claim_id),
                "canonical_claim": self.publication.canonical_claim,
                "headline": self.publication.headline,
                "verdict": self.publication.verdict,
                "summary": self.publication.summary,
                "version": self.publication.version,
                "revision_kind": self.publication.revision_kind,
                "organization": {
                    "id": str(self.organization.pk),
                    "name": self.organization.name,
                    "slug": self.organization.slug,
                    "public_profile_available": True,
                    "logo_url": self.organization.logo_url,
                },
                "published_at": self.publication.published_at.isoformat(),
                "sources": [
                    {
                        "url": self.source.url,
                        "title": self.source.title,
                        "source_type": self.source.source_type,
                    }
                ],
                "match_method": self.match.match_method,
                "similarity_score": self.match.similarity_score,
            },
        )

    def test_all_revision_kinds_and_legacy_none_are_exposed(self):
        for revision_kind in [*OfficialFactCheck.RevisionKind.values, None]:
            with self.subTest(revision_kind=revision_kind):
                self.publication.revision_kind = revision_kind
                self.assertEqual(self.build()["revision_kind"], revision_kind)

    def test_eligible_partner_with_disabled_logo_never_exposes_stored_logo(self):
        self.organization.public_logo_enabled = False
        organization = self.build()["organization"]
        self.assertTrue(organization["public_profile_available"])
        self.assertIsNone(organization["logo_url"])

    def test_missing_logo_is_not_fabricated(self):
        for logo_url in [None, ""]:
            with self.subTest(logo_url=logo_url):
                self.organization.logo_url = logo_url
                self.assertEqual(self.build()["organization"]["logo_url"], logo_url)

    def test_ineligible_partner_cannot_expose_profile_or_logo(self):
        cases = [
            ("public_profile_enabled", False),
            *[
                ("verification_status", value)
                for value in Organization.VerificationStatus.values
                if value != Organization.VerificationStatus.VERIFIED
            ],
            *[
                ("partner_status", value)
                for value in Organization.PartnerStatus.values
                if value != Organization.PartnerStatus.ACTIVE
            ],
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                original = getattr(self.organization, field)
                setattr(self.organization, field, value)
                organization = self.build()["organization"]
                self.assertFalse(organization["public_profile_available"])
                self.assertIsNone(organization["logo_url"])
                setattr(self.organization, field, original)

    def test_public_availability_delegates_to_existing_eligibility_contract(self):
        with patch(
            "api.knowledge_reuse_service.is_public_partner_eligible",
            wraps=is_public_partner_eligible,
        ) as eligible:
            self.assertTrue(self.build()["organization"]["public_profile_available"])
        eligible.assert_called_once_with(self.organization)

        with patch(
            "api.knowledge_reuse_service.is_public_partner_eligible", return_value=False
        ) as eligible:
            organization = self.build()["organization"]
        eligible.assert_called_once_with(self.organization)
        self.assertFalse(organization["public_profile_available"])
        self.assertIsNone(organization["logo_url"])

    def test_non_published_publication_is_rejected(self):
        for publication_status in OfficialFactCheck.PublicationStatus.values:
            if publication_status == OfficialFactCheck.PublicationStatus.PUBLISHED:
                continue
            with self.subTest(publication_status=publication_status):
                self.publication.publication_status = publication_status
                with self.assertRaises(InvalidKnowledgeReuse):
                    self.build()
        self.publication.source_items.all.assert_not_called()

    def test_optional_legacy_publication_fields_remain_optional(self):
        self.publication.organization = None
        self.publication.claim_id = None
        self.publication.published_at = None
        payload = self.build()
        self.assertIsNone(payload["organization"])
        self.assertIsNone(payload["claim_id"])
        self.assertIsNone(payload["published_at"])
        self.assertIsNone(build_published_fact_check_payload(None))

    def test_legacy_sources_and_match_metadata_remain_unchanged(self):
        self.publication.source_items.all.return_value = []
        self.publication.sources = [
            "https://source.example/legacy",
            {"url": "https://source.example/second", "title": "Legacy title"},
        ]
        self.match = PublishedFactCheckMatch(
            fact_check=self.publication,
            match_method=KnowledgeReuseEvent.MatchMethod.EXACT_TEXT,
            similarity_score=None,
        )
        payload = self.build()
        self.assertEqual(
            payload["sources"],
            [
                {
                    "url": "https://source.example/legacy",
                    "title": None,
                    "source_type": "LEGACY_IMPORT",
                },
                {
                    "url": "https://source.example/second",
                    "title": "Legacy title",
                    "source_type": "LEGACY_IMPORT",
                },
            ],
        )
        self.assertEqual(
            payload["match_method"], KnowledgeReuseEvent.MatchMethod.EXACT_TEXT
        )
        self.assertIsNone(payload["similarity_score"])

    def test_building_payload_emits_no_telemetry_or_ai_replacement_summary(self):
        with patch(
            "api.knowledge_reuse_service.record_knowledge_reuse"
        ) as record, patch(
            "api.knowledge_reuse_service.generate_embedding"
        ) as generate:
            payload = self.build()
        record.assert_not_called()
        generate.assert_not_called()
        self.assertEqual(payload["summary"], self.publication.summary)
        # Exact whitelists also exclude membership, capabilities, invitations,
        # private reviewer data, AI replacement fields and telemetry fields.
        self.assertEqual(
            set(payload),
            {
                "fact_check_id",
                "claim_id",
                "canonical_claim",
                "headline",
                "verdict",
                "summary",
                "version",
                "revision_kind",
                "organization",
                "published_at",
                "sources",
                "match_method",
                "similarity_score",
            },
        )
        self.assertEqual(
            set(payload["organization"]),
            {
                "id",
                "name",
                "slug",
                "public_profile_available",
                "logo_url",
            },
        )

    def related_reference(self, **overrides):
        return SimpleNamespace(
            **{
                "fact_check": self.publication,
                "relationship_kind": "RELATED",
                "match_method": "SEMANTIC",
                "similarity_score": 0.99,
                **overrides,
            }
        )

    def test_related_payload_is_exactly_the_public_reading_whitelist(self):
        payload = build_related_published_fact_check_payload(self.related_reference())
        self.assertEqual(
            payload,
            {
                "fact_check_id": str(self.publication.id),
                "headline": self.public_detail["article"]["headline"],
                "published_at": self.public_detail["published_at"],
                "match_method": "SEMANTIC",
                "organization": {
                    "name": self.organization.name,
                    "slug": self.organization.slug,
                    "public_profile_available": True,
                },
            },
        )
        self.assertEqual(
            set(payload),
            {
                "fact_check_id",
                "headline",
                "published_at",
                "match_method",
                "organization",
            },
        )
        self.assertEqual(
            set(payload["organization"]),
            {
                "name",
                "slug",
                "public_profile_available",
            },
        )
        self.assertTrue(
            {
                "verdict",
                "canonical_claim",
                "summary",
                "sources",
                "similarity_score",
                "ai_verdict",
                "final_verdict",
                "adjudication_decision",
            }.isdisjoint(payload)
        )
        self.publication.source_items.all.assert_not_called()

    def test_related_methods_and_null_publication_date(self):
        self.public_detail["published_at"] = None
        for method in ("SEMANTIC", "FULL_TEXT", "EXACT_HEADLINE", "EXACT_CANONICAL"):
            with self.subTest(method=method):
                payload = build_related_published_fact_check_payload(
                    self.related_reference(match_method=method)
                )
                self.assertEqual(payload["match_method"], method)
                self.assertIsNone(payload["published_at"])
        for method in ("EQUIVALENT_CLAIM", "EXACT_TEXT", "invalid"):
            with self.subTest(method=method):
                self.assertIsNone(
                    build_related_published_fact_check_payload(
                        self.related_reference(match_method=method)
                    )
                )

    def test_related_builder_requires_related_published_public_linkable_partner(self):
        self.assertIsNone(build_related_published_fact_check_payload(None))
        self.assertIsNone(
            build_related_published_fact_check_payload(
                self.related_reference(
                    relationship_kind=ClaimFactCheckReference.RelationshipKind.AUTHORITATIVE
                )
            )
        )
        for status in OfficialFactCheck.PublicationStatus.values:
            if status == "PUBLISHED":
                continue
            with self.subTest(status=status):
                self.publication.publication_status = status
                self.assertIsNone(
                    build_related_published_fact_check_payload(self.related_reference())
                )
        self.publication.publication_status = "PUBLISHED"
        for slug in ("", " "):
            with self.subTest(slug=slug):
                self.organization.slug = slug
                self.assertIsNone(
                    build_related_published_fact_check_payload(self.related_reference())
                )
        self.publication.organization = None
        self.assertIsNone(
            build_related_published_fact_check_payload(self.related_reference())
        )

    def test_related_builder_delegates_eligibility_without_telemetry_or_providers(self):
        with patch(
            "api.knowledge_reuse_service.is_public_partner_eligible", return_value=False
        ) as eligible:
            self.assertIsNone(
                build_related_published_fact_check_payload(self.related_reference())
            )
        eligible.assert_called_once_with(self.organization)
        with patch(
            "api.knowledge_reuse_service.is_public_partner_eligible",
            wraps=is_public_partner_eligible,
        ) as eligible, patch(
            "api.knowledge_reuse_service.record_knowledge_reuse"
        ) as record, patch(
            "api.knowledge_reuse_service.generate_embedding"
        ) as embedding, patch(
            "api.services.call_llm_with_fallback"
        ) as llm:
            payload = build_related_published_fact_check_payload(
                self.related_reference()
            )
        self.assertIsNotNone(payload)
        eligible.assert_called_once_with(self.organization)
        for provider in (record, embedding, llm):
            provider.assert_not_called()

    def test_related_builder_uses_validated_public_projection_not_mutable_live_fields(
        self,
    ):
        self.publication.headline = "Mutable live headline that must not surface"
        self.organization.name = "Mutable live organization name"
        self.organization.slug = "mutable-live-slug"
        self.public_detail.update(
            {
                "selected_publication_id": str(self.publication.id),
                "organization": {
                    "name": "Sealed Public Partner",
                    "slug": "sealed-public-partner",
                },
                "article": {
                    "headline": "Sealed snapshot headline",
                },
                "published_at": "2026-09-15T10:00:00+00:00",
            }
        )

        payload = build_related_published_fact_check_payload(self.related_reference())

        self.public_detail_lookup.assert_called_with(
            organization=self.organization,
            publication_id=self.publication.id,
        )
        self.assertEqual(payload["fact_check_id"], str(self.publication.id))
        self.assertEqual(payload["headline"], "Sealed snapshot headline")
        self.assertEqual(payload["published_at"], "2026-09-15T10:00:00+00:00")
        self.assertEqual(
            payload["organization"],
            {
                "name": "Sealed Public Partner",
                "slug": "sealed-public-partner",
                "public_profile_available": True,
            },
        )

    def test_related_builder_fails_closed_only_for_publication_not_found(self):
        with patch(
            "api.knowledge_reuse_service.get_public_partner_fact_check_detail",
            side_effect=PublicPublicationNotFound("Publication not found."),
        ):
            self.assertIsNone(
                build_related_published_fact_check_payload(self.related_reference())
            )

        with patch(
            "api.knowledge_reuse_service.get_public_partner_fact_check_detail",
            side_effect=RuntimeError("Unexpected public projection failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "Unexpected public projection failure"
            ):
                build_related_published_fact_check_payload(self.related_reference())
