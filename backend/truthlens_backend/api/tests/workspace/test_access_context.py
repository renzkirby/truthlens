from django.contrib.auth.models import User
from django.test import TestCase

from api.models import (
    Organization,
    OrganizationMembership,
    UserProfile,
)
from api.organization_service import (
    PartnerCapability,
    get_workspace_access_context,
)


class WorkspaceAccessContextTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Workspace Partner",
            slug="workspace-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
            logo_url="https://example.com/workspace-partner-logo.png",
        )

    def test_regular_user_has_no_workspace_access(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-user",
            password="test-password",
        )

        context = get_workspace_access_context(user)

        self.assertFalse(context["can_access"])

        self.assertFalse(context["is_platform_safety_moderator"])

        self.assertEqual(
            context["platform_capabilities"],
            [],
        )

        self.assertEqual(
            context["memberships"],
            [],
        )

        self.assertIsNone(context["default_organization_id"])

    def test_platform_safety_moderator_does_not_get_verification_workspace_access(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-safety",
            password="test-password",
        )

        user.profile.role = UserProfile.Role.MOD

        user.profile.save(update_fields=["role"])

        context = get_workspace_access_context(user)

        self.assertFalse(context["can_access"])

        self.assertTrue(context["is_platform_safety_moderator"])

        self.assertEqual(
            context["platform_capabilities"],
            [],
        )

        self.assertEqual(
            context["memberships"],
            [],
        )

        self.assertIsNone(context["default_organization_id"])

    def test_lead_verifier_gets_partner_workspace_context(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-lead",
            password="test-password",
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        context = get_workspace_access_context(user)

        self.assertTrue(context["can_access"])

        self.assertFalse(context["is_platform_safety_moderator"])

        self.assertEqual(
            context["platform_capabilities"],
            [],
        )

        self.assertEqual(
            len(context["memberships"]),
            1,
        )

        membership = context["memberships"][0]

        self.assertEqual(
            membership["organization"]["id"],
            str(self.organization.id),
        )

        self.assertEqual(
            membership["organization"]["logo_url"],
            self.organization.logo_url,
        )

        self.assertEqual(
            membership["role"],
            OrganizationMembership.Role.LEAD_VERIFIER,
        )

        self.assertIn(
            PartnerCapability.CLAIM_VERIFICATION_WORK,
            membership["capabilities"],
        )

        self.assertIn(
            PartnerCapability.REVIEW_EVIDENCE,
            membership["capabilities"],
        )

        self.assertIn(
            PartnerCapability.ADJUDICATE,
            membership["capabilities"],
        )

        self.assertIn(
            PartnerCapability.CREATE_FACT_CHECK_DRAFT,
            membership["capabilities"],
        )

        self.assertIn(
            PartnerCapability.PUBLISH_FACT_CHECK,
            membership["capabilities"],
        )

        self.assertNotIn(
            PartnerCapability.REVIEW_SAFETY,
            membership["capabilities"],
        )

        self.assertEqual(
            context["default_organization_id"],
            str(self.organization.id),
        )

    def test_workspace_context_exposes_student_publication_subtype(self):
        self.organization.organization_type = Organization.OrganizationType.NEWS
        self.organization.organization_subtype = (
            Organization.OrganizationSubtype.STUDENT_PUBLICATION
        )
        self.organization.save(
            update_fields=["organization_type", "organization_subtype"]
        )

        user = User.objects.create_user(
            username="workspace-student-publication-lead",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=user,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        context = get_workspace_access_context(user)

        self.assertEqual(
            context["memberships"][0]["organization"]["organization_subtype"],
            Organization.OrganizationSubtype.STUDENT_PUBLICATION,
        )

    def test_partner_contributor_does_not_gain_workspace_access(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-contributor",
            password="test-password",
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=user,
            role=(OrganizationMembership.Role.CONTRIBUTOR),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        context = get_workspace_access_context(user)

        self.assertFalse(context["can_access"])

        self.assertEqual(
            context["memberships"],
            [],
        )

    def test_platform_safety_and_partner_authority_remain_separate(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-dual-role",
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

        context = get_workspace_access_context(user)

        self.assertTrue(context["is_platform_safety_moderator"])

        self.assertEqual(
            context["platform_capabilities"],
            [],
        )

        partner_capabilities = context["memberships"][0]["capabilities"]

        self.assertNotIn(
            PartnerCapability.REVIEW_SAFETY,
            partner_capabilities,
        )

        self.assertIn(
            PartnerCapability.ADJUDICATE,
            partner_capabilities,
        )

    def test_active_partner_admin_keeps_organization_management_workspace_context(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-admin",
            password="test-password",
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=user,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )

        context = get_workspace_access_context(user)

        self.assertTrue(context["can_access"])
        self.assertEqual(len(context["memberships"]), 1)
        self.assertEqual(
            context["memberships"][0]["capabilities"],
            [PartnerCapability.MANAGE_ORGANIZATION],
        )

    def test_factual_role_loses_workspace_access_when_partner_is_suspended(
        self,
    ):
        user = User.objects.create_user(
            username="workspace-suspended-partner-lead",
            password="test-password",
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=user,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED
        self.organization.save(update_fields=["partner_status"])

        context = get_workspace_access_context(user)

        self.assertFalse(context["can_access"])
        self.assertEqual(context["memberships"], [])
        self.assertIsNone(context["default_organization_id"])

