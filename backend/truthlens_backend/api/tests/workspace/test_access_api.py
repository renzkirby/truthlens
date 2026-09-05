from django.contrib.auth.models import User
from django.urls import reverse

from rest_framework import status
from rest_framework.test import (
    APIClient,
    APITestCase,
)

from api.models import (
    Organization,
    OrganizationMembership,
    UserProfile,
)
from api.organization_service import (
    PartnerCapability,
)


class WorkspaceAccessApiTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Workspace API Partner",
            slug="workspace-api-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.unauthenticated_client = APIClient()

    def _client_for(self, user):
        client = APIClient()

        client.force_authenticate(user=user)

        return client

    def test_auth_me_requires_authentication(self):
        response = self.unauthenticated_client.get(reverse("auth_me"))

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_regular_user_receives_no_workspace_access(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-api-user",
            password="test-password",
        )

        response = self._client_for(user).get(reverse("auth_me"))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "workspace",
            response.data,
        )

        workspace = response.data["workspace"]

        self.assertFalse(workspace["can_access"])

        self.assertFalse(workspace["is_platform_safety_moderator"])

        self.assertEqual(
            workspace["platform_capabilities"],
            [],
        )

        self.assertEqual(
            workspace["memberships"],
            [],
        )

        self.assertIsNone(workspace["default_organization_id"])

    def test_platform_safety_moderator_receives_only_platform_authority(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-api-safety",
            password="test-password",
        )

        user.profile.role = UserProfile.Role.MOD

        user.profile.save(update_fields=["role"])

        response = self._client_for(user).get(reverse("auth_me"))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        workspace = response.data["workspace"]

        self.assertTrue(workspace["can_access"])

        self.assertTrue(workspace["is_platform_safety_moderator"])

        self.assertEqual(
            workspace["platform_capabilities"],
            [
                PartnerCapability.REVIEW_SAFETY,
            ],
        )

        self.assertEqual(
            workspace["memberships"],
            [],
        )

        self.assertIsNone(workspace["default_organization_id"])

    def test_lead_verifier_receives_organization_workspace_context(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-api-lead",
            password="test-password",
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        response = self._client_for(user).get(reverse("auth_me"))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        workspace = response.data["workspace"]

        self.assertTrue(workspace["can_access"])

        self.assertFalse(workspace["is_platform_safety_moderator"])

        self.assertEqual(
            workspace["platform_capabilities"],
            [],
        )

        self.assertEqual(
            len(workspace["memberships"]),
            1,
        )

        membership = workspace["memberships"][0]

        self.assertEqual(
            membership["organization"]["id"],
            str(self.organization.id),
        )

        self.assertEqual(
            membership["organization"]["name"],
            self.organization.name,
        )

        self.assertEqual(
            membership["organization"]["slug"],
            self.organization.slug,
        )

        self.assertEqual(
            membership["role"],
            OrganizationMembership.Role.LEAD_VERIFIER,
        )

        capabilities = set(membership["capabilities"])

        self.assertEqual(
            capabilities,
            {
                PartnerCapability.CLAIM_VERIFICATION_WORK,
                PartnerCapability.REVIEW_EVIDENCE,
                PartnerCapability.ADJUDICATE,
                PartnerCapability.CREATE_FACT_CHECK_DRAFT,
                PartnerCapability.PUBLISH_FACT_CHECK,
            },
        )

        self.assertEqual(
            workspace["default_organization_id"],
            str(self.organization.id),
        )

    def test_dual_role_user_keeps_platform_and_partner_authority_separate(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-api-dual",
            password="test-password",
        )

        user.profile.role = UserProfile.Role.MOD

        user.profile.save(update_fields=["role"])

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        response = self._client_for(user).get(reverse("auth_me"))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        workspace = response.data["workspace"]

        self.assertTrue(workspace["is_platform_safety_moderator"])

        self.assertEqual(
            workspace["platform_capabilities"],
            [
                PartnerCapability.REVIEW_SAFETY,
            ],
        )

        partner_capabilities = set(workspace["memberships"][0]["capabilities"])

        self.assertNotIn(
            PartnerCapability.REVIEW_SAFETY,
            partner_capabilities,
        )

        self.assertIn(
            PartnerCapability.ADJUDICATE,
            partner_capabilities,
        )

        self.assertIn(
            PartnerCapability.CLAIM_VERIFICATION_WORK,
            partner_capabilities,
        )
