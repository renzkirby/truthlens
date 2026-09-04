from django.contrib.auth.models import User
from django.urls import reverse

from rest_framework import status
from rest_framework.test import (
    APIClient,
    APITestCase,
)

from .models import (
    Organization,
    OrganizationMembership,
)


class OrganizationAdminApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="org-owner",
            email="owner@example.com",
            password="test-password",
        )

        self.admin = User.objects.create_user(
            username="org-admin",
            email="admin@example.com",
            password="test-password",
        )

        self.lead = User.objects.create_user(
            username="org-lead",
            email="lead@example.com",
            password="test-password",
        )

        self.member = User.objects.create_user(
            username="org-member",
            email="member@example.com",
            password="test-password",
        )

        self.other_owner = User.objects.create_user(
            username="other-owner",
            email="other@example.com",
            password="test-password",
        )

        self.left_user = User.objects.create_user(
            username="former-member",
            email="former@example.com",
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name="Administration Partner",
            slug="administration-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.other_organization = Organization.objects.create(
            name="Other Partner",
            slug="other-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=(OrganizationMembership.Role.ADMIN),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=(OrganizationMembership.Role.CONTRIBUTOR),
            status=(OrganizationMembership.Status.SUSPENDED),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.left_user,
            role=(OrganizationMembership.Role.RESEARCHER),
            status=(OrganizationMembership.Status.LEFT),
        )

        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.other_owner,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.url = reverse(
            "organization_members",
            kwargs={
                "organization_id": self.organization.id,
            },
        )

    def client_for(
        self,
        user,
    ):
        client = APIClient()

        client.force_authenticate(
            user=user,
        )

        return client

    def test_owner_can_view_member_roster(self):
        response = self.client_for(
            self.owner,
        ).get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            4,
        )

        usernames = {item["user"]["username"] for item in response.data["results"]}

        self.assertEqual(
            usernames,
            {
                "org-owner",
                "org-admin",
                "org-lead",
                "org-member",
            },
        )

        self.assertNotIn(
            "former-member",
            usernames,
        )

    def test_admin_can_view_member_roster(self):
        response = self.client_for(
            self.admin,
        ).get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_factual_role_cannot_manage_roster(self):
        response = self.client_for(
            self.lead,
        ).get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_other_organization_owner_cannot_manage_roster(
        self,
    ):
        response = self.client_for(
            self.other_owner,
        ).get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_roster_exposes_membership_not_personal_reputation(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).get(self.url)

        member = response.data["results"][0]

        self.assertIn(
            "email",
            member["user"],
        )

        self.assertNotIn(
            "trust_score",
            member["user"],
        )

        self.assertNotIn(
            "workspace",
            member["user"],
        )

    def test_summary_counts_current_statuses(self):
        response = self.client_for(
            self.owner,
        ).get(self.url)

        self.assertEqual(
            response.data["summary"],
            {
                "active": 3,
                "pending": 0,
                "suspended": 1,
            },
        )
