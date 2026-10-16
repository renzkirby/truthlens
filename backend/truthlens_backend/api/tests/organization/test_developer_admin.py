from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.core import mail
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
from api.organization_provisioning_service import (
    create_and_send_primary_admin_invitation,
)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@truthlens.test",
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

    def create_unowned_organization(self, suffix=""):
        return Organization.objects.create(
            name=f"Unowned Developer Partner{suffix}",
            slug=f"unowned-developer-partner{suffix}",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

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

    def test_organization_without_owner_exposes_primary_admin_action(self):
        organization = self.create_unowned_organization()
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse(
                "developer_admin:api_organization_change",
                args=(organization.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primary Admin")
        self.assertContains(response, "Not yet assigned")
        self.assertContains(response, "Provision Primary Admin")

    def test_organization_with_owner_hides_initial_provision_action(self):
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse(
                "developer_admin:api_organization_change",
                args=(self.organization.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.owner.username)
        self.assertContains(response, self.owner.email)
        self.assertContains(response, "Membership status: Active")
        self.assertNotContains(response, "Provision Primary Admin")

    def test_developer_console_can_provision_primary_admin_invitation(self):
        organization = self.create_unowned_organization("-provision")
        self.client.force_login(self.superuser)
        url = reverse(
            "developer_admin:api_organization_primary_admin_provision",
            args=(organization.pk,),
        )

        response = self.client.post(
            url,
            {"email": "Console.Primary@Example.com"},
        )

        self.assertRedirects(
            response,
            reverse(
                "developer_admin:api_organization_change",
                args=(organization.pk,),
            ),
        )
        invitation = OrganizationInvitation.objects.get(
            organization=organization,
            email="console.primary@example.com",
        )
        self.assertEqual(
            invitation.purpose,
            OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING,
        )
        self.assertEqual(
            invitation.invited_role,
            OrganizationMembership.Role.OWNER,
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_primary_admin_provision_form_requests_only_email(self):
        organization = self.create_unowned_organization("-form")
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse(
                "developer_admin:api_organization_primary_admin_provision",
                args=(organization.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("developer_admin:index"))
        self.assertContains(
            response,
            reverse(
                "developer_admin:app_list",
                kwargs={"app_label": "api"},
            ),
        )
        self.assertContains(
            response,
            reverse("developer_admin:api_organization_changelist"),
        )
        self.assertContains(response, "Primary Admin Email")
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="password"')
        self.assertNotContains(response, 'name="username"')

    def test_pending_primary_admin_invitation_is_visible_without_token(self):
        organization = self.create_unowned_organization("-pending")
        raw_token = "developer-console-primary-admin-token"

        with patch(
            "api.organization_provisioning_service.generate_invitation_token",
            return_value=raw_token,
        ):
            invitation = create_and_send_primary_admin_invitation(
                organization=organization,
                email="pending-primary@example.com",
                actor=self.superuser,
            )

        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse(
                "developer_admin:api_organization_change",
                args=(organization.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primary Admin invitation pending")
        self.assertContains(response, invitation.email)
        self.assertContains(response, "Sent:")
        self.assertContains(response, "Expires:")
        self.assertContains(response, "Resend invitation")
        self.assertNotContains(response, raw_token)
        self.assertNotContains(response, invitation.token_digest)

    def test_developer_console_can_resend_primary_admin_invitation(self):
        organization = self.create_unowned_organization("-resend")
        invitation = create_and_send_primary_admin_invitation(
            organization=organization,
            email="resend-primary@example.com",
            actor=self.superuser,
        )
        old_digest = invitation.token_digest
        mail.outbox.clear()
        self.client.force_login(self.superuser)

        resend_url = reverse(
            "developer_admin:api_organization_primary_admin_resend",
            args=(organization.pk,),
        )
        confirmation = self.client.get(resend_url)

        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, reverse("developer_admin:index"))
        self.assertContains(
            confirmation,
            reverse(
                "developer_admin:app_list",
                kwargs={"app_label": "api"},
            ),
        )
        self.assertContains(
            confirmation,
            reverse("developer_admin:api_organization_changelist"),
        )
        self.assertContains(confirmation, invitation.email)
        self.assertNotContains(confirmation, invitation.token_digest)

        response = self.client.post(
            resend_url,
            {},
        )

        self.assertRedirects(
            response,
            reverse(
                "developer_admin:api_organization_change",
                args=(organization.pk,),
            ),
        )
        invitation.refresh_from_db()
        self.assertNotEqual(invitation.token_digest, old_digest)
        self.assertEqual(invitation.send_count, 2)
        self.assertEqual(len(mail.outbox), 1)

    def test_non_superuser_cannot_access_primary_admin_custom_view(self):
        organization = self.create_unowned_organization("-denied")
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse(
                "developer_admin:api_organization_primary_admin_provision",
                args=(organization.pk,),
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/developer-console/login/", response.url)

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
