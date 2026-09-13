from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    EvidenceSubmission,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OrganizationMembership,
    VerificationAssignment,
)
from api.publishing_service import (
    PublishingConflict,
    abandon_fact_check_draft,
    create_fact_check_draft,
    publish_fact_check,
    return_fact_check_for_rework,
    submit_fact_check_for_review,
    update_fact_check_draft,
)
from api.tests.adjudication.test_adjudication_transaction_contract import (
    AdjudicationContractFixtures,
)


class PublicationWorkflowFixtures(AdjudicationContractFixtures):
    def setUp(self):
        super().setUp()
        self.researcher = User.objects.create_user(
            username="publication-workflow-researcher",
            password="test-password",
        )
        self.owner = User.objects.create_user(
            username="publication-workflow-owner",
            password="test-password",
        )
        self.admin = User.objects.create_user(
            username="publication-workflow-admin",
            password="test-password",
        )
        for user, role in (
            (self.researcher, OrganizationMembership.Role.RESEARCHER),
            (self.owner, OrganizationMembership.Role.OWNER),
            (self.admin, OrganizationMembership.Role.ADMIN),
        ):
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=user,
                role=role,
                status=OrganizationMembership.Status.ACTIVE,
            )

    def decided_context(self, *, suffix="workflow"):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        evidence = context["evidence"][0]
        evidence.evidence_caption = f"Sealed evidence {suffix}."
        evidence.evidence_url = f"https://example.com/sealed-{suffix}"
        evidence.evidence_type = EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION
        evidence.verified_by = self.lead
        evidence.verified_at = timezone.now()
        evidence.save(
            update_fields=[
                "evidence_caption",
                "evidence_url",
                "evidence_type",
                "verified_by",
                "verified_at",
            ]
        )
        context["decision"] = self.issue(context)["decision"]
        return context

    def create_draft(self, context, *, actor=None, suffix="workflow"):
        actor = actor or self.lead
        return create_fact_check_draft(
            decision=context["decision"],
            actor=actor,
            organization_id=self.organization.id,
            expected_decision_revision=context["decision"].revision_number,
            headline=f"Fact check {suffix}",
            summary=f"Summary {suffix}.",
            article_body=f"Complete article analysis {suffix}.",
            source_urls=[f"https://example.com/editorial-{suffix}"],
        )

    def submit(self, context, fact_check, *, actor=None):
        return submit_fact_check_for_review(
            fact_check=fact_check,
            actor=actor or self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=fact_check.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )

    def publish(self, context, fact_check, *, actor=None):
        return publish_fact_check(
            fact_check=fact_check,
            actor=actor or self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=fact_check.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )["fact_check"]

    def supersede_decision(self, context, *, organization=None):
        organization = organization or self.organization
        previous = context["decision"]
        AdjudicationDecision.objects.filter(pk=previous.pk).update(
            is_current=False
        )
        previous.refresh_from_db()
        replacement = AdjudicationDecision.objects.create(
            claim=context["claim"],
            moderation_case=context["case"],
            verdict=AdjudicationDecision.Verdict.MISLEADING,
            canonical_claim="The current claim requires additional context.",
            rationale="A later human adjudication superseded the first decision.",
            decided_by=self.lead,
            organization=organization,
            revision_number=previous.revision_number + 1,
            supersedes=previous,
            is_current=True,
        )
        AdjudicationDecisionEvidenceSnapshot.objects.create(
            decision=replacement,
            claim_id=context["claim"].id,
            evidence_records=previous.evidence_snapshot.evidence_records,
        )
        return replacement


