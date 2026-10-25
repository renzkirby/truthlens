from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from api.models import Organization, OrganizationMembership


class OrganizationMembershipConstraintTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="single-organization-member",
            email="single-org@example.com",
        )
        self.organization_a = Organization.objects.create(
            name="Constraint Partner A",
            slug="constraint-partner-a",
        )
        self.organization_b = Organization.objects.create(
            name="Constraint Partner B",
            slug="constraint-partner-b",
        )

    def test_user_cannot_hold_two_current_organization_memberships(self):
        OrganizationMembership.objects.create(
            organization=self.organization_a,
            user=self.user,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationMembership.objects.create(
                organization=self.organization_b,
                user=self.user,
                role=OrganizationMembership.Role.LEAD_VERIFIER,
                status=OrganizationMembership.Status.PENDING,
            )

    def test_left_history_does_not_block_new_current_membership(self):
        OrganizationMembership.objects.create(
            organization=self.organization_a,
            user=self.user,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.LEFT,
        )
        membership = OrganizationMembership.objects.create(
            organization=self.organization_b,
            user=self.user,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        self.assertEqual(
            membership.organization,
            self.organization_b,
        )

    def test_suspended_membership_still_blocks_second_organization(self):
        OrganizationMembership.objects.create(
            organization=self.organization_a,
            user=self.user,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.SUSPENDED,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationMembership.objects.create(
                organization=self.organization_b,
                user=self.user,
                role=OrganizationMembership.Role.RESEARCHER,
                status=OrganizationMembership.Status.ACTIVE,
            )
