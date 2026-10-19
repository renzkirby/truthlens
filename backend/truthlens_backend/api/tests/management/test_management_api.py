import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    AccountabilityEvent,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from api.management_governance_service import MANAGE_PARTNER_ORGANIZATION
from api.organization_invitation_service import (
    OrganizationInvitationDeliveryError,
    hash_invitation_token,
)
from api.organization_provisioning_service import PROVISION_PARTNER_ORGANIZATION


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@truthlens.test",
)
class ManagementApiTests(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="platform-admin",
            email="platform-admin@example.com",
            password="test-password",
        )
        self.staff_user = User.objects.create_user(
            username="staff-user",
            email="staff@example.com",
            password="test-password",
            is_staff=True,
        )
        self.ordinary_user = User.objects.create_user(
            username="ordinary-user",
            email="ordinary@example.com",
            password="test-password",
        )
        self.owner = User.objects.create_user(
            username="primary-admin",
            email="primary-admin@example.com",
            password="test-password",
        )
        self.organization_admin = User.objects.create_user(
            username="organization-admin",
            email="organization-admin@example.com",
            password="test-password",
        )
        self.inviter = User.objects.create_user(
            username="inviter",
            email="inviter@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Verified Newsroom",
            slug="verified-newsroom",
            description="A governance-safe organization description.",
            website="https://newsroom.example.com",
            logo_url="https://newsroom.example.com/logo.png",
            expertise_areas=["elections", "health"],
            public_profile_enabled=True,
            public_logo_enabled=True,
            organization_type=Organization.OrganizationType.NEWS,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.pending_organization = Organization.objects.create(
            name="Pending Research Group",
            slug="pending-research-group",
            organization_type=Organization.OrganizationType.RESEARCH,
            verification_status=Organization.VerificationStatus.PENDING,
            partner_status=Organization.PartnerStatus.SUSPENDED,
        )
        self.owner_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=timezone.now(),
            approved_by=self.superuser,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
            approved_at=timezone.now(),
            approved_by=self.owner,
        )
        self.raw_token = "management-api-raw-invitation-token"
        self.invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email="researcher@example.com",
            invited_role=OrganizationMembership.Role.RESEARCHER,
            purpose=OrganizationInvitation.InvitationPurpose.MEMBERSHIP,
            invited_by=self.inviter,
            token_digest=hash_invitation_token(self.raw_token),
            status=OrganizationInvitation.Status.PENDING,
            expires_at=timezone.now() + timedelta(days=7),
            last_sent_at=timezone.now(),
        )
        self.pending_primary_admin_invitation = (
            OrganizationInvitation.objects.create(
                organization=self.pending_organization,
                email="pending-primary@example.com",
                invited_role=OrganizationMembership.Role.OWNER,
                purpose=(
                    OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
                ),
                invited_by=self.superuser,
                token_digest="b" * 64,
                status=OrganizationInvitation.Status.PENDING,
                expires_at=timezone.now() + timedelta(days=7),
                last_sent_at=timezone.now(),
                send_count=2,
            )
        )

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def management_urls(self):
        return (
            reverse("management_overview"),
            reverse("management_organizations"),
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.organization.id},
            ),
            reverse("management_memberships"),
            reverse(
                "management_membership_detail",
                kwargs={"membership_id": self.owner_membership.id},
            ),
            reverse("management_invitations"),
            reverse(
                "management_invitation_detail",
                kwargs={"invitation_id": self.invitation.id},
            ),
        )

    def assert_all_management_endpoints(self, user, expected_status):
        client = self.client_for(user)
        for url in self.management_urls():
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, expected_status)

    def assert_all_management_write_endpoints(self, user, expected_status):
        client = self.client_for(user)
        requests = (
            (
                "post",
                reverse("management_organizations"),
                {
                    "name": "Unauthorized Organization",
                    "slug": "unauthorized-organization",
                    "organization_type": Organization.OrganizationType.OTHER,
                },
            ),
            (
                "patch",
                reverse(
                    "management_organization_platform_trust",
                    kwargs={"organization_id": self.organization.id},
                ),
                {"partner_status": Organization.PartnerStatus.SUSPENDED},
            ),
            (
                "post",
                reverse(
                    "management_primary_admin_provision",
                    kwargs={"organization_id": self.pending_organization.id},
                ),
                {"email": "unauthorized-primary@example.com"},
            ),
            (
                "post",
                reverse(
                    "management_primary_admin_resend",
                    kwargs={"organization_id": self.pending_organization.id},
                ),
                {},
            ),
            (
                "post",
                reverse(
                    "management_primary_admin_cancel",
                    kwargs={"organization_id": self.pending_organization.id},
                ),
                {},
            ),
        )
        for method, url, payload in requests:
            with self.subTest(method=method, url=url):
                response = getattr(client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, expected_status)

    def test_active_superuser_can_access_all_management_apis(self):
        self.assert_all_management_endpoints(self.superuser, status.HTTP_200_OK)

    def test_staff_non_superuser_is_forbidden(self):
        self.assert_all_management_endpoints(
            self.staff_user,
            status.HTTP_403_FORBIDDEN,
        )

    def test_ordinary_authenticated_user_is_forbidden(self):
        self.assert_all_management_endpoints(
            self.ordinary_user,
            status.HTTP_403_FORBIDDEN,
        )

    def test_organization_owner_is_forbidden(self):
        self.assert_all_management_endpoints(
            self.owner,
            status.HTTP_403_FORBIDDEN,
        )

    def test_organization_admin_is_forbidden(self):
        self.assert_all_management_endpoints(
            self.organization_admin,
            status.HTTP_403_FORBIDDEN,
        )

    def test_anonymous_user_is_rejected(self):
        self.assert_all_management_endpoints(None, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_superuser_is_forbidden(self):
        inactive_superuser = User.objects.create_superuser(
            username="inactive-platform-admin",
            email="inactive@example.com",
            password="test-password",
            is_active=False,
        )
        self.assert_all_management_endpoints(
            inactive_superuser,
            status.HTTP_403_FORBIDDEN,
        )

    def test_every_management_write_rejects_non_platform_authority(self):
        inactive_superuser = User.objects.create_superuser(
            username="inactive-write-admin",
            email="inactive-write@example.com",
            password="test-password",
            is_active=False,
        )
        for user, expected_status in (
            (None, status.HTTP_401_UNAUTHORIZED),
            (self.staff_user, status.HTTP_403_FORBIDDEN),
            (self.ordinary_user, status.HTTP_403_FORBIDDEN),
            (self.owner, status.HTTP_403_FORBIDDEN),
            (self.organization_admin, status.HTTP_403_FORBIDDEN),
            (inactive_superuser, status.HTTP_403_FORBIDDEN),
        ):
            with self.subTest(user=getattr(user, "username", "anonymous")):
                self.assert_all_management_write_endpoints(user, expected_status)

    def test_overview_counts_are_explicit_and_correct(self):
        response = self.client_for(self.superuser).get(
            reverse("management_overview")
        )

        self.assertEqual(
            response.data,
            {
                "organizations": {
                    "total": 2,
                    "active_partners": 1,
                    "pending_verification": 1,
                    "suspended_partners": 1,
                }
            },
        )

    def test_organization_list_returns_only_governance_fields(self):
        response = self.client_for(self.superuser).get(
            reverse("management_organizations")
        )

        self.assertEqual(response.data["count"], 2)
        item = next(
            row
            for row in response.data["results"]
            if row["id"] == str(self.organization.id)
        )
        self.assertEqual(
            set(item),
            {
                "id",
                "name",
                "slug",
                "organization_type",
                "organization_type_label",
                "verification_status",
                "verification_status_label",
                "partner_status",
                "partner_status_label",
                "public_profile_enabled",
                "updated_at",
            },
        )

    def test_organization_detail_returns_current_primary_admin(self):
        response = self.client_for(self.superuser).get(
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.organization.id},
            )
        )

        primary_admin = response.data["primary_admin"]
        self.assertEqual(primary_admin["state"], "CURRENT")
        self.assertEqual(primary_admin["membership"]["role"], "OWNER")
        self.assertEqual(
            primary_admin["membership"]["role_label"],
            "Primary Admin",
        )
        self.assertIsNone(primary_admin["invitation"])

    def test_organization_detail_returns_safe_pending_primary_admin(self):
        response = self.client_for(self.superuser).get(
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.pending_organization.id},
            )
        )

        primary_admin = response.data["primary_admin"]
        self.assertEqual(primary_admin["state"], "PENDING")
        self.assertIsNone(primary_admin["membership"])
        self.assertEqual(
            primary_admin["invitation"]["role_label"],
            "Primary Admin",
        )
        self.assertNotIn("token_digest", primary_admin["invitation"])

    def test_membership_owner_role_label_is_primary_admin(self):
        response = self.client_for(self.superuser).get(
            reverse(
                "management_membership_detail",
                kwargs={"membership_id": self.owner_membership.id},
            )
        )

        self.assertEqual(response.data["role"], "OWNER")
        self.assertEqual(response.data["role_label"], "Primary Admin")

    def test_membership_list_and_detail_are_read_only(self):
        client = self.client_for(self.superuser)
        self.assertEqual(
            client.post(reverse("management_memberships"), {}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_organization_detail_remains_read_only(self):
        client = self.client_for(self.superuser)
        self.assertEqual(
            client.patch(
                reverse(
                    "management_organization_detail",
                    kwargs={"organization_id": self.organization.id},
                ),
                {"partner_status": Organization.PartnerStatus.SUSPENDED},
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.patch(
                reverse(
                    "management_membership_detail",
                    kwargs={"membership_id": self.owner_membership.id},
                ),
                {"status": OrganizationMembership.Status.SUSPENDED},
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_invitation_list_and_detail_are_read_only(self):
        client = self.client_for(self.superuser)
        self.assertEqual(
            client.post(reverse("management_invitations"), {}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.patch(
                reverse(
                    "management_invitation_detail",
                    kwargs={"invitation_id": self.invitation.id},
                ),
                {"status": OrganizationInvitation.Status.CANCELLED},
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_invitation_responses_never_expose_tokens_or_digests(self):
        client = self.client_for(self.superuser)
        for url in (
            reverse("management_invitations"),
            reverse(
                "management_invitation_detail",
                kwargs={"invitation_id": self.invitation.id},
            ),
        ):
            with self.subTest(url=url):
                payload = json.dumps(client.get(url).data)
                self.assertNotIn("token_digest", payload)
                self.assertNotIn(self.invitation.token_digest, payload)
                self.assertNotIn(self.raw_token, payload)

    def test_search_and_filters_do_not_bypass_authority(self):
        query = "?q=Verified&partner_status=ACTIVE"
        for user in (self.staff_user, self.ordinary_user, self.owner):
            with self.subTest(user=user.username):
                response = self.client_for(user).get(
                    reverse("management_organizations") + query
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_organization_search_and_filters_return_matching_records(self):
        response = self.client_for(self.superuser).get(
            reverse("management_organizations")
            + "?q=newsroom&verification_status=VERIFIED"
            + "&partner_status=ACTIVE&organization_type=NEWS"
            + "&public_profile_enabled=true"
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.organization.id))

    def test_membership_and_invitation_filters_return_matching_records(self):
        client = self.client_for(self.superuser)
        memberships = client.get(
            reverse("management_memberships")
            + f"?q=primary&organization_id={self.organization.id}"
            + "&role=OWNER&status=ACTIVE"
        )
        invitations = client.get(
            reverse("management_invitations")
            + f"?q=researcher&organization_id={self.organization.id}"
            + "&status=PENDING&purpose=MEMBERSHIP&invited_role=RESEARCHER"
        )

        self.assertEqual(memberships.data["count"], 1)
        self.assertEqual(invitations.data["count"], 1)

    def test_auth_me_management_access_is_true_for_active_superuser(self):
        response = self.client_for(self.superuser).get(reverse("auth_me"))

        self.assertEqual(
            response.data["management_console"],
            {"can_access": True},
        )

    def test_auth_me_management_access_is_false_for_ordinary_user(self):
        response = self.client_for(self.ordinary_user).get(reverse("auth_me"))

        self.assertEqual(
            response.data["management_console"],
            {"can_access": False},
        )

    def test_auth_me_workspace_context_remains_separate(self):
        response = self.client_for(self.owner).get(reverse("auth_me"))

        self.assertIn("workspace", response.data)
        self.assertTrue(response.data["workspace"]["can_access"])
        self.assertFalse(response.data["management_console"]["can_access"])

    def test_authorized_organization_creation_is_safe_and_audited(self):
        response = self.client_for(self.superuser).post(
            reverse("management_organizations"),
            {
                "name": "Independent Verification Lab",
                "slug": "independent-verification-lab",
                "organization_type": Organization.OrganizationType.RESEARCH,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        organization = Organization.objects.get(pk=response.data["id"])
        self.assertEqual(
            organization.verification_status,
            Organization.VerificationStatus.UNVERIFIED,
        )
        self.assertEqual(organization.partner_status, Organization.PartnerStatus.NONE)
        self.assertFalse(organization.public_profile_enabled)
        self.assertFalse(organization.public_logo_enabled)
        self.assertFalse(organization.memberships.exists())
        self.assertEqual(response.data["primary_admin"]["state"], "NONE")
        self.assertNotIn("token_digest", json.dumps(response.data))

        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_CREATED,
            resource_id=str(organization.pk),
        )
        self.assertEqual(event.authority_scope, AccountabilityEvent.AuthorityScope.PLATFORM)
        self.assertEqual(event.actor, self.superuser)
        self.assertEqual(event.subject_organization, organization)
        self.assertEqual(event.capability, MANAGE_PARTNER_ORGANIZATION)

    def test_organization_creation_rejects_unknown_fields_and_invalid_choices(self):
        base_payload = {
            "name": "Strict Organization",
            "slug": "strict-organization",
            "organization_type": Organization.OrganizationType.OTHER,
        }
        for override, expected_field in (
            ({"description": "Platform-controlled text"}, "description"),
            ({"public_profile_enabled": True}, "public_profile_enabled"),
            ({"owner": 123}, "owner"),
            ({"organization_type": "INVALID"}, "organization_type"),
            ({"verification_status": "INVALID"}, "verification_status"),
            ({"partner_status": "INVALID"}, "partner_status"),
            ({"verification_status": Organization.VerificationStatus.UNVERIFIED}, "verification_status"),
            ({"verification_status": Organization.VerificationStatus.PENDING}, "verification_status"),
            ({"verification_status": Organization.VerificationStatus.VERIFIED}, "verification_status"),
            ({"partner_status": Organization.PartnerStatus.NONE}, "partner_status"),
            ({"partner_status": Organization.PartnerStatus.ACTIVE}, "partner_status"),
            ({"partner_status": Organization.PartnerStatus.SUSPENDED}, "partner_status"),
            ({"partner_status": Organization.PartnerStatus.FORMER}, "partner_status"),
        ):
            with self.subTest(field=expected_field):
                response = self.client_for(self.superuser).post(
                    reverse("management_organizations"),
                    {**base_payload, **override},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(expected_field, response.data)

    def test_organization_creation_rejects_duplicate_slug_and_name_safely(self):
        for payload, field in (
            (
                {
                    "name": "Unique Name",
                    "slug": self.organization.slug,
                    "organization_type": Organization.OrganizationType.OTHER,
                },
                "slug",
            ),
            (
                {
                    "name": "vErIfIeD nEwSrOoM",
                    "slug": "unique-slug",
                    "organization_type": Organization.OrganizationType.OTHER,
                },
                "name",
            ),
        ):
            with self.subTest(field=field):
                response = self.client_for(self.superuser).post(
                    reverse("management_organizations"),
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                self.assertIn(field, response.data)

    def test_platform_trust_partial_and_combined_updates_are_audited(self):
        url = reverse(
            "management_organization_platform_trust",
            kwargs={"organization_id": self.pending_organization.id},
        )
        client = self.client_for(self.superuser)

        verification_response = client.patch(
            url,
            {"verification_status": Organization.VerificationStatus.VERIFIED},
            format="json",
        )
        partner_response = client.patch(
            url,
            {"partner_status": Organization.PartnerStatus.ACTIVE},
            format="json",
        )
        combined_response = client.patch(
            url,
            {
                "verification_status": Organization.VerificationStatus.REJECTED,
                "partner_status": Organization.PartnerStatus.FORMER,
            },
            format="json",
        )

        self.assertEqual(verification_response.status_code, status.HTTP_200_OK)
        self.assertEqual(partner_response.status_code, status.HTTP_200_OK)
        self.assertEqual(combined_response.status_code, status.HTTP_200_OK)
        self.pending_organization.refresh_from_db()
        self.assertEqual(
            self.pending_organization.verification_status,
            Organization.VerificationStatus.REJECTED,
        )
        self.assertEqual(
            self.pending_organization.partner_status,
            Organization.PartnerStatus.FORMER,
        )
        events = AccountabilityEvent.objects.filter(
            action_type=(
                AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
            ),
            subject_organization=self.pending_organization,
        ).order_by("created_at")
        self.assertEqual(events.count(), 3)
        self.assertEqual(
            events.last().previous_state,
            {
                "verification_status": Organization.VerificationStatus.VERIFIED,
                "partner_status": Organization.PartnerStatus.ACTIVE,
            },
        )
        self.assertEqual(
            events.last().new_state,
            {
                "verification_status": Organization.VerificationStatus.REJECTED,
                "partner_status": Organization.PartnerStatus.FORMER,
            },
        )
        self.assertEqual(events.last().actor, self.superuser)
        self.assertEqual(events.last().capability, MANAGE_PARTNER_ORGANIZATION)

    def test_platform_trust_rejects_unsupported_empty_and_invalid_payloads(self):
        url = reverse(
            "management_organization_platform_trust",
            kwargs={"organization_id": self.organization.id},
        )
        original_name = self.organization.name
        original_event_count = AccountabilityEvent.objects.count()
        for payload, expected_field in (
            ({"name": "Changed by platform"}, "name"),
            ({"description": "Changed by platform"}, "description"),
            ({}, "non_field_errors"),
            ({"verification_status": "INVALID"}, "verification_status"),
            ({"partner_status": "INVALID"}, "partner_status"),
        ):
            with self.subTest(field=expected_field):
                response = self.client_for(self.superuser).patch(
                    url,
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(expected_field, response.data)

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, original_name)
        self.assertEqual(AccountabilityEvent.objects.count(), original_event_count)

    def test_platform_trust_no_op_does_not_create_event(self):
        response = self.client_for(self.superuser).patch(
            reverse(
                "management_organization_platform_trust",
                kwargs={"organization_id": self.organization.id},
            ),
            {
                "verification_status": self.organization.verification_status,
                "partner_status": self.organization.partner_status,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            AccountabilityEvent.objects.filter(
                action_type=(
                    AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
                )
            ).exists()
        )

    def test_primary_admin_provision_returns_safe_pending_invitation(self):
        organization = Organization.objects.create(
            name="Provision Through Management",
            slug="provision-through-management",
        )
        response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_provision",
                kwargs={"organization_id": organization.id},
            ),
            {"email": "new.primary@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            set(response.data),
            {"id", "email", "role_label", "status", "last_sent_at", "expires_at", "send_count"},
        )
        invitation = OrganizationInvitation.objects.get(pk=response.data["id"])
        self.assertEqual(
            invitation.purpose,
            OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING,
        )
        self.assertEqual(invitation.invited_role, OrganizationMembership.Role.OWNER)
        self.assertEqual(response.data["role_label"], "Primary Admin")
        self.assertNotIn("token", json.dumps(response.data).lower())
        events = AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
            resource_id=str(invitation.pk),
        )
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().capability, PROVISION_PARTNER_ORGANIZATION)

    def test_primary_admin_provision_rejects_unknown_fields_and_conflicts(self):
        unknown_response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_provision",
                kwargs={"organization_id": self.pending_organization.id},
            ),
            {"email": "new@example.com", "password": "not-permitted"},
            format="json",
        )
        current_response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_provision",
                kwargs={"organization_id": self.organization.id},
            ),
            {"email": "new@example.com"},
            format="json",
        )
        pending_response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_provision",
                kwargs={"organization_id": self.pending_organization.id},
            ),
            {"email": "new@example.com"},
            format="json",
        )

        self.assertEqual(unknown_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", unknown_response.data)
        self.assertEqual(current_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(pending_response.status_code, status.HTTP_409_CONFLICT)

    def test_primary_admin_delivery_failure_rolls_back_invitation_and_audit(self):
        organization = Organization.objects.create(
            name="Delivery Failure Partner",
            slug="delivery-failure-partner",
        )
        with patch(
            "api.organization_provisioning_service.send_organization_invitation_email",
            side_effect=OrganizationInvitationDeliveryError("email unavailable"),
        ):
            response = self.client_for(self.superuser).post(
                reverse(
                    "management_primary_admin_provision",
                    kwargs={"organization_id": organization.id},
                ),
                {"email": "delivery@example.com"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(organization.invitations.exists())
        self.assertFalse(
            AccountabilityEvent.objects.filter(subject_organization=organization).exists()
        )

    def test_pending_primary_admin_invitation_can_be_resent_safely(self):
        original_digest = self.pending_primary_admin_invitation.token_digest
        response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_resend",
                kwargs={"organization_id": self.pending_organization.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_primary_admin_invitation.refresh_from_db()
        self.assertNotEqual(
            self.pending_primary_admin_invitation.token_digest,
            original_digest,
        )
        self.assertEqual(self.pending_primary_admin_invitation.send_count, 3)
        self.assertNotIn("token", json.dumps(response.data).lower())
        events = AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_RESENT,
            resource_id=str(self.pending_primary_admin_invitation.pk),
        )
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().capability, PROVISION_PARTNER_ORGANIZATION)

    def test_primary_admin_resend_rejects_current_missing_and_expired_states(self):
        current_response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_resend",
                kwargs={"organization_id": self.organization.id},
            ),
            {},
            format="json",
        )
        no_invitation_organization = Organization.objects.create(
            name="No Invitation Partner",
            slug="no-invitation-partner",
        )
        missing_response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_resend",
                kwargs={"organization_id": no_invitation_organization.id},
            ),
            {},
            format="json",
        )
        self.pending_primary_admin_invitation.expires_at = timezone.now() - timedelta(seconds=1)
        self.pending_primary_admin_invitation.save(update_fields=["expires_at"])
        expired_response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_resend",
                kwargs={"organization_id": self.pending_organization.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(current_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(missing_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(expired_response.status_code, status.HTTP_409_CONFLICT)

    def test_pending_primary_admin_invitation_can_be_cancelled_safely(self):
        original_digest = self.pending_primary_admin_invitation.token_digest
        response = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_cancel",
                kwargs={"organization_id": self.pending_organization.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data),
            {
                "id",
                "email",
                "role_label",
                "status",
                "last_sent_at",
                "expires_at",
                "send_count",
            },
        )
        serialized = json.dumps(response.data).lower()
        self.assertNotIn("token", serialized)
        self.assertNotIn("token_digest", serialized)
        self.assertNotIn("raw_token", serialized)

        self.pending_primary_admin_invitation.refresh_from_db()
        self.assertEqual(
            self.pending_primary_admin_invitation.status,
            OrganizationInvitation.Status.CANCELLED,
        )
        self.assertNotEqual(
            self.pending_primary_admin_invitation.token_digest,
            original_digest,
        )
        detail = self.client_for(self.superuser).get(
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.pending_organization.id},
            )
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["primary_admin"]["state"], "NONE")

        events = AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED,
            resource_id=str(self.pending_primary_admin_invitation.pk),
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            capability=PROVISION_PARTNER_ORGANIZATION,
        )
        self.assertEqual(events.count(), 1)

        replacement = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_provision",
                kwargs={"organization_id": self.pending_organization.id},
            ),
            {"email": "replacement-primary@example.com"},
            format="json",
        )
        self.assertEqual(replacement.status_code, status.HTTP_201_CREATED)

    def test_primary_admin_cancel_rejects_unsupported_and_inactive_states(self):
        cancel_url = reverse(
            "management_primary_admin_cancel",
            kwargs={"organization_id": self.pending_organization.id},
        )
        unknown = self.client_for(self.superuser).post(
            cancel_url,
            {"email": "not-accepted@example.com"},
            format="json",
        )
        self.assertEqual(unknown.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", unknown.data)

        no_invitation_organization = Organization.objects.create(
            name="No Cancellation Invitation",
            slug="no-cancellation-invitation",
        )
        missing = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_cancel",
                kwargs={"organization_id": no_invitation_organization.id},
            ),
            {},
            format="json",
        )
        current = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_cancel",
                kwargs={"organization_id": self.organization.id},
            ),
            {},
            format="json",
        )

        invalid_organization = Organization.objects.create(
            name="Invalid Cancellation Invitation",
            slug="invalid-cancellation-invitation",
        )
        OrganizationInvitation.objects.create(
            organization=invalid_organization,
            email="ordinary-cancellation@example.com",
            invited_role=OrganizationMembership.Role.RESEARCHER,
            purpose=OrganizationInvitation.InvitationPurpose.MEMBERSHIP,
            invited_by=self.superuser,
            token_digest="c" * 64,
            status=OrganizationInvitation.Status.PENDING,
            expires_at=timezone.now() + timedelta(days=1),
            last_sent_at=timezone.now(),
        )
        wrong_purpose = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_cancel",
                kwargs={"organization_id": invalid_organization.id},
            ),
            {},
            format="json",
        )

        self.pending_primary_admin_invitation.expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.pending_primary_admin_invitation.save(update_fields=["expires_at"])
        expired = self.client_for(self.superuser).post(
            cancel_url,
            {},
            format="json",
        )

        self.assertEqual(missing.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(current.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(wrong_purpose.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(expired.status_code, status.HTTP_409_CONFLICT)

        not_found = self.client_for(self.superuser).post(
            reverse(
                "management_primary_admin_cancel",
                kwargs={"organization_id": uuid4()},
            ),
            {},
            format="json",
        )
        self.assertEqual(not_found.status_code, status.HTTP_404_NOT_FOUND)
