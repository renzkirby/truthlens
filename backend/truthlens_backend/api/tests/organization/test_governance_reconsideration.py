from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    AccountabilityEvent,
    Organization,
    OrganizationGovernanceNoticeRecipient,
    OrganizationGovernanceReconsideration,
    OrganizationMembership,
)
from api.organization_partnership_lifecycle_service import (
    suspend_partner_organization_partnership,
)


class GovernanceReconsiderationTests(APITestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="reconsideration-platform-admin",
            email="platform@example.com",
            password="test-password",
        )
        self.other_platform_admin = User.objects.create_superuser(
            username="reconsideration-independent-admin",
            email="other-platform@example.com",
            password="test-password",
        )
        self.organization_admin = User.objects.create_user(
            username="reconsideration-org-admin",
            email="org-admin@example.com",
            password="test-password",
        )
        self.member = User.objects.create_user(
            username="reconsideration-member",
            email="member@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Reconsideration Partner",
            slug="reconsideration-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        with self.captureOnCommitCallbacks(execute=True):
            suspend_partner_organization_partnership(
                organization_id=self.organization.pk,
                actor=self.platform_admin,
                suspension_type="REMEDIAL",
                factors=["VERIFICATION_STANDARDS"],
                severity="HIGH",
                rationale=(
                    "Repeated sourcing failures require temporary remediation before "
                    "professional access resumes."
                ),
                policy_basis="Partnership Enforcement Policy §13.1",
                supporting_basis=(
                    "Internal review of affected investigations and corrective history."
                ),
                supporting_references=["RECONSIDERATION-001"],
                remediation_problem="Repeated sourcing failures.",
                remediation_required_action="Correct the sourcing review process.",
                remediation_evidence_required="Updated sourcing procedure.",
                remediation_deadline=timezone.localdate() + timedelta(days=30),
                remediation_review_method="Platform review of submitted procedure.",
                remediation_failure_consequence="Continued proportionate restriction.",
            )
        self.admin_notice = OrganizationGovernanceNoticeRecipient.objects.get(
            governance_event__subject_organization=self.organization,
            governance_event__reason_code="PARTNERSHIP_SUSPENDED",
            user=self.organization_admin,
        )
        self.member_notice = OrganizationGovernanceNoticeRecipient.objects.get(
            governance_event=self.admin_notice.governance_event,
            user=self.member,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def request_payload(self):
        return {
            "grounds": [
                "MATERIAL_FACTS_INCORRECT",
                "RELEVANT_EVIDENCE_OVERLOOKED",
            ],
            "request_statement": (
                "The organization believes the suspension relied on an incorrect "
                "factual premise and omitted relevant review records."
            ),
            "supporting_references": ["ORG-REVIEW-001"],
        }

    def submit(self):
        return self.client_for(self.organization_admin).post(
            reverse(
                "governance_notice_reconsideration",
                kwargs={"notice_id": self.admin_notice.pk},
            ),
            self.request_payload(),
            format="json",
        )

    def test_admin_can_submit_without_restoring_partner_authority(self):
        response = self.submit()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.organization.refresh_from_db()
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.SUSPENDED,
        )
        reconsideration = OrganizationGovernanceReconsideration.objects.get()
        self.assertEqual(reconsideration.status, "SUBMITTED")
        self.assertEqual(reconsideration.suspension_event, self.admin_notice.governance_event)

    def test_member_cannot_submit_reconsideration(self):
        response = self.client_for(self.member).post(
            reverse(
                "governance_notice_reconsideration",
                kwargs={"notice_id": self.member_notice.pk},
            ),
            self.request_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(OrganizationGovernanceReconsideration.objects.count(), 0)

    def test_duplicate_open_request_returns_conflict(self):
        self.assertEqual(self.submit().status_code, status.HTTP_201_CREATED)
        duplicate = self.submit()
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(OrganizationGovernanceReconsideration.objects.count(), 1)

    def test_original_decision_maker_self_review_requires_override_when_admin_available(self):
        reconsideration_id = self.submit().data["id"]
        response = self.client_for(self.platform_admin).post(
            reverse(
                "management_governance_reconsideration_review",
                kwargs={
                    "organization_id": self.organization.pk,
                    "reconsideration_id": reconsideration_id,
                },
            ),
            {"reviewer_independence_note": "Original reviewer context retained."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("independence_override_rationale", response.data)

    def test_independent_admin_can_uphold_suspension(self):
        reconsideration_id = self.submit().data["id"]
        review = self.client_for(self.other_platform_admin).post(
            reverse(
                "management_governance_reconsideration_review",
                kwargs={
                    "organization_id": self.organization.pk,
                    "reconsideration_id": reconsideration_id,
                },
            ),
            {"reviewer_independence_note": "Independent Platform Admin review."},
            format="json",
        )
        self.assertEqual(review.status_code, status.HTTP_200_OK)
        self.assertEqual(review.data["status"], "UNDER_REVIEW")

        resolution = self.client_for(self.other_platform_admin).post(
            reverse(
                "management_governance_reconsideration_resolve",
                kwargs={
                    "organization_id": self.organization.pk,
                    "reconsideration_id": reconsideration_id,
                },
            ),
            {
                "outcome": "UPHELD",
                "resolution_rationale": (
                    "The reconsideration did not establish a basis to revoke the "
                    "current suspension."
                ),
                "internal_supporting_basis": (
                    "Independent review confirmed the suspension record and the "
                    "relevant evidence considered."
                ),
            },
            format="json",
        )
        self.assertEqual(resolution.status_code, status.HTTP_200_OK)
        self.assertEqual(resolution.data["outcome"], "UPHELD")
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.partner_status, "SUSPENDED")

    def test_revoked_reconsideration_uses_governed_reinstatement(self):
        reconsideration_id = self.submit().data["id"]
        self.client_for(self.other_platform_admin).post(
            reverse(
                "management_governance_reconsideration_review",
                kwargs={
                    "organization_id": self.organization.pk,
                    "reconsideration_id": reconsideration_id,
                },
            ),
            {"reviewer_independence_note": "Independent Platform Admin review."},
            format="json",
        )
        with self.captureOnCommitCallbacks(execute=True):
            resolution = self.client_for(self.other_platform_admin).post(
                reverse(
                    "management_governance_reconsideration_resolve",
                    kwargs={
                        "organization_id": self.organization.pk,
                        "reconsideration_id": reconsideration_id,
                    },
                ),
                {
                    "outcome": "REVOKED",
                    "resolution_rationale": (
                        "Independent review found that continued suspension is no "
                        "longer justified by the complete record."
                    ),
                    "internal_supporting_basis": (
                        "The omitted records materially changed the proportionality "
                        "assessment supporting continued restriction."
                    ),
                },
                format="json",
            )
        self.assertEqual(resolution.status_code, status.HTTP_200_OK)
        self.assertEqual(resolution.data["outcome"], "REVOKED")
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.partner_status, "ACTIVE")
        self.assertTrue(
            AccountabilityEvent.objects.filter(
                subject_organization=self.organization,
                reason_code="PARTNERSHIP_REINSTATED",
            ).exists()
        )
