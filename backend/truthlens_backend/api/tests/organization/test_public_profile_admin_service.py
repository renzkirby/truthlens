from django.contrib.auth.models import (
    AnonymousUser,
    User,
)
from django.test import TestCase

from api.models import (
    Organization,
    OrganizationMembership,
)
from api.organization_public_profile_service import (
    InvalidOrganizationPublicProfileChanges,
    OrganizationPublicProfileAuthorizationError,
    update_organization_public_profile,
)
from api.organization_service import (
    PartnerCapability,
    get_membership_capabilities,
    has_capability,
)


class OrganizationPublicProfileAdminServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Profile Administration Partner",
            slug="profile-administration-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

        self.other_organization = Organization.objects.create(
            name="Other Profile Administration Partner",
            slug="other-profile-administration-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

        self.owner, self.owner_membership = self.create_member(
            "profile-owner",
            OrganizationMembership.Role.OWNER,
        )
        self.admin, self.admin_membership = self.create_member(
            "profile-admin",
            OrganizationMembership.Role.ADMIN,
        )
        self.lead, self.lead_membership = self.create_member(
            "profile-lead",
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self.moderator, self.moderator_membership = self.create_member(
            "profile-moderator",
            OrganizationMembership.Role.MODERATOR,
        )
        self.researcher, self.researcher_membership = self.create_member(
            "profile-researcher",
            OrganizationMembership.Role.RESEARCHER,
        )
        self.contributor, self.contributor_membership = self.create_member(
            "profile-contributor",
            OrganizationMembership.Role.CONTRIBUTOR,
        )
        self.suspended_owner, self.suspended_owner_membership = self.create_member(
            "suspended-profile-owner",
            OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.SUSPENDED,
        )
        self.left_admin, self.left_admin_membership = self.create_member(
            "left-profile-admin",
            OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.LEFT,
        )
        self.other_owner, self.other_owner_membership = self.create_member(
            "other-profile-owner",
            OrganizationMembership.Role.OWNER,
            organization=self.other_organization,
        )

    def create_member(
        self,
        username,
        role,
        *,
        status=OrganizationMembership.Status.ACTIVE,
        organization=None,
    ):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
        )

        membership = OrganizationMembership.objects.create(
            organization=organization or self.organization,
            user=user,
            role=role,
            status=status,
        )

        return user, membership

    def update_as(
        self,
        actor,
        changes=None,
    ):
        return update_organization_public_profile(
            organization=self.organization,
            actor=actor,
            changes=changes
            or {
                "description": "Updated public description",
            },
        )

    def assert_cannot_update(self, actor):
        with self.assertRaises(OrganizationPublicProfileAuthorizationError):
            self.update_as(actor)

    def test_owner_can_update_public_profile_fields(self):
        updated = self.update_as(
            self.owner,
            {
                "description": "Public partner profile",
                "website": "https://example.com/profile",
                "expertise_areas": ["Elections", "Media literacy"],
                "public_profile_enabled": True,
                "public_logo_enabled": True,
            },
        )

        self.assertEqual(updated.description, "Public partner profile")
        self.assertEqual(updated.website, "https://example.com/profile")
        self.assertEqual(updated.expertise_areas, ["Elections", "Media literacy"])
        self.assertTrue(updated.public_profile_enabled)
        self.assertTrue(updated.public_logo_enabled)

    def test_unauthenticated_actor_cannot_administer_public_profile(self):
        self.assert_cannot_update(AnonymousUser())

    def test_admin_can_update_public_profile_fields(self):
        updated = self.update_as(
            self.admin,
            {
                "description": "Administrator update",
                "public_profile_enabled": True,
            },
        )

        self.assertEqual(updated.description, "Administrator update")
        self.assertTrue(updated.public_profile_enabled)

    def test_lead_verifier_cannot_administer_public_profile(self):
        self.assert_cannot_update(self.lead)

    def test_moderator_cannot_administer_public_profile(self):
        self.assert_cannot_update(self.moderator)

    def test_researcher_cannot_administer_public_profile(self):
        self.assert_cannot_update(self.researcher)

    def test_contributor_cannot_administer_public_profile(self):
        self.assert_cannot_update(self.contributor)

    def test_suspended_owner_cannot_administer_public_profile(self):
        self.assert_cannot_update(self.suspended_owner)

    def test_left_admin_cannot_administer_public_profile(self):
        self.assert_cannot_update(self.left_admin)

    def test_manager_from_another_organization_cannot_administer_target(self):
        self.assert_cannot_update(self.other_owner)

    def test_owner_can_configure_unverified_organization(self):
        self.organization.verification_status = (
            Organization.VerificationStatus.UNVERIFIED
        )
        self.organization.save(update_fields=["verification_status"])

        updated = self.update_as(
            self.owner,
            {
                "public_profile_enabled": True,
            },
        )

        self.assertTrue(updated.public_profile_enabled)
        self.assertEqual(
            updated.verification_status,
            Organization.VerificationStatus.UNVERIFIED,
        )

    def test_admin_can_configure_non_active_partner_organization(self):
        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED
        self.organization.save(update_fields=["partner_status"])

        updated = self.update_as(
            self.admin,
            {
                "public_logo_enabled": True,
            },
        )

        self.assertTrue(updated.public_logo_enabled)
        self.assertEqual(
            updated.partner_status,
            Organization.PartnerStatus.SUSPENDED,
        )

    def test_profile_changes_do_not_alter_memberships_or_capabilities(self):
        membership_state = list(
            OrganizationMembership.objects.filter(
                organization=self.organization,
            )
            .order_by("id")
            .values_list(
                "id",
                "role",
                "status",
            )
        )
        lead_capabilities = get_membership_capabilities(self.lead_membership)

        self.update_as(
            self.owner,
            {
                "description": "Presentation only",
                "public_profile_enabled": True,
                "public_logo_enabled": True,
            },
        )

        self.assertEqual(
            list(
                OrganizationMembership.objects.filter(
                    organization=self.organization,
                )
                .order_by("id")
                .values_list(
                    "id",
                    "role",
                    "status",
                )
            ),
            membership_state,
        )
        self.lead_membership.refresh_from_db()
        self.assertEqual(
            get_membership_capabilities(self.lead_membership),
            lead_capabilities,
        )

    def test_public_flags_do_not_grant_factual_capabilities(self):
        self.organization.verification_status = (
            Organization.VerificationStatus.UNVERIFIED
        )
        self.organization.save(update_fields=["verification_status"])

        self.assertFalse(
            has_capability(
                self.lead,
                PartnerCapability.PUBLISH_FACT_CHECK,
                organization=self.organization,
            )
        )

        self.update_as(
            self.owner,
            {
                "public_profile_enabled": True,
                "public_logo_enabled": True,
            },
        )

        self.assertFalse(
            has_capability(
                self.lead,
                PartnerCapability.PUBLISH_FACT_CHECK,
                organization=self.organization,
            )
        )

    def test_service_rejects_unsupported_changes(self):
        for changes in [
            {
                "verification_status": Organization.VerificationStatus.VERIFIED,
            },
            {
                "logo_url": "https://example.com/logo.png",
            },
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(InvalidOrganizationPublicProfileChanges):
                    self.update_as(
                        self.owner,
                        changes,
                    )