class PublicationWorkflowApiTests(PublicationWorkflowFixtures, APITestCase):
    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def queue_url(self, *, organization=None, queue="DRAFTING", **params):
        organization = organization or self.organization
        query = {
            "organization_id": str(organization.id),
            "queue": queue,
            **params,
        }
        return reverse("publication_work_item_queue") + "?" + "&".join(
            f"{key}={value}" for key, value in query.items()
        )

    def detail_url(self, resource_type, resource_id, *, organization=None):
        organization = organization or self.organization
        return (
            reverse(
                "publication_work_item_detail",
                kwargs={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                },
            )
            + f"?organization_id={organization.id}"
        )

    def create_url(self, claim):
        return reverse(
            "moderation_fact_check_draft_create",
            kwargs={"claim_id": claim.id},
        )

    def mutation_url(self, action, fact_check):
        return reverse(
            f"moderation_fact_check_{action}",
            kwargs={"fact_check_id": fact_check.id},
        )

    def draft_payload(self, context, **overrides):
        values = {
            "organization_id": str(self.organization.id),
            "expected_decision_revision": context["decision"].revision_number,
            "headline": "Reload-safe initial fact check",
            "summary": "A concise editorial summary.",
            "article_body": "A complete article grounded in sealed evidence.",
            "source_urls": ["https://example.com/editorial-api-source"],
        }
        values.update(overrides)
        return values

    def transition_payload(self, context, fact_check, **overrides):
        values = {
            "organization_id": str(self.organization.id),
            "expected_edit_generation": fact_check.edit_generation,
            "expected_decision_revision": context["decision"].revision_number,
        }
        values.update(overrides)
        return values

    def recovery_payload(self, fact_check, **overrides):
        values = {
            "organization_id": str(self.organization.id),
            "expected_edit_generation": fact_check.edit_generation,
            "reason": "The article needs a clearer explanation of the source.",
        }
        values.update(overrides)
        return values

    def test_authentication_and_role_capabilities_are_enforced(self):
        context = self.decided_context(suffix="capabilities")
        anonymous = APIClient().get(self.queue_url())
        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED)

        for actor in (self.lead, self.moderator, self.researcher):
            with self.subTest(actor=actor.username, queue="DRAFTING"):
                response = self.client_for(actor).get(self.queue_url())
                self.assertEqual(response.status_code, status.HTTP_200_OK)

        for actor in (self.owner, self.admin):
            with self.subTest(actor=actor.username, queue="DRAFTING"):
                response = self.client_for(actor).get(self.queue_url())
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertEqual(
            self.client_for(self.lead).get(
                self.queue_url(queue="REVIEW")
            ).status_code,
            status.HTTP_200_OK,
        )
        for actor in (self.moderator, self.researcher, self.owner, self.admin):
            with self.subTest(actor=actor.username, queue="REVIEW"):
                response = self.client_for(actor).get(
                    self.queue_url(queue="REVIEW")
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertTrue(
            any(
                item["resource_id"] == str(context["claim"].id)
                for item in self.client_for(self.lead).get(
                    self.queue_url()
                ).data["results"]
            )
        )

    def test_active_membership_and_verified_active_partner_are_required(self):
        self.decided_context(suffix="partner-state")
        client = self.client_for(self.lead)
        membership = OrganizationMembership.objects.get(
            organization=self.organization,
            user=self.lead,
        )

        membership.status = OrganizationMembership.Status.SUSPENDED
        membership.save(update_fields=["status"])
        self.assertEqual(
            client.get(self.queue_url()).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        membership.status = OrganizationMembership.Status.ACTIVE
        membership.save(update_fields=["status"])

        for field, disabled, restored in (
            (
                "verification_status",
                self.organization.VerificationStatus.PENDING,
                self.organization.VerificationStatus.VERIFIED,
            ),
            (
                "partner_status",
                self.organization.PartnerStatus.SUSPENDED,
                self.organization.PartnerStatus.ACTIVE,
            ),
        ):
            setattr(self.organization, field, disabled)
            self.organization.save(update_fields=[field])
            self.assertEqual(
                client.get(self.queue_url()).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            setattr(self.organization, field, restored)
            self.organization.save(update_fields=[field])

    def test_authorized_empty_queue_has_pagination_envelope(self):
        response = self.client_for(self.lead).get(
            self.queue_url(queue="REVIEW", limit=7, offset=0)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "count": 0,
                "limit": 7,
                "offset": 0,
                "organization": {
                    "id": str(self.organization.id),
                    "name": self.organization.name,
                    "slug": self.organization.slug,
                },
                "results": [],
            },
        )

    def test_drafting_queue_exposes_eligible_draft_and_in_review_initial_work(self):
        eligible = self.decided_context(suffix="eligible")
        draft_context = self.decided_context(suffix="draft")
        draft = self.create_draft(draft_context, suffix="draft")
        review_context = self.decided_context(suffix="review")
        submitted = self.submit(
            review_context,
            self.create_draft(review_context, suffix="review"),
        )

        response = self.client_for(self.researcher).get(self.queue_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_id = {item["resource_id"]: item for item in response.data["results"]}
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(
            by_id[str(eligible["claim"].id)]["resource_type"],
            "ELIGIBLE_CLAIM",
        )
        self.assertEqual(
            by_id[str(draft.id)]["article"]["publication_status"],
            OfficialFactCheck.PublicationStatus.DRAFT,
        )
        self.assertEqual(
            by_id[str(submitted.id)]["article"]["publication_status"],
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        self.assertNotIn("PUBLISH", by_id[str(submitted.id)]["allowed_actions"])

        paged = self.client_for(self.lead).get(
            self.queue_url(limit=1, offset=1)
        )
        self.assertEqual(paged.data["count"], 3)
        self.assertEqual(paged.data["limit"], 1)
        self.assertEqual(paged.data["offset"], 1)
        self.assertEqual(len(paged.data["results"]), 1)

    def test_stale_initial_work_does_not_hide_new_current_decision_eligibility(self):
        context = self.decided_context(suffix="stale-initial")
        stale_draft = self.create_draft(context, suffix="stale-initial")
        current = self.supersede_decision(context)

        response = self.client_for(self.lead).get(self.queue_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_id = {item["resource_id"]: item for item in response.data["results"]}
        self.assertIn(str(stale_draft.id), by_id)
        self.assertIn(str(context["claim"].id), by_id)
        eligible = by_id[str(context["claim"].id)]
        self.assertEqual(eligible["decision"]["id"], str(current.id))
        self.assertEqual(eligible["allowed_actions"], ["CREATE_DRAFT"])

        detail = self.client_for(self.lead).get(
            self.detail_url("ELIGIBLE_CLAIM", context["claim"].id)
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["decision"]["id"], str(current.id))
        self.assertEqual(detail.data["allowed_actions"], ["CREATE_DRAFT"])

    def test_current_decision_active_initial_work_suppresses_duplicate_create(self):
        context = self.decided_context(suffix="current-active")
        draft = self.create_draft(context, suffix="current-active")
        response = self.client_for(self.lead).get(self.queue_url())
        resource_ids = {
            item["resource_id"] for item in response.data["results"]
        }
        self.assertIn(str(draft.id), resource_ids)
        self.assertNotIn(str(context["claim"].id), resource_ids)
        detail = self.client_for(self.lead).get(
            self.detail_url("ELIGIBLE_CLAIM", context["claim"].id)
        )
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_legacy_unsealed_published_work_suppresses_initial_create(self):
        context = self.decided_context(suffix="legacy-published")
        draft = self.create_draft(context, suffix="legacy-published")
        OfficialFactCheck.objects.filter(pk=draft.pk).update(
            organization_id=self.other_organization.id,
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            reviewed_by_id=self.lead.id,
            reviewed_at=timezone.now(),
            published_by_id=self.lead.id,
            published_at=timezone.now(),
        )
        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=draft
            ).exists()
        )

        response = self.client_for(self.lead).get(self.queue_url())
        self.assertNotIn(
            str(context["claim"].id),
            {item["resource_id"] for item in response.data["results"]},
        )
        detail = self.client_for(self.lead).get(
            self.detail_url("ELIGIBLE_CLAIM", context["claim"].id)
        )
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_available_assignment_exposes_conflict_without_create_action(self):
        context = self.decided_context(suffix="available-assignment")
        context["assignment"].status = VerificationAssignment.Status.AVAILABLE
        context["assignment"].save(update_fields=["status"])

        response = self.client_for(self.lead).get(self.queue_url())
        item = next(
            item
            for item in response.data["results"]
            if item["resource_id"] == str(context["claim"].id)
        )
        self.assertNotIn("CREATE_DRAFT", item["allowed_actions"])
        self.assertIn(
            "ASSIGNMENT_CONFLICT",
            {blocker["code"] for blocker in item["blockers"]},
        )
        detail = self.client_for(self.lead).get(
            self.detail_url("ELIGIBLE_CLAIM", context["claim"].id)
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["allowed_actions"], [])
        self.assertIn(
            "ASSIGNMENT_CONFLICT",
            {blocker["code"] for blocker in detail.data["blockers"]},
        )

    def test_legacy_null_initial_work_is_reloadable_through_mutation_responses(self):
        context = self.decided_context(suffix="legacy-null")
        draft = self.create_draft(context, suffix="legacy-null")
        OfficialFactCheck.objects.filter(pk=draft.pk).update(revision_kind=None)
        draft.refresh_from_db()
        client = self.client_for(self.lead)

        drafting = client.get(self.queue_url())
        draft_item = next(
            item
            for item in drafting.data["results"]
            if item["resource_id"] == str(draft.id)
        )
        self.assertEqual(draft_item["workflow_kind"], "INITIAL")
        self.assertEqual(
            draft_item["article"]["publication_status"],
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

        updated = client.patch(
            self.mutation_url("draft_update", draft),
            {
                **self.transition_payload(context, draft),
                "headline": "Updated legacy-compatible draft",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["workflow_kind"], "INITIAL")
        draft.refresh_from_db()

        submitted = client.post(
            self.mutation_url("submit", draft),
            self.transition_payload(context, draft),
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertEqual(submitted.data["workflow_kind"], "INITIAL")
        draft.refresh_from_db()

        review = client.get(self.queue_url(queue="REVIEW"))
        self.assertIn(
            str(draft.id),
            {item["resource_id"] for item in review.data["results"]},
        )
        published = client.post(
            self.mutation_url("publish", draft),
            self.transition_payload(context, draft),
            format="json",
        )
        self.assertEqual(published.status_code, status.HTTP_200_OK)
        self.assertEqual(published.data["workflow_kind"], "INITIAL")

    def test_legacy_null_draft_advertises_and_completes_abandonment(self):
        context = self.decided_context(suffix="legacy-null-abandon")
        draft = self.create_draft(context, suffix="legacy-null-abandon")
        OfficialFactCheck.objects.filter(pk=draft.pk).update(revision_kind=None)
        draft.refresh_from_db()
        client = self.client_for(self.lead)

        queue = client.get(self.queue_url())
        item = next(
            item
            for item in queue.data["results"]
            if item["resource_id"] == str(draft.id)
        )
        self.assertEqual(item["workflow_kind"], "INITIAL")
        self.assertIn("ABANDON", item["allowed_actions"])

        response = client.post(
            self.mutation_url("abandon", draft),
            self.recovery_payload(draft),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["workflow_kind"], "INITIAL")
        self.assertEqual(
            response.data["publication_status"],
            OfficialFactCheck.PublicationStatus.ARCHIVED,
        )

    def test_legacy_null_review_advertises_and_completes_return_for_rework(self):
        context = self.decided_context(suffix="legacy-null-rework")
        draft = self.create_draft(context, suffix="legacy-null-rework")
        OfficialFactCheck.objects.filter(pk=draft.pk).update(revision_kind=None)
        draft.refresh_from_db()
        submitted = self.submit(context, draft)
        client = self.client_for(self.lead)

        queue = client.get(self.queue_url(queue="REVIEW"))
        item = next(
            item
            for item in queue.data["results"]
            if item["resource_id"] == str(submitted.id)
        )
        self.assertEqual(item["workflow_kind"], "INITIAL")
        self.assertIn("RETURN_FOR_REWORK", item["allowed_actions"])

        response = client.post(
            self.mutation_url("return_for_rework", submitted),
            self.recovery_payload(submitted),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["workflow_kind"], "INITIAL")
        self.assertEqual(
            response.data["publication_status"],
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

    def test_review_queue_orders_oldest_submission_then_stable_id(self):
        first_context = self.decided_context(suffix="review-oldest")
        first = self.submit(
            first_context,
            self.create_draft(first_context, suffix="review-oldest"),
        )
        second_context = self.decided_context(suffix="review-newest")
        second = self.submit(
            second_context,
            self.create_draft(second_context, suffix="review-newest"),
        )
        now = timezone.now()
        OfficialFactCheck.objects.filter(pk=first.pk).update(
            submitted_for_review_at=now - timedelta(hours=1)
        )
        OfficialFactCheck.objects.filter(pk=second.pk).update(
            submitted_for_review_at=now
        )

        response = self.client_for(self.lead).get(
            self.queue_url(queue="REVIEW")
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["resource_id"] for item in response.data["results"]],
            [str(first.id), str(second.id)],
        )
        self.assertTrue(
            all(
                item["workflow_kind"] == OfficialFactCheck.RevisionKind.INITIAL
                for item in response.data["results"]
            )
        )

    def test_c1_queues_exclude_editorial_and_correction_work(self):
        created = []
        for revision_kind, suffix in (
            (OfficialFactCheck.RevisionKind.EDITORIAL_REVISION, "editorial"),
            (OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION, "correction"),
        ):
            context = self.decided_context(suffix=suffix)
            predecessor = self.create_draft(context, suffix=f"{suffix}-predecessor")
            predecessor = abandon_fact_check_draft(
                fact_check=predecessor,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_edit_generation=predecessor.edit_generation,
                reason="Test-only predecessor for queue filtering.",
            )
            created.append(
                OfficialFactCheck.objects.create(
                    claim=context["claim"],
                    adjudication_decision=context["decision"],
                    organization=self.organization,
                    canonical_claim=context["decision"].canonical_claim,
                    verdict=context["decision"].verdict,
                    headline=f"Excluded {suffix} work",
                    summary=f"Excluded {suffix} summary.",
                    article_body=f"Excluded {suffix} body.",
                    publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
                    version=predecessor.version + 1,
                    drafted_by=self.lead,
                    supersedes=predecessor,
                    revision_kind=revision_kind,
                    revision_reason=f"Test-only {suffix} provenance.",
                    revision_requested_by=self.lead,
                    revision_requested_at=timezone.now(),
                )
            )

        drafting = self.client_for(self.lead).get(self.queue_url())
        review = self.client_for(self.lead).get(self.queue_url(queue="REVIEW"))
        self.assertEqual(drafting.status_code, status.HTTP_200_OK)
        self.assertEqual(review.status_code, status.HTTP_200_OK)
        returned_ids = {
            item["resource_id"]
            for response in (drafting, review)
            for item in response.data["results"]
        }
        for fact_check in created:
            self.assertNotIn(str(fact_check.id), returned_ids)
            self.assertNotIn(str(fact_check.claim_id), returned_ids)

    def test_c1_mutation_endpoints_reject_explicit_revision_work_before_mutation(self):
        client = self.client_for(self.lead)
        for revision_kind, suffix in (
            (OfficialFactCheck.RevisionKind.EDITORIAL_REVISION, "editorial-http"),
            (OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION, "correction-http"),
        ):
            context = self.decided_context(suffix=suffix)
            predecessor = self.create_draft(context, suffix=f"{suffix}-predecessor")
            predecessor = abandon_fact_check_draft(
                fact_check=predecessor,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_edit_generation=predecessor.edit_generation,
                reason="Test-only predecessor for HTTP boundary coverage.",
            )
            revision = OfficialFactCheck.objects.create(
                claim=context["claim"],
                adjudication_decision=context["decision"],
                organization=self.organization,
                canonical_claim=context["decision"].canonical_claim,
                verdict=context["decision"].verdict,
                headline=f"Protected {suffix} headline",
                summary=f"Protected {suffix} summary.",
                article_body=f"Protected {suffix} body.",
                publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
                version=predecessor.version + 1,
                edit_generation=3,
                drafted_by=self.lead,
                supersedes=predecessor,
                revision_kind=revision_kind,
                revision_reason=f"Test-only {suffix} provenance.",
                revision_requested_by=self.lead,
                revision_requested_at=timezone.now(),
            )
            original = {
                "publication_status": revision.publication_status,
                "headline": revision.headline,
                "summary": revision.summary,
                "article_body": revision.article_body,
                "edit_generation": revision.edit_generation,
            }

            for action in (
                "draft_update",
                "submit",
                "publish",
                "return_for_rework",
                "abandon",
            ):
                with self.subTest(revision_kind=revision_kind, action=action):
                    if action == "draft_update":
                        response = client.patch(
                            self.mutation_url(action, revision),
                            {
                                **self.transition_payload(context, revision),
                                "headline": "A C1 endpoint must not apply this edit.",
                            },
                            format="json",
                        )
                    elif action in {"return_for_rework", "abandon"}:
                        response = client.post(
                            self.mutation_url(action, revision),
                            self.recovery_payload(revision),
                            format="json",
                        )
                    else:
                        response = client.post(
                            self.mutation_url(action, revision),
                            self.transition_payload(context, revision),
                            format="json",
                        )
                    self.assertEqual(
                        response.status_code,
                        status.HTTP_404_NOT_FOUND,
                    )
                    revision.refresh_from_db()
                    self.assertEqual(
                        {
                            "publication_status": revision.publication_status,
                            "headline": revision.headline,
                            "summary": revision.summary,
                            "article_body": revision.article_body,
                            "edit_generation": revision.edit_generation,
                        },
                        original,
                    )

    def test_eligible_and_fact_check_detail_are_authoritative_and_minimized(self):
        context = self.decided_context(suffix="details")
        client = self.client_for(self.lead)
        eligible = client.get(
            self.detail_url("ELIGIBLE_CLAIM", context["claim"].id)
        )
        self.assertEqual(eligible.status_code, status.HTTP_200_OK)
        self.assertEqual(eligible.data["allowed_actions"], ["CREATE_DRAFT"])
        self.assertEqual(eligible.data["sealed_evidence"]["count"], 1)
        self.assertEqual(
            eligible.data["sealed_evidence"]["basis"],
            "SEALED_DECISION_EVIDENCE",
        )
        self.assertEqual(
            set(eligible.data["decision"]["decided_by"]),
            {"id", "username"},
        )

        draft = self.create_draft(context, suffix="details")
        detail = client.get(self.detail_url("FACT_CHECK", draft.id))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["id"], str(draft.id))
        self.assertEqual(detail.data["fact_check_id"], str(draft.id))
        self.assertEqual(
            detail.data["concurrency"],
            {
                "edit_generation": 1,
                "article_version": 1,
                "decision_revision": 1,
            },
        )
        self.assertEqual(set(detail.data["drafted_by"]), {"id", "username"})
        self.assertNotIn("email", detail.data["drafted_by"])

        provenance = {
            source["provenance"]: source
            for source in detail.data["source_items"]
        }
        self.assertTrue(provenance["SEALED_EVIDENCE"]["immutable"])
        self.assertTrue(
            provenance["SEALED_EVIDENCE"]["captured_evidence_ids"]
        )
        self.assertFalse(provenance["EDITORIAL"]["immutable"])

    def test_live_evidence_changes_do_not_rewrite_detail_provenance(self):
        context = self.decided_context(suffix="immutable-provenance")
        draft = self.create_draft(context, suffix="immutable-provenance")
        snapshot_record = context["decision"].evidence_snapshot.evidence_records[0]
        original_caption = snapshot_record["evidence_caption"]
        original_url = snapshot_record["evidence_url"]

        EvidenceSubmission.objects.filter(pk=context["evidence"][0].pk).update(
            evidence_caption="Mutated live caption.",
            evidence_url="https://example.com/mutated-live-evidence",
            evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
        )
        response = self.client_for(self.lead).get(
            self.detail_url("FACT_CHECK", draft.id)
        )
        entry = response.data["sealed_evidence"]["entries"][0]
        self.assertEqual(entry["evidence_caption"], original_caption)
        self.assertEqual(entry["evidence_url"], original_url)
        self.assertEqual(
            entry["evidence_status"],
            EvidenceSubmission.EvidenceStatus.VERIFIED,
        )

    def test_sealed_source_preserves_independent_editorial_selection_state(self):
        context = self.decided_context(suffix="dual-source")
        shared_url = context["decision"].evidence_snapshot.evidence_records[0][
            "evidence_url"
        ]
        draft = create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            organization_id=self.organization.id,
            expected_decision_revision=context["decision"].revision_number,
            headline="Dual-provenance source",
            summary="The sealed source was also selected editorially.",
            article_body="The article retains both meanings after reload.",
            source_urls=[shared_url],
        )
        client = self.client_for(self.lead)
        detail = client.get(self.detail_url("FACT_CHECK", draft.id))
        shared = next(
            source
            for source in detail.data["source_items"]
            if source["url"] == shared_url
        )
        self.assertEqual(shared["provenance"], "SEALED_EVIDENCE")
        self.assertTrue(shared["captured_evidence_ids"])
        self.assertTrue(shared["is_editorially_selected"])

        no_op = client.patch(
            self.mutation_url("draft_update", draft),
            {
                **self.transition_payload(context, draft),
                "source_urls": [shared_url],
            },
            format="json",
        )
        self.assertEqual(no_op.status_code, status.HTTP_200_OK)
        self.assertEqual(no_op.data["edit_generation"], 1)
        draft.refresh_from_db()

        removed = client.patch(
            self.mutation_url("draft_update", draft),
            {
                **self.transition_payload(context, draft),
                "source_urls": [],
            },
            format="json",
        )
        self.assertEqual(removed.status_code, status.HTTP_200_OK)
        self.assertEqual(removed.data["edit_generation"], 2)
        shared_after = next(
            source
            for source in removed.data["source_items"]
            if source["url"] == shared_url
        )
        self.assertEqual(shared_after["provenance"], "SEALED_EVIDENCE")
        self.assertTrue(shared_after["captured_evidence_ids"])
        self.assertFalse(shared_after["is_editorially_selected"])

    def test_historical_unknown_editorial_selection_is_serialized_as_null(self):
        context = self.decided_context(suffix="unknown-selection")
        draft = self.create_draft(context, suffix="unknown-selection")
        source = draft.source_items.get(
            url=context["decision"].evidence_snapshot.evidence_records[0][
                "evidence_url"
            ]
        )
        type(source).objects.filter(pk=source.pk).update(
            is_editorially_selected=None
        )

        response = self.client_for(self.lead).get(
            self.detail_url("FACT_CHECK", draft.id)
        )
        projected = next(
            item
            for item in response.data["source_items"]
            if item["id"] == str(source.id)
        )
        self.assertIsNone(projected["is_editorially_selected"])

    def test_cross_organization_resources_are_404_without_metadata(self):
        context = self.decided_context(suffix="tenant")
        draft = self.create_draft(context, suffix="tenant")
        for url in (
            self.detail_url(
                "FACT_CHECK",
                draft.id,
                organization=self.other_organization,
            ),
            self.mutation_url("submit", draft),
        ):
            with self.subTest(url=url):
                if "submit" in url:
                    response = self.client_for(self.lead).post(
                        url,
                        {
                            "organization_id": str(self.other_organization.id),
                            "expected_edit_generation": draft.edit_generation,
                            "expected_decision_revision": (
                                context["decision"].revision_number
                            ),
                        },
                        format="json",
                    )
                else:
                    response = self.client_for(self.lead).get(url)
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                self.assertNotIn("current", response.data)

    def test_all_initial_mutations_return_the_common_detail_shape(self):
        context = self.decided_context(suffix="mutations")
        client = self.client_for(self.lead)
        created = client.post(
            self.create_url(context["claim"]),
            self.draft_payload(context),
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        common = {
            "resource_type",
            "resource_id",
            "workflow_kind",
            "fact_check_id",
            "organization",
            "claim",
            "decision",
            "article",
            "sealed_evidence",
            "source_items",
            "allowed_actions",
            "blockers",
            "concurrency",
        }
        self.assertTrue(common.issubset(created.data))
        fact_check = OfficialFactCheck.objects.get(pk=created.data["id"])

        updated = client.patch(
            self.mutation_url("draft_update", fact_check),
            {
                **self.transition_payload(context, fact_check),
                "headline": "Updated initial publication",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertTrue(common.issubset(updated.data))
        fact_check.refresh_from_db()

        submitted = client.post(
            self.mutation_url("submit", fact_check),
            self.transition_payload(context, fact_check),
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertTrue(common.issubset(submitted.data))
        fact_check.refresh_from_db()

        returned = client.post(
            self.mutation_url("return_for_rework", fact_check),
            self.recovery_payload(fact_check),
            format="json",
        )
        self.assertEqual(returned.status_code, status.HTTP_200_OK)
        self.assertTrue(common.issubset(returned.data))
        fact_check.refresh_from_db()

        resubmitted = client.post(
            self.mutation_url("submit", fact_check),
            self.transition_payload(context, fact_check),
            format="json",
        )
        self.assertEqual(resubmitted.status_code, status.HTTP_200_OK)
        fact_check.refresh_from_db()

        published = client.post(
            self.mutation_url("publish", fact_check),
            self.transition_payload(context, fact_check),
            format="json",
        )
        self.assertEqual(published.status_code, status.HTTP_200_OK)
        self.assertTrue(common.issubset(published.data))

        abandon_context = self.decided_context(suffix="abandon-response")
        abandoned_draft = self.create_draft(
            abandon_context,
            suffix="abandon-response",
        )
        abandoned = client.post(
            self.mutation_url("abandon", abandoned_draft),
            self.recovery_payload(abandoned_draft),
            format="json",
        )
        self.assertEqual(abandoned.status_code, status.HTTP_200_OK)
        self.assertTrue(common.issubset(abandoned.data))

    def test_stale_mutations_return_safe_structured_current_state(self):
        context = self.decided_context(suffix="stale")
        client = self.client_for(self.lead)
        draft = self.create_draft(context, suffix="stale")
        update_fact_check_draft(
            fact_check=draft,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=draft.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
            headline="Concurrent headline",
        )

        response = client.patch(
            self.mutation_url("draft_update", draft),
            {
                **self.transition_payload(context, draft),
                "headline": "Stale headline",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "STALE_EDIT_GENERATION")
        self.assertEqual(response.data["current"]["edit_generation"], 2)
        self.assertEqual(response.data["current"]["article_version"], 1)
        self.assertEqual(response.data["current"]["decision_revision"], 1)
        self.assertEqual(response.data["blockers"], [])

        draft.refresh_from_db()
        submitted = self.submit(context, draft)
        stale_generation = submitted.edit_generation - 1
        for action in ("publish", "return_for_rework"):
            with self.subTest(action=action):
                payload = (
                    self.recovery_payload(
                        submitted,
                        expected_edit_generation=stale_generation,
                    )
                    if action == "return_for_rework"
                    else self.transition_payload(
                        context,
                        submitted,
                        expected_edit_generation=stale_generation,
                    )
                )
                result = client.post(
                    self.mutation_url(action, submitted),
                    payload,
                    format="json",
                )
                self.assertEqual(result.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(result.data["code"], "STALE_EDIT_GENERATION")

        returned = return_fact_check_for_rework(
            fact_check=submitted,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=submitted.edit_generation,
            reason="Prepare an abandonment stale-write check.",
        )
        result = client.post(
            self.mutation_url("abandon", returned),
            self.recovery_payload(
                returned,
                expected_edit_generation=returned.edit_generation - 1,
            ),
            format="json",
        )
        self.assertEqual(result.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(result.data["code"], "STALE_EDIT_GENERATION")

    def test_stale_submit_and_stale_decision_revision_are_conflicts(self):
        context = self.decided_context(suffix="stale-submit")
        draft = self.create_draft(context, suffix="stale-submit")
        client = self.client_for(self.lead)
        stale_submit = client.post(
            self.mutation_url("submit", draft),
            self.transition_payload(
                context,
                draft,
                expected_edit_generation=draft.edit_generation + 1,
            ),
            format="json",
        )
        self.assertEqual(stale_submit.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale_submit.data["code"], "STALE_EDIT_GENERATION")

        stale_decision = client.patch(
            self.mutation_url("draft_update", draft),
            {
                **self.transition_payload(
                    context,
                    draft,
                    expected_decision_revision=(
                        context["decision"].revision_number + 1
                    ),
                ),
                "summary": "This request carries a stale decision revision.",
            },
            format="json",
        )
        self.assertEqual(stale_decision.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale_decision.data["code"], "STALE_DECISION_REVISION")


class PublicationWorkflowRecoveryTests(PublicationWorkflowFixtures, TestCase):
    def test_stale_decision_does_not_expose_another_organizations_revision(self):
        context = self.decided_context(suffix="cross-org-current")
        draft = self.create_draft(context, suffix="cross-org-current")
        replacement = self.supersede_decision(
            context,
            organization=self.other_organization,
        )

        with self.assertRaises(PublishingConflict) as raised:
            update_fact_check_draft(
                fact_check=draft,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_edit_generation=draft.edit_generation,
                expected_decision_revision=context["decision"].revision_number,
                headline="This edit must fail against the new decision.",
            )
        self.assertEqual(raised.exception.code, "STALE_DECISION_REVISION")
        self.assertIsNone(raised.exception.current)
        self.assertEqual(replacement.organization, self.other_organization)

    def test_edit_generation_changes_once_per_effective_mutation(self):
        context = self.decided_context(suffix="generation")
        draft = self.create_draft(context, suffix="generation")
        self.assertEqual(draft.edit_generation, 1)

        updated = update_fact_check_draft(
            fact_check=draft,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=1,
            expected_decision_revision=context["decision"].revision_number,
            headline="New headline",
            summary="New summary.",
            article_body="New body.",
            source_urls=["https://example.com/new-editorial-source"],
        )
        self.assertEqual(updated.edit_generation, 2)

        no_op = update_fact_check_draft(
            fact_check=updated,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=2,
            expected_decision_revision=context["decision"].revision_number,
            headline=updated.headline,
            summary=updated.summary,
            article_body=updated.article_body,
            source_urls=["https://example.com/new-editorial-source"],
        )
        self.assertEqual(no_op.edit_generation, 2)

        submitted = self.submit(context, no_op)
        self.assertEqual(submitted.edit_generation, 3)
        returned = return_fact_check_for_rework(
            fact_check=submitted,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=3,
            reason="The article needs another editorial pass.",
        )
        self.assertEqual(returned.edit_generation, 4)

    def test_rework_clears_review_cycle_and_keeps_assignment_active(self):
        context = self.decided_context(suffix="rework")
        submitted = self.submit(
            context,
            self.create_draft(context, suffix="rework"),
        )
        first_submission = submitted.submitted_for_review_at
        returned = return_fact_check_for_rework(
            fact_check=submitted,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_edit_generation=submitted.edit_generation,
            reason="  Clarify the relationship between both sources.  ",
        )
        context["assignment"].refresh_from_db()
        self.assertEqual(
            returned.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )
        self.assertIsNone(returned.submitted_for_review_at)
        self.assertIsNone(returned.reviewed_by)
        self.assertIsNone(returned.published_by)
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )
        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=returned
            ).exists()
        )
        event = ModerationEvent.objects.get(
            case=context["case"],
            event_type=ModerationEvent.EventType.ARTICLE_RETURNED_FOR_REWORK,
        )
        self.assertEqual(
            event.notes,
            "Clarify the relationship between both sources.",
        )
        self.assertEqual(event.metadata["edit_generation"], returned.edit_generation)

        resubmitted = self.submit(context, returned)
        self.assertIsNotNone(resubmitted.submitted_for_review_at)
        self.assertGreater(resubmitted.submitted_for_review_at, first_submission)

    def test_abandon_archives_without_sealing_or_completing_assignment(self):
        context = self.decided_context(suffix="abandon")
        draft = self.create_draft(context, suffix="abandon")
        abandoned = abandon_fact_check_draft(
            fact_check=draft,
            actor=self.researcher,
            organization_id=self.organization.id,
            expected_edit_generation=draft.edit_generation,
            reason="  The draft should be replaced with a new approach.  ",
        )
        context["assignment"].refresh_from_db()
        self.assertEqual(
            abandoned.publication_status,
            OfficialFactCheck.PublicationStatus.ARCHIVED,
        )
        self.assertIsNotNone(abandoned.archived_at)
        self.assertEqual(abandoned.edit_generation, 1)
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )
        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=abandoned
            ).exists()
        )
        event = ModerationEvent.objects.get(
            case=context["case"],
            event_type=ModerationEvent.EventType.ARTICLE_ABANDONED,
        )
        self.assertEqual(
            event.notes,
            "The draft should be replaced with a new approach.",
        )

        replacement = self.create_draft(context, suffix="replacement")
        self.assertEqual(replacement.version, abandoned.version + 1)
        self.assertEqual(
            replacement.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

    def test_recovery_rolls_back_when_event_attribution_fails(self):
        rework_context = self.decided_context(suffix="rollback-rework")
        submitted = self.submit(
            rework_context,
            self.create_draft(rework_context, suffix="rollback-rework"),
        )
        with patch(
            "api.publishing_service._record_publication_event",
            return_value=None,
        ), self.assertRaises(PublishingConflict):
            return_fact_check_for_rework(
                fact_check=submitted,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_edit_generation=submitted.edit_generation,
                reason="This transition cannot lose its event.",
            )
        submitted.refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )

        abandon_context = self.decided_context(suffix="rollback-abandon")
        draft = self.create_draft(abandon_context, suffix="rollback-abandon")
        with patch(
            "api.publishing_service._record_publication_event",
            return_value=None,
        ), self.assertRaises(PublishingConflict):
            abandon_fact_check_draft(
                fact_check=draft,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_edit_generation=draft.edit_generation,
                reason="This transition cannot lose its event.",
            )
        draft.refresh_from_db()
        self.assertEqual(
            draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )
        self.assertIsNone(draft.archived_at)

    def test_publishing_verifies_generation_without_increment_and_seals_it(self):
        context = self.decided_context(suffix="sealed-generation")
        submitted = self.submit(
            context,
            self.create_draft(context, suffix="sealed-generation"),
        )
        generation = submitted.edit_generation
        published = self.publish(context, submitted)
        self.assertEqual(published.edit_generation, generation)
        context["assignment"].refresh_from_db()
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        published.edit_generation += 1
        with self.assertRaises(ValidationError):
            published.save(update_fields=["edit_generation"])
