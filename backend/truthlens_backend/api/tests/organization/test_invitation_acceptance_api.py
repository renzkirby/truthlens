from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import (
    APIClient,
    APITestCase,
)

from api.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)

from api.organization_invitation_service import (
    create_organization_invitation,
    resend_organization_invitation,
    cancel_organization_invitation,
)


class OrganizationInvitationAcceptanceApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="invitation-owner",
            email="owner@example.com",
            password="test-password",
        )

        self.recipient = User.objects.create_user(
            username="invitation-recipient",
            email="recipient@example.com",
            password="test-password",
        )

        self.wrong_user = User.objects.create_user(
            username="wrong-recipient",
            email="wrong@example.com",
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name="Recipient Partner",
            slug="recipient-partner",
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

    def client_for(
        self,
        user,
    ):
        client = APIClient()

        client.force_authenticate(
            user=user,
        )

        return client

    def create_invitation(
        self,
        *,
        email=None,
        role=None,
    ):
        if email is None:
            email = self.recipient.email

        if role is None:
            role = OrganizationMembership.Role.RESEARCHER

        return create_organization_invitation(
            organization=self.organization,
            email=email,
            invited_role=role,
            actor=self.owner,
        )

    def test_invitation_preview_is_public(
        self,
    ):
        invitation, raw_token = self.create_invitation()

        url = reverse(
            "organization_invitation_detail",
            kwargs={
                "token": raw_token,
            },
        )

        response = APIClient().get(
            url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["organization"]["id"],
            str(self.organization.id),
        )

        self.assertEqual(
            response.data["organization"]["name"],
            self.organization.name,
        )

        self.assertEqual(
            response.data["invited_role"],
            OrganizationMembership.Role.RESEARCHER,
        )

        self.assertEqual(
            response.data["status"],
            OrganizationInvitation.Status.PENDING,
        )

    def test_public_preview_does_not_expose_private_invitation_data(
        self,
    ):
        _invitation, raw_token = self.create_invitation()

        url = reverse(
            "organization_invitation_detail",
            kwargs={
                "token": raw_token,
            },
        )

        response = APIClient().get(
            url,
        )

        forbidden_fields = {
            "email",
            "token_digest",
            "send_count",
            "last_sent_at",
            "accepted_by",
            "accepted_at",
            "cancelled_by",
            "cancelled_at",
        }

        self.assertTrue(forbidden_fields.isdisjoint(response.data.keys()))

        self.assertNotIn(
            "account_exists",
            response.data,
        )

        self.assertNotIn(
            "is_registered",
            response.data,
        )

    def test_invalid_invitation_preview_returns_404(
        self,
    ):
        url = reverse(
            "organization_invitation_detail",
            kwargs={
                "token": "invalid-token",
            },
        )

        response = APIClient().get(
            url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_expired_invitation_preview_returns_expired_state(
        self,
    ):
        invitation, raw_token = self.create_invitation()

        invitation.expires_at = timezone.now() - timedelta(minutes=1)

        invitation.save(
            update_fields=[
                "expires_at",
            ]
        )

        url = reverse(
            "organization_invitation_detail",
            kwargs={
                "token": raw_token,
            },
        )

        response = APIClient().get(
            url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["status"],
            OrganizationInvitation.Status.EXPIRED,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.EXPIRED,
        )

    def test_acceptance_requires_authentication(
        self,
    ):
        _invitation, raw_token = self.create_invitation()

        url = reverse(
            "organization_invitation_accept",
            kwargs={
                "token": raw_token,
            },
        )

        response = APIClient().post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_correct_recipient_can_accept_invitation(
        self,
    ):
        invitation, raw_token = self.create_invitation()

        url = reverse(
            "organization_invitation_accept",
            kwargs={
                "token": raw_token,
            },
        )

        response = self.client_for(
            self.recipient,
        ).post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        membership = OrganizationMembership.objects.get(
            organization=self.organization,
            user=self.recipient,
        )

        self.assertEqual(
            membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

        self.assertEqual(
            membership.role,
            OrganizationMembership.Role.RESEARCHER,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.ACCEPTED,
        )

        self.assertEqual(
            response.data["membership"]["status"],
            OrganizationMembership.Status.ACTIVE,
        )

    def test_wrong_account_cannot_accept_invitation(
        self,
    ):
        invitation, raw_token = self.create_invitation()

        url = reverse(
            "organization_invitation_accept",
            kwargs={
                "token": raw_token,
            },
        )

        response = self.client_for(
            self.wrong_user,
        ).post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertFalse(
            OrganizationMembership.objects.filter(
                organization=self.organization,
                user=self.wrong_user,
            ).exists()
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.PENDING,
        )

    def test_expired_invitation_cannot_be_accepted(
        self,
    ):
        invitation, raw_token = self.create_invitation()

        invitation.expires_at = timezone.now() - timedelta(seconds=1)

        invitation.save(
            update_fields=[
                "expires_at",
            ]
        )

        url = reverse(
            "organization_invitation_accept",
            kwargs={
                "token": raw_token,
            },
        )

        response = self.client_for(
            self.recipient,
        ).post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.EXPIRED,
        )

        self.assertFalse(
            OrganizationMembership.objects.filter(
                organization=self.organization,
                user=self.recipient,
            ).exists()
        )

    def test_accepted_invitation_url_becomes_invalid(
        self,
    ):
        _invitation, raw_token = self.create_invitation()

        accept_url = reverse(
            "organization_invitation_accept",
            kwargs={
                "token": raw_token,
            },
        )

        client = self.client_for(
            self.recipient,
        )

        first = client.post(
            accept_url,
            {},
            format="json",
        )

        self.assertEqual(
            first.status_code,
            status.HTTP_200_OK,
        )

        second = client.post(
            accept_url,
            {},
            format="json",
        )

        self.assertEqual(
            second.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        preview_url = reverse(
            "organization_invitation_detail",
            kwargs={
                "token": raw_token,
            },
        )

        preview = APIClient().get(
            preview_url,
        )

        self.assertEqual(
            preview.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_resend_invalidates_previous_preview_url(
        self,
    ):
        invitation, raw_token = self.create_invitation()

        resend_organization_invitation(
            invitation=invitation,
            actor=self.owner,
        )

        old_url = reverse(
            "organization_invitation_detail",
            kwargs={
                "token": raw_token,
            },
        )

        response = APIClient().get(
            old_url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_cancelled_invitation_url_no_longer_resolves(
        self,
    ):
        invitation, raw_token = self.create_invitation()

        cancel_organization_invitation(
            invitation=invitation,
            actor=self.owner,
        )

        url = reverse(
            "organization_invitation_detail",
            kwargs={
                "token": raw_token,
            },
        )

        response = APIClient().get(
            url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_left_member_can_accept_new_invitation(
        self,
    ):
        membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.recipient,
            role=(OrganizationMembership.Role.CONTRIBUTOR),
            status=(OrganizationMembership.Status.LEFT),
        )

        membership_id = membership.id

        _invitation, raw_token = self.create_invitation(
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
        )

        url = reverse(
            "organization_invitation_accept",
            kwargs={
                "token": raw_token,
            },
        )

        response = self.client_for(
            self.recipient,
        ).post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        membership.refresh_from_db()

        self.assertEqual(
            membership.id,
            membership_id,
        )

        self.assertEqual(
            membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

        self.assertEqual(
            membership.role,
            OrganizationMembership.Role.LEAD_VERIFIER,
        )

    def test_acceptance_response_does_not_expose_secrets(
        self,
    ):
        _invitation, raw_token = self.create_invitation()

        url = reverse(
            "organization_invitation_accept",
            kwargs={
                "token": raw_token,
            },
        )

        response = self.client_for(
            self.recipient,
        ).post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        invitation_data = response.data["invitation"]

        self.assertNotIn(
            "token_digest",
            invitation_data,
        )

        self.assertNotIn(
            "email",
            invitation_data,
        )
