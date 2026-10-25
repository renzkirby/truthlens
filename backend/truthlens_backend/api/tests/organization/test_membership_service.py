from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase
from django.utils import timezone

from api.models import Organization, OrganizationMembership
from api.organization_membership_service import (
    InvalidOrganizationMembershipRole,
    OrganizationMembershipAuthorizationError,
    OrganizationMembershipConflict,
    change_organization_membership_role,
    remove_organization_membership,
    restore_organization_membership,
    suspend_organization_membership,
)
from api.organization_service import PartnerCapability, has_capability


class OrganizationMembershipServiceTests(TestCase):
    def setUp(self):
        self.admin_a = User.objects.create_user(
            username="membership-admin-a",
            email="admin-a@example.com",
            password="test-password",
        )
        self.admin_b = User.objects.create_user(
            username="membership-admin-b",
            email="admin-b@example.com",
            password="test-password",
        )
        self.lead = User.objects.create_user(
            username="membership-lead",
            email="lead@example.com",
            password="test-password",
        )
        self.reviewer = User.objects.create_user(
            username="membership-reviewer",
            email="reviewer@example.com",
            password="test-password",
        )
        self.researcher = User.objects.create_user(
            username="membership-researcher",
            email="researcher@example.com",
            password="test-password",
        )
        self.other_admin = User.objects.create_user(
            username="other-membership-admin",
            email="other-admin@example.com",
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name="Membership Partner",
            slug="membership-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.other_organization = Organization.objects.create(
            name="Other Membership Partner",
            slug="other-membership-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

        now = timezone.now()
        self.admin_a_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin_a,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=now,
            approved_by=self.admin_a,
        )
        self.admin_b_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin_b,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=now,
            approved_by=self.admin_a,
        )
        self.lead_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=now,
            approved_by=self.admin_a,
        )
        self.reviewer_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.reviewer,
            role=OrganizationMembership.Role.VERIFICATION_REVIEWER,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=now,
            approved_by=self.admin_a,
        )
        self.researcher_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.researcher,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=now,
            approved_by=self.admin_a,
        )
        self.other_admin_membership = OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.other_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=now,
            approved_by=self.other_admin,
        )

    def test_admin_can_promote_researcher_to_admin(self):
        membership = change_organization_membership_role(
            organization=self.organization,
            membership_id=self.researcher_membership.id,
            role=OrganizationMembership.Role.ADMIN,
            actor=self.admin_a,
        )
        self.assertEqual(membership.role, OrganizationMembership.Role.ADMIN)

    def test_admin_can_assign_verification_reviewer(self):
        membership = change_organization_membership_role(
            organization=self.organization,
            membership_id=self.researcher_membership.id,
            role=OrganizationMembership.Role.VERIFICATION_REVIEWER,
            actor=self.admin_a,
        )
        self.assertEqual(
            membership.role,
            OrganizationMembership.Role.VERIFICATION_REVIEWER,
        )

    def test_admin_can_suspend_another_admin_when_one_remains(self):
        membership = suspend_organization_membership(
            organization=self.organization,
            membership_id=self.admin_b_membership.id,
            actor=self.admin_a,
        )
        self.assertEqual(membership.status, OrganizationMembership.Status.SUSPENDED)

    def test_admin_can_remove_another_admin_when_one_remains(self):
        membership = remove_organization_membership(
            organization=self.organization,
            membership_id=self.admin_b_membership.id,
            actor=self.admin_a,
        )
        self.assertEqual(membership.status, OrganizationMembership.Status.LEFT)

    def test_final_active_admin_cannot_be_suspended(self):
        self.admin_b_membership.status = OrganizationMembership.Status.SUSPENDED
        self.admin_b_membership.save(update_fields=["status"])

        with self.assertRaises(OrganizationMembershipConflict):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=self.admin_a_membership.id,
                actor=self.admin_a,
            )

    def test_final_active_admin_cannot_be_removed(self):
        self.admin_b_membership.status = OrganizationMembership.Status.LEFT
        self.admin_b_membership.save(update_fields=["status"])

        with self.assertRaises(OrganizationMembershipConflict):
            remove_organization_membership(
                organization=self.organization,
                membership_id=self.admin_a_membership.id,
                actor=self.admin_a,
            )

    def test_final_active_admin_cannot_be_demoted(self):
        self.admin_b_membership.status = OrganizationMembership.Status.SUSPENDED
        self.admin_b_membership.save(update_fields=["status"])

        with self.assertRaises(OrganizationMembershipConflict):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=self.admin_a_membership.id,
                role=OrganizationMembership.Role.RESEARCHER,
                actor=self.admin_a,
            )

    def test_supported_roles_exclude_retired_roles(self):
        values = {value for value, _label in OrganizationMembership.Role.choices}
        self.assertEqual(
            values,
            {
                OrganizationMembership.Role.ADMIN,
                OrganizationMembership.Role.LEAD_VERIFIER,
                OrganizationMembership.Role.VERIFICATION_REVIEWER,
                OrganizationMembership.Role.RESEARCHER,
            },
        )

    def test_retired_role_cannot_be_assigned(self):
        with self.assertRaises(InvalidOrganizationMembershipRole):
            change_organization_membership_role(
                organization=self.organization,
                membership_id=self.researcher_membership.id,
                role="CONTRIBUTOR",
                actor=self.admin_a,
            )

    def test_factual_role_cannot_manage_memberships(self):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=self.researcher_membership.id,
                actor=self.lead,
            )

    def test_other_organization_admin_cannot_manage_membership(self):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=self.researcher_membership.id,
                actor=self.other_admin,
            )

    def test_suspended_member_can_be_restored(self):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED
        self.researcher_membership.save(update_fields=["status"])

        membership = restore_organization_membership(
            organization=self.organization,
            membership_id=self.researcher_membership.id,
            actor=self.admin_a,
        )
        self.assertEqual(membership.status, OrganizationMembership.Status.ACTIVE)

    def test_admin_has_management_capability_only(self):
        self.assertTrue(
            has_capability(
                self.admin_a,
                PartnerCapability.MANAGE_ORGANIZATION,
                organization=self.organization,
            )
        )
        self.assertFalse(
            has_capability(
                self.admin_a,
                PartnerCapability.CLAIM_VERIFICATION_WORK,
                organization=self.organization,
            )
        )
        self.assertFalse(
            has_capability(
                self.admin_a,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

    def test_verification_reviewer_has_review_and_adjudication_not_claiming(self):
        self.assertTrue(
            has_capability(
                self.reviewer,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization,
            )
        )
        self.assertTrue(
            has_capability(
                self.reviewer,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )
        self.assertFalse(
            has_capability(
                self.reviewer,
                PartnerCapability.CLAIM_VERIFICATION_WORK,
                organization=self.organization,
            )
        )

    def test_unauthenticated_actor_cannot_manage_membership(self):
        with self.assertRaises(OrganizationMembershipAuthorizationError):
            suspend_organization_membership(
                organization=self.organization,
                membership_id=self.researcher_membership.id,
                actor=AnonymousUser(),
            )
