from copy import deepcopy

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.factual_correction_service import request_factual_correction
from api.models import (
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OfficialFactCheckSource,
    OrganizationMembership,
)
from api.publishing_service import (
    abandon_editorial_revision_draft,
    create_editorial_revision_draft,
    publish_editorial_revision,
    submit_fact_check_for_review,
)
from api.tests.workspace.test_publication_workflow_api import (
    PublicationWorkflowFixtures,
)


class OrganizationPublicationsApiTests(PublicationWorkflowFixtures, TestCase):
    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def list_url(self, *, organization=None, **params):
        organization = organization or self.organization
        query = {
            "organization_id": str(organization.id),
            **params,
        }
        return reverse("organization_publication_library") + "?" + "&".join(
            f"{key}={value}" for key, value in query.items()
        )

    def detail_url(self, fact_check, *, organization=None):
        organization = organization or self.organization
        return (
            reverse(
                "organization_publication_detail",
                kwargs={"fact_check_id": fact_check.id},
            )
            + f"?organization_id={organization.id}"
        )

    def make_published(self, *, suffix):
        context = self.decided_context(suffix=suffix)
        draft = self.create_draft(context, suffix=suffix)
        context["published"] = self.publish(context, self.submit(context, draft))
        return context

    def make_revision(self, context, *, reason="Clarify the published article."):
        return create_editorial_revision_draft(
            predecessor_id=context["published"].id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=context["published"].version,
            expected_decision_revision=context["decision"].revision_number,
            revision_reason=reason,
        )

    def publish_revision(self, context, revision):
        submitted = submit_fact_check_for_review(
            fact_check=revision,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=revision.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )
        return publish_editorial_revision(
            revision_id=submitted.id,
            predecessor_id=context["published"].id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=context["published"].version,
            expected_revision_version=submitted.version,
            expected_edit_generation=submitted.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )["fact_check"]

    def test_library_authorization_and_cross_organization_detail(self):
        context = self.make_published(suffix="library-authorization")
        self.assertEqual(
            self.client_for(self.researcher).get(self.list_url()).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client_for(self.owner).get(self.list_url()).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            APIClient().get(self.list_url()).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client_for(self.lead)
            .get(
                self.detail_url(
                    context["published"], organization=self.other_organization
                )
            )
            .status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_list_is_current_only_deterministic_and_counts_published_history(self):
        first = self.make_published(suffix="library-current-one")
        second = self.make_published(suffix="library-current-two")

        abandoned = self.make_revision(first, reason="Abandoned editorial attempt.")
        abandon_editorial_revision_draft(
            revision=abandoned,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=abandoned.edit_generation,
            reason="This editorial direction will not be used.",
        )
        replacement = self.make_revision(first, reason="Published editorial update.")
        first["published"] = self.publish_revision(first, replacement)

        response = self.client_for(self.lead).get(self.list_url(limit=1, offset=0))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        next_page = self.client_for(self.lead).get(self.list_url(limit=1, offset=1))
        self.assertEqual(len(next_page.data["results"]), 1)
        returned_ids = {
            response.data["results"][0]["publication_id"],
            next_page.data["results"][0]["publication_id"],
        }
        self.assertEqual(
            returned_ids,
            {str(first["published"].id), str(second["published"].id)},
        )

        item = next(
            item
            for item in (response.data["results"] + next_page.data["results"])
            if item["publication_id"] == str(first["published"].id)
        )
        self.assertEqual(item["history_state"], "CURRENT")
        self.assertEqual(item["lineage"]["previous_versions_count"], 1)
        self.assertEqual(first["published"].version, 3)
        self.assertNotEqual(
            item["lineage"]["previous_versions_count"],
            first["published"].version - 1,
        )
        self.assertNotIn(str(abandoned.id), returned_ids)

    def test_dated_publication_sorts_before_undated_legacy_across_pages(self):
        dated = self.make_published(suffix="library-dated-ordering")
        legacy_context = self.decided_context(suffix="library-undated-ordering")
        legacy = OfficialFactCheck.objects.create(
            claim=legacy_context["claim"],
            adjudication_decision=legacy_context["decision"],
            organization=self.organization,
            canonical_claim=legacy_context["decision"].canonical_claim,
            verdict=legacy_context["decision"].verdict,
            headline="Undated legacy current publication",
            summary="This compatibility record has no known publication time.",
            article_body="It remains visible after dated current publications.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
            drafted_by=self.lead,
            published_by=self.lead,
            published_at=None,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )

        first_page = self.client_for(self.lead).get(
            self.list_url(limit=1, offset=0)
        )
        second_page = self.client_for(self.lead).get(
            self.list_url(limit=1, offset=1)
        )

        self.assertEqual(first_page.status_code, status.HTTP_200_OK)
        self.assertEqual(second_page.status_code, status.HTTP_200_OK)
        self.assertEqual(first_page.data["count"], 2)
        self.assertEqual(second_page.data["count"], 2)
        self.assertEqual(
            first_page.data["results"][0]["publication_id"],
            str(dated["published"].id),
        )
        legacy_item = second_page.data["results"][0]
        self.assertEqual(legacy_item["publication_id"], str(legacy.id))
        self.assertEqual(legacy_item["record_state"], "LEGACY_UNSEALED")
        self.assertEqual(legacy_item["allowed_actions"], [])

    def test_current_and_superseded_detail_exclude_abandoned_draft(self):
        context = self.make_published(suffix="library-lineage")
        original = context["published"]
        abandoned = self.make_revision(context, reason="Discarded wording.")
        abandon_editorial_revision_draft(
            revision=abandoned,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=abandoned.edit_generation,
            reason="Discard this unpublished version.",
        )
        replacement = self.make_revision(context, reason="Clearer organization context.")
        current = self.publish_revision(context, replacement)

        superseded = self.client_for(self.lead).get(self.detail_url(original))
        self.assertEqual(superseded.status_code, status.HTTP_200_OK)
        self.assertEqual(superseded.data["history_state"], "SUPERSEDED")
        self.assertEqual(superseded.data["current_publication_id"], str(current.id))
        superseded_correction = superseded.data["factual_correction_workflow"]
        self.assertNotIn(
            "REQUEST_FACTUAL_CORRECTION",
            superseded_correction["allowed_actions"],
        )
        self.assertIn(
            "HISTORICAL_PUBLICATION",
            {
                item["code"]
                for item in superseded_correction["blockers"][
                    "REQUEST_FACTUAL_CORRECTION"
                ]
            },
        )
        self.assertEqual(superseded.data["blockers"], [])
        current_detail = self.client_for(self.lead).get(self.detail_url(current))
        self.assertEqual(current_detail.data["history_state"], "CURRENT")
        self.assertEqual(current_detail.data["record_state"], "SEALED")
        self.assertEqual(
            current_detail.data["allowed_actions"],
            ["CREATE_EDITORIAL_REVISION"],
        )
        self.assertIn(
            "REQUEST_FACTUAL_CORRECTION",
            current_detail.data["factual_correction_workflow"]["allowed_actions"],
        )
        lineage_ids = {
            item["publication_id"] for item in current_detail.data["lineage"]
        }
        self.assertEqual(lineage_ids, {str(original.id), str(current.id)})
        self.assertNotIn(str(abandoned.id), lineage_ids)
        self.assertEqual(
            current_detail.data["decision"]["decided_by"]["id"], self.lead.id
        )
        self.assertEqual(current_detail.data["published_by"]["id"], self.lead.id)
        self.assertNotIn("payload", current_detail.data)

    def test_record_states_control_revision_action(self):
        sealed = self.make_published(suffix="library-sealed")
        sealed_detail = self.client_for(self.lead).get(
            self.detail_url(sealed["published"])
        )
        self.assertEqual(sealed_detail.data["record_state"], "SEALED")
        self.assertEqual(
            sealed_detail.data["allowed_actions"], ["CREATE_EDITORIAL_REVISION"]
        )
        self.assertIn(
            "REQUEST_FACTUAL_CORRECTION",
            sealed_detail.data["factual_correction_workflow"]["allowed_actions"],
        )

        legacy_context = self.decided_context(suffix="library-legacy")
        legacy = OfficialFactCheck.objects.create(
            claim=legacy_context["claim"],
            adjudication_decision=legacy_context["decision"],
            organization=self.organization,
            canonical_claim=legacy_context["decision"].canonical_claim,
            verdict=legacy_context["decision"].verdict,
            headline="Legacy unsealed publication",
            summary="A readable historical compatibility record.",
            article_body="No publication seal was created for this legacy row.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
            drafted_by=self.lead,
            published_by=self.lead,
            published_at=sealed["published"].published_at,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        legacy_detail = self.client_for(self.lead).get(self.detail_url(legacy))
        self.assertEqual(legacy_detail.data["record_state"], "LEGACY_UNSEALED")
        self.assertEqual(legacy_detail.data["allowed_actions"], [])
        self.assertNotIn(
            "REQUEST_FACTUAL_CORRECTION",
            legacy_detail.data["factual_correction_workflow"]["allowed_actions"],
        )
        self.assertIn(
            "PUBLICATION_NOT_READY",
            {
                item["code"]
                for item in legacy_detail.data["factual_correction_workflow"][
                    "blockers"
                ]["REQUEST_FACTUAL_CORRECTION"]
            },
        )

        invalid = self.make_published(suffix="library-invalid")
        payload = deepcopy(invalid["published"].publication_snapshot.payload)
        payload["headline"] = "Tampered sealed headline"
        OfficialFactCheckPublicationSnapshot.objects.filter(
            fact_check=invalid["published"]
        ).update(payload=payload)
        invalid_detail = self.client_for(self.lead).get(
            self.detail_url(invalid["published"])
        )
        self.assertEqual(invalid_detail.data["record_state"], "INVALID_SEAL")
        self.assertEqual(invalid_detail.data["allowed_actions"], [])
        self.assertNotIn(
            "REQUEST_FACTUAL_CORRECTION",
            invalid_detail.data["factual_correction_workflow"]["allowed_actions"],
        )
        self.assertIn(
            "PUBLICATION_NOT_READY",
            {
                item["code"]
                for item in invalid_detail.data["factual_correction_workflow"][
                    "blockers"
                ]["REQUEST_FACTUAL_CORRECTION"]
            },
        )

    def test_active_correction_and_active_revision_remove_create_action(self):
        correction = self.make_published(suffix="library-correction-reservation")
        request_factual_correction(
            predecessor_id=correction["published"].id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=correction["published"].version,
            expected_decision_revision=correction["decision"].revision_number,
            correction_reason="The factual judgment needs accountable review.",
        )
        response = self.client_for(self.lead).get(
            self.detail_url(correction["published"])
        )
        self.assertEqual(response.data["allowed_actions"], [])
        self.assertIn(
            "ACTIVE_CORRECTION_RESERVATION",
            {item["code"] for item in response.data["blockers"]},
        )

        active = self.make_published(suffix="library-active-revision")
        self.make_revision(active)
        response = self.client_for(self.lead).get(self.detail_url(active["published"]))
        self.assertEqual(response.data["allowed_actions"], [])
        self.assertIn(
            "ACTIVE_PUBLICATION_WORK_EXISTS",
            {item["code"] for item in response.data["blockers"]},
        )

    def test_invalid_historical_ancestor_blocks_revision_action(self):
        context = self.make_published(suffix="library-invalid-ancestor")
        original = context["published"]
        revision = self.make_revision(
            context,
            reason="Publish a valid second version before corrupting history.",
        )
        current = self.publish_revision(context, revision)

        payload = deepcopy(original.publication_snapshot.payload)
        payload["headline"] = "Corrupted historical ancestor headline"
        OfficialFactCheckPublicationSnapshot.objects.filter(
            fact_check=original
        ).update(payload=payload)

        detail = self.client_for(self.lead).get(self.detail_url(current))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["record_state"], "SEALED")
        self.assertNotIn(
            "CREATE_EDITORIAL_REVISION",
            detail.data["allowed_actions"],
        )
        self.assertIn(
            "PUBLICATION_NOT_READY",
            {item["code"] for item in detail.data["blockers"]},
        )

        listing = self.client_for(self.lead).get(self.list_url())
        item = next(
            result
            for result in listing.data["results"]
            if result["publication_id"] == str(current.id)
        )
        self.assertNotIn("CREATE_EDITORIAL_REVISION", item["allowed_actions"])
        self.assertIn(
            "PUBLICATION_NOT_READY",
            {blocker["code"] for blocker in item["blockers"]},
        )

    def test_legacy_current_without_timestamp_is_listed_and_inspectable(self):
        context = self.decided_context(suffix="library-legacy-no-timestamp")
        legacy = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Legacy current publication without timestamp",
            summary="This compatibility record remains internally readable.",
            article_body="It has no publication timestamp or publication seal.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
            drafted_by=self.lead,
            published_by=self.lead,
            published_at=None,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )

        listing = self.client_for(self.lead).get(self.list_url())
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        item = next(
            result
            for result in listing.data["results"]
            if result["publication_id"] == str(legacy.id)
        )
        self.assertEqual(item["record_state"], "LEGACY_UNSEALED")
        self.assertEqual(item["allowed_actions"], [])

        detail = self.client_for(self.lead).get(self.detail_url(legacy))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["record_state"], "LEGACY_UNSEALED")
        self.assertEqual(detail.data["allowed_actions"], [])
        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=legacy
            ).exists()
        )

    def test_sources_preserve_c3_semantics(self):
        publisher = User.objects.create_user(
            username="organization-publication-publisher",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=publisher,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        context = self.decided_context(suffix="library-sources")
        draft = self.create_draft(
            context,
            actor=publisher,
            suffix="library-sources",
        )
        OfficialFactCheckSource.objects.create(
            fact_check=draft,
            url="https://example.com/legacy-source-semantics",
            source_type=OfficialFactCheckSource.SourceType.LEGACY_IMPORT,
            is_editorially_selected=None,
        )
        context["published"] = self.publish(
            context,
            self.submit(context, draft, actor=publisher),
            actor=publisher,
        )
        detail = self.client_for(self.lead).get(self.detail_url(context["published"]))
        by_origin = {
            item["source_origin"]: item for item in detail.data["source_items"]
        }
        self.assertIn("DECISION_EVIDENCE", by_origin)
        self.assertIn("ORGANIZATION_EDITORIAL", by_origin)
        self.assertTrue(
            by_origin["DECISION_EVIDENCE"]["captured_evidence_ids"]
        )
        self.assertEqual(
            by_origin["ORGANIZATION_EDITORIAL"]["added_by"],
            {"id": publisher.id, "username": publisher.username},
        )
        self.assertFalse(
            by_origin["DECISION_EVIDENCE"]["is_editorially_selected"]
        )
        self.assertTrue(
            by_origin["ORGANIZATION_EDITORIAL"]["is_editorially_selected"]
        )
        self.assertIsNone(by_origin["LEGACY_IMPORT"]["is_editorially_selected"])
        self.assertEqual(detail.data["decision"]["decided_by"]["id"], self.lead.id)
        self.assertEqual(detail.data["published_by"]["id"], publisher.id)
        self.assertEqual(
            detail.data["organization"]["id"], str(self.organization.id)
        )

    def test_search_is_current_and_organization_scoped(self):
        if connection.vendor != "postgresql":
            self.skipTest("Publication search uses PostgreSQL search_vector.")
        matching = self.make_published(suffix="library-search-needle")
        self.make_published(suffix="library-search-other")
        other_context = self.decided_context(suffix="library-search-other-org")
        OfficialFactCheck.objects.create(
            claim=other_context["claim"],
            adjudication_decision=other_context["decision"],
            organization=self.other_organization,
            canonical_claim=other_context["decision"].canonical_claim,
            verdict=other_context["decision"].verdict,
            headline="Needle in another organization",
            summary="Must remain tenant scoped.",
            article_body="Needle content.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
            published_by=self.lead,
            published_at=matching["published"].published_at,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        response = self.client_for(self.lead).get(self.list_url(search="needle"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["publication_id"] for item in response.data["results"]],
            [str(matching["published"].id)],
        )
