from django.contrib.auth.models import (
    AnonymousUser,
    User,
)
from django.test import TestCase
from django.utils import timezone

from api.models import (
    Organization,
    OrganizationMembership,
)
from api.organization_membership_service import (
    InvalidOrganizationMembershipRole,
    OrganizationMembershipAuthorizationError,
    OrganizationMembershipConflict,
    OrganizationMembershipNotFound,
    change_organization_membership_role,
    remove_organization_membership,
    restore_organization_membership,
    suspend_organization_membership,
)
from api.organization_service import (
    PartnerCapability,
    has_capability,
)


class OrganizationMembershipServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="membership-owner",
            email="owner@example.com",
            password="test-password",
        )

        self.admin = User.objects.create_user(
            username="membership-admin",
            email="admin@example.com",
            password="test-password",
        )

        self.lead = User.objects.create_user(
            username="membership-lead",
            email="lead@example.com",
            password="test-password",
        )

        self.researcher = User.objects.create_user(
            username="membership-researcher",
            email="researcher@example.com",
            password="test-password",
        )

        self.contributor = User.objects.create_user(
            username="membership-contributor",
            email="contributor@example.com",
            password="test-password",
        )

        self.other_owner = User.objects.create_user(
            username="other-membership-owner",
            email="other-owner@example.com",
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name="Membership Partner",
            slug="membership-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.other_organization = Organization.objects.create(
            name="Other Membership Partner",
            slug="other-membership-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        now = timezone.now()

        self.owner_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_at=now,
            approved_by=self.owner,
        )

        self.admin_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=(OrganizationMembership.Role.ADMIN),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_at=now,
            approved_by=self.owner,
        )

        self.lead_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_at=now,
            approved_by=self.owner,
        )

        self.researcher_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.researcher,
            role=(OrganizationMembership.Role.RESEARCHER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_at=now,
            approved_by=self.owner,
        )

        self.contributor_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.contributor,
            role=(OrganizationMembership.Role.CONTRIBUTOR),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_at=now,
            approved_by=self.owner,
        )

        self.other_owner_membership = OrganizationMembership.objects.create(
            organization=(self.other_organization),
            user=self.other_owner,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_at=now,
            approved_by=self.other_owner,
        )

    # ─────────────────────────────────────────────
    # Owner role management
    # ─────────────────────────────────────────────

    def test_owner_can_promote_researcher_to_admin(
        self,
    ):
        membership = change_organization_membership_role(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            role=(OrganizationMembership.Role.ADMIN),
            actor=self.owner,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.role,
            OrganizationMembership.Role.ADMIN,
        )

    def test_owner_can_demote_admin_to_researcher(
        self,
    ):
        membership = change_organization_membership_role(
            organization=self.organization,
            membership_id=(self.admin_membership.id),
            role=(OrganizationMembership.Role.RESEARCHER),
            actor=self.owner,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.role,
            (OrganizationMembership.Role.RESEARCHER),
        )

    def test_owner_can_suspend_admin(
        self,
    ):
        membership = suspend_organization_membership(
            organization=self.organization,
            membership_id=(self.admin_membership.id),
            actor=self.owner,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.status,
            (OrganizationMembership.Status.SUSPENDED),
        )

    def test_owner_can_restore_suspended_admin(
        self,
    ):
        self.admin_membership.status = OrganizationMembership.Status.SUSPENDED

        self.admin_membership.save(
            update_fields=[
                "status",
            ]
        )

        membership = restore_organization_membership(
            organization=self.organization,
            membership_id=(self.admin_membership.id),
            actor=self.owner,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_owner_can_remove_admin(
        self,
    ):
        membership_id = self.admin_membership.id

        membership = remove_organization_membership(
            organization=self.organization,
            membership_id=membership_id,
            actor=self.owner,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.id,
            membership_id,
        )

        self.assertEqual(
            membership.status,
            OrganizationMembership.Status.LEFT,
        )

        self.assertTrue(
            OrganizationMembership.objects.filter(
                id=membership_id,
            ).exists()
        )

    # ─────────────────────────────────────────────
    # Admin role management
    # ─────────────────────────────────────────────

    def test_admin_can_change_researcher_to_moderator(
        self,
    ):
        membership = change_organization_membership_role(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            role=(OrganizationMembership.Role.MODERATOR),
            actor=self.admin,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.role,
            (OrganizationMembership.Role.MODERATOR),
        )

    def test_admin_can_suspend_researcher(
        self,
    ):
        membership = suspend_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.admin,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.status,
            (OrganizationMembership.Status.SUSPENDED),
        )

    def test_admin_can_restore_researcher(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        membership = restore_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.admin,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_admin_can_remove_researcher(
        self,
    ):
        membership = remove_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.admin,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.status,
            OrganizationMembership.Status.LEFT,
        )

    # ─────────────────────────────────────────────
    # Admin hierarchy restrictions
    # ─────────────────────────────────────────────

    def test_admin_cannot_manage_admin(
        self,
    ):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=(self.admin_membership.id),
                actor=self.admin,
            )

        self.admin_membership.refresh_from_db()

        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_admin_cannot_assign_admin_role(
        self,
    ):
        with self.assertRaises(InvalidOrganizationMembershipRole):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                role=(OrganizationMembership.Role.ADMIN),
                actor=self.admin,
            )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.role,
            (OrganizationMembership.Role.RESEARCHER),
        )

    def test_admin_cannot_assign_owner_role(
        self,
    ):
        with self.assertRaises(InvalidOrganizationMembershipRole):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                role=(OrganizationMembership.Role.OWNER),
                actor=self.admin,
            )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.role,
            (OrganizationMembership.Role.RESEARCHER),
        )

    # ─────────────────────────────────────────────
    # Owner protection
    # ─────────────────────────────────────────────

    def test_owner_cannot_manage_owner_membership(
        self,
    ):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=(self.owner_membership.id),
                actor=self.owner,
            )

        self.owner_membership.refresh_from_db()

        self.assertEqual(
            self.owner_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_owner_cannot_assign_owner_role(
        self,
    ):
        with self.assertRaises(InvalidOrganizationMembershipRole):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                role=(OrganizationMembership.Role.OWNER),
                actor=self.owner,
            )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.role,
            (OrganizationMembership.Role.RESEARCHER),
        )

    def test_owner_cannot_remove_owner_membership(
        self,
    ):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            remove_organization_membership(
                organization=self.organization,
                membership_id=(self.owner_membership.id),
                actor=self.owner,
            )

        self.owner_membership.refresh_from_db()

        self.assertEqual(
            self.owner_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    # ─────────────────────────────────────────────
    # State transition rules
    # ─────────────────────────────────────────────

    def test_active_membership_can_be_suspended(
        self,
    ):
        suspend_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.owner,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            (OrganizationMembership.Status.SUSPENDED),
        )

    def test_suspended_membership_can_be_restored(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        restore_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.owner,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_active_membership_can_be_removed(
        self,
    ):
        remove_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.owner,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.LEFT,
        )

    def test_suspended_membership_can_be_removed(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        remove_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.owner,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.LEFT,
        )

    def test_suspended_membership_cannot_be_suspended_again(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        with self.assertRaises(OrganizationMembershipConflict):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                actor=self.owner,
            )

    def test_active_membership_cannot_be_restored(
        self,
    ):
        with self.assertRaises(OrganizationMembershipConflict):
            restore_organization_membership(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                actor=self.owner,
            )

    def test_left_membership_cannot_have_role_changed(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.LEFT

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        with self.assertRaises(OrganizationMembershipConflict):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                role=(OrganizationMembership.Role.CONTRIBUTOR),
                actor=self.owner,
            )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.role,
            (OrganizationMembership.Role.RESEARCHER),
        )

    def test_same_role_change_is_conflict(
        self,
    ):
        with self.assertRaises(OrganizationMembershipConflict):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                role=(OrganizationMembership.Role.RESEARCHER),
                actor=self.owner,
            )

    # ─────────────────────────────────────────────
    # Authorization and organization scope
    # ─────────────────────────────────────────────

    def test_factual_role_cannot_manage_membership(
        self,
    ):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                actor=self.lead,
            )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_other_organization_owner_cannot_manage_member(
        self,
    ):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                actor=self.other_owner,
            )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_unauthenticated_actor_cannot_manage_membership(
        self,
    ):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                actor=AnonymousUser(),
            )

    def test_membership_from_another_organization_is_not_found(
        self,
    ):
        with self.assertRaises(OrganizationMembershipNotFound):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=(self.other_owner_membership.id),
                actor=self.owner,
            )

    # ─────────────────────────────────────────────
    # Role validation
    # ─────────────────────────────────────────────

    def test_invalid_role_is_rejected(
        self,
    ):
        with self.assertRaises(InvalidOrganizationMembershipRole):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                role="SUPER_ADMIN",
                actor=self.owner,
            )

    def test_blank_role_is_rejected(
        self,
    ):
        with self.assertRaises(InvalidOrganizationMembershipRole):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=(self.researcher_membership.id),
                role="",
                actor=self.owner,
            )

    # ─────────────────────────────────────────────
    # Capability effects
    # ─────────────────────────────────────────────

    def test_suspension_immediately_revokes_capabilities(
        self,
    ):
        self.assertTrue(
            has_capability(
                self.lead,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

        suspend_organization_membership(
            organization=self.organization,
            membership_id=(self.lead_membership.id),
            actor=self.owner,
        )

        self.assertFalse(
            has_capability(
                self.lead,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

        self.assertFalse(
            has_capability(
                self.lead,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

    def test_restoration_restores_role_capabilities(
        self,
    ):
        self.lead_membership.status = OrganizationMembership.Status.SUSPENDED

        self.lead_membership.save(
            update_fields=[
                "status",
            ]
        )

        self.assertFalse(
            has_capability(
                self.lead,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

        restore_organization_membership(
            organization=self.organization,
            membership_id=(self.lead_membership.id),
            actor=self.owner,
        )

        self.assertTrue(
            has_capability(
                self.lead,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

        self.assertTrue(
            has_capability(
                self.lead,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

    def test_role_change_immediately_changes_capabilities(
        self,
    ):
        self.assertFalse(
            has_capability(
                self.researcher,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

        change_organization_membership_role(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            role=(OrganizationMembership.Role.MODERATOR),
            actor=self.owner,
        )

        self.assertTrue(
            has_capability(
                self.researcher,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

        self.assertTrue(
            has_capability(
                self.researcher,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

    def test_removal_immediately_revokes_capabilities(
        self,
    ):
        self.assertTrue(
            has_capability(
                self.lead,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

        remove_organization_membership(
            organization=self.organization,
            membership_id=(self.lead_membership.id),
            actor=self.owner,
        )

        self.assertFalse(
            has_capability(
                self.lead,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )

    # ─────────────────────────────────────────────
    # Membership history / provenance
    # ─────────────────────────────────────────────

    def test_role_change_preserves_admission_metadata(
        self,
    ):
        original_joined_at = self.researcher_membership.joined_at

        original_approved_at = self.researcher_membership.approved_at

        original_approved_by_id = self.researcher_membership.approved_by_id

        change_organization_membership_role(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            role=(OrganizationMembership.Role.MODERATOR),
            actor=self.owner,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.joined_at,
            original_joined_at,
        )

        self.assertEqual(
            self.researcher_membership.approved_at,
            original_approved_at,
        )

        self.assertEqual(
            self.researcher_membership.approved_by_id,
            original_approved_by_id,
        )

    def test_suspension_preserves_admission_metadata(
        self,
    ):
        original_joined_at = self.researcher_membership.joined_at

        original_approved_at = self.researcher_membership.approved_at

        original_approved_by_id = self.researcher_membership.approved_by_id

        suspend_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.owner,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.joined_at,
            original_joined_at,
        )

        self.assertEqual(
            self.researcher_membership.approved_at,
            original_approved_at,
        )

        self.assertEqual(
            self.researcher_membership.approved_by_id,
            original_approved_by_id,
        )

    def test_removal_preserves_membership_history(
        self,
    ):
        original_id = self.researcher_membership.id

        original_joined_at = self.researcher_membership.joined_at

        original_approved_at = self.researcher_membership.approved_at

        original_approved_by_id = self.researcher_membership.approved_by_id

        remove_organization_membership(
            organization=self.organization,
            membership_id=(self.researcher_membership.id),
            actor=self.owner,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.id,
            original_id,
        )

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.LEFT,
        )

        self.assertEqual(
            self.researcher_membership.joined_at,
            original_joined_at,
        )

        self.assertEqual(
            self.researcher_membership.approved_at,
            original_approved_at,
        )

        self.assertEqual(
            self.researcher_membership.approved_by_id,
            original_approved_by_id,
        )
