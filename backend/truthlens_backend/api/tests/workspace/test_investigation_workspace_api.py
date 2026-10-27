"""Guided Investigation Workspace read-projection API tests."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    Claim,
    EvidenceReviewDecision,
    EvidenceSubmission,
    ModerationCase,
    OfficialFactCheck,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
)


class InvestigationWorkspaceApiTests(APITestCase):
    def setUp(self):
        self.organization = self.partner("guided-a")
        self.other = self.partner("guided-b")
        self.actor = User.objects.create_user(username="guided-lead")
        self.membership = OrganizationMembership.objects.create(
            user=self.actor,
            organization=self.organization,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Guided investigation claim",
            ai_verdict="UNVERIFIED",
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
            "verification_investigation_detail",
            kwargs={"assignment_id": self.assignment.pk},
        )

    def partner(self, slug):
        return Organization.objects.create(
            name=slug,
            slug=slug,
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    def get(self, **scope):
        return self.client.get(
            self.url,
            scope or {"organization_id": self.organization.pk},
        )

    def evidence(self, evidence_status="UNVERIFIED", *, contributor=None):
        contributor = contributor or User.objects.create_user(
            username=f"evidence-{EvidenceSubmission.objects.count()}"
        )
        thread = Thread.objects.create(
            claim=self.claim,
            author=contributor,
            caption="Evidence thread",
        )
        evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=contributor,
            evidence_status=evidence_status,
            evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
            evidence_caption="Evidence",
            evidence_url="https://example.test/evidence",
            verified_at=(
                timezone.now()
                if evidence_status != EvidenceSubmission.EvidenceStatus.UNVERIFIED
                else None
            ),
            verified_by=(
                self.actor
                if evidence_status != EvidenceSubmission.EvidenceStatus.UNVERIFIED
                else None
            ),
        )
        if evidence_status != EvidenceSubmission.EvidenceStatus.UNVERIFIED:
            evidence_case = ModerationCase.objects.create(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
                organization=self.organization,
                status=ModerationCase.Status.RESOLVED,
                resolution_code=evidence_status,
                resolved_by=self.actor,
                resolved_at=evidence.verified_at,
            )
            EvidenceReviewDecision.objects.create(
                evidence_submission=evidence,
                organization=self.organization,
                moderation_case=evidence_case,
                reviewed_by=self.actor,
                disposition=evidence_status,
                notes="Reviewed test evidence.",
                rejection_reason=(
                    EvidenceSubmission.RejectionReason.OTHER
                    if evidence_status == EvidenceSubmission.EvidenceStatus.REJECTED
                    else None
                ),
                reviewed_at=evidence.verified_at,
            )
        return evidence

    def resolved_decision(self):
        case = ModerationCase.objects.create(
            claim=self.claim,
            organization=self.organization,
            case_type=ModerationCase.CaseType.ADJUDICATION,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=AdjudicationDecision.Verdict.FACT,
        )
        decision = AdjudicationDecision.objects.create(
            claim=self.claim,
            organization=self.organization,
            moderation_case=case,
            decided_by=self.actor,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim=self.claim.context_text,
            rationale="Reviewed evidence supports the claim.",
        )
        evidence = (
            EvidenceSubmission.objects.filter(
                thread__claim=self.claim,
                evidence_status__in={
                    EvidenceSubmission.EvidenceStatus.VERIFIED,
                    EvidenceSubmission.EvidenceStatus.REJECTED,
                },
            )
            .select_related("thread", "contributor", "verified_by")
            .order_by("submitted_at", "id")
            .first()
        )
        if evidence is None:
            evidence = self.evidence(EvidenceSubmission.EvidenceStatus.VERIFIED)

        AdjudicationDecisionEvidenceSnapshot.objects.create(
            decision=decision,
            claim_id=self.claim.pk,
            schema_version=1,
            evidence_records=[
                {
                    "id": str(evidence.pk),
                    "thread_id": str(evidence.thread_id),
                    "evidence_status": evidence.evidence_status,
                    "evidence_type": evidence.evidence_type,
                    "evidence_caption": evidence.evidence_caption,
                    "evidence_url": evidence.evidence_url,
                    "contributor_id": str(evidence.contributor_id),
                    "reviewer_id": (
                        str(evidence.verified_by_id)
                        if evidence.verified_by_id is not None
                        else None
                    ),
                    "submitted_at": (
                        evidence.submitted_at.isoformat()
                        if evidence.submitted_at is not None
                        else None
                    ),
                    "reviewed_at": (
                        evidence.verified_at.isoformat()
                        if evidence.verified_at is not None
                        else None
                    ),
                    "moderator_notes": evidence.moderator_notes,
                    "rejection_reason": evidence.rejection_reason,
                }
            ],
        )
        return decision

    def test_requires_authentication_and_organization_scope(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.get().status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(self.actor)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.client.get(self.url, {"organization_id": "invalid"}).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_admin_is_forbidden_from_operational_workspace(self):
        self.membership.role = OrganizationMembership.Role.ADMIN
        self.membership.save(update_fields=["role"])
        self.assertEqual(self.get().status_code, status.HTTP_403_FORBIDDEN)

    def test_existing_operational_roles_can_view(self):
        for role in (
            OrganizationMembership.Role.LEAD_VERIFIER,
            OrganizationMembership.Role.VERIFICATION_REVIEWER,
            OrganizationMembership.Role.RESEARCHER,
        ):
            with self.subTest(role=role):
                OrganizationMembership.objects.filter(pk=self.membership.pk).update(role=role)
                self.assertEqual(self.get().status_code, status.HTTP_200_OK)

    def test_wrong_organization_does_not_expose_investigation(self):
        self.membership.status = OrganizationMembership.Status.LEFT
        self.membership.save(update_fields=["status"])
        OrganizationMembership.objects.create(
            user=self.actor,
            organization=self.other,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        response = self.get(organization_id=self.other.pk)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_active_assignment_is_required(self):
        VerificationAssignment.objects.filter(pk=self.assignment.pk).update(
            status=VerificationAssignment.Status.COMPLETED
        )
        self.assertEqual(self.get().status_code, status.HTTP_404_NOT_FOUND)

    def test_no_evidence_state_and_release_action(self):
        payload = self.get().json()
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["state"]["code"], "ACTIVE_NO_EVIDENCE")
        self.assertEqual(payload["pending"][0]["code"], "NO_EVIDENCE")
        self.assertEqual(
            [item["code"] for item in payload["allowed_actions"]],
            ["RELEASE_INVESTIGATION"],
        )

    def test_claim_payload_includes_community_discussions(self):
        first = Thread.objects.create(
            claim=self.claim,
            author=self.actor,
            caption="First community discussion",
            status=Thread.Status.OPEN,
        )
        second = Thread.objects.create(
            claim=self.claim,
            author=self.actor,
            caption="Second community discussion",
            status=Thread.Status.OPEN,
        )

        payload = self.get().json()
        threads = payload["claim"]["community_threads"]

        self.assertEqual(
            {thread["id"] for thread in threads},
            {str(first.pk), str(second.pk)},
        )
        for thread in threads:
            self.assertEqual(thread["claim_id"], str(self.claim.pk))
            self.assertEqual(
                set(thread),
                {"id", "claim_id", "caption", "status", "created_at"},
            )

    def test_unreviewed_evidence_state_and_review_action(self):
        evidence = self.evidence()
        case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            status=ModerationCase.Status.OPEN,
        )
        payload = self.get().json()
        self.assertEqual(payload["state"]["code"], "EVIDENCE_REVIEW")
        self.assertEqual(payload["evidence"]["unreviewed"], 1)
        self.assertEqual(payload["context_links"]["evidence_case_id"], str(case.pk))
        self.assertEqual(
            [item["code"] for item in payload["allowed_actions"]],
            ["REVIEW_EVIDENCE"],
        )

    def test_inherited_review_requires_successor_action(self):
        contributor = User.objects.create_user(username="guided-inherited-contributor")
        thread = Thread.objects.create(
            claim=self.claim,
            author=contributor,
            caption="Inherited evidence thread",
        )
        evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=contributor,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            verified_by=self.actor,
            verified_at=timezone.now(),
        )
        prior_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.other,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=EvidenceSubmission.EvidenceStatus.VERIFIED,
            resolved_at=timezone.now(),
        )
        EvidenceReviewDecision.objects.create(
            evidence_submission=evidence,
            organization=self.other,
            moderation_case=prior_case,
            disposition=EvidenceReviewDecision.Disposition.VERIFIED,
            reviewed_at=prior_case.resolved_at,
        )
        handoff_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            status=ModerationCase.Status.OPEN,
        )

        payload = self.get().json()

        self.assertEqual(payload["state"]["code"], "EVIDENCE_REVIEW")
        self.assertEqual(payload["evidence"]["unreviewed"], 0)
        self.assertEqual(payload["evidence"]["inherited_review_pending"], 1)
        self.assertEqual(
            [item["code"] for item in payload["pending"]],
            ["INHERITED_EVIDENCE_REVIEW", "ACTIVE_EVIDENCE_CASE"],
        )
        self.assertIn("accept the prior review", payload["state"]["detail"])
        self.assertEqual(
            payload["context_links"]["evidence_case_id"],
            str(handoff_case.pk),
        )

    def test_review_state_is_visible_without_review_permission(self):
        reviewer = User.objects.create_user(username="guided-researcher")
        OrganizationMembership.objects.create(
            user=reviewer,
            organization=self.organization,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        evidence = self.evidence()
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            status=ModerationCase.Status.OPEN,
        )
        self.client.force_authenticate(reviewer)
        payload = self.get().json()
        self.assertEqual(payload["state"]["code"], "EVIDENCE_REVIEW")
        self.assertEqual(payload["allowed_actions"], [])

    def test_reviewed_evidence_with_adjudication_case_is_adjudication(self):
        contributor = User.objects.create_user(username="guided-contributor")
        self.evidence(EvidenceSubmission.EvidenceStatus.VERIFIED, contributor=contributor)
        case = ModerationCase.objects.create(
            claim=self.claim,
            organization=self.organization,
            case_type=ModerationCase.CaseType.ADJUDICATION,
            status=ModerationCase.Status.OPEN,
        )
        payload = self.get().json()
        self.assertEqual(payload["state"]["code"], "ADJUDICATION")
        self.assertEqual(payload["context_links"]["adjudication_case_id"], str(case.pk))
        self.assertIn("ADJUDICATE", [item["code"] for item in payload["allowed_actions"]])

    def test_current_attributable_decision_is_drafting_ready(self):
        self.evidence(EvidenceSubmission.EvidenceStatus.VERIFIED)
        decision = self.resolved_decision()
        payload = self.get().json()
        self.assertEqual(payload["state"]["code"], "DRAFTING_READY")
        self.assertEqual(
            payload["adjudication"]["current_decision"]["id"],
            str(decision.pk),
        )
        self.assertIn("CREATE_DRAFT", [item["code"] for item in payload["allowed_actions"]])

    def test_active_draft_and_review_states(self):
        self.evidence(EvidenceSubmission.EvidenceStatus.VERIFIED)
        decision = self.resolved_decision()
        fact_check = OfficialFactCheck.objects.create(
            claim=self.claim,
            adjudication_decision=decision,
            organization=self.organization,
            canonical_claim=decision.canonical_claim,
            verdict=decision.verdict,
            headline="Draft headline",
            summary="Draft summary",
            article_body="Draft body",
            publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            drafted_by=self.actor,
        )
        draft_payload = self.get().json()
        self.assertEqual(draft_payload["state"]["code"], "DRAFTING")
        self.assertEqual(draft_payload["publication"]["id"], str(fact_check.pk))
        self.assertIn("CONTINUE_DRAFT", [item["code"] for item in draft_payload["allowed_actions"]])

        fact_check.publication_status = OfficialFactCheck.PublicationStatus.IN_REVIEW
        fact_check.submitted_for_review_at = timezone.now()
        fact_check.save(update_fields=["publication_status", "submitted_for_review_at", "updated_at"])
        review_payload = self.get().json()
        self.assertEqual(review_payload["state"]["code"], "PUBLICATION_REVIEW")
        self.assertIn(
            "REVIEW_PUBLICATION",
            [item["code"] for item in review_payload["allowed_actions"]],
        )

    def test_read_projection_does_not_call_ai_or_write(self):
        before = {
            "assignments": VerificationAssignment.objects.count(),
            "cases": ModerationCase.objects.count(),
            "decisions": AdjudicationDecision.objects.count(),
            "fact_checks": OfficialFactCheck.objects.count(),
        }
        with (
            patch(
                "api.services.call_llm_with_fallback",
                side_effect=AssertionError("AI must not run in investigation projection"),
            ),
            patch(
                "api.models.Claim.compute_final_verdict",
                side_effect=AssertionError("Read projection must not compute a verdict"),
            ),
        ):
            first = self.get()
            second = self.get()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(
            before,
            {
                "assignments": VerificationAssignment.objects.count(),
                "cases": ModerationCase.objects.count(),
                "decisions": AdjudicationDecision.objects.count(),
                "fact_checks": OfficialFactCheck.objects.count(),
            },
        )
