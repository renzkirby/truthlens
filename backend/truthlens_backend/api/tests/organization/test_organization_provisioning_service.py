from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

from api.models import (
    AccountabilityEvent,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from api.organization_invitation_service import (
    OrganizationInvitationConflict,
    accept_organization_invitation,
)
from api.organization_provisioning_service import (
    PROVISION_PARTNER_ORGANIZATION,
    OrganizationProvisioningAuthorizationError,
    OrganizationProvisioningConflict,
    cancel_organization_admin_invitation,
    create_and_send_organization_admin_invitation,
    resend_organization_admin_invitation,
)


class OrganizationProvisioningServiceTests(TestCase):
    def setUp(self):
        self.developer = User.objects.create_superuser(
            username="provisioning-developer",
            email="developer@example.com",
            password="test-password",
        )
        self.ordinary_user = User.objects.create_user(
            username="provisioning-user",
            email="ordinary@example.com",
            password="test-password",
        )
        self.recipient = User.objects.create_user(
            username="provisioning-recipient",
            email="recipient@example.com",
            password="test-password",
        )
        self.recipient.profile.is_email_verified = True
        self.recipient.profile.save(update_fields=["is_email_verified"])
        self.organization = Organization.objects.create(
            name="Provisioning Partner",
            slug="provisioning-partner",
        )

    def provision(self, *, email=None, actor=None):
        return create_and_send_organization_admin_invitation(
            organization=self.organization,
            email=email or self.recipient.email,
            actor=actor or self.developer,
        )

    def test_superuser_provisions_organization_admin(self):
        invitation = self.provision()

        self.assertEqual(
            invitation.invited_role,
            OrganizationMembership.Role.ADMIN,
        )
        self.assertEqual(
            invitation.purpose,
            OrganizationInvitation.InvitationPurpose.ORGANIZATION_ADMIN_ONBOARDING,
        )
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Organization Admin", mail.outbox[0].body)

        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
            resource_id=str(invitation.pk),
        )
        self.assertEqual(event.capability, PROVISION_PARTNER_ORGANIZATION)

    def test_non_superuser_cannot_provision_admin(self):
        with self.assertRaises(OrganizationProvisioningAuthorizationError):
            self.provision(actor=self.ordinary_user)

    def test_acceptance_creates_active_admin(self):
        raw_token = "organization-admin-token"
        with patch(
            "api.organization_provisioning_service.generate_invitation_token",
            return_value=raw_token,
        ):
            invitation = self.provision()

        result = accept_organization_invitation(
            raw_token=raw_token,
            actor=self.recipient,
        )

        invitation.refresh_from_db()
        membership = result["membership"]
        self.assertEqual(membership.role, OrganizationMembership.Role.ADMIN)
        self.assertEqual(membership.status, OrganizationMembership.Status.ACTIVE)
        self.assertEqual(invitation.status, OrganizationInvitation.Status.ACCEPTED)

    def test_existing_current_membership_in_other_org_blocks_provisioning(self):
        other = Organization.objects.create(
            name="Other Provisioning Partner",
            slug="other-provisioning-partner",
        )
        OrganizationMembership.objects.create(
            organization=other,
            user=self.recipient,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        with self.assertRaises(OrganizationProvisioningConflict):
            self.provision()

    def test_existing_admin_blocks_initial_admin_provisioning(self):
        admin = User.objects.create_user(
            username="existing-admin",
            email="existing-admin@example.com",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )

        with self.assertRaises(OrganizationProvisioningConflict):
            self.provision()

    def test_resend_rotates_delivery_and_cancel_closes_invitation(self):
        invitation = self.provision()
        original_digest = invitation.token_digest

        resent = resend_organization_admin_invitation(
            invitation=invitation,
            actor=self.developer,
        )
        resent.refresh_from_db()
        self.assertNotEqual(resent.token_digest, original_digest)
        self.assertEqual(resent.send_count, 2)

        cancelled = cancel_organization_admin_invitation(
            invitation=resent,
            actor=self.developer,
        )
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, OrganizationInvitation.Status.CANCELLED)
        self.assertEqual(cancelled.cancelled_by, self.developer)

    def test_acceptance_rejects_new_cross_org_membership_race(self):
        raw_token = "cross-org-admin-token"
        with patch(
            "api.organization_provisioning_service.generate_invitation_token",
            return_value=raw_token,
        ):
            invitation = self.provision()

        other = Organization.objects.create(
            name="Concurrent Partner",
            slug="concurrent-partner",
        )
        OrganizationMembership.objects.create(
            organization=other,
            user=self.recipient,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        with self.assertRaises(OrganizationInvitationConflict):
            accept_organization_invitation(
                raw_token=raw_token,
                actor=self.recipient,
            )

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)
