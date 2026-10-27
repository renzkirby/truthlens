from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    Claim,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    VerificationAssignment,
)
from api.organization_invitation_service import hash_invitation_token
from api.organization_partnership_lifecycle_service import (
    OrganizationPartnershipLifecycleConflict,
)


class OrganizationPartnershipLifecycleApiTests(APITestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="lifecycle-api-platform-admin",
            email="platform@example.com",
            password="test-password",
        )
        self.organization_admin = User.objects.create_user(
            username="lifecycle-api-org-admin",
            email="org-admin@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Lifecycle API Partner",
            slug="lifecycle-api-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            public_profile_enabled=True,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )
        now = timezone.now()
        self.invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email="pending-lifecycle-api@example.com",
            invited_role=OrganizationMembership.Role.RESEARCHER,
            invited_by=self.organization_admin,
            token_digest=hash_invitation_token("lifecycle-api-token"),
            status=OrganizationInvitation.Status.PENDING,
            expires_at=now + timedelta(days=7),
            last_sent_at=now,
        )
        self.claim = Claim.objects.create(
            context_text="Lifecycle API unfinished investigation."
        )
        self.assignment = VerificationAssignment.objects.create(
            claim=self.claim,
            organization=self.organization,
            claimed_by=self.organization_admin,
            status=VerificationAssignment.Status.ACTIVE,
            claimed_at=now,
        )

    def authenticated_client(self):
        client = APIClient()
        client.force_authenticate(user=self.platform_admin)
        return client

    def detail_url(self, organization=None):
        return reverse(
            "management_organization_detail",
            kwargs={"organization_id": (organization or self.organization).pk},
        )

    def end_url(self, organization=None):
        return reverse(
            "management_organization_end_partnership",
            kwargs={"organization_id": (organization or self.organization).pk},
        )

    def test_detail_projects_current_lifecycle_and_end_partnership_impact(self):
        response = self.authenticated_client().get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["lifecycle"],
            {
                "state": "ACTIVE_PARTNER",
                "operational_access": "ENABLED",
                "can_end_partnership": True,
                "end_partnership_blockers": [],
                "impact": {
                    "current_memberships": 1,
                    "pending_invitations": 1,
                    "active_investigations": 1,
                    "active_factual_corrections": 0,
                },
            },
        )

    def test_end_partnership_returns_transition_summary_and_refreshed_projection(self):
        response = self.authenticated_client().post(self.end_url(), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["transition"],
            {
                "ended_memberships": 1,
                "cancelled_invitations": 1,
                "requeued_investigations": 1,
            },
        )
        self.assertEqual(
            response.data["organization"]["verification_status"],
            Organization.VerificationStatus.VERIFIED,
        )
        self.assertEqual(
            response.data["organization"]["partner_status"],
            Organization.PartnerStatus.FORMER,
        )
        self.assertEqual(
            response.data["organization"]["lifecycle"],
            {
                "state": "FORMER_PARTNER",
                "operational_access": "DISABLED",
                "can_end_partnership": False,
                "end_partnership_blockers": [
                    {
                        "code": "PARTNERSHIP_NOT_ENDABLE",
                        "count": 0,
                        "message": "Only active or suspended partnerships can be ended.",
                    }
                ],
                "impact": {
                    "current_memberships": 0,
                    "pending_invitations": 0,
                    "active_investigations": 0,
                    "active_factual_corrections": 0,
                },
            },
        )

        self.membership.refresh_from_db()
        self.invitation.refresh_from_db()
        self.assignment.refresh_from_db()
        self.assertEqual(
            self.membership.status,
            OrganizationMembership.Status.LEFT,
        )
        self.assertEqual(
            self.invitation.status,
            OrganizationInvitation.Status.CANCELLED,
        )
        self.assertEqual(
            self.assignment.status,
            VerificationAssignment.Status.RELEASED,
        )

    def test_suspended_partner_projects_disabled_access_but_can_still_be_ended(self):
        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED
        self.organization.save(update_fields=["partner_status"])

        response = self.authenticated_client().get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["lifecycle"]["state"], "SUSPENDED_PARTNER")
        self.assertEqual(response.data["lifecycle"]["operational_access"], "DISABLED")
        self.assertTrue(response.data["lifecycle"]["can_end_partnership"])

    def test_onboarding_organization_is_not_endable(self):
        onboarding = Organization.objects.create(
            name="Lifecycle Onboarding",
            slug="lifecycle-onboarding",
            verification_status=Organization.VerificationStatus.UNVERIFIED,
            partner_status=Organization.PartnerStatus.NONE,
        )

        response = self.authenticated_client().get(self.detail_url(onboarding))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["lifecycle"]["state"], "ONBOARDING")
        self.assertEqual(response.data["lifecycle"]["operational_access"], "SETUP_ONLY")
        self.assertFalse(response.data["lifecycle"]["can_end_partnership"])
        self.assertEqual(
            response.data["lifecycle"]["end_partnership_blockers"][0]["code"],
            "PARTNERSHIP_NOT_ENDABLE",
        )

    def test_end_partnership_conflict_is_reported_as_409_without_partial_response(self):
        with patch(
            "api.management_views.end_partner_organization_partnership",
            side_effect=OrganizationPartnershipLifecycleConflict(
                "Resolve or cancel the active factual correction before ending "
                "this organization's partnership."
            ),
        ):
            response = self.authenticated_client().post(self.end_url(), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            {
                "detail": (
                    "Resolve or cancel the active factual correction before ending "
                    "this organization's partnership."
                )
            },
        )

    def test_end_partnership_rejects_unexpected_payload_fields(self):
        response = self.authenticated_client().post(
            self.end_url(),
            {"partner_status": Organization.PartnerStatus.FORMER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.organization.refresh_from_db()
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )

    def test_end_partnership_unknown_organization_returns_404(self):
        response = self.authenticated_client().post(
            reverse(
                "management_organization_end_partnership",
                kwargs={"organization_id": uuid4()},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
