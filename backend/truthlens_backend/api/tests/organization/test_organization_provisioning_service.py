import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from api.models import (
    AccountabilityEvent,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from api.organization_invitation_service import (
    InvalidOrganizationInvitationRole,
    OrganizationInvitationAuthorizationError,
    OrganizationInvitationConflict,
    OrganizationInvitationNotFound,
    accept_organization_invitation,
    create_organization_invitation,
    hash_invitation_token,
    resend_organization_invitation,
)
from api.organization_provisioning_service import (
    PROVISION_PARTNER_ORGANIZATION,
    OrganizationProvisioningAuthorizationError,
    OrganizationProvisioningConflict,
    create_and_send_primary_admin_invitation,
    resend_primary_admin_invitation,
)
from api.serializers import OrganizationInvitationPublicSerializer


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@truthlens.test",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class OrganizationProvisioningServiceTests(TestCase):
    def setUp(self):
        self.developer = User.objects.create_superuser(
            username="provisioning-developer",
            email="developer@example.com",
            password="test-password",
        )
        self.staff_user = User.objects.create_user(
            username="provisioning-staff",
            email="staff@example.com",
            password="test-password",
            is_staff=True,
        )
        self.ordinary_user = User.objects.create_user(
            username="provisioning-user",
            email="ordinary@example.com",
            password="test-password",
        )
        self.owner_manager = User.objects.create_user(
            username="provisioning-owner",
            email="owner@example.com",
            password="test-password",
        )
        self.organization_admin = User.objects.create_user(
            username="provisioning-admin",
            email="admin@example.com",
            password="test-password",
        )
        self.recipient = User.objects.create_user(
            username="primary-admin-recipient",
            email="recipient@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Provisioning Partner",
            slug="provisioning-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    def verify_email(self, user):
        user.profile.is_email_verified = True
        user.profile.save(update_fields=["is_email_verified"])
        return user

    def create_management_membership(self, user, role, status=None):
        return OrganizationMembership.objects.create(
            organization=self.organization,
            user=user,
            role=role,
            status=status or OrganizationMembership.Status.ACTIVE,
        )

    def provision(self, *, email=None, actor=None):
        return create_and_send_primary_admin_invitation(
            organization=self.organization,
            email=email or self.recipient.email,
            actor=actor or self.developer,
        )

    def provision_with_token(self, raw_token="primary-admin-raw-token"):
        with patch(
            "api.organization_provisioning_service.generate_invitation_token",
            return_value=raw_token,
        ):
            invitation = self.provision()

        return invitation, raw_token

    def test_active_superuser_can_create_primary_admin_invitation(self):
        invitation = self.provision(email=" New.Primary@Example.com ")

        self.assertEqual(invitation.email, "new.primary@example.com")
        self.assertEqual(
            invitation.purpose,
            OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING,
        )
        self.assertEqual(
            invitation.invited_role,
            OrganizationMembership.Role.OWNER,
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_ordinary_user_cannot_provision_primary_admin(self):
        with self.assertRaises(OrganizationProvisioningAuthorizationError):
            self.provision(actor=self.ordinary_user)

    def test_organization_owner_cannot_provision_primary_admin(self):
        self.create_management_membership(
            self.owner_manager,
            OrganizationMembership.Role.OWNER,
        )

        with self.assertRaises(OrganizationProvisioningAuthorizationError):
            self.provision(actor=self.owner_manager)

    def test_organization_admin_cannot_provision_primary_admin(self):
        self.create_management_membership(
            self.organization_admin,
            OrganizationMembership.Role.ADMIN,
        )

        with self.assertRaises(OrganizationProvisioningAuthorizationError):
            self.provision(actor=self.organization_admin)

    def test_non_superuser_staff_cannot_provision_primary_admin(self):
        with self.assertRaises(OrganizationProvisioningAuthorizationError):
            self.provision(actor=self.staff_user)

    def test_invitation_stores_only_digest_and_does_not_create_user(self):
        raw_token = "known-primary-admin-token"
        initial_user_count = User.objects.count()

        with patch(
            "api.organization_provisioning_service.generate_invitation_token",
            return_value=raw_token,
        ):
            invitation = self.provision(email="unregistered@example.com")

        self.assertEqual(User.objects.count(), initial_user_count)
        self.assertEqual(invitation.token_digest, hash_invitation_token(raw_token))
        self.assertNotEqual(invitation.token_digest, raw_token)
        self.assertNotIn(raw_token, json.dumps({
            "purpose": invitation.purpose,
            "role": invitation.invited_role,
        }))

    def test_current_owner_blocks_provisioning(self):
        membership = self.create_management_membership(
            self.owner_manager,
            OrganizationMembership.Role.OWNER,
        )

        with self.assertRaises(OrganizationProvisioningConflict):
            self.provision()

        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)
        self.assertEqual(OrganizationInvitation.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_suspended_owner_blocks_provisioning(self):
        self.create_management_membership(
            self.owner_manager,
            OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.SUSPENDED,
        )

        with self.assertRaises(OrganizationProvisioningConflict):
            self.provision()

    def test_multiple_pending_primary_admin_invitations_are_blocked(self):
        first = self.provision()

        with self.assertRaises(OrganizationProvisioningConflict):
            self.provision(email="other-recipient@example.com")

        self.assertEqual(
            OrganizationInvitation.objects.filter(
                organization=self.organization,
                purpose=(
                    OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
                ),
                status=OrganizationInvitation.Status.PENDING,
            ).count(),
            1,
        )
        self.assertTrue(
            OrganizationInvitation.objects.filter(pk=first.pk).exists()
        )

    def test_expired_primary_admin_invitation_can_be_replaced(self):
        expired = self.provision()
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])

        replacement = self.provision(email="replacement@example.com")

        expired.refresh_from_db()
        self.assertEqual(expired.status, OrganizationInvitation.Status.EXPIRED)
        self.assertEqual(replacement.status, OrganizationInvitation.Status.PENDING)
        self.assertNotEqual(replacement.pk, expired.pk)

    def test_existing_current_member_is_not_implicitly_promoted(self):
        self.create_management_membership(
            self.recipient,
            OrganizationMembership.Role.RESEARCHER,
        )

        with self.assertRaises(OrganizationProvisioningConflict):
            self.provision()

    def test_resend_rotates_token_and_remains_developer_only(self):
        invitation = self.provision()
        original_digest = invitation.token_digest
        mail.outbox.clear()

        resent = resend_primary_admin_invitation(
            invitation=invitation,
            actor=self.developer,
        )

        resent.refresh_from_db()
        self.assertNotEqual(resent.token_digest, original_digest)
        self.assertEqual(resent.send_count, 2)
        self.assertEqual(len(mail.outbox), 1)

        with self.assertRaises(OrganizationProvisioningAuthorizationError):
            resend_primary_admin_invitation(
                invitation=resent,
                actor=self.ordinary_user,
            )

    def test_ordinary_invitation_service_rejects_owner(self):
        self.create_management_membership(
            self.owner_manager,
            OrganizationMembership.Role.OWNER,
        )

        with self.assertRaises(InvalidOrganizationInvitationRole):
            create_organization_invitation(
                organization=self.organization,
                email="forbidden-owner@example.com",
                invited_role=OrganizationMembership.Role.OWNER,
                actor=self.owner_manager,
            )

    def test_ordinary_invitation_cannot_resend_onboarding_invitation(self):
        invitation = self.provision()
        self.create_management_membership(
            self.organization_admin,
            OrganizationMembership.Role.ADMIN,
        )

        with self.assertRaises(OrganizationInvitationAuthorizationError):
            resend_organization_invitation(
                invitation=invitation,
                actor=self.organization_admin,
            )

    def test_ordinary_membership_invitation_still_accepts_normally(self):
        ordinary_organization = Organization.objects.create(
            name="Ordinary Invitation Partner",
            slug="ordinary-invitation-partner",
        )
        owner = User.objects.create_user(
            username="ordinary-invitation-owner",
            email="ordinary-owner@example.com",
            password="test-password",
        )
        recipient = User.objects.create_user(
            username="ordinary-invitation-recipient",
            email="ordinary-recipient@example.com",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=ordinary_organization,
            user=owner,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.verify_email(recipient)

        invitation, raw_token = create_organization_invitation(
            organization=ordinary_organization,
            email=recipient.email,
            invited_role=OrganizationMembership.Role.RESEARCHER,
            actor=owner,
        )
        result = accept_organization_invitation(
            raw_token=raw_token,
            actor=recipient,
        )

        self.assertEqual(
            invitation.purpose,
            OrganizationInvitation.InvitationPurpose.MEMBERSHIP,
        )
        self.assertEqual(
            result["membership"].role,
            OrganizationMembership.Role.RESEARCHER,
        )

    def test_primary_admin_acceptance_requires_authentication(self):
        _invitation, raw_token = self.provision_with_token()

        with self.assertRaises(OrganizationInvitationAuthorizationError):
            accept_organization_invitation(
                raw_token=raw_token,
                actor=None,
            )

    def test_primary_admin_acceptance_requires_matching_email(self):
        invitation, raw_token = self.provision_with_token()

        with self.assertRaises(OrganizationInvitationAuthorizationError):
            accept_organization_invitation(
                raw_token=raw_token,
                actor=self.ordinary_user,
            )

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)

    def test_primary_admin_acceptance_requires_verified_email(self):
        invitation, raw_token = self.provision_with_token()

        with self.assertRaises(OrganizationInvitationAuthorizationError):
            accept_organization_invitation(
                raw_token=raw_token,
                actor=self.recipient,
            )

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)

    def test_primary_admin_acceptance_creates_active_owner_and_consumes_token(self):
        self.verify_email(self.recipient)
        invitation, raw_token = self.provision_with_token()
        original_digest = invitation.token_digest

        result = accept_organization_invitation(
            raw_token=raw_token,
            actor=self.recipient,
        )

        membership = result["membership"]
        invitation.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)
        self.assertEqual(membership.status, OrganizationMembership.Status.ACTIVE)
        self.assertEqual(invitation.status, OrganizationInvitation.Status.ACCEPTED)
        self.assertNotEqual(invitation.token_digest, original_digest)

        with self.assertRaises(OrganizationInvitationNotFound):
            accept_organization_invitation(
                raw_token=raw_token,
                actor=self.recipient,
            )

    def test_left_membership_is_reactivated_as_owner(self):
        self.verify_email(self.recipient)
        membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.recipient,
            role=OrganizationMembership.Role.CONTRIBUTOR,
            status=OrganizationMembership.Status.LEFT,
        )
        original_membership_id = membership.pk
        _invitation, raw_token = self.provision_with_token()

        result = accept_organization_invitation(
            raw_token=raw_token,
            actor=self.recipient,
        )

        membership.refresh_from_db()
        self.assertEqual(result["membership"].pk, original_membership_id)
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)
        self.assertEqual(membership.status, OrganizationMembership.Status.ACTIVE)

    def test_current_membership_appearing_before_acceptance_is_conflict(self):
        self.verify_email(self.recipient)
        invitation, raw_token = self.provision_with_token()
        membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.recipient,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        with self.assertRaises(OrganizationInvitationConflict):
            accept_organization_invitation(
                raw_token=raw_token,
                actor=self.recipient,
            )

        membership.refresh_from_db()
        invitation.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.RESEARCHER)
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)

    def test_another_owner_appearing_before_acceptance_is_safe_conflict(self):
        self.verify_email(self.recipient)
        invitation, raw_token = self.provision_with_token()
        competing_owner = self.create_management_membership(
            self.owner_manager,
            OrganizationMembership.Role.OWNER,
        )

        with self.assertRaises(OrganizationInvitationConflict):
            accept_organization_invitation(
                raw_token=raw_token,
                actor=self.recipient,
            )

        competing_owner.refresh_from_db()
        invitation.refresh_from_db()
        self.assertEqual(competing_owner.role, OrganizationMembership.Role.OWNER)
        self.assertEqual(
            competing_owner.status,
            OrganizationMembership.Status.ACTIVE,
        )
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)
        self.assertFalse(
            OrganizationMembership.objects.filter(
                organization=self.organization,
                user=self.recipient,
            ).exists()
        )

    def test_primary_admin_user_facing_label_is_used(self):
        invitation = self.provision()

        self.assertEqual(
            OrganizationInvitationPublicSerializer(invitation).data[
                "invited_role_label"
            ],
            "Primary Admin",
        )
        self.assertIn("Primary Admin", mail.outbox[0].body)
        self.assertNotIn("as Owner", mail.outbox[0].body)

    def test_provisioning_accountability_is_platform_scoped_and_secret_free(self):
        raw_token = "audit-secret-raw-token"

        with patch(
            "api.organization_provisioning_service.generate_invitation_token",
            return_value=raw_token,
        ):
            invitation = self.provision()

        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
            resource_id=str(invitation.pk),
        )
        self.assertEqual(
            event.authority_scope,
            AccountabilityEvent.AuthorityScope.PLATFORM,
        )
        self.assertEqual(event.actor, self.developer)
        self.assertIsNone(event.authority_organization)
        self.assertEqual(event.subject_organization, self.organization)
        self.assertEqual(event.capability, PROVISION_PARTNER_ORGANIZATION)

        payload = json.dumps(
            {
                "previous_state": event.previous_state,
                "new_state": event.new_state,
                "context": event.context,
                "notes": event.notes,
            }
        ).lower()
        self.assertNotIn(raw_token.lower(), payload)
        self.assertNotIn("token_digest", payload)
        self.assertNotIn("password", payload)
