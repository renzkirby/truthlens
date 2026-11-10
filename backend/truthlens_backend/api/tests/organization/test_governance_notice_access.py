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
    OrganizationMembership,
)
from api.organization_partnership_lifecycle_service import (
    end_partner_organization_partnership,
    suspend_partner_organization_partnership,
)


class GovernanceNoticeAccessTests(APITestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="governance-notice-platform-admin",
            email="platform@example.com",
            password="test-password",
        )
        self.organization_admin = User.objects.create_user(
            username="governance-notice-org-admin",
            email="org-admin@example.com",
            password="test-password",
        )
        self.member = User.objects.create_user(
            username="governance-notice-member",
            email="member@example.com",
            password="test-password",
        )
        self.outsider = User.objects.create_user(
            username="governance-notice-outsider",
            email="outsider@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Governance Notice Partner",
            slug="governance-notice-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.admin_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.member_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def suspension_payload(self):
        return {
            "suspension_type": "REMEDIAL",
            "factors": ["VERIFICATION_STANDARDS"],
            "severity": "HIGH",
            "rationale": (
                "Repeated sourcing failures require temporary remediation before "
                "professional access resumes."
            ),
            "policy_basis": "Partnership Enforcement Policy §13.1",
            "supporting_basis": (
                "Internal review of affected investigations and prior corrective "
                "guidance."
            ),
            "supporting_references": ["INV-GOV-NOTICE-001"],
            "remediation_problem": (
                "Repeated sourcing failures in completed verification work."
            ),
            "remediation_required_action": (
                "Review affected investigations and correct the sourcing process."
            ),
            "remediation_evidence_required": (
                "Updated evidence-review procedure and corrected investigation records."
            ),
            "remediation_deadline": timezone.localdate() + timedelta(days=30),
            "remediation_review_method": (
                "Platform Governance will review the submitted procedure and records."
            ),
            "remediation_failure_consequence": (
                "TruthLens may continue the suspension or consider a stronger "
                "proportionate governance action."
            ),
        }

    def ending_payload(self):
        return {
            "ending_type": "ADMINISTRATIVE_CONCLUSION",
            "ground": "PROLONGED_ABANDONMENT",
            "factors": ["INACTIVITY_RESPONSIVENESS"],
            "severity": "",
            "rationale": (
                "The organization can no longer maintain an active partnership "
                "because required operations have ceased."
            ),
            "policy_basis": "Partnership Enforcement Policy §19.2",
            "supporting_basis": (
                "Internal administrative record confirming prolonged inactivity "
                "and loss of operational capacity."
            ),
            "supporting_references": ["GOV-END-001"],
        }

    def suspend(self):
        suspend_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
            **self.suspension_payload(),
        )
        return AccountabilityEvent.objects.get(
            subject_organization=self.organization,
            reason_code="PARTNERSHIP_SUSPENDED",
        )

    def test_suspension_snapshots_admin_and_member_recipients(self):
        event = self.suspend()

        recipients = OrganizationGovernanceNoticeRecipient.objects.filter(
            governance_event=event,
        ).order_by("audience", "user_id")

        self.assertEqual(recipients.count(), 2)
        self.assertTrue(
            recipients.filter(
                user=self.organization_admin,
                audience=OrganizationGovernanceNoticeRecipient.Audience.ADMIN,
            ).exists()
        )
        self.assertTrue(
            recipients.filter(
                user=self.member,
                audience=OrganizationGovernanceNoticeRecipient.Audience.MEMBER,
            ).exists()
        )

    def test_admin_notice_projection_is_detailed_but_allowlisted(self):
        event = self.suspend()
        event.context["governance"]["internal_secret"] = "must never leak"
        event.save(update_fields=["context"])

        notice = OrganizationGovernanceNoticeRecipient.objects.get(
            governance_event=event,
            user=self.organization_admin,
        )
        response = self.client_for(self.organization_admin).get(
            reverse("governance_notice_detail", kwargs={"notice_id": notice.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["audience"], "ADMIN")
        self.assertEqual(
            response.data["action"]["code"],
            "PARTNERSHIP_SUSPENDED",
        )
        self.assertEqual(
            response.data["rationale"],
            self.suspension_payload()["rationale"],
        )
        self.assertEqual(
            response.data["governance"]["policy_basis"],
            "Partnership Enforcement Policy §13.1",
        )
        self.assertIn("remediation", response.data["governance"])
        self.assertNotIn("supporting_basis", response.data)
        self.assertNotIn("supporting_basis", response.data["governance"])
        self.assertNotIn("internal_secret", response.data["governance"])

    def test_member_notice_projection_is_status_only(self):
        event = self.suspend()
        notice = OrganizationGovernanceNoticeRecipient.objects.get(
            governance_event=event,
            user=self.member,
        )
        response = self.client_for(self.member).get(
            reverse("governance_notice_detail", kwargs={"notice_id": notice.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["audience"], "MEMBER")
        self.assertIn("personal TruthLens Community account", response.data["message"])
        self.assertNotIn("rationale", response.data)
        self.assertNotIn("governance", response.data)

    def test_outsider_cannot_probe_another_users_notice(self):
        event = self.suspend()
        notice = OrganizationGovernanceNoticeRecipient.objects.get(
            governance_event=event,
            user=self.organization_admin,
        )

        response = self.client_for(self.outsider).get(
            reverse("governance_notice_detail", kwargs={"notice_id": notice.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {"detail": "Governance notice not found."})

    def test_mark_viewed_requires_recipient_and_is_idempotent(self):
        event = self.suspend()
        notice = OrganizationGovernanceNoticeRecipient.objects.get(
            governance_event=event,
            user=self.organization_admin,
        )
        url = reverse("governance_notice_viewed", kwargs={"notice_id": notice.pk})
        client = self.client_for(self.organization_admin)

        first = client.patch(url, {}, format="json")
        second = client.patch(url, {}, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(first.data["viewed_at"])
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["viewed_at"], second.data["viewed_at"])

    def test_former_admin_can_still_read_ending_notice_after_membership_is_retired(self):
        end_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
            **self.ending_payload(),
        )

        self.admin_membership.refresh_from_db()
        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.LEFT,
        )

        event = AccountabilityEvent.objects.get(
            subject_organization=self.organization,
            reason_code="PARTNERSHIP_ENDED",
        )
        notice = OrganizationGovernanceNoticeRecipient.objects.get(
            governance_event=event,
            user=self.organization_admin,
        )
        response = self.client_for(self.organization_admin).get(
            reverse("governance_notice_detail", kwargs={"notice_id": notice.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["audience"], "ADMIN")
        self.assertEqual(response.data["partner_status"], Organization.PartnerStatus.FORMER)
        self.assertEqual(response.data["action"]["label"], "Partnership Ended")

    def test_notice_list_returns_only_current_users_rows(self):
        self.suspend()

        admin_response = self.client_for(self.organization_admin).get(
            reverse("governance_notice_list")
        )
        outsider_response = self.client_for(self.outsider).get(
            reverse("governance_notice_list")
        )

        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(admin_response.data["results"]), 1)
        self.assertEqual(
            admin_response.data["results"][0]["audience"],
            "ADMIN",
        )
        self.assertEqual(outsider_response.status_code, status.HTTP_200_OK)
        self.assertEqual(outsider_response.data["results"], [])
