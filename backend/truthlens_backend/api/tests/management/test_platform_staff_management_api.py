from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import AccountabilityEvent, PlatformStaffInvitation, UserProfile
from api.platform_staff_service import MANAGE_PLATFORM_STAFF


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@truthlens.test",
)
class PlatformStaffManagementApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="platform-admin",
            email="platform-admin@example.com",
            password="test-password",
        )
        self.moderator = User.objects.create_user(
            username="safety-moderator",
            email="safety@example.com",
            password="test-password",
        )
        moderator_profile, _ = UserProfile.objects.get_or_create(user=self.moderator)
        moderator_profile.role = UserProfile.Role.MOD
        moderator_profile.is_email_verified = True
        moderator_profile.save(update_fields=["role", "is_email_verified"])

        self.ordinary = User.objects.create_user(
            username="eligible-user",
            email="eligible@example.com",
            password="test-password",
        )
        ordinary_profile, _ = UserProfile.objects.get_or_create(user=self.ordinary)
        ordinary_profile.is_email_verified = True
        ordinary_profile.save(update_fields=["is_email_verified"])

        self.unverified = User.objects.create_user(
            username="unverified-user",
            email="unverified@example.com",
            password="test-password",
        )
        UserProfile.objects.get_or_create(user=self.unverified)

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def invitation_token_from_latest_email(self):
        marker = "/platform-staff-invitations/"
        self.assertTrue(mail.outbox)
        self.assertIn(marker, mail.outbox[-1].body)
        return mail.outbox[-1].body.split(marker, 1)[1].split()[0].strip()

    def create_invitation(self, email):
        response = self.client_for(self.admin).post(
            reverse("management_platform_staff_invitations"),
            {"email": email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        invitation = PlatformStaffInvitation.objects.get(pk=response.data["id"])
        return response, invitation, self.invitation_token_from_latest_email()

    def test_platform_admin_can_list_platform_staff(self):
        response = self.client_for(self.admin).get(reverse("management_platform_staff"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_username = {item["username"]: item for item in response.data["results"]}
        self.assertEqual(
            by_username[self.admin.username]["platform_role"],
            "PLATFORM_ADMIN",
        )
        self.assertFalse(by_username[self.admin.username]["can_revoke"])
        self.assertEqual(
            by_username[self.moderator.username]["platform_role"],
            "PLATFORM_SAFETY_MODERATOR",
        )
        self.assertTrue(by_username[self.moderator.username]["can_revoke"])
        self.assertNotIn(self.ordinary.username, by_username)

    def test_platform_admin_can_send_platform_staff_invitation(self):
        response, invitation, _token = self.create_invitation("new-moderator@example.com")

        self.assertEqual(response.data["email"], "new-moderator@example.com")
        self.assertEqual(
            response.data["platform_role"],
            PlatformStaffInvitation.PlatformRole.PLATFORM_SAFETY_MODERATOR,
        )
        self.assertEqual(invitation.status, PlatformStaffInvitation.Status.PENDING)
        self.assertEqual(invitation.invited_by, self.admin)
        self.assertEqual(invitation.send_count, 1)
        self.assertEqual(mail.outbox[-1].to, ["new-moderator@example.com"])
        self.assertIn("Platform Safety Moderator", mail.outbox[-1].subject)

        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CREATED,
            resource_id=str(invitation.id),
        )
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.capability, MANAGE_PLATFORM_STAFF)
        self.assertEqual(
            event.resource_type,
            AccountabilityEvent.ResourceType.PLATFORM_STAFF_INVITATION,
        )

    def test_duplicate_pending_invitation_is_blocked(self):
        self.create_invitation("pending@example.com")

        response = self.client_for(self.admin).post(
            reverse("management_platform_staff_invitations"),
            {"email": "PENDING@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_existing_platform_staff_cannot_be_invited(self):
        client = self.client_for(self.admin)

        moderator_response = client.post(
            reverse("management_platform_staff_invitations"),
            {"email": self.moderator.email},
            format="json",
        )
        admin_response = client.post(
            reverse("management_platform_staff_invitations"),
            {"email": self.admin.email},
            format="json",
        )

        self.assertEqual(moderator_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(admin_response.status_code, status.HTTP_409_CONFLICT)

    def test_invitation_rejects_email_owned_only_by_inactive_account(self):
        inactive = User.objects.create_user(
            username="inactive-user",
            email="inactive@example.com",
            password="test-password",
            is_active=False,
        )
        UserProfile.objects.get_or_create(user=inactive)

        response = self.client_for(self.admin).post(
            reverse("management_platform_staff_invitations"),
            {"email": inactive.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_public_invitation_detail_does_not_expose_email(self):
        _response, _invitation, token = self.create_invitation(self.ordinary.email)

        response = self.client_for(None).get(
            reverse("platform_staff_invitation_detail", kwargs={"token": token})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("email", response.data)
        self.assertEqual(
            response.data["platform_role"],
            PlatformStaffInvitation.PlatformRole.PLATFORM_SAFETY_MODERATOR,
        )
        self.assertIsNone(response.data["recipient_matches_current_user"])

    def test_verified_matching_user_can_accept_invitation(self):
        _response, invitation, token = self.create_invitation(self.ordinary.email)

        response = self.client_for(self.ordinary).post(
            reverse("platform_staff_invitation_accept", kwargs={"token": token}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.ordinary.profile.refresh_from_db()
        invitation.refresh_from_db()
        self.assertEqual(self.ordinary.profile.role, UserProfile.Role.MOD)
        self.assertEqual(invitation.status, PlatformStaffInvitation.Status.ACCEPTED)
        self.assertEqual(invitation.accepted_by, self.ordinary)
        self.assertIsNotNone(invitation.accepted_at)

        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_ACCEPTED,
            resource_id=str(invitation.id),
        )
        self.assertEqual(event.actor, self.ordinary)
        self.assertEqual(
            event.authority_scope,
            AccountabilityEvent.AuthorityScope.PERSONAL,
        )
        self.assertEqual(event.capability, "")

    def test_acceptance_requires_matching_verified_email(self):
        _response, _invitation, ordinary_token = self.create_invitation(self.ordinary.email)

        wrong_user = User.objects.create_user(
            username="wrong-user",
            email="wrong@example.com",
            password="test-password",
        )
        wrong_profile, _ = UserProfile.objects.get_or_create(user=wrong_user)
        wrong_profile.is_email_verified = True
        wrong_profile.save(update_fields=["is_email_verified"])

        wrong_response = self.client_for(wrong_user).post(
            reverse(
                "platform_staff_invitation_accept",
                kwargs={"token": ordinary_token},
            ),
            {},
            format="json",
        )
        self.assertEqual(wrong_response.status_code, status.HTTP_403_FORBIDDEN)

        mail.outbox.clear()
        _response, _invitation, unverified_token = self.create_invitation(
            self.unverified.email
        )
        unverified_response = self.client_for(self.unverified).post(
            reverse(
                "platform_staff_invitation_accept",
                kwargs={"token": unverified_token},
            ),
            {},
            format="json",
        )
        self.assertEqual(unverified_response.status_code, status.HTTP_403_FORBIDDEN)
        self.unverified.profile.refresh_from_db()
        self.assertEqual(self.unverified.profile.role, UserProfile.Role.USER)

    def test_platform_admin_can_resend_and_cancel_pending_invitation(self):
        _response, invitation, old_token = self.create_invitation("lifecycle@example.com")
        old_digest = invitation.token_digest
        mail.outbox.clear()

        resend = self.client_for(self.admin).post(
            reverse(
                "management_platform_staff_invitation_resend",
                kwargs={"invitation_id": invitation.id},
            ),
            {},
            format="json",
        )
        self.assertEqual(resend.status_code, status.HTTP_200_OK)
        invitation.refresh_from_db()
        self.assertNotEqual(invitation.token_digest, old_digest)
        self.assertEqual(invitation.send_count, 2)
        self.assertEqual(len(mail.outbox), 1)

        old_link = self.client_for(None).get(
            reverse(
                "platform_staff_invitation_detail",
                kwargs={"token": old_token},
            )
        )
        self.assertEqual(old_link.status_code, status.HTTP_404_NOT_FOUND)
        new_token = self.invitation_token_from_latest_email()
        self.assertNotEqual(new_token, old_token)

        cancel = self.client_for(self.admin).post(
            reverse(
                "management_platform_staff_invitation_cancel",
                kwargs={"invitation_id": invitation.id},
            ),
            {},
            format="json",
        )
        self.assertEqual(cancel.status_code, status.HTTP_200_OK)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, PlatformStaffInvitation.Status.CANCELLED)
        self.assertEqual(invitation.cancelled_by, self.admin)

        cancelled_link = self.client_for(None).get(
            reverse(
                "platform_staff_invitation_detail",
                kwargs={"token": new_token},
            )
        )
        self.assertEqual(cancelled_link.status_code, status.HTTP_404_NOT_FOUND)

    def test_platform_admin_can_revoke_safety_moderator_role_and_audit_it(self):
        response = self.client_for(self.admin).delete(
            reverse(
                "management_platform_staff_detail",
                kwargs={"user_id": self.moderator.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moderator.profile.refresh_from_db()
        self.assertEqual(self.moderator.profile.role, UserProfile.Role.USER)

        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.PLATFORM_SAFETY_MODERATOR_REVOKED,
            resource_id=str(self.moderator.id),
        )
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.capability, MANAGE_PLATFORM_STAFF)
        self.assertEqual(
            event.previous_state,
            {"platform_role": "PLATFORM_SAFETY_MODERATOR"},
        )
        self.assertEqual(event.new_state, {"platform_role": "COMMUNITY_USER"})

    def test_safety_moderator_cannot_manage_platform_staff_or_invitations(self):
        client = self.client_for(self.moderator)

        list_response = client.get(reverse("management_platform_staff"))
        invitation_list_response = client.get(
            reverse("management_platform_staff_invitations")
        )
        invitation_create_response = client.post(
            reverse("management_platform_staff_invitations"),
            {"email": "blocked@example.com"},
            format="json",
        )
        revoke_response = client.delete(
            reverse(
                "management_platform_staff_detail",
                kwargs={"user_id": self.moderator.id},
            )
        )

        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            invitation_list_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            invitation_create_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(revoke_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invitation_governance_action_is_visible_in_governance_audit(self):
        _response, invitation, _token = self.create_invitation("audit@example.com")

        response = self.client_for(self.admin).get(
            reverse("management_governance_audit"),
            {"action_type": "PLATFORM_STAFF_INVITATION_CREATED"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        event = response.data["results"][0]
        self.assertEqual(event["resource"]["type"], "PLATFORM_STAFF_INVITATION")
        self.assertEqual(event["resource"]["id"], str(invitation.id))
