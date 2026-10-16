import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from api.organization_invitation_service import hash_invitation_token


class ManagementApiTests(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="platform-admin",
            email="platform-admin@example.com",
            password="test-password",
        )
        self.staff_user = User.objects.create_user(
            username="staff-user",
            email="staff@example.com",
            password="test-password",
            is_staff=True,
        )
        self.ordinary_user = User.objects.create_user(
            username="ordinary-user",
            email="ordinary@example.com",
            password="test-password",
        )
        self.owner = User.objects.create_user(
            username="primary-admin",
            email="primary-admin@example.com",
            password="test-password",
        )
        self.organization_admin = User.objects.create_user(
            username="organization-admin",
            email="organization-admin@example.com",
            password="test-password",
        )
        self.inviter = User.objects.create_user(
            username="inviter",
            email="inviter@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Verified Newsroom",
            slug="verified-newsroom",
            description="A governance-safe organization description.",
            website="https://newsroom.example.com",
            logo_url="https://newsroom.example.com/logo.png",
            expertise_areas=["elections", "health"],
            public_profile_enabled=True,
            public_logo_enabled=True,
            organization_type=Organization.OrganizationType.NEWS,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.pending_organization = Organization.objects.create(
            name="Pending Research Group",
            slug="pending-research-group",
            organization_type=Organization.OrganizationType.RESEARCH,
            verification_status=Organization.VerificationStatus.PENDING,
            partner_status=Organization.PartnerStatus.SUSPENDED,
        )
        self.owner_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=timezone.now(),
            approved_by=self.superuser,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=timezone.now(),
            approved_by=self.owner,
        )
        self.raw_token = "management-api-raw-invitation-token"
        self.invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email="researcher@example.com",
            invited_role=OrganizationMembership.Role.RESEARCHER,
            purpose=OrganizationInvitation.InvitationPurpose.MEMBERSHIP,
            invited_by=self.inviter,
            token_digest=hash_invitation_token(self.raw_token),
            status=OrganizationInvitation.Status.PENDING,
            expires_at=timezone.now() + timedelta(days=7),
            last_sent_at=timezone.now(),
        )
        self.pending_primary_admin_invitation = (
            OrganizationInvitation.objects.create(
                organization=self.pending_organization,
                email="pending-primary@example.com",
                invited_role=OrganizationMembership.Role.OWNER,
                purpose=(
                    OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
                ),
                invited_by=self.superuser,
                token_digest="b" * 64,
                status=OrganizationInvitation.Status.PENDING,
                expires_at=timezone.now() + timedelta(days=7),
                last_sent_at=timezone.now(),
                send_count=2,
            )
        )

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def management_urls(self):
        return (
            reverse("management_overview"),
            reverse("management_organizations"),
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.organization.id},
            ),
            reverse("management_memberships"),
            reverse(
                "management_membership_detail",
                kwargs={"membership_id": self.owner_membership.id},
            ),
            reverse("management_invitations"),
            reverse(
                "management_invitation_detail",
                kwargs={"invitation_id": self.invitation.id},
            ),
        )

    def assert_all_management_endpoints(self, user, expected_status):
        client = self.client_for(user)
        for url in self.management_urls():
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, expected_status)

    def test_active_superuser_can_access_all_management_apis(self):
        self.assert_all_management_endpoints(self.superuser, status.HTTP_200_OK)

    def test_staff_non_superuser_is_forbidden(self):
        self.assert_all_management_endpoints(
            self.staff_user,
            status.HTTP_403_FORBIDDEN,
        )

    def test_ordinary_authenticated_user_is_forbidden(self):
        self.assert_all_management_endpoints(
            self.ordinary_user,
            status.HTTP_403_FORBIDDEN,
        )

    def test_organization_owner_is_forbidden(self):
        self.assert_all_management_endpoints(
            self.owner,
            status.HTTP_403_FORBIDDEN,
        )

    def test_organization_admin_is_forbidden(self):
        self.assert_all_management_endpoints(
            self.organization_admin,
            status.HTTP_403_FORBIDDEN,
        )

    def test_anonymous_user_is_rejected(self):
        self.assert_all_management_endpoints(None, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_superuser_is_forbidden(self):
        inactive_superuser = User.objects.create_superuser(
            username="inactive-platform-admin",
            email="inactive@example.com",
            password="test-password",
            is_active=False,
        )
        self.assert_all_management_endpoints(
            inactive_superuser,
            status.HTTP_403_FORBIDDEN,
        )

    def test_overview_counts_are_explicit_and_correct(self):
        response = self.client_for(self.superuser).get(
            reverse("management_overview")
        )

        self.assertEqual(
            response.data,
            {
                "organizations": {
                    "total": 2,
                    "active_partners": 1,
                    "pending_verification": 1,
                    "suspended_partners": 1,
                }
            },
        )

    def test_organization_list_returns_only_governance_fields(self):
        response = self.client_for(self.superuser).get(
            reverse("management_organizations")
        )

        self.assertEqual(response.data["count"], 2)
        item = next(
            row
            for row in response.data["results"]
            if row["id"] == str(self.organization.id)
        )
        self.assertEqual(
            set(item),
            {
                "id",
                "name",
                "slug",
                "organization_type",
                "organization_type_label",
                "verification_status",
                "verification_status_label",
                "partner_status",
                "partner_status_label",
                "public_profile_enabled",
                "updated_at",
            },
        )

    def test_organization_detail_returns_current_primary_admin(self):
        response = self.client_for(self.superuser).get(
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.organization.id},
            )
        )

        primary_admin = response.data["primary_admin"]
        self.assertEqual(primary_admin["state"], "CURRENT")
        self.assertEqual(primary_admin["membership"]["role"], "OWNER")
        self.assertEqual(
            primary_admin["membership"]["role_label"],
            "Primary Admin",
        )
        self.assertIsNone(primary_admin["invitation"])

    def test_organization_detail_returns_safe_pending_primary_admin(self):
        response = self.client_for(self.superuser).get(
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.pending_organization.id},
            )
        )

        primary_admin = response.data["primary_admin"]
        self.assertEqual(primary_admin["state"], "PENDING")
        self.assertIsNone(primary_admin["membership"])
        self.assertEqual(
            primary_admin["invitation"]["role_label"],
            "Primary Admin",
        )
        self.assertNotIn("token_digest", primary_admin["invitation"])

    def test_membership_owner_role_label_is_primary_admin(self):
        response = self.client_for(self.superuser).get(
            reverse(
                "management_membership_detail",
                kwargs={"membership_id": self.owner_membership.id},
            )
        )

        self.assertEqual(response.data["role"], "OWNER")
        self.assertEqual(response.data["role_label"], "Primary Admin")

    def test_membership_list_and_detail_are_read_only(self):
        client = self.client_for(self.superuser)
        self.assertEqual(
            client.post(reverse("management_memberships"), {}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_organization_list_and_detail_are_read_only(self):
        client = self.client_for(self.superuser)
        self.assertEqual(
            client.post(reverse("management_organizations"), {}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.patch(
                reverse(
                    "management_organization_detail",
                    kwargs={"organization_id": self.organization.id},
                ),
                {"partner_status": Organization.PartnerStatus.SUSPENDED},
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.patch(
                reverse(
                    "management_membership_detail",
                    kwargs={"membership_id": self.owner_membership.id},
                ),
                {"status": OrganizationMembership.Status.SUSPENDED},
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_invitation_list_and_detail_are_read_only(self):
        client = self.client_for(self.superuser)
        self.assertEqual(
            client.post(reverse("management_invitations"), {}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.patch(
                reverse(
                    "management_invitation_detail",
                    kwargs={"invitation_id": self.invitation.id},
                ),
                {"status": OrganizationInvitation.Status.CANCELLED},
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_invitation_responses_never_expose_tokens_or_digests(self):
        client = self.client_for(self.superuser)
        for url in (
            reverse("management_invitations"),
            reverse(
                "management_invitation_detail",
                kwargs={"invitation_id": self.invitation.id},
            ),
        ):
            with self.subTest(url=url):
                payload = json.dumps(client.get(url).data)
                self.assertNotIn("token_digest", payload)
                self.assertNotIn(self.invitation.token_digest, payload)
                self.assertNotIn(self.raw_token, payload)

    def test_search_and_filters_do_not_bypass_authority(self):
        query = "?q=Verified&partner_status=ACTIVE"
        for user in (self.staff_user, self.ordinary_user, self.owner):
            with self.subTest(user=user.username):
                response = self.client_for(user).get(
                    reverse("management_organizations") + query
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_organization_search_and_filters_return_matching_records(self):
        response = self.client_for(self.superuser).get(
            reverse("management_organizations")
            + "?q=newsroom&verification_status=VERIFIED"
            + "&partner_status=ACTIVE&organization_type=NEWS"
            + "&public_profile_enabled=true"
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.organization.id))

    def test_membership_and_invitation_filters_return_matching_records(self):
        client = self.client_for(self.superuser)
        memberships = client.get(
            reverse("management_memberships")
            + f"?q=primary&organization_id={self.organization.id}"
            + "&role=OWNER&status=ACTIVE"
        )
        invitations = client.get(
            reverse("management_invitations")
            + f"?q=researcher&organization_id={self.organization.id}"
            + "&status=PENDING&purpose=MEMBERSHIP&invited_role=RESEARCHER"
        )

        self.assertEqual(memberships.data["count"], 1)
        self.assertEqual(invitations.data["count"], 1)

    def test_auth_me_management_access_is_true_for_active_superuser(self):
        response = self.client_for(self.superuser).get(reverse("auth_me"))

        self.assertEqual(
            response.data["management_console"],
            {"can_access": True},
        )

    def test_auth_me_management_access_is_false_for_ordinary_user(self):
        response = self.client_for(self.ordinary_user).get(reverse("auth_me"))

        self.assertEqual(
            response.data["management_console"],
            {"can_access": False},
        )

    def test_auth_me_workspace_context_remains_separate(self):
        response = self.client_for(self.owner).get(reverse("auth_me"))

        self.assertIn("workspace", response.data)
        self.assertTrue(response.data["workspace"]["can_access"])
        self.assertFalse(response.data["management_console"]["can_access"])
