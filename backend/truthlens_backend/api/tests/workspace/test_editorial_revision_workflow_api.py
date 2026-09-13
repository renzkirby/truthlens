from copy import deepcopy

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.factual_correction_service import request_factual_correction
from api.models import (
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
)
from api.tests.workspace.test_publication_workflow_api import (
    PublicationWorkflowFixtures,
)


class EditorialRevisionWorkflowApiTests(PublicationWorkflowFixtures, TestCase):
    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def make_published(self, *, suffix):
        context = self.decided_context(suffix=suffix)
        draft = self.create_draft(context, suffix=suffix)
        context["published"] = self.publish(context, self.submit(context, draft))
        return context

    def create_url(self, predecessor):
        return reverse(
            "editorial_revision_draft_create",
            kwargs={"predecessor_id": predecessor.id},
        )

    def revision_url(self, action, revision):
        return reverse(
            f"editorial_revision_{action}",
            kwargs={"revision_id": revision.id},
        )

    def queue_url(self, *, queue="DRAFTING", workflow_kind=None):
        params = [
            f"organization_id={self.organization.id}",
            f"queue={queue}",
        ]
        if workflow_kind is not None:
            params.append(f"workflow_kind={workflow_kind}")
        return reverse("publication_work_item_queue") + "?" + "&".join(params)

    def detail_url(self, revision, *, workflow_kind=None):
        params = [f"organization_id={self.organization.id}"]
        if workflow_kind is not None:
            params.append(f"workflow_kind={workflow_kind}")
        return (
            reverse(
                "publication_work_item_detail",
                kwargs={"resource_type": "FACT_CHECK", "resource_id": revision.id},
            )
            + "?"
            + "&".join(params)
        )

    def initial_mutation_url(self, action, revision):
        return reverse(
            f"moderation_fact_check_{action}",
            kwargs={"fact_check_id": revision.id},
        )

    def create_payload(self, context, **overrides):
        payload = {
            "organization_id": str(self.organization.id),
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
            "revision_reason": "Clarify the article without changing its verdict.",
        }
        payload.update(overrides)
        return payload

    def transition_payload(self, context, revision, **overrides):
        payload = {
            "organization_id": str(self.organization.id),
            "expected_edit_generation": revision.edit_generation,
            "expected_decision_revision": context["decision"].revision_number,
        }
        payload.update(overrides)
        return payload

    def recovery_payload(self, revision, **overrides):
        payload = {
            "organization_id": str(self.organization.id),
            "expected_edit_generation": revision.edit_generation,
            "reason": "The editorial explanation needs clearer wording.",
        }
        payload.update(overrides)
        return payload

    def publish_payload(self, context, revision, **overrides):
        payload = {
            "organization_id": str(self.organization.id),
            "expected_predecessor_version": context["published"].version,
            "expected_revision_version": revision.version,
            "expected_edit_generation": revision.edit_generation,
            "expected_decision_revision": context["decision"].revision_number,
        }
        payload.update(overrides)
        return payload

    def create_revision(self, context, *, client=None, **overrides):
        response = (client or self.client_for(self.lead)).post(
            self.create_url(context["published"]),
            self.create_payload(context, **overrides),
            format="json",
        )
        return response

    def test_editorial_revision_http_lifecycle_and_publish_generation(self):
        context = self.make_published(suffix="revision-http-lifecycle")
        client = self.client_for(self.lead)

        created = self.create_revision(context, client=client)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["workflow_kind"], "EDITORIAL_REVISION")
        self.assertEqual(created.data["revision"]["kind"], "EDITORIAL_REVISION")
        self.assertEqual(
            created.data["allowed_actions"],
            ["UPDATE_DRAFT", "ABANDON", "SUBMIT"],
        )
        revision = OfficialFactCheck.objects.get(pk=created.data["id"])
        original_authority = (
            revision.claim_id,
            revision.adjudication_decision_id,
            revision.canonical_claim,
            revision.verdict,
        )

        updated = client.patch(
            self.revision_url("draft_update", revision),
            {
                **self.transition_payload(context, revision),
                "headline": "A clearer editorial headline",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        revision.refresh_from_db()
        self.assertEqual(
            (
                revision.claim_id,
                revision.adjudication_decision_id,
                revision.canonical_claim,
                revision.verdict,
            ),
            original_authority,
        )

        submitted = client.post(
            self.revision_url("submit", revision),
            self.transition_payload(context, revision),
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertEqual(
            submitted.data["allowed_actions"],
            ["RETURN_FOR_REWORK", "PUBLISH_REPLACEMENT"],
        )
        revision.refresh_from_db()
        first_review_generation = revision.edit_generation

        returned = client.post(
            self.revision_url("return_for_rework", revision),
            self.recovery_payload(revision),
            format="json",
        )
        self.assertEqual(returned.status_code, status.HTTP_200_OK)
        self.assertEqual(
            returned.data["allowed_actions"],
            ["UPDATE_DRAFT", "ABANDON", "SUBMIT"],
        )
        revision.refresh_from_db()
        self.assertEqual(revision.publication_status, "DRAFT")
        self.assertEqual(revision.edit_generation, first_review_generation + 1)
        self.assertIsNone(revision.submitted_for_review_at)
        rework_event = ModerationEvent.objects.filter(
            case=context["case"],
            event_type=ModerationEvent.EventType.ARTICLE_RETURNED_FOR_REWORK,
        ).latest("created_at")
        self.assertEqual(
            rework_event.metadata["revision_kind"], "EDITORIAL_REVISION"
        )
        self.assertEqual(
            rework_event.metadata["supersedes_fact_check_id"],
            str(context["published"].id),
        )

        resubmitted = client.post(
            self.revision_url("submit", revision),
            self.transition_payload(context, revision),
            format="json",
        )
        self.assertEqual(resubmitted.status_code, status.HTTP_200_OK)
        revision.refresh_from_db()

        stale = client.post(
            self.revision_url("publish", revision),
            self.publish_payload(
                context,
                revision,
                expected_edit_generation=first_review_generation,
            ),
            format="json",
        )
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale.data["code"], "STALE_EDIT_GENERATION")

        published = client.post(
            self.revision_url("publish", revision),
            self.publish_payload(context, revision),
            format="json",
        )
        self.assertEqual(published.status_code, status.HTTP_200_OK)
        self.assertEqual(published.data["history_state"], "CURRENT")
        self.assertEqual(published.data["selected_publication_id"], str(revision.id))
        context["published"].refresh_from_db()
        revision.refresh_from_db()
        self.assertEqual(context["published"].publication_status, "ARCHIVED")
        self.assertEqual(revision.publication_status, "PUBLISHED")
        self.assertEqual(
            revision.adjudication_decision_id,
            context["published"].adjudication_decision_id,
        )

    def test_abandon_releases_predecessor_for_later_revision(self):
        context = self.make_published(suffix="revision-http-abandon")
        client = self.client_for(self.lead)
        created = self.create_revision(context, client=client)
        revision = OfficialFactCheck.objects.get(pk=created.data["id"])

        abandoned = client.post(
            self.revision_url("abandon", revision),
            self.recovery_payload(revision),
            format="json",
        )
        self.assertEqual(abandoned.status_code, status.HTTP_200_OK)
        revision.refresh_from_db()
        self.assertEqual(revision.publication_status, "ARCHIVED")
        self.assertIsNone(revision.published_at)
        abandoned_event = ModerationEvent.objects.filter(
            case=context["case"],
            event_type=ModerationEvent.EventType.ARTICLE_ABANDONED,
        ).latest("created_at")
        self.assertEqual(
            abandoned_event.metadata["revision_kind"], "EDITORIAL_REVISION"
        )

        later = self.create_revision(
            context,
            client=client,
            revision_reason="A later editorial direction is ready to proceed.",
        )
        self.assertEqual(later.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(later.data["id"], str(revision.id))

    def test_revision_resolvers_enforce_kind_scope_and_capability(self):
        context = self.make_published(suffix="revision-http-guards")
        cross_org = self.client_for(self.lead).post(
            self.create_url(context["published"]),
            self.create_payload(
                context,
                organization_id=str(self.other_organization.id),
            ),
            format="json",
        )
        self.assertEqual(cross_org.status_code, status.HTTP_404_NOT_FOUND)

        forbidden = self.create_revision(context, client=self.client_for(self.owner))
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        other_context = self.decided_context(suffix="revision-kind-guards")
        initial = self.create_draft(other_context, suffix="revision-kind-guards")
        initial_response = self.client_for(self.lead).patch(
            self.revision_url("draft_update", initial),
            {
                **self.transition_payload(other_context, initial),
                "headline": "Must not update an initial draft",
            },
            format="json",
        )
        self.assertEqual(initial_response.status_code, status.HTTP_404_NOT_FOUND)

        correction = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Reserved factual correction",
            summary="This row cannot enter editorial routes.",
            article_body="Correction work remains outside C4.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=context["published"].version + 1,
            supersedes=context["published"],
            revision_kind=OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            revision_reason="Reserved factual change.",
            revision_requested_by=self.lead,
            revision_requested_at=timezone.now(),
        )
        correction_response = self.client_for(self.lead).patch(
            self.revision_url("draft_update", correction),
            {
                **self.transition_payload(context, correction),
                "headline": "Must not update correction work",
            },
            format="json",
        )
        self.assertEqual(correction_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_c1_mutation_routes_remain_initial_only(self):
        context = self.make_published(suffix="revision-c1-mutation-isolation")
        created = self.create_revision(context)
        revision = OfficialFactCheck.objects.get(pk=created.data["id"])
        client = self.client_for(self.lead)

        responses = (
            client.patch(
                self.initial_mutation_url("draft_update", revision),
                {
                    **self.transition_payload(context, revision),
                    "headline": "C1 must not edit revision work",
                },
                format="json",
            ),
            client.post(
                self.initial_mutation_url("submit", revision),
                self.transition_payload(context, revision),
                format="json",
            ),
            client.post(
                self.initial_mutation_url("return_for_rework", revision),
                self.recovery_payload(revision),
                format="json",
            ),
            client.post(
                self.initial_mutation_url("abandon", revision),
                self.recovery_payload(revision),
                format="json",
            ),
            client.post(
                self.initial_mutation_url("publish", revision),
                self.transition_payload(context, revision),
                format="json",
            ),
        )
        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_requires_a_current_sealed_predecessor(self):
        context = self.decided_context(suffix="revision-unsealed-predecessor")
        legacy = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Legacy current publication",
            summary="This current record predates publication seals.",
            article_body="It remains internally readable but not revisable.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
            drafted_by=self.lead,
            published_by=self.lead,
            published_at=timezone.now(),
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        context["published"] = legacy

        response = self.create_revision(context)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "PUBLICATION_NOT_READY")

    def test_create_rejects_an_invalid_older_publication_seal(self):
        context = self.make_published(suffix="revision-invalid-history")
        original = context["published"]
        client = self.client_for(self.lead)

        created = self.create_revision(context, client=client)
        first_revision = OfficialFactCheck.objects.get(pk=created.data["id"])
        submitted = client.post(
            self.revision_url("submit", first_revision),
            self.transition_payload(context, first_revision),
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        first_revision.refresh_from_db()
        published = client.post(
            self.revision_url("publish", first_revision),
            self.publish_payload(context, first_revision),
            format="json",
        )
        self.assertEqual(published.status_code, status.HTTP_200_OK)
        first_revision.refresh_from_db()

        original_payload = deepcopy(original.publication_snapshot.payload)
        original_payload["headline"] = "Corrupted historical sealed headline"
        OfficialFactCheckPublicationSnapshot.objects.filter(
            fact_check=original
        ).update(payload=original_payload)
        context["published"] = first_revision
        before_count = OfficialFactCheck.objects.filter(
            claim=context["claim"]
        ).count()

        rejected = self.create_revision(context, client=client)
        self.assertEqual(rejected.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            before_count,
        )
        self.assertFalse(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            ).exists()
        )

    def test_create_rejects_protected_factual_authority_input(self):
        context = self.make_published(suffix="revision-protected-input")
        before_count = OfficialFactCheck.objects.filter(
            claim=context["claim"]
        ).count()

        response = self.create_revision(
            context,
            verdict="FACT",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("verdict", response.data["errors"])
        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            before_count,
        )

    def test_workflow_modes_preserve_c1_defaults_and_exclude_corrections(self):
        revision_context = self.make_published(suffix="revision-queue")
        revision_response = self.create_revision(revision_context)
        revision = OfficialFactCheck.objects.get(pk=revision_response.data["id"])
        initial_context = self.decided_context(suffix="initial-queue")
        initial = self.create_draft(initial_context, suffix="initial-queue")
        correction_context = self.make_published(suffix="correction-queue")
        correction = OfficialFactCheck.objects.create(
            claim=correction_context["claim"],
            adjudication_decision=correction_context["decision"],
            organization=self.organization,
            canonical_claim=correction_context["decision"].canonical_claim,
            verdict=correction_context["decision"].verdict,
            headline="Active correction queue sentinel",
            summary="Must never appear in C4 queues.",
            article_body="Reserved correction workflow.",
            publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            version=correction_context["published"].version + 1,
            supersedes=correction_context["published"],
            revision_kind=OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            revision_reason="Correction queue sentinel.",
            revision_requested_by=self.lead,
            revision_requested_at=timezone.now(),
        )

        client = self.client_for(self.lead)
        default = client.get(self.queue_url())
        self.assertNotIn(
            str(revision.id),
            {item["resource_id"] for item in default.data["results"]},
        )
        self.assertTrue(
            all(item["workflow_kind"] == "INITIAL" for item in default.data["results"])
        )
        self.assertEqual(client.get(self.detail_url(revision)).status_code, 404)

        revisions = client.get(
            self.queue_url(workflow_kind="EDITORIAL_REVISION")
        )
        self.assertEqual(
            [item["resource_id"] for item in revisions.data["results"]],
            [str(revision.id)],
        )
        detail = client.get(
            self.detail_url(revision, workflow_kind="EDITORIAL_REVISION")
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            detail.data["concurrency"]["predecessor_version"],
            revision_context["published"].version,
        )

        combined = client.get(self.queue_url(workflow_kind="ALL"))
        combined_ids = {item["resource_id"] for item in combined.data["results"]}
        self.assertIn(str(initial.id), combined_ids)
        self.assertIn(str(revision.id), combined_ids)
        self.assertNotIn(str(correction.id), combined_ids)
        self.assertNotIn(
            "FACTUAL_CORRECTION",
            {item["workflow_kind"] for item in combined.data["results"]},
        )

    def test_active_correction_reservation_blocks_revision_mutations(self):
        context = self.make_published(suffix="revision-reservation")
        request_factual_correction(
            predecessor_id=context["published"].id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=context["published"].version,
            expected_decision_revision=context["decision"].revision_number,
            correction_reason="Reserve this claim for factual review.",
        )
        blocked_create = self.create_revision(context)
        self.assertEqual(blocked_create.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            blocked_create.data["code"], "ACTIVE_CORRECTION_RESERVATION"
        )
        revision = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Blocked editorial revision",
            summary="Every C4 mutation must respect the reservation.",
            article_body="This work cannot advance while correction is active.",
            publication_status=OfficialFactCheck.PublicationStatus.IN_REVIEW,
            version=context["published"].version + 1,
            supersedes=context["published"],
            revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            revision_reason="Ordinary editorial work.",
            revision_requested_by=self.lead,
            revision_requested_at=timezone.now(),
        )
        client = self.client_for(self.lead)
        update = client.patch(
            self.revision_url("draft_update", revision),
            {
                **self.transition_payload(context, revision),
                "headline": "Blocked update",
            },
            format="json",
        )
        submit = client.post(
            self.revision_url("submit", revision),
            self.transition_payload(context, revision),
            format="json",
        )
        abandon = client.post(
            self.revision_url("abandon", revision),
            self.recovery_payload(revision),
            format="json",
        )
        returned = client.post(
            self.revision_url("return_for_rework", revision),
            self.recovery_payload(revision),
            format="json",
        )
        published = client.post(
            self.revision_url("publish", revision),
            self.publish_payload(context, revision),
            format="json",
        )
        for response in (update, submit, abandon, returned, published):
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data["code"], "ACTIVE_CORRECTION_RESERVATION")
