from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from .models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from .organization_invitation_service import (
    InvalidOrganizationInvitationRole,
    OrganizationInvitationAuthorizationError,
    OrganizationInvitationConflict,
    create_organization_invitation,
    hash_invitation_token,
    OrganizationInvitationError,
    OrganizationInvitationDeliveryError,
    cancel_organization_invitation,
    create_and_send_organization_invitation,
    get_organization_invitations,
    resend_organization_invitation,
)
from unittest.mock import patch

from django.core import mail
from django.test import (
    TestCase,
    override_settings,
)


@override_settings(
    EMAIL_BACKEND=("django.core.mail.backends." "locmem.EmailBackend"),
    DEFAULT_FROM_EMAIL=("noreply@truthlens.test"),
)
class OrganizationInvitationServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="invite-owner",
            email="owner@example.com",
            password="test-password",
        )

        self.admin = User.objects.create_user(
            username="invite-admin",
            email="admin@example.com",
            password="test-password",
        )

        self.lead = User.objects.create_user(
            username="invite-lead",
            email="lead@example.com",
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name="Invitation Partner",
            slug="invitation-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=(OrganizationMembership.Role.ADMIN),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

    def test_owner_can_invite_admin(
        self,
    ):
        invitation, token = create_organization_invitation(
            organization=(self.organization),
            email=("NewAdmin@Example.com "),
            invited_role=(OrganizationMembership.Role.ADMIN),
            actor=self.owner,
        )

        self.assertEqual(
            invitation.email,
            "newadmin@example.com",
        )

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.PENDING,
        )

        self.assertEqual(
            invitation.invited_role,
            OrganizationMembership.Role.ADMIN,
        )

        self.assertNotEqual(
            invitation.token_digest,
            token,
        )

        self.assertEqual(
            invitation.token_digest,
            hash_invitation_token(token),
        )

    def test_admin_can_invite_factual_role(
        self,
    ):
        invitation, _ = create_organization_invitation(
            organization=(self.organization),
            email=("researcher@example.com"),
            invited_role=(OrganizationMembership.Role.RESEARCHER),
            actor=self.admin,
        )

        self.assertEqual(
            invitation.invited_role,
            OrganizationMembership.Role.RESEARCHER,
        )

    def test_admin_cannot_invite_admin(
        self,
    ):
        with self.assertRaises(InvalidOrganizationInvitationRole):
            create_organization_invitation(
                organization=(self.organization),
                email=("another-admin@example.com"),
                invited_role=(OrganizationMembership.Role.ADMIN),
                actor=self.admin,
            )

    def test_owner_cannot_invite_owner(
        self,
    ):
        with self.assertRaises(InvalidOrganizationInvitationRole):
            create_organization_invitation(
                organization=(self.organization),
                email=("owner-two@example.com"),
                invited_role=(OrganizationMembership.Role.OWNER),
                actor=self.owner,
            )

    def test_factual_role_cannot_invite(
        self,
    ):
        with self.assertRaises(OrganizationInvitationAuthorizationError):
            create_organization_invitation(
                organization=(self.organization),
                email=("member@example.com"),
                invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
                actor=self.lead,
            )

    def test_duplicate_pending_invitation_is_blocked(
        self,
    ):
        create_organization_invitation(
            organization=self.organization,
            email="pending@example.com",
            invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
            actor=self.owner,
        )

        with self.assertRaises(OrganizationInvitationConflict):
            create_organization_invitation(
                organization=(self.organization),
                email="PENDING@example.com",
                invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
                actor=self.owner,
            )

    def test_current_member_cannot_be_invited(
        self,
    ):
        with self.assertRaises(OrganizationInvitationConflict):
            create_organization_invitation(
                organization=(self.organization),
                email=self.lead.email,
                invited_role=(OrganizationMembership.Role.RESEARCHER),
                actor=self.owner,
            )

    def test_raw_token_is_not_stored(
        self,
    ):
        invitation, token = create_organization_invitation(
            organization=(self.organization),
            email="token@example.com",
            invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
            actor=self.owner,
        )

        invitation.refresh_from_db()

        self.assertNotEqual(
            invitation.token_digest,
            token,
        )

        self.assertEqual(
            len(invitation.token_digest),
            64,
        )

    def test_invitation_has_future_expiry(
        self,
    ):
        invitation, _ = create_organization_invitation(
            organization=(self.organization),
            email="expiry@example.com",
            invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
            actor=self.owner,
        )

        self.assertGreater(
            invitation.expires_at,
            timezone.now(),
        )

    def test_blank_invitation_email_is_rejected(
        self,
    ):
        with self.assertRaises(OrganizationInvitationError):
            create_organization_invitation(
                organization=(self.organization),
                email="   ",
                invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
                actor=self.owner,
            )

    def test_invalid_invitation_email_is_rejected(
        self,
    ):
        with self.assertRaises(OrganizationInvitationError):
            create_organization_invitation(
                organization=(self.organization),
                email="not-an-email",
                invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
                actor=self.owner,
            )

    def test_create_and_send_delivers_invitation_email(
        self,
    ):
        invitation = create_and_send_organization_invitation(
            organization=self.organization,
            email="recipient@example.com",
            invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
            actor=self.owner,
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

        self.assertEqual(
            mail.outbox[0].to,
            ["recipient@example.com"],
        )

        self.assertIn(
            self.organization.name,
            mail.outbox[0].subject,
        )

        self.assertIn(
            "/organization-invitations/",
            mail.outbox[0].body,
        )

        self.assertEqual(
            invitation.send_count,
            1,
        )

    @patch(
        "api.organization_invitation_service." "EmailMultiAlternatives.send",
        side_effect=Exception("SMTP unavailable"),
    )
    def test_delivery_failure_rolls_back_creation(
        self,
        _mock_send,
    ):
        with self.assertRaises(OrganizationInvitationDeliveryError):
            create_and_send_organization_invitation(
                organization=self.organization,
                email="failed@example.com",
                invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
                actor=self.owner,
            )

        self.assertFalse(
            OrganizationInvitation.objects.filter(
                organization=self.organization,
                email="failed@example.com",
            ).exists()
        )

    def test_resend_rotates_token_and_increments_count(
        self,
    ):
        invitation = create_and_send_organization_invitation(
            organization=self.organization,
            email="resend@example.com",
            invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
            actor=self.owner,
        )

        old_digest = invitation.token_digest

        mail.outbox.clear()

        invitation = resend_organization_invitation(
            invitation=invitation,
            actor=self.owner,
        )

        self.assertNotEqual(
            invitation.token_digest,
            old_digest,
        )

        self.assertEqual(
            invitation.send_count,
            2,
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

    def test_cancel_invalidates_pending_invitation(
        self,
    ):
        invitation, _ = create_organization_invitation(
            organization=self.organization,
            email="cancel@example.com",
            invited_role=(OrganizationMembership.Role.RESEARCHER),
            actor=self.owner,
        )

        old_digest = invitation.token_digest

        invitation = cancel_organization_invitation(
            invitation=invitation,
            actor=self.owner,
        )

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.CANCELLED,
        )

        self.assertEqual(
            invitation.cancelled_by,
            self.owner,
        )

        self.assertIsNotNone(
            invitation.cancelled_at,
        )

        self.assertNotEqual(
            invitation.token_digest,
            old_digest,
        )

    def test_listing_materializes_expired_invitations(
        self,
    ):
        invitation, _ = create_organization_invitation(
            organization=self.organization,
            email="expired@example.com",
            invited_role=(OrganizationMembership.Role.CONTRIBUTOR),
            actor=self.owner,
        )

        invitation.expires_at = timezone.now() - timedelta(minutes=1)

        invitation.save(
            update_fields=[
                "expires_at",
            ]
        )

        list(
            get_organization_invitations(
                organization=self.organization,
                actor=self.owner,
            )
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.EXPIRED,
        )
