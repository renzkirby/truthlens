from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Organization, OrganizationMembership
from api.organization_service import (
    CURRENT_WORKSPACE_GUIDE_VERSION,
    get_workspace_access_context,
)


class WorkspaceGuideTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Workspace Guide Partner",
            slug="workspace-guide-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.user = User.objects.create_user(
            username="workspace-guide-lead",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.client.force_authenticate(self.user)

    def test_workspace_context_exposes_versioned_guide_state(self):
        context = get_workspace_access_context(self.user)

        self.assertEqual(
            context["guide_current_version"],
            CURRENT_WORKSPACE_GUIDE_VERSION,
        )
        self.assertEqual(context["guide_version_seen"], 0)

    def test_partner_member_can_complete_current_workspace_guide(self):
        response = self.client.post(reverse("complete_workspace_guide"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["guide_current_version"],
            CURRENT_WORKSPACE_GUIDE_VERSION,
        )
        self.assertEqual(
            response.data["guide_version_seen"],
            CURRENT_WORKSPACE_GUIDE_VERSION,
        )

        self.user.profile.refresh_from_db()
        self.assertEqual(
            self.user.profile.workspace_guide_version_seen,
            CURRENT_WORKSPACE_GUIDE_VERSION,
        )

        context = get_workspace_access_context(self.user)
        self.assertEqual(
            context["guide_version_seen"],
            CURRENT_WORKSPACE_GUIDE_VERSION,
        )

    def test_completing_workspace_guide_is_idempotent(self):
        self.user.profile.workspace_guide_version_seen = CURRENT_WORKSPACE_GUIDE_VERSION
        self.user.profile.save(update_fields=["workspace_guide_version_seen"])

        response = self.client.post(reverse("complete_workspace_guide"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["guide_version_seen"],
            CURRENT_WORKSPACE_GUIDE_VERSION,
        )

    def test_regular_user_cannot_complete_workspace_guide(self):
        regular_user = User.objects.create_user(
            username="workspace-guide-regular",
            password="test-password",
        )
        self.client.force_authenticate(regular_user)

        response = self.client.post(reverse("complete_workspace_guide"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        regular_user.profile.refresh_from_db()
        self.assertEqual(regular_user.profile.workspace_guide_version_seen, 0)
