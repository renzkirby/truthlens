from django.contrib.auth.models import User
from django.urls import reverse

from rest_framework import status
from rest_framework.test import (
    APIClient,
    APITestCase,
)

from api.models import (
    Organization,
    OrganizationMembership,
)


class OrganizationMembershipManagementApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="membership-api-owner",
            email="owner@example.com",
            password="test-password",
        )

        self.admin = User.objects.create_user(
            username="membership-api-admin",
            email="admin@example.com",
            password="test-password",
        )

        self.lead = User.objects.create_user(
            username="membership-api-lead",
            email="lead@example.com",
            password="test-password",
        )

        self.researcher = User.objects.create_user(
            username="membership-api-researcher",
            email="researcher@example.com",
            password="test-password",
        )

        self.contributor = User.objects.create_user(
            username="membership-api-contributor",
            email="contributor@example.com",
            password="test-password",
        )

        self.other_owner = User.objects.create_user(
            username="membership-api-other-owner",
            email="other-owner@example.com",
            password="test-password",
        )

        self.other_member = User.objects.create_user(
            username="membership-api-other-member",
            email="other-member@example.com",
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name="Membership API Partner",
            slug="membership-api-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.other_organization = Organization.objects.create(
            name="Other Membership API Partner",
            slug="other-membership-api-partner",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.owner_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_by=self.owner,
        )

        self.admin_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=(OrganizationMembership.Role.ADMIN),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_by=self.owner,
        )

        self.lead_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_by=self.owner,
        )

        self.researcher_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.researcher,
            role=(OrganizationMembership.Role.RESEARCHER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_by=self.owner,
        )

        self.contributor_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.contributor,
            role=(OrganizationMembership.Role.CONTRIBUTOR),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_by=self.owner,
        )

        self.other_owner_membership = OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.other_owner,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_by=self.other_owner,
        )

        self.other_member_membership = OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.other_member,
            role=(OrganizationMembership.Role.RESEARCHER),
            status=(OrganizationMembership.Status.ACTIVE),
            approved_by=self.other_owner,
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

    def role_url(
        self,
        membership=None,
        organization=None,
    ):
        membership = membership or self.researcher_membership

        organization = organization or self.organization

        return reverse(
            "organization_membership_role_update",
            kwargs={
                "organization_id": organization.id,
                "membership_id": membership.id,
            },
        )

    def suspend_url(
        self,
        membership=None,
        organization=None,
    ):
        membership = membership or self.researcher_membership

        organization = organization or self.organization

        return reverse(
            "organization_membership_suspend",
            kwargs={
                "organization_id": organization.id,
                "membership_id": membership.id,
            },
        )

    def restore_url(
        self,
        membership=None,
        organization=None,
    ):
        membership = membership or self.researcher_membership

        organization = organization or self.organization

        return reverse(
            "organization_membership_restore",
            kwargs={
                "organization_id": organization.id,
                "membership_id": membership.id,
            },
        )

    def remove_url(
        self,
        membership=None,
        organization=None,
    ):
        membership = membership or self.researcher_membership

        organization = organization or self.organization

        return reverse(
            "organization_membership_remove",
            kwargs={
                "organization_id": organization.id,
                "membership_id": membership.id,
            },
        )

    # ─────────────────────────────────────────────
    # Authentication
    # ─────────────────────────────────────────────

    def test_role_change_requires_authentication(
        self,
    ):
        response = APIClient().patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.MODERATOR),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_suspend_requires_authentication(
        self,
    ):
        response = APIClient().post(
            self.suspend_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_restore_requires_authentication(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        response = APIClient().post(
            self.restore_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_remove_requires_authentication(
        self,
    ):
        response = APIClient().post(
            self.remove_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    # ─────────────────────────────────────────────
    # Owner operations
    # ─────────────────────────────────────────────

    def test_owner_can_change_researcher_to_admin(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.ADMIN),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.role,
            OrganizationMembership.Role.ADMIN,
        )

        self.assertEqual(
            response.data["role"],
            OrganizationMembership.Role.ADMIN,
        )

    def test_owner_can_suspend_admin(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.suspend_url(
                self.admin_membership,
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.admin_membership.refresh_from_db()

        self.assertEqual(
            self.admin_membership.status,
            (OrganizationMembership.Status.SUSPENDED),
        )

        self.assertEqual(
            response.data["status"],
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

        response = self.client_for(
            self.owner,
        ).post(
            self.restore_url(
                self.admin_membership,
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.admin_membership.refresh_from_db()

        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_owner_can_remove_admin(
        self,
    ):
        membership_id = self.admin_membership.id

        response = self.client_for(
            self.owner,
        ).post(
            self.remove_url(
                self.admin_membership,
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.admin_membership.refresh_from_db()

        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.LEFT,
        )

        self.assertEqual(
            response.data["status"],
            OrganizationMembership.Status.LEFT,
        )

        self.assertTrue(
            OrganizationMembership.objects.filter(
                id=membership_id,
            ).exists()
        )

    # ─────────────────────────────────────────────
    # Admin operations
    # ─────────────────────────────────────────────

    def test_admin_can_change_researcher_to_moderator(
        self,
    ):
        response = self.client_for(
            self.admin,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.MODERATOR),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.role,
            (OrganizationMembership.Role.MODERATOR),
        )

    def test_admin_can_suspend_researcher(
        self,
    ):
        response = self.client_for(
            self.admin,
        ).post(
            self.suspend_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
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

        response = self.client_for(
            self.admin,
        ).post(
            self.restore_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_admin_can_remove_researcher(
        self,
    ):
        response = self.client_for(
            self.admin,
        ).post(
            self.remove_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.LEFT,
        )

    # ─────────────────────────────────────────────
    # Hierarchy restrictions
    # ─────────────────────────────────────────────

    def test_admin_cannot_manage_admin(
        self,
    ):
        response = self.client_for(
            self.admin,
        ).post(
            self.suspend_url(
                self.admin_membership,
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.admin_membership.refresh_from_db()

        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_admin_cannot_assign_admin_role(
        self,
    ):
        response = self.client_for(
            self.admin,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.ADMIN),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.role,
            (OrganizationMembership.Role.RESEARCHER),
        )

    def test_admin_cannot_assign_owner_role(
        self,
    ):
        response = self.client_for(
            self.admin,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.OWNER),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_owner_cannot_assign_owner_role(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.OWNER),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_owner_cannot_suspend_owner(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.suspend_url(
                self.owner_membership,
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.owner_membership.refresh_from_db()

        self.assertEqual(
            self.owner_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_owner_cannot_remove_owner(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.remove_url(
                self.owner_membership,
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.owner_membership.refresh_from_db()

        self.assertEqual(
            self.owner_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    # ─────────────────────────────────────────────
    # Invalid state transitions
    # ─────────────────────────────────────────────

    def test_suspend_already_suspended_member_returns_conflict(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        response = self.client_for(
            self.owner,
        ).post(
            self.suspend_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

    def test_restore_active_member_returns_conflict(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.restore_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

    def test_same_role_change_returns_conflict(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.RESEARCHER),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

    def test_left_membership_role_change_returns_conflict(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.LEFT

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.CONTRIBUTOR),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

    # ─────────────────────────────────────────────
    # Payload validation
    # ─────────────────────────────────────────────

    def test_role_change_requires_role(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "role",
            response.data,
        )

    def test_invalid_role_returns_bad_request(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {
                "role": "SUPER_ADMIN",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_blank_role_returns_bad_request(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {
                "role": "",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    # ─────────────────────────────────────────────
    # Organization isolation
    # ─────────────────────────────────────────────

    def test_other_organization_owner_cannot_manage_member(
        self,
    ):
        response = self.client_for(
            self.other_owner,
        ).post(
            self.suspend_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.researcher_membership.refresh_from_db()

        self.assertEqual(
            self.researcher_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_authorized_owner_gets_not_found_for_member_from_other_organization(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.suspend_url(
                membership=(self.other_member_membership),
                organization=self.organization,
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.other_member_membership.refresh_from_db()

        self.assertEqual(
            self.other_member_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )

    def test_factual_role_cannot_manage_membership(
        self,
    ):
        response = self.client_for(
            self.lead,
        ).post(
            self.suspend_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # ─────────────────────────────────────────────
    # API response shape / privacy
    # ─────────────────────────────────────────────

    def test_role_update_returns_membership_serializer(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.MODERATOR),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            str(response.data["id"]),
            str(self.researcher_membership.id),
        )

        self.assertEqual(
            response.data["role"],
            OrganizationMembership.Role.MODERATOR,
        )

        self.assertEqual(
            response.data["status"],
            OrganizationMembership.Status.ACTIVE,
        )

        self.assertIn(
            "user",
            response.data,
        )

        self.assertEqual(
            response.data["user"]["username"],
            self.researcher.username,
        )

        self.assertEqual(
            response.data["user"]["email"],
            self.researcher.email,
        )

    def test_membership_response_does_not_expose_reputation_or_workspace(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.MODERATOR),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertNotIn(
            "trust_score",
            response.data,
        )

        self.assertNotIn(
            "workspace",
            response.data,
        )

        self.assertNotIn(
            "trust_score",
            response.data["user"],
        )

        self.assertNotIn(
            "workspace",
            response.data["user"],
        )

    def test_suspend_returns_updated_membership(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.suspend_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["status"],
            (OrganizationMembership.Status.SUSPENDED),
        )

    def test_restore_returns_updated_membership(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        response = self.client_for(
            self.owner,
        ).post(
            self.restore_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["status"],
            OrganizationMembership.Status.ACTIVE,
        )

    def test_remove_returns_left_membership(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.remove_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["status"],
            OrganizationMembership.Status.LEFT,
        )

        self.assertEqual(
            str(response.data["id"]),
            str(self.researcher_membership.id),
        )

    # ─────────────────────────────────────────────
    # HTTP method restrictions
    # ─────────────────────────────────────────────

    def test_role_endpoint_rejects_post(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).post(
            self.role_url(),
            {
                "role": (OrganizationMembership.Role.MODERATOR),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_suspend_endpoint_rejects_patch(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).patch(
            self.suspend_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_restore_endpoint_rejects_patch(
        self,
    ):
        self.researcher_membership.status = OrganizationMembership.Status.SUSPENDED

        self.researcher_membership.save(
            update_fields=[
                "status",
            ]
        )

        response = self.client_for(
            self.owner,
        ).patch(
            self.restore_url(),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_remove_endpoint_rejects_delete(
        self,
    ):
        response = self.client_for(
            self.owner,
        ).delete(
            self.remove_url(),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
