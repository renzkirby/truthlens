from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api.developer_admin import (
    DeveloperOrganizationAdmin,
    developer_admin_site,
)
from api.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    UserProfile,
)
from api.organization_invitation_service import (
    InvalidOrganizationInvitationRole,
    create_organization_invitation,
)
from api.organization_service import (
    PartnerCapability,
    has_capability,
)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class DeveloperConsoleTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="developer-superuser",
            email="developer@example.com",
            password="test-password",
        )
        self.staff_user = User.objects.create_user(
            username="staff-non-superuser",
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
            username="partner-primary-admin",
            email="primary-admin@example.com",
            password="test-password",
        )
        self.organization_admin = User.objects.create_user(
            username="partner-admin",
            email="partner-admin@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Developer Console Partner",
            slug="developer-console-partner",
            description="Organization-controlled description",
            website="https://partner.example.com",
            logo_url="https://partner.example.com/logo.png",
            expertise_areas=["health"],
            public_profile_enabled=True,
            public_logo_enabled=True,
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.owner_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=timezone.now(),
            approved_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=timezone.now(),
            approved_by=self.owner,
        )
        self.invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email="invitee@example.com",
            invited_role=OrganizationMembership.Role.RESEARCHER,
            invited_by=self.owner,
            token_digest="a" * 64,
            status=OrganizationInvitation.Status.PENDING,
            expires_at=timezone.now() + timedelta(days=7),
            last_sent_at=timezone.now(),
        )

    def assert_console_denied(self, user):
        self.client.force_login(user)

        response = self.client.get(reverse("developer_admin:index"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/developer-console/login/", response.url)

    def test_active_superuser_can_access_developer_console(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("developer_admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TruthLens Developer Console")
        self.assertContains(response, "Partner Organization Governance")

    def test_authenticated_non_superuser_cannot_access_developer_console(self):
        self.assert_console_denied(self.staff_user)

    def test_ordinary_user_cannot_access_developer_console(self):
        self.assert_console_denied(self.ordinary_user)

    def test_organization_owner_cannot_access_developer_console(self):
        self.assert_console_denied(self.owner)

    def test_organization_admin_cannot_access_developer_console(self):
        self.assert_console_denied(self.organization_admin)

    def test_only_governance_models_are_registered(self):
        self.assertIn(Organization, developer_admin_site._registry)
        self.assertIn(OrganizationMembership, developer_admin_site._registry)
        self.assertIn(OrganizationInvitation, developer_admin_site._registry)
        self.assertNotIn(User, developer_admin_site._registry)
        self.assertNotIn(UserProfile, developer_admin_site._registry)

    def test_organization_is_available_for_platform_governance(self):
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("developer_admin:api_organization_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertContains(
            response,
            self.organization.get_verification_status_display(),
        )
        self.assertContains(
            response,
            self.organization.get_partner_status_display(),
        )

    def test_organization_identity_and_profile_fields_are_readonly_after_creation(self):
        model_admin = developer_admin_site._registry[Organization]

        readonly_fields = model_admin.get_readonly_fields(
            request=None,
            obj=self.organization,
        )

        self.assertIsInstance(model_admin, DeveloperOrganizationAdmin)
        self.assertIn("name", readonly_fields)
        self.assertIn("slug", readonly_fields)
        self.assertIn("organization_type", readonly_fields)
        self.assertIn("description", readonly_fields)
        self.assertIn("website", readonly_fields)
        self.assertIn("logo_url", readonly_fields)
        self.assertIn("expertise_areas", readonly_fields)
        self.assertIn("public_profile_enabled", readonly_fields)
        self.assertIn("public_logo_enabled", readonly_fields)
        self.assertNotIn("verification_status", readonly_fields)
        self.assertNotIn("partner_status", readonly_fields)

    def test_organization_platform_status_can_change_without_profile_mutation(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse(
                "developer_admin:api_organization_change",
                args=(self.organization.pk,),
            ),
            {
                "name": "Changed Identity",
                "slug": "changed-identity",
                "organization_type": Organization.OrganizationType.NEWS,
                "verification_status": Organization.VerificationStatus.REJECTED,
                "partner_status": Organization.PartnerStatus.SUSPENDED,
                "description": "Changed profile",
                "website": "https://changed.example.com",
                "public_profile_enabled": "",
                "_save": "Save",
            },
        )

        self.assertRedirects(
            response,
            reverse("developer_admin:api_organization_changelist"),
        )

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Developer Console Partner")
        self.assertEqual(self.organization.slug, "developer-console-partner")
        self.assertEqual(
            self.organization.organization_type,
            Organization.OrganizationType.FACT_CHECKING,
        )
        self.assertEqual(
            self.organization.verification_status,
            Organization.VerificationStatus.REJECTED,
        )
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.SUSPENDED,
        )
        self.assertEqual(
            self.organization.description,
            "Organization-controlled description",
        )
        self.assertEqual(
            self.organization.website,
            "https://partner.example.com",
        )
        self.assertTrue(self.organization.public_profile_enabled)

    def test_developer_can_create_organization_identity_record(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("developer_admin:api_organization_add"),
            {
                "name": "New Institutional Partner",
                "slug": "new-institutional-partner",
                "organization_type": Organization.OrganizationType.UNIVERSITY,
                "verification_status": Organization.VerificationStatus.PENDING,
                "partner_status": Organization.PartnerStatus.NONE,
                "_save": "Save",
            },
        )

        self.assertRedirects(
            response,
            reverse("developer_admin:api_organization_changelist"),
        )
        self.assertTrue(
            Organization.objects.filter(
                name="New Institutional Partner",
                slug="new-institutional-partner",
                organization_type=Organization.OrganizationType.UNIVERSITY,
                verification_status=Organization.VerificationStatus.PENDING,
                partner_status=Organization.PartnerStatus.NONE,
            ).exists()
        )

    def test_membership_is_available_for_readonly_inspection(self):
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("developer_admin:api_organizationmembership_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertContains(response, self.owner.username)
        self.assertContains(response, "Primary Admin")

        detail_response = self.client.get(
            reverse(
                "developer_admin:api_organizationmembership_change",
                args=(self.owner_membership.pk,),
            )
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Primary Admin")
        self.assertNotContains(detail_response, "(OWNER)")

        mutation_response = self.client.post(
            reverse(
                "developer_admin:api_organizationmembership_change",
                args=(self.owner_membership.pk,),
            ),
            {"role": OrganizationMembership.Role.CONTRIBUTOR},
        )

        self.assertEqual(mutation_response.status_code, 403)
        self.owner_membership.refresh_from_db()
        self.assertEqual(
            self.owner_membership.role,
            OrganizationMembership.Role.OWNER,
        )

    def test_invitation_is_available_for_readonly_inspection(self):
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("developer_admin:api_organizationinvitation_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertContains(response, self.invitation.email)

        detail_response = self.client.get(
            reverse(
                "developer_admin:api_organizationinvitation_change",
                args=(self.invitation.pk,),
            )
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, self.invitation.token_digest)

        model_admin = developer_admin_site._registry[OrganizationInvitation]
        self.assertIn("token_digest", model_admin.readonly_fields)

        mutation_response = self.client.post(
            reverse(
                "developer_admin:api_organizationinvitation_change",
                args=(self.invitation.pk,),
            ),
            {"status": OrganizationInvitation.Status.ACCEPTED},
        )

        self.assertEqual(mutation_response.status_code, 403)
        self.invitation.refresh_from_db()
        self.assertEqual(
            self.invitation.status,
            OrganizationInvitation.Status.PENDING,
        )

    def test_owner_storage_and_existing_permission_semantics_are_preserved(self):
        self.owner_membership.refresh_from_db()

        self.assertEqual(self.owner_membership.role, "OWNER")
        self.assertTrue(
            has_capability(
                self.owner,
                PartnerCapability.MANAGE_ORGANIZATION,
                organization=self.organization,
            )
        )
        self.assertFalse(
            has_capability(
                self.owner,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

    def test_ordinary_owner_invitation_remains_forbidden(self):
        with self.assertRaises(InvalidOrganizationInvitationRole):
            create_organization_invitation(
                organization=self.organization,
                email="second-owner@example.com",
                invited_role=OrganizationMembership.Role.OWNER,
                actor=self.owner,
            )

    def test_default_admin_remains_available(self):
        self.assertIn(Organization, admin.site._registry)

        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
