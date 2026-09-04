from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
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
)


@override_settings(
    EMAIL_BACKEND=("django.core.mail.backends." "locmem.EmailBackend"),
    DEFAULT_FROM_EMAIL=("noreply@truthlens.test"),
)
class OrganizationInvitationApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="test-password",
        )

        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )

        self.lead = User.objects.create_user(
            username="lead",
            email="lead@example.com",
            password="test-password",
        )

        self.other_owner = User.objects.create_user(
            username="other-owner",
            email="other-owner@example.com",
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name="Invitation Partner",
            slug="invitation-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.other_organization = Organization.objects.create(
            name="Other Invitation Partner",
            slug="other-invitation-partner",
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

        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.other_owner,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.list_url = reverse(
            "organization_invitations",
            kwargs={
                "organization_id": (self.organization.id),
            },
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
        email="invitee@example.com",
        role=None,
    ):
        if role is None:
            role = OrganizationMembership.Role.RESEARCHER

        invitation, _raw_token = create_organization_invitation(
            organization=self.organization,
            email=email,
            invited_role=role,
            actor=self.owner,
        )

        return invitation

    def test_owner_can_create_invitation(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.list_url,
            {
                "email": (" New.Person@Example.COM "),
                "invited_role": (OrganizationMembership.Role.RESEARCHER),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        invitation = OrganizationInvitation.objects.get(
            organization=self.organization,
            email="new.person@example.com",
        )

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.PENDING,
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

        self.assertNotIn(
            "token_digest",
            response.data,
        )

    def test_admin_cannot_invite_admin(
        self,
    ):
        response = self.client_for(
            self.admin,
        ).post(
            self.list_url,
            {
                "email": "new-admin@example.com",
                "invited_role": (OrganizationMembership.Role.ADMIN),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_factual_role_cannot_manage_invitations(
        self,
    ):
        response = self.client_for(
            self.lead,
        ).get(
            self.list_url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_other_organization_owner_cannot_manage_invitations(
        self,
    ):
        response = self.client_for(
            self.other_owner,
        ).get(
            self.list_url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_duplicate_pending_invitation_returns_conflict(
        self,
    ):
        self.create_invitation(
            email="duplicate@example.com",
        )

        response = self.client_for(
            self.owner,
        ).post(
            self.list_url,
            {
                "email": "duplicate@example.com",
                "invited_role": (OrganizationMembership.Role.RESEARCHER),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

    def test_listing_materializes_expired_invitation(
        self,
    ):
        invitation = self.create_invitation(
            email="expired@example.com",
        )

        invitation.expires_at = timezone.now() - timedelta(minutes=1)

        invitation.save(
            update_fields=[
                "expires_at",
            ]
        )

        response = self.client_for(
            self.owner,
        ).get(
            self.list_url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.EXPIRED,
        )

        self.assertEqual(
            response.data["summary"]["expired"],
            1,
        )

    def test_listing_never_exposes_token_digest(
        self,
    ):
        self.create_invitation()

        response = self.client_for(
            self.owner,
        ).get(
            self.list_url,
        )

        invitation = response.data["results"][0]

        self.assertNotIn(
            "token_digest",
            invitation,
        )

    def test_owner_can_resend_pending_invitation(
        self,
    ):
        invitation = self.create_invitation()

        old_digest = invitation.token_digest

        mail.outbox.clear()

        url = reverse(
            "organization_invitation_resend",
            kwargs={
                "organization_id": (self.organization.id),
                "invitation_id": (invitation.id),
            },
        )

        response = self.client_for(
            self.owner,
        ).post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        invitation.refresh_from_db()

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

    def test_owner_can_cancel_pending_invitation(
        self,
    ):
        invitation = self.create_invitation()

        old_digest = invitation.token_digest

        url = reverse(
            "organization_invitation_cancel",
            kwargs={
                "organization_id": (self.organization.id),
                "invitation_id": (invitation.id),
            },
        )

        response = self.client_for(
            self.owner,
        ).post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            OrganizationInvitation.Status.CANCELLED,
        )

        self.assertEqual(
            invitation.cancelled_by,
            self.owner,
        )

        self.assertNotEqual(
            invitation.token_digest,
            old_digest,
        )

    def test_cancelled_invitation_cannot_be_cancelled_again(
        self,
    ):
        invitation = self.create_invitation()

        url = reverse(
            "organization_invitation_cancel",
            kwargs={
                "organization_id": (self.organization.id),
                "invitation_id": (invitation.id),
            },
        )

        client = self.client_for(
            self.owner,
        )

        first = client.post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            first.status_code,
            status.HTTP_200_OK,
        )

        second = client.post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            second.status_code,
            status.HTTP_409_CONFLICT,
        )

    def test_invitation_id_is_scoped_to_route_organization(
        self,
    ):
        invitation, _ = create_organization_invitation(
            organization=(self.other_organization),
            email="other@example.com",
            invited_role=(OrganizationMembership.Role.RESEARCHER),
            actor=self.other_owner,
        )

        url = reverse(
            "organization_invitation_resend",
            kwargs={
                "organization_id": (self.organization.id),
                "invitation_id": (invitation.id),
            },
        )

        response = self.client_for(
            self.owner,
        ).post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    @patch(
        "api.organization_invitation_service." "EmailMultiAlternatives.send",
        side_effect=Exception("SMTP unavailable"),
    )
    def test_delivery_failure_returns_503_and_rolls_back_creation(
        self,
        _mock_send,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.list_url,
            {
                "email": "failed@example.com",
                "invited_role": (OrganizationMembership.Role.RESEARCHER),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

        self.assertFalse(
            OrganizationInvitation.objects.filter(
                organization=self.organization,
                email="failed@example.com",
            ).exists()
        )

    def test_invitation_administration_requires_authentication(
        self,
    ):
        response = APIClient().get(
            self.list_url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
