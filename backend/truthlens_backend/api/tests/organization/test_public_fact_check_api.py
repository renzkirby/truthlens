import uuid
from copy import deepcopy

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    EvidenceSubmission,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OfficialFactCheckSource,
    Organization,
    OrganizationMembership,
)
from api.publishing_service import (
    abandon_editorial_revision_draft,
    create_editorial_revision_draft,
    create_fact_check_draft,
    publish_fact_check,
    submit_fact_check_for_review,
)
from api.tests.workspace.test_factual_correction_publication_history import (
    FactualCorrectionPublicationHistoryFixtures,
)
from api.throttles import PublicPartnerRateThrottle
from api.views import (
    public_partner_fact_check_detail,
    public_partner_fact_checks,
)


class PublicFactCheckApiTests(
    FactualCorrectionPublicationHistoryFixtures,
    TestCase,
):
    organization_fields = {
        "id",
        "name",
        "slug",
        "logo_url",
        "organization_type",
        "organization_type_label",
    }
    collection_item_fields = {
        "publication_id",
        "claim_id",
        "decision",
        "article",
        "published_at",
        "history",
    }
    detail_fields = {
        "selected_publication_id",
        "current_publication_id",
        "history_state",
        "organization",
        "claim_id",
        "decision",
        "article",
        "published_at",
        "revision",
        "sources",
        "lineage",
    }

    def setUp(self):
        cache.clear()
        super().setUp()
        Organization.objects.filter(
            id__in=[self.organization.id, self.other_organization.id]
        ).update(public_profile_enabled=True)
        self.organization.logo_url = "https://example.com/public-partner-logo.png"
        self.organization.public_logo_enabled = True
        self.organization.save(update_fields=["logo_url", "public_logo_enabled"])
        self.organization.refresh_from_db()
        self.other_organization.refresh_from_db()

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def collection_url(self, organization=None):
        organization = organization or self.organization
        return reverse(
            "public_partner_fact_checks",
            kwargs={"slug": organization.slug},
        )

    def detail_url(self, publication, organization=None):
        organization = organization or self.organization
        publication_id = getattr(publication, "id", publication)
        return reverse(
            "public_partner_fact_check_detail",
            kwargs={
                "slug": organization.slug,
                "publication_id": publication_id,
            },
        )

    def make_published(self, suffix):
        return self.make_published_context(suffix=suffix)

    def set_published_at(self, fact_check, published_at):
        payload = deepcopy(fact_check.publication_snapshot.payload)
        payload["published_at"] = published_at.isoformat()
        OfficialFactCheck.objects.filter(pk=fact_check.pk).update(
            published_at=published_at
        )
        OfficialFactCheckPublicationSnapshot.objects.filter(
            fact_check=fact_check
        ).update(
            captured_at=published_at,
            payload=payload,
        )

    def test_anonymous_collection_and_current_detail_expose_exact_public_contract(self):
        context = self.make_published("public-contract")
        client = APIClient()

        collection = client.get(self.collection_url())
        detail = client.get(self.detail_url(context["published"]))

        self.assertEqual(collection.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(collection.data),
            {"count", "limit", "offset", "organization", "results"},
        )
        self.assertEqual(
            set(collection.data["organization"]),
            self.organization_fields,
        )
        self.assertEqual(collection.data["count"], 1)
        item = collection.data["results"][0]
        self.assertEqual(set(item), self.collection_item_fields)
        self.assertEqual(set(item["decision"]), {"canonical_claim", "verdict"})
        self.assertEqual(
            set(item["article"]),
            {"headline", "summary", "version", "revision_kind"},
        )
        self.assertEqual(
            set(item["history"]),
            {"previous_versions_count", "has_factual_correction"},
        )
        self.assertEqual(set(detail.data), self.detail_fields)
        self.assertEqual(detail.data["history_state"], "CURRENT")
        self.assertEqual(
            detail.data["article"]["article_body"],
            context["seal"].payload["article_body"],
        )
        self.assertEqual(
            detail.data["organization"]["logo_url"],
            self.organization.logo_url,
        )

    def test_existing_public_partner_profile_contract_is_unchanged(self):
        response = APIClient().get(
            reverse("public_partner_detail", kwargs={"slug": self.organization.slug})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data),
            {
                "id",
                "name",
                "slug",
                "description",
                "website",
                "logo_url",
                "organization_type",
                "organization_type_label",
                "expertise_areas",
            },
        )

    def test_public_organization_logo_honors_public_logo_setting(self):
        context = self.make_published("public-logo")

        visible = APIClient().get(self.detail_url(context["published"]))
        self.assertEqual(
            visible.data["organization"]["logo_url"],
            self.organization.logo_url,
        )

        Organization.objects.filter(pk=self.organization.pk).update(
            public_logo_enabled=False
        )

        hidden = APIClient().get(self.detail_url(context["published"]))
        self.assertIsNone(hidden.data["organization"]["logo_url"])

    def test_unknown_and_ineligible_partner_slugs_return_not_found(self):
        client = APIClient()
        context = self.make_published("ineligible-partner")
        unknown = client.get(
            reverse("public_partner_fact_checks", kwargs={"slug": "unknown-partner"})
        )
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)
        unknown_detail = client.get(
            reverse(
                "public_partner_fact_check_detail",
                kwargs={
                    "slug": "unknown-partner",
                    "publication_id": context["published"].id,
                },
            )
        )
        self.assertEqual(unknown_detail.status_code, status.HTTP_404_NOT_FOUND)

        eligibility_changes = (
            {"public_profile_enabled": False},
            {"verification_status": Organization.VerificationStatus.UNVERIFIED},
            {"partner_status": Organization.PartnerStatus.SUSPENDED},
        )
        for changes in eligibility_changes:
            with self.subTest(changes=changes):
                Organization.objects.filter(pk=self.organization.pk).update(**changes)
                response = client.get(self.collection_url())
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                detail_response = client.get(self.detail_url(context["published"]))
                self.assertEqual(
                    detail_response.status_code,
                    status.HTTP_404_NOT_FOUND,
                )
                Organization.objects.filter(pk=self.organization.pk).update(
                    public_profile_enabled=True,
                    verification_status=Organization.VerificationStatus.VERIFIED,
                    partner_status=Organization.PartnerStatus.ACTIVE,
                )

    def test_only_current_cards_appear_and_history_counts_actual_lineage(self):
        context = self.make_published("published-history")
        original = context["published"]
        draft_context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        draft_context["decision"] = self.issue(draft_context)["decision"]
        in_review_draft = create_fact_check_draft(
            decision=draft_context["decision"],
            actor=self.lead,
            organization_id=self.organization.id,
            expected_decision_revision=draft_context["decision"].revision_number,
            headline="Unpublished draft",
            summary="This draft is not public.",
            article_body="Draft body.",
            source_urls=["https://example.com/unpublished-draft"],
        )
        in_review = submit_fact_check_for_review(
            fact_check=in_review_draft,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=in_review_draft.edit_generation,
            expected_decision_revision=draft_context["decision"].revision_number,
        )
        self.assertEqual(
            in_review.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        draft_only_context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        draft_only_context["decision"] = self.issue(draft_only_context)["decision"]
        draft_only = create_fact_check_draft(
            decision=draft_only_context["decision"],
            actor=self.lead,
            organization_id=self.organization.id,
            expected_decision_revision=(draft_only_context["decision"].revision_number),
            headline="Another unpublished draft",
            summary="This draft also remains private.",
            article_body="Draft-only body.",
            source_urls=["https://example.com/draft-only"],
        )

        abandoned = create_editorial_revision_draft(
            predecessor_id=context["published"].id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=context["published"].version,
            expected_decision_revision=context["decision"].revision_number,
            revision_reason="Abandoned wording.",
        )
        abandon_editorial_revision_draft(
            revision=abandoned,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=abandoned.edit_generation,
            reason="Do not publish this revision.",
        )
        replacement = self.make_submitted_revision(
            context,
            reason="Published clarification.",
        )
        context["published"] = self.replace(context, replacement)["fact_check"]

        response = APIClient().get(self.collection_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        item = response.data["results"][0]
        self.assertEqual(item["publication_id"], str(context["published"].id))
        self.assertNotEqual(item["publication_id"], str(original.id))
        self.assertNotEqual(item["publication_id"], str(abandoned.id))
        self.assertNotEqual(item["publication_id"], str(in_review.id))
        self.assertNotEqual(item["publication_id"], str(draft_only.id))
        self.assertEqual(context["published"].version, 3)
        self.assertEqual(item["history"]["previous_versions_count"], 1)
        self.assertNotEqual(
            item["history"]["previous_versions_count"],
            context["published"].version - 1,
        )

    def test_current_and_historical_editorial_details_use_actual_lineage(self):
        context = self.make_published("editorial-lineage")
        original = context["published"]
        original_payload = deepcopy(context["seal"].payload)
        revision = self.make_submitted_revision(
            context,
            reason="Clarify public wording.",
        )
        current = self.replace(context, revision)["fact_check"]

        historical = APIClient().get(self.detail_url(original))
        current_response = APIClient().get(self.detail_url(current))

        self.assertEqual(historical.status_code, status.HTTP_200_OK)
        self.assertEqual(current_response.status_code, status.HTTP_200_OK)
        self.assertEqual(historical.data["history_state"], "SUPERSEDED")
        self.assertEqual(current_response.data["history_state"], "CURRENT")
        self.assertEqual(historical.data["current_publication_id"], str(current.id))
        self.assertEqual(
            [entry["publication_id"] for entry in current_response.data["lineage"]],
            [str(original.id), str(current.id)],
        )
        self.assertEqual(
            current_response.data["decision"]["canonical_claim"],
            original_payload["canonical_claim"],
        )
        self.assertEqual(
            current_response.data["decision"]["verdict"],
            original_payload["verdict"],
        )
        self.assertEqual(
            current_response.data["revision"]["reason"],
            "Clarify public wording.",
        )
        self.assertEqual(
            set(current_response.data["revision"]),
            {"kind", "reason", "requested_at", "predecessor"},
        )
        self.assertEqual(
            current_response.data["revision"]["predecessor"]["publication_id"],
            str(original.id),
        )
        self.assertTrue(
            all(
                set(item)
                == {
                    "publication_id",
                    "version",
                    "revision_kind",
                    "headline",
                    "canonical_claim",
                    "verdict",
                    "published_at",
                    "history_state",
                    "revision_reason",
                }
                for item in current_response.data["lineage"]
            )
        )

    def test_factual_correction_projects_changed_decision_and_history_flag(self):
        context = self.make_prepared_context(suffix="public-correction")
        original = context["published"]
        original_payload = deepcopy(context["seal"].payload)
        corrected = self.finalize_prepared_correction(context)

        collection = APIClient().get(self.collection_url())
        detail = APIClient().get(self.detail_url(corrected))

        self.assertTrue(
            collection.data["results"][0]["history"]["has_factual_correction"]
        )
        self.assertEqual(detail.data["article"]["revision_kind"], "FACTUAL_CORRECTION")
        self.assertNotEqual(
            detail.data["decision"]["canonical_claim"],
            original_payload["canonical_claim"],
        )
        self.assertNotEqual(
            detail.data["decision"]["verdict"],
            original_payload["verdict"],
        )
        self.assertEqual(
            detail.data["revision"]["reason"],
            context["correction_request"].correction_reason,
        )
        self.assertEqual(
            [entry["history_state"] for entry in detail.data["lineage"]],
            ["SUPERSEDED", "CURRENT"],
        )
        historical = APIClient().get(self.detail_url(original))
        self.assertEqual(historical.status_code, status.HTTP_200_OK)
        self.assertEqual(historical.data["history_state"], "SUPERSEDED")

    def test_unsealed_and_invalid_current_publications_are_not_public(self):
        valid = self.make_published("valid-baseline")
        legacy_context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        legacy_context["decision"] = self.issue(legacy_context)["decision"]
        legacy = OfficialFactCheck.objects.create(
            claim=legacy_context["claim"],
            adjudication_decision=legacy_context["decision"],
            organization=self.organization,
            canonical_claim=legacy_context["decision"].canonical_claim,
            verdict=legacy_context["decision"].verdict,
            headline="Legacy unsealed publication",
            summary="No trustworthy public seal exists.",
            article_body="Internal legacy content.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
            published_by=self.lead,
            published_at=timezone.now(),
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        invalid = self.make_published("invalid-current")["published"]
        payload = deepcopy(invalid.publication_snapshot.payload)
        payload["headline"] = "Tampered snapshot headline"
        OfficialFactCheckPublicationSnapshot.objects.filter(fact_check=invalid).update(
            payload=payload
        )

        collection = APIClient().get(self.collection_url())
        returned_ids = {item["publication_id"] for item in collection.data["results"]}
        self.assertEqual(returned_ids, {str(valid["published"].id)})
        self.assertEqual(
            APIClient().get(self.detail_url(legacy)).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            APIClient().get(self.detail_url(invalid)).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_invalid_historical_ancestor_blocks_the_complete_public_lineage(self):
        context = self.make_published("invalid-ancestor")
        ancestor = context["published"]
        revision = self.make_submitted_revision(
            context,
            reason="Valid successor wording.",
        )
        current = self.replace(context, revision)["fact_check"]
        payload = deepcopy(ancestor.publication_snapshot.payload)
        payload["summary"] = "Tampered historical summary."
        OfficialFactCheckPublicationSnapshot.objects.filter(fact_check=ancestor).update(
            payload=payload
        )

        collection = APIClient().get(self.collection_url())
        self.assertEqual(collection.data["count"], 0)
        self.assertEqual(
            APIClient().get(self.detail_url(current)).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            APIClient().get(self.detail_url(ancestor)).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_disconnected_lineage_is_omitted_and_not_directly_readable(self):
        context = self.make_published("disconnected-lineage")
        ancestor = context["published"]

        revision = self.make_submitted_revision(
            context,
            reason="Successor before disconnected history.",
        )
        current = self.replace(context, revision)["fact_check"]

        recorded_at = timezone.now()
        disconnected = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Disconnected historical publication",
            summary="This recorded publication is not connected to the current chain.",
            article_body="Historical content is intentionally disconnected.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=current.version + 1,
            drafted_by=self.lead,
            reviewed_by=self.lead,
            reviewed_at=recorded_at,
            published_by=self.lead,
            published_at=recorded_at,
            archived_at=recorded_at,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )

        collection = APIClient().get(self.collection_url())

        self.assertEqual(collection.data["count"], 0)

        self.assertEqual(
            APIClient().get(self.detail_url(current)).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            APIClient().get(self.detail_url(ancestor)).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            APIClient().get(self.detail_url(disconnected)).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_cross_organization_and_unknown_publication_ids_do_not_leak(self):
        context = self.make_published("organization-scope")
        client = APIClient()
        cross_organization = client.get(
            self.detail_url(context["published"], organization=self.other_organization)
        )
        unknown = client.get(self.detail_url(uuid.uuid4()))
        self.assertEqual(cross_organization.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)

    def test_source_and_citation_mappings_are_exact_and_private_data_is_absent(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        context["decision"] = self.issue(context)["decision"]
        evidence_url = context["evidence"][0].evidence_url
        private_actor = User.objects.create_user(
            username="private-source-editor",
            email="private-source-editor@example.com",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=private_actor,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        draft = create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            organization_id=self.organization.id,
            expected_decision_revision=context["decision"].revision_number,
            headline="Public source semantics",
            summary="Only safe source provenance is public.",
            article_body="The published explanation uses snapshot-backed sources.",
            source_urls=[
                evidence_url,
                "https://example.com/editorial-source",
            ],
        )
        OfficialFactCheckSource.objects.filter(
            fact_check=draft,
            source_type=OfficialFactCheckSource.SourceType.MODERATOR_ADDED,
        ).update(is_editorially_selected=False, added_by=private_actor)
        OfficialFactCheckSource.objects.create(
            fact_check=draft,
            url="https://example.com/legacy-source",
            title="Legacy source",
            source_type=OfficialFactCheckSource.SourceType.LEGACY_IMPORT,
            is_editorially_selected=None,
            added_by=private_actor,
        )
        submitted = submit_fact_check_for_review(
            fact_check=draft,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=draft.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )
        published = publish_fact_check(
            fact_check=submitted,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=submitted.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )["fact_check"]

        response = APIClient().get(self.detail_url(published))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            all(
                set(source) == {"url", "title", "source_origin", "citation_state"}
                for source in response.data["sources"]
            )
        )
        by_origin = {
            source["source_origin"]: source for source in response.data["sources"]
        }
        self.assertEqual(
            by_origin["DECISION_EVIDENCE"]["citation_state"],
            "CITED_IN_ARTICLE",
        )
        self.assertEqual(
            by_origin["ORGANIZATION_EDITORIAL"]["citation_state"],
            "NOT_CITED_IN_ARTICLE",
        )
        self.assertEqual(
            by_origin["LEGACY_IMPORT"]["citation_state"],
            "CITATION_HISTORY_UNAVAILABLE",
        )

        serialized = str(response.data)
        snapshot_sources = published.publication_snapshot.payload["sources"]
        evidence_source = next(
            source for source in snapshot_sources if source["lineage"]
        )
        captured_evidence_id = evidence_source["lineage"][0]["captured_evidence_id"]
        for private_value in (
            private_actor.username,
            private_actor.email,
            str(context["decision"].id),
            str(context["decision"].evidence_snapshot.id),
            str(context["evidence"][0].id),
            str(
                OfficialFactCheckSource.objects.filter(fact_check=published)
                .values_list("id", flat=True)
                .first()
            ),
            str(published.publication_snapshot.id),
            str(published.publication_snapshot.decision_snapshot_id),
            captured_evidence_id,
            "added_by",
            "captured_evidence_id",
            "decision_evidence_snapshot_id",
            "publication_snapshot",
            "decided_by",
            "published_by",
            "verification_run_id",
            "ai_verdict",
            "ai_summary",
            "confidence",
            "memberships",
            "capabilities",
            "allowed_actions",
            "blockers",
            "concurrency",
        ):
            self.assertNotIn(private_value, serialized)

    def test_count_filters_invalid_records_before_deterministic_pagination(self):
        first = self.make_published("pagination-first")["published"]
        second = self.make_published("pagination-second")["published"]
        invalid = self.make_published("pagination-invalid")["published"]
        tie_time = timezone.now().replace(microsecond=0)
        self.set_published_at(first, tie_time)
        self.set_published_at(second, tie_time)
        payload = deepcopy(invalid.publication_snapshot.payload)
        payload["article_body"] = "Tampered invalid body."
        OfficialFactCheckPublicationSnapshot.objects.filter(fact_check=invalid).update(
            payload=payload
        )

        first_page = APIClient().get(
            self.collection_url(),
            {"limit": 1, "offset": 0},
        )
        repeated_page = APIClient().get(
            self.collection_url(),
            {"limit": 1, "offset": 0},
        )
        second_page = APIClient().get(
            self.collection_url(),
            {"limit": 1, "offset": 1},
        )
        self.assertEqual(first_page.data["count"], 2)
        self.assertEqual(second_page.data["count"], 2)
        self.assertEqual(first_page.data["results"], repeated_page.data["results"])
        returned_ids = {
            first_page.data["results"][0]["publication_id"],
            second_page.data["results"][0]["publication_id"],
        }
        self.assertEqual(returned_ids, {str(first.id), str(second.id)})
        self.assertEqual(
            [
                first_page.data["results"][0]["publication_id"],
                second_page.data["results"][0]["publication_id"],
            ],
            sorted([str(first.id), str(second.id)]),
        )
        self.assertNotIn(str(invalid.id), returned_ids)

    def test_endpoints_are_get_only_allow_anonymous_and_use_public_throttle(self):
        context = self.make_published("http-contract")
        self.assertEqual(
            public_partner_fact_checks.cls.throttle_classes,
            [PublicPartnerRateThrottle],
        )
        self.assertEqual(
            public_partner_fact_check_detail.cls.throttle_classes,
            [PublicPartnerRateThrottle],
        )
        client = APIClient()
        self.assertEqual(
            client.get(self.collection_url()).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            client.get(self.detail_url(context["published"])).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            client.post(self.collection_url(), {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.patch(
                self.detail_url(context["published"]),
                {},
                format="json",
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_collection_query_validation_is_bounded_and_rejects_unknown_fields(self):
        client = APIClient()
        for params in (
            {"limit": 0},
            {"limit": 51},
            {"offset": -1},
            {"internal": "true"},
        ):
            with self.subTest(params=params):
                response = client.get(self.collection_url(), params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
