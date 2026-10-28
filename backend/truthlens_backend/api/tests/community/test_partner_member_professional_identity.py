from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Organization, OrganizationMembership


class PartnerMemberProfessionalIdentityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="partner-professional",
            password="test-password",
        )
        self.user.profile.trust_score = 78.5
        self.user.profile.save(update_fields=["trust_score"])
        self.organization = Organization.objects.create(
            name="Professional Identity Partner",
            slug="professional-identity-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            public_profile_enabled=True,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_current_user_keeps_reputation_data_but_hides_it_as_identity(self):
        response = self.client.get(reverse("auth_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["trust_score"], 78.5)
        self.assertIsNotNone(response.data["trust_breakdown"])

        identity = response.data["community_identity"]
        self.assertTrue(identity["can_participate"])
        self.assertTrue(identity["reputation_applicable"])
        self.assertFalse(identity["reputation_visible"])
        self.assertEqual(
            identity["professional_identity"]["display_label"],
            "Lead Verifier at Professional Identity Partner",
        )
        self.assertEqual(
            identity["professional_identity"]["role_label"],
            "Lead Verifier",
        )
        self.assertTrue(identity["professional_identity"]["authority_active"])

    def test_dashboard_exposes_professional_identity_without_removing_reputation_data(self):
        response = self.client.get(reverse("user_hub"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["user_info"]["professional_identity"]["display_label"],
            "Lead Verifier at Professional Identity Partner",
        )
        self.assertEqual(response.data["reputation"]["trust_score"], 78.5)

    def test_left_membership_restores_ordinary_reputation_presentation(self):
        self.membership.status = OrganizationMembership.Status.LEFT
        self.membership.save(update_fields=["status"])

        response = self.client.get(reverse("auth_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        identity = response.data["community_identity"]
        self.assertTrue(identity["reputation_visible"])
        self.assertIsNone(identity["professional_identity"])
        self.assertEqual(response.data["trust_score"], 78.5)

    def test_suspended_membership_remains_professional_but_has_no_active_authority(self):
        self.membership.status = OrganizationMembership.Status.SUSPENDED
        self.membership.save(update_fields=["status"])

        response = self.client.get(reverse("auth_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        identity = response.data["community_identity"]
        self.assertFalse(identity["reputation_visible"])
        self.assertFalse(identity["professional_identity"]["authority_active"])
        self.assertEqual(
            identity["professional_identity"]["membership_status"],
            OrganizationMembership.Status.SUSPENDED,
        )

    def test_suspended_organization_remains_professional_but_has_no_active_authority(self):
        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED
        self.organization.save(update_fields=["partner_status"])

        response = self.client.get(reverse("auth_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        identity = response.data["community_identity"]
        self.assertFalse(identity["reputation_visible"])
        self.assertFalse(identity["professional_identity"]["authority_active"])
        self.assertEqual(
            identity["professional_identity"]["organization"]["partner_status"],
            Organization.PartnerStatus.SUSPENDED,
        )
