from copy import deepcopy
from datetime import timedelta
import uuid

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    AdjudicationDecision,
    EvidenceSource,
    EvidenceSubmission,
    FactualCorrectionProposal,
    ModerationCase,
    ModerationEvent,
    OrganizationMembership,
    UserProfile,
    VerificationEvidence,
    VerificationRun,
)
from api.tests.workspace.test_factual_correction_handoff import (
    FactualCorrectionHandoffFixtures,
)


class FactualCorrectionWorkflowApiTests(
    FactualCorrectionHandoffFixtures,
    TestCase,
):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            username="correction-api-owner",
            password="test-password",
        )
        self.platform_moderator = User.objects.create_user(
            username="correction-api-platform-moderator",
            password="test-password",
        )
        self.platform_moderator.profile.role = UserProfile.Role.MOD
        self.platform_moderator.profile.save(update_fields=["role"])
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
        )

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def collection_url(self, *, organization=None, **params):
        organization = organization or self.organization
        values = {"organization_id": organization.id, **params}
        return reverse("factual_correction_collection") + "?" + "&".join(
            f"{key}={value}" for key, value in values.items()
        )

    def detail_url(self, correction, *, organization=None):
        organization = organization or self.organization
        return (
            reverse(
                "factual_correction_detail",
                kwargs={"request_id": getattr(correction, "id", correction)},
            )
            + f"?organization_id={organization.id}"
        )

    @staticmethod
    def request_url(predecessor):
        return reverse(
            "factual_correction_request_create",
            kwargs={"predecessor_id": getattr(predecessor, "id", predecessor)},
        )

    @staticmethod
    def mutation_url(name, correction, **kwargs):
        return reverse(
            name,
            kwargs={
                "request_id": getattr(correction, "id", correction),
                **kwargs,
            },
        )

    def request_payload(self, context, **overrides):
        values = {
            "organization_id": str(self.organization.id),
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
            "correction_reason": (
                "New reporting requires accountable correction review."
            ),
        }
        values.update(overrides)
        return values

    def concurrency_payload(self, context, *, proposal_version, **overrides):
        values = {
            "organization_id": str(self.organization.id),
            "expected_proposal_version": proposal_version,
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
        }
        values.update(overrides)
        return values

    def proposal_payload(self, context, *, proposal_version=0, **overrides):
        values = {
            **self.concurrency_payload(
                context,
                proposal_version=proposal_version,
            ),
            "proposed_verdict": AdjudicationDecision.Verdict.FACT,
            "proposed_canonical_claim": "The corrected claim is supported.",
            "proposed_rationale": "Fresh human review supports this correction.",
            "headline": "Corrected factual finding",
            "summary": "An accountable correction summary.",
            "article_body": "The complete human-reviewed correction analysis.",
            "source_urls": [context["evidence"][0].evidence_url],
        }
        values.update(overrides)
        return values

    def test_request_endpoint_returns_reload_safe_detail_and_preserves_authority(self):
        context = self.make_published_context(suffix="api-request")
        decision_count = AdjudicationDecision.objects.filter(
            claim=context["claim"]
        ).count()

        response = self.client_for(self.lead).post(
            self.request_url(context["published"]),
            self.request_payload(context),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["workflow_kind"], "FACTUAL_CORRECTION")
        self.assertEqual(response.data["stage"], "EVIDENCE_REVIEW")
        self.assertEqual(response.data["request"]["status"], "ACTIVE")
        self.assertEqual(
            set(response.data["request"]["requested_by"]),
            {"id", "username"},
        )
        self.assertEqual(
            response.data["predecessor_publication"]["id"],
            str(context["published"].id),
        )
        self.assertEqual(
            response.data["concurrency"],
            {
                "expected_predecessor_version": context["published"].version,
                "expected_decision_revision": context["decision"].revision_number,
                "expected_proposal_version": 0,
            },
        )
        self.assertIsNone(response.data["proposal"])
        self.assertIn("sealed_predecessor_evidence", response.data)
        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        self.assertTrue(context["decision"].is_current)
        self.assertEqual(
            context["published"].publication_status,
            context["published"].PublicationStatus.PUBLISHED,
        )
        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            decision_count,
        )

    def test_request_validation_authorization_tenant_and_conflicts(self):
        malformed = self.make_published_context(suffix="api-request-malformed")
        self.assertEqual(
            self.client_for(self.lead).post(
                self.request_url(malformed["published"]),
                self.request_payload(malformed, expected_predecessor_version=0),
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        for actor in (self.owner, self.platform_moderator, self.researcher):
            context = self.make_published_context(
                suffix=f"api-request-denied-{actor.username}"
            )
            with self.subTest(actor=actor.username):
                self.assertEqual(
                    self.client_for(actor).post(
                        self.request_url(context["published"]),
                        self.request_payload(context),
                        format="json",
                    ).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        wrong_tenant = self.make_published_context(suffix="api-request-tenant")
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.assertEqual(
            self.client_for(self.lead).post(
                self.request_url(wrong_tenant["published"]),
                self.request_payload(
                    wrong_tenant,
                    organization_id=str(self.other_organization.id),
                ),
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        duplicate = self.make_published_context(suffix="api-request-duplicate")
        first = self.client_for(self.lead).post(
            self.request_url(duplicate["published"]),
            self.request_payload(duplicate),
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            self.client_for(self.lead).post(
                self.request_url(duplicate["published"]),
                self.request_payload(duplicate),
                format="json",
            ).status_code,
            status.HTTP_409_CONFLICT,
        )

        for field in ("expected_predecessor_version", "expected_decision_revision"):
            context = self.make_published_context(suffix=f"api-request-{field}")
            self.assertEqual(
                self.client_for(self.lead).post(
                    self.request_url(context["published"]),
                    self.request_payload(context, **{field: 999}),
                    format="json",
                ).status_code,
                status.HTTP_409_CONFLICT,
            )

    def test_collection_filters_paginates_and_has_bounded_query_growth(self):
        active = self.make_correction_review_context(suffix="api-queue-active")
        cancelled = self.make_correction_review_context(suffix="api-queue-cancelled")
        self.cancel_factual_context(cancelled)

        client = self.client_for(self.lead)
        default = client.get(self.collection_url(limit=1, offset=0))
        self.assertEqual(default.status_code, status.HTTP_200_OK)
        self.assertEqual(default.data["count"], 1)
        self.assertEqual(
            default.data["results"][0]["request_id"],
            str(active["correction_request"].id),
        )
        filtered = client.get(self.collection_url(status="CANCELLED"))
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(filtered.data["results"][0]["stage"], "CANCELLED")
        self.assertEqual(
            client.get(self.collection_url(status="ALL")).data["count"],
            2,
        )

        with CaptureQueriesContext(connection) as one_page_queries:
            client.get(self.collection_url(status="ALL", limit=1))
        with CaptureQueriesContext(connection) as two_page_queries:
            client.get(self.collection_url(status="ALL", limit=2))
        self.assertLessEqual(len(two_page_queries), len(one_page_queries) + 1)

    def cancel_factual_context(self, context):
        return self.client_for(self.lead).post(
            self.mutation_url(
                "factual_correction_cancel",
                context["correction_request"],
            ),
            {
                **self.concurrency_payload(context, proposal_version=0),
                "cancellation_reason": "The report was withdrawn.",
            },
            format="json",
        )

    def test_detail_actions_and_correction_review_provenance_are_actor_specific(self):
        context = self.make_correction_review_context(suffix="api-detail-actions")
        correction = context["correction_request"]

        researcher_detail = self.client_for(self.researcher).get(
            self.detail_url(correction)
        )
        self.assertEqual(researcher_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            researcher_detail.data["allowed_actions"],
            ["SAVE_CORRECTION_PROPOSAL"],
        )
        self.assertEqual(
            self.client_for(self.owner).get(self.detail_url(correction)).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.assertEqual(
            self.client_for(self.lead).get(
                self.detail_url(correction, organization=self.other_organization)
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        saved = self.client_for(self.researcher).put(
            self.mutation_url("factual_correction_proposal_save", correction),
            self.proposal_payload(context),
            format="json",
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        self.assertEqual(saved.data["proposal"]["status"], "DRAFT")

        evidence = context["evidence"][0]
        response = self.client_for(self.moderator).post(
            self.mutation_url(
                "factual_correction_evidence_review",
                correction,
                evidence_id=evidence.id,
            ),
            {
                "organization_id": str(self.organization.id),
                "evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
                "expected_evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
                "expected_case_id": str(context["evidence_case"].id),
                "moderator_notes": "Reaffirmed for this correction.",
                "expected_predecessor_version": context["published"].version,
                "expected_decision_revision": context["decision"].revision_number,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["evidence_review"]["items"][0]
        self.assertTrue(item["has_qualifying_correction_review"])
        self.assertTrue(item["is_reaffirmation"])
        self.assertEqual(
            item["correction_review"]["reviewed_by"]["username"],
            self.moderator.username,
        )
        self.assertEqual(response.data["stage"], "PROPOSAL_DRAFT")
        proposal = FactualCorrectionProposal.objects.get(
            correction_request=correction
        )
        self.assertEqual(proposal.status, FactualCorrectionProposal.Status.DRAFT)

    def test_detail_projects_only_eligible_supporting_verification_runs(self):
        context = self.make_correction_review_context(
            suffix="api-supporting-verification-runs"
        )
        correction = context["correction_request"]
        now = timezone.now()
        older = VerificationRun.objects.create(
            claim=context["claim"],
            status=VerificationRun.Status.COMPLETED,
            pipeline_version="supporting-v1",
            completed_at=now - timedelta(days=2),
        )
        newer = VerificationRun.objects.create(
            claim=context["claim"],
            status=VerificationRun.Status.COMPLETED,
            pipeline_version="supporting-v2",
            completed_at=now - timedelta(days=1),
        )
        evidence_sources = [
            EvidenceSource.objects.create(
                provider="TEST",
                url=f"https://example.com/supporting-run-{index}",
            )
            for index in range(2)
        ]
        for evidence_source in evidence_sources:
            VerificationEvidence.objects.create(
                verification_run=newer,
                evidence_source=evidence_source,
            )

        excluded_status_runs = []
        for run_status in (
            VerificationRun.Status.PENDING,
            VerificationRun.Status.RUNNING,
            VerificationRun.Status.ABSTAINED,
            VerificationRun.Status.FAILED,
            VerificationRun.Status.CANCELLED,
        ):
            excluded_status_runs.append(
                VerificationRun.objects.create(
                    claim=context["claim"],
                    status=run_status,
                    pipeline_version=f"excluded-{run_status.lower()}",
                    completed_at=now,
                )
            )
        completed_without_timestamp = VerificationRun.objects.create(
            claim=context["claim"],
            status=VerificationRun.Status.COMPLETED,
            pipeline_version="excluded-missing-completion",
            completed_at=None,
        )
        other = self.make_published_context(suffix="api-supporting-run-other-claim")
        other_claim_run = VerificationRun.objects.create(
            claim=other["claim"],
            status=VerificationRun.Status.COMPLETED,
            pipeline_version="excluded-other-claim",
            completed_at=now,
        )

        client = self.client_for(self.lead)
        queue = client.get(self.collection_url())
        detail = client.get(self.detail_url(correction))

        self.assertEqual(queue.status_code, status.HTTP_200_OK)
        self.assertTrue(
            all(
                "eligible_verification_runs" not in item
                for item in queue.data["results"]
            )
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        eligible_runs = detail.data["eligible_verification_runs"]
        self.assertEqual(
            [item["id"] for item in eligible_runs],
            [str(newer.id), str(older.id)],
        )
        self.assertEqual(
            [item["evidence_count"] for item in eligible_runs],
            [2, 0],
        )
        self.assertTrue(
            all(
                set(item)
                == {
                    "id",
                    "pipeline_version",
                    "completed_at",
                    "evidence_count",
                }
                for item in eligible_runs
            )
        )
        excluded_ids = {
            str(completed_without_timestamp.id),
            str(other_claim_run.id),
        }
        excluded_ids.update(str(run.id) for run in excluded_status_runs)
        self.assertTrue(
            excluded_ids.isdisjoint({item["id"] for item in eligible_runs})
        )

        saved = self.client_for(self.researcher).put(
            self.mutation_url("factual_correction_proposal_save", correction),
            self.proposal_payload(
                context,
                verification_run_id=str(newer.id),
            ),
            format="json",
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        self.assertEqual(saved.data["proposal"]["verification_run_id"], str(newer.id))
        self.assertIn(
            str(newer.id),
            {item["id"] for item in saved.data["eligible_verification_runs"]},
        )

        denied = self.client_for(self.owner).get(self.detail_url(correction))
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("eligible_verification_runs", denied.data)

        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        wrong_organization = client.get(
            self.detail_url(correction, organization=self.other_organization)
        )
        self.assertEqual(wrong_organization.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("eligible_verification_runs", wrong_organization.data)

    def test_proposal_prepare_publish_endpoints_expose_authoritative_results(self):
        context = self.make_correction_review_context(suffix="api-full-flow")
        self.review_correction(context)
        correction = context["correction_request"]

        saved = self.client_for(self.researcher).put(
            self.mutation_url("factual_correction_proposal_save", correction),
            self.proposal_payload(context),
            format="json",
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        self.assertEqual(saved.data["proposal"]["version"], 1)
        self.assertEqual(saved.data["proposal"]["status"], "DRAFT")
        self.assertEqual(
            saved.data["concurrency"]["expected_proposal_version"],
            1,
        )

        stale = self.client_for(self.researcher).put(
            self.mutation_url("factual_correction_proposal_save", correction),
            self.proposal_payload(context, proposal_version=0),
            format="json",
        )
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)

        prepared = self.client_for(self.lead).post(
            self.mutation_url("factual_correction_proposal_prepare", correction),
            self.concurrency_payload(context, proposal_version=1),
            format="json",
        )
        self.assertEqual(prepared.status_code, status.HTTP_200_OK)
        self.assertEqual(prepared.data["stage"], "PREPARED")
        self.assertEqual(prepared.data["proposal"]["status"], "PREPARED")

        evidence = context["evidence"][0]
        evidence.refresh_from_db()
        evidence_case = context["evidence_case"]
        evidence_case.refresh_from_db()
        proposal = FactualCorrectionProposal.objects.get(
            correction_request=correction
        )
        evidence_state = {
            "evidence_status": evidence.evidence_status,
            "verified_by_id": evidence.verified_by_id,
            "verified_at": evidence.verified_at,
            "moderator_notes": evidence.moderator_notes,
            "rejection_reason": evidence.rejection_reason,
        }
        evidence_case_state = {
            "status": evidence_case.status,
            "resolved_by_id": evidence_case.resolved_by_id,
            "resolved_at": evidence_case.resolved_at,
            "resolution_code": evidence_case.resolution_code,
            "resolution_summary": evidence_case.resolution_summary,
        }
        evidence_case_count = ModerationCase.objects.filter(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
        ).count()
        proposal_state = {
            "status": proposal.status,
            "version": proposal.version,
            "prepared_payload": deepcopy(proposal.prepared_payload),
            "prepared_by_id": proposal.prepared_by_id,
            "prepared_at": proposal.prepared_at,
        }
        correction_event_count = ModerationEvent.objects.filter(
            metadata__correction_request_id=str(correction.id)
        ).count()

        prepared_detail = self.client_for(self.lead).get(
            self.detail_url(correction)
        )
        self.assertEqual(prepared_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(prepared_detail.data["stage"], "PREPARED")
        self.assertNotIn(
            "REVIEW_CORRECTION_EVIDENCE",
            prepared_detail.data["allowed_actions"],
        )
        self.assertIn(
            "PROPOSAL_PREPARED",
            {
                item["code"]
                for item in prepared_detail.data["blockers"][
                    "REVIEW_CORRECTION_EVIDENCE"
                ]
            },
        )
        self.assertTrue(
            all(
                item["allowed_actions"] == []
                for item in prepared_detail.data["evidence_review"]["items"]
            )
        )
        self.assertIn(
            "PUBLISH_FACTUAL_CORRECTION",
            prepared_detail.data["allowed_actions"],
        )
        self.assertIn(
            "CANCEL_FACTUAL_CORRECTION",
            prepared_detail.data["allowed_actions"],
        )

        frozen_review = self.client_for(self.moderator).post(
            self.mutation_url(
                "factual_correction_evidence_review",
                correction,
                evidence_id=evidence.id,
            ),
            {
                "organization_id": str(self.organization.id),
                "evidence_status": EvidenceSubmission.EvidenceStatus.REJECTED,
                "expected_evidence_status": evidence.evidence_status,
                "expected_case_id": str(context["evidence_case"].id),
                "moderator_notes": "This must not alter prepared authority.",
                "rejection_reason": EvidenceSubmission.RejectionReason.IRRELEVANT,
                "expected_predecessor_version": context["published"].version,
                "expected_decision_revision": context["decision"].revision_number,
            },
            format="json",
        )
        self.assertEqual(frozen_review.status_code, status.HTTP_409_CONFLICT)
        evidence.refresh_from_db()
        evidence_case.refresh_from_db()
        proposal.refresh_from_db()
        self.assertEqual(
            {
                "evidence_status": evidence.evidence_status,
                "verified_by_id": evidence.verified_by_id,
                "verified_at": evidence.verified_at,
                "moderator_notes": evidence.moderator_notes,
                "rejection_reason": evidence.rejection_reason,
            },
            evidence_state,
        )
        self.assertEqual(
            {
                "status": evidence_case.status,
                "resolved_by_id": evidence_case.resolved_by_id,
                "resolved_at": evidence_case.resolved_at,
                "resolution_code": evidence_case.resolution_code,
                "resolution_summary": evidence_case.resolution_summary,
            },
            evidence_case_state,
        )
        self.assertEqual(
            ModerationCase.objects.filter(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
            ).count(),
            evidence_case_count,
        )
        self.assertEqual(
            {
                "status": proposal.status,
                "version": proposal.version,
                "prepared_payload": proposal.prepared_payload,
                "prepared_by_id": proposal.prepared_by_id,
                "prepared_at": proposal.prepared_at,
            },
            proposal_state,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(
                metadata__correction_request_id=str(correction.id)
            ).count(),
            correction_event_count,
        )

        immutable = self.client_for(self.researcher).put(
            self.mutation_url("factual_correction_proposal_save", correction),
            self.proposal_payload(context, proposal_version=1),
            format="json",
        )
        self.assertEqual(immutable.status_code, status.HTTP_409_CONFLICT)

        published = self.client_for(self.publisher).post(
            self.mutation_url("factual_correction_publish", correction),
            self.concurrency_payload(context, proposal_version=1),
            format="json",
        )
        self.assertEqual(published.status_code, status.HTTP_200_OK)
        self.assertEqual(published.data["correction"]["stage"], "COMPLETED")
        self.assertEqual(
            published.data["correction"]["completed_publication"]["id"],
            published.data["publication"]["selected_publication_id"],
        )
        self.assertNotEqual(
            published.data["correction"]["current_decision"]["id"],
            published.data["correction"]["predecessor_decision"]["id"],
        )
        self.assertEqual(
            published.data["publication"]["article"]["revision_kind"],
            "FACTUAL_CORRECTION",
        )
        self.assertEqual(
            published.data["publication"]["history_state"],
            "CURRENT",
        )
        self.assertEqual(
            self.client_for(self.lead).post(
                self.mutation_url("factual_correction_cancel", correction),
                {
                    **self.concurrency_payload(context, proposal_version=1),
                    "cancellation_reason": "Too late to cancel.",
                },
                format="json",
            ).status_code,
            status.HTTP_409_CONFLICT,
        )

    def test_prepared_evidence_conflict_preserves_cancellation(self):
        context = self.make_correction_review_context(
            suffix="api-prepared-cancellation"
        )
        self.review_correction(context)
        correction = context["correction_request"]
        saved = self.client_for(self.researcher).put(
            self.mutation_url("factual_correction_proposal_save", correction),
            self.proposal_payload(context),
            format="json",
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        prepared = self.client_for(self.lead).post(
            self.mutation_url("factual_correction_proposal_prepare", correction),
            self.concurrency_payload(context, proposal_version=1),
            format="json",
        )
        self.assertEqual(prepared.status_code, status.HTTP_200_OK)

        evidence = context["evidence"][0]
        frozen_review = self.client_for(self.moderator).post(
            self.mutation_url(
                "factual_correction_evidence_review",
                correction,
                evidence_id=evidence.id,
            ),
            {
                "organization_id": str(self.organization.id),
                "evidence_status": EvidenceSubmission.EvidenceStatus.REJECTED,
                "expected_evidence_status": evidence.evidence_status,
                "expected_case_id": str(context["evidence_case"].id),
                "moderator_notes": "Prepared evidence must stay frozen.",
                "rejection_reason": EvidenceSubmission.RejectionReason.IRRELEVANT,
                "expected_predecessor_version": context["published"].version,
                "expected_decision_revision": context["decision"].revision_number,
            },
            format="json",
        )
        self.assertEqual(frozen_review.status_code, status.HTTP_409_CONFLICT)

        cancelled = self.client_for(self.lead).post(
            self.mutation_url("factual_correction_cancel", correction),
            {
                **self.concurrency_payload(context, proposal_version=1),
                "cancellation_reason": "Cancel after the frozen review was refused.",
            },
            format="json",
        )
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(cancelled.data["stage"], "CANCELLED")

    def test_capability_denial_precedes_internal_identifier_lookup(self):
        context = self.make_correction_review_context(suffix="api-private-identifiers")
        correction = context["correction_request"]
        random_request_id = uuid.uuid4()
        denied_client = self.client_for(self.owner)

        real_detail = denied_client.get(self.detail_url(correction))
        random_detail = denied_client.get(self.detail_url(random_request_id))
        self.assertEqual(real_detail.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(random_detail.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(real_detail.data["code"], "FORBIDDEN")
        self.assertEqual(real_detail.data, random_detail.data)

        cancellation_payload = {
            **self.concurrency_payload(context, proposal_version=0),
            "cancellation_reason": "This actor cannot cancel correction work.",
        }
        real_mutation = denied_client.post(
            self.mutation_url("factual_correction_cancel", correction),
            cancellation_payload,
            format="json",
        )
        random_mutation = denied_client.post(
            self.mutation_url("factual_correction_cancel", random_request_id),
            cancellation_payload,
            format="json",
        )
        self.assertEqual(real_mutation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(random_mutation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(real_mutation.data, random_mutation.data)

        evidence_payload = {
            "organization_id": str(self.organization.id),
            "evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
            "expected_evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
            "expected_case_id": str(context["evidence_case"].id),
            "moderator_notes": "This actor cannot review correction evidence.",
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
        }
        real_evidence = denied_client.post(
            self.mutation_url(
                "factual_correction_evidence_review",
                correction,
                evidence_id=context["evidence"][0].id,
            ),
            evidence_payload,
            format="json",
        )
        random_evidence = denied_client.post(
            self.mutation_url(
                "factual_correction_evidence_review",
                correction,
                evidence_id=uuid.uuid4(),
            ),
            evidence_payload,
            format="json",
        )
        self.assertEqual(real_evidence.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(random_evidence.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(real_evidence.data, random_evidence.data)

        predecessor = self.make_published_context(suffix="api-private-predecessor")
        real_predecessor = denied_client.post(
            self.request_url(predecessor["published"]),
            self.request_payload(predecessor),
            format="json",
        )
        random_predecessor = denied_client.post(
            self.request_url(uuid.uuid4()),
            self.request_payload(predecessor),
            format="json",
        )
        self.assertEqual(real_predecessor.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(random_predecessor.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(real_predecessor.data, random_predecessor.data)

    def test_cancel_endpoint_is_reload_safe_and_rejects_stale_or_denied_calls(self):
        denied = self.make_correction_review_context(suffix="api-cancel-denied")
        self.assertEqual(
            self.client_for(self.researcher).post(
                self.mutation_url(
                    "factual_correction_cancel",
                    denied["correction_request"],
                ),
                {
                    **self.concurrency_payload(denied, proposal_version=0),
                    "cancellation_reason": "No longer required.",
                },
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        stale = self.make_correction_review_context(suffix="api-cancel-stale")
        self.assertEqual(
            self.client_for(self.lead).post(
                self.mutation_url(
                    "factual_correction_cancel",
                    stale["correction_request"],
                ),
                {
                    **self.concurrency_payload(
                        stale,
                        proposal_version=1,
                    ),
                    "cancellation_reason": "No longer required.",
                },
                format="json",
            ).status_code,
            status.HTTP_409_CONFLICT,
        )

        context = self.make_correction_review_context(suffix="api-cancel-success")
        response = self.cancel_factual_context(context)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["stage"], "CANCELLED")
        self.assertEqual(response.data["request"]["status"], "CANCELLED")
        self.assertEqual(response.data["correction_case"]["status"], "CANCELLED")
        self.assertEqual(response.data["allowed_actions"], [])

    def test_correction_cases_are_hidden_from_ordinary_adjudication_apis(self):
        context = self.make_correction_review_context(suffix="api-isolation")
        correction = context["correction_request"]
        client = self.client_for(self.lead)
        queue_url = (
            reverse("adjudication_case_queue")
            + f"?organization_id={self.organization.id}"
        )
        queue = client.get(queue_url)
        self.assertEqual(queue.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            str(context["correction_case"].id),
            {item["id"] for item in queue.data["results"]},
        )
        detail = client.get(
            reverse(
                "adjudication_case_detail",
                kwargs={"case_id": context["correction_case"].id},
            )
            + f"?organization_id={self.organization.id}"
        )
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)
        correction_detail = client.get(self.detail_url(correction))
        self.assertEqual(
            correction_detail.data["correction_case"]["id"],
            str(context["correction_case"].id),
        )

    def test_publications_detail_exposes_separate_correction_workflow(self):
        context = self.make_published_context(suffix="api-publication-integration")
        publication_url = (
            reverse(
                "organization_publication_detail",
                kwargs={"fact_check_id": context["published"].id},
            )
            + f"?organization_id={self.organization.id}"
        )
        before = self.client_for(self.lead).get(publication_url)
        self.assertEqual(before.status_code, status.HTTP_200_OK)
        self.assertIn(
            "REQUEST_FACTUAL_CORRECTION",
            before.data["factual_correction_workflow"]["allowed_actions"],
        )
        researcher_view = self.client_for(self.researcher).get(publication_url)
        self.assertEqual(researcher_view.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            "REQUEST_FACTUAL_CORRECTION",
            researcher_view.data["factual_correction_workflow"]["allowed_actions"],
        )
        editorial_blockers = before.data["blockers"]

        reservation = self.request_correction(context)
        after = self.client_for(self.lead).get(publication_url)
        workflow = after.data["factual_correction_workflow"]
        self.assertEqual(
            workflow["active_request_id"],
            str(reservation["request"].id),
        )
        self.assertEqual(workflow["allowed_actions"], ["OPEN_FACTUAL_CORRECTION"])
        self.assertNotIn("REQUEST_FACTUAL_CORRECTION", workflow["allowed_actions"])
        researcher_after = self.client_for(self.researcher).get(publication_url)
        self.assertEqual(researcher_after.status_code, status.HTTP_200_OK)
        self.assertEqual(
            researcher_after.data["factual_correction_workflow"][
                "allowed_actions"
            ],
            ["OPEN_FACTUAL_CORRECTION"],
        )
        self.assertNotEqual(after.data["blockers"], editorial_blockers)
        self.assertIn(
            "ACTIVE_CORRECTION_RESERVATION",
            {item["code"] for item in after.data["blockers"]},
        )

        owner_view = self.client_for(self.owner).get(publication_url)
        self.assertEqual(owner_view.status_code, status.HTTP_403_FORBIDDEN)

    def test_factual_corrections_do_not_enter_publication_work_items(self):
        context = self.make_correction_review_context(suffix="api-work-item-isolation")
        response = self.client_for(self.lead).get(
            reverse("publication_work_item_queue")
            + f"?organization_id={self.organization.id}"
            "&queue=DRAFTING&workflow_kind=ALL"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            str(context["correction_request"].id),
            {item["resource_id"] for item in response.data["results"]},
        )
        self.assertNotIn(
            "FACTUAL_CORRECTION",
            {item["workflow_kind"] for item in response.data["results"]},
        )
