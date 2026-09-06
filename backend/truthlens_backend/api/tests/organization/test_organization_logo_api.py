from io import BytesIO
import os
from unittest.mock import patch
import uuid

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import (
    APIClient,
    APITestCase,
)

from api.models import (
    Organization,
    OrganizationMembership,
)
from api.organization_logo_service import OrganizationLogoStorageError


SUPABASE_URL = "https://truthlens-api-test.supabase.co"


class FakeOrganizationLogoStorage:
    def __init__(self):
        self.uploads = []
        self.deletions = []
        self.fail_upload = False

    def upload(
        self,
        *,
        object_path,
        content,
    ):
        if self.fail_upload:
            raise OrganizationLogoStorageError("Organization logo storage failed.")

        self.uploads.append(object_path)
        return (
            f"{SUPABASE_URL}/storage/v1/object/public/"
            f"organization-logos/{object_path}"
        )

    def delete(
        self,
        *,
        object_path,
    ):
        self.deletions.append(object_path)


def make_logo_file():
    output = BytesIO()
    Image.new("RGBA", (64, 48), (20, 80, 180, 128)).save(
        output,
        format="PNG",
    )
    return SimpleUploadedFile(
        "organization-logo.png",
        output.getvalue(),
        content_type="image/png",
    )


@override_settings(SUPABASE_ORGANIZATION_LOGOS_BUCKET="organization-logos")
class OrganizationLogoApiTests(APITestCase):
    response_fields = {
        "id",
        "name",
        "slug",
        "organization_type",
        "organization_type_label",
        "verification_status",
        "partner_status",
        "description",
        "website",
        "logo_url",
        "expertise_areas",
        "public_profile_enabled",
        "public_logo_enabled",
        "publicly_visible",
    }

    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "SUPABASE_URL": SUPABASE_URL,
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

        self.organization = Organization.objects.create(
            name="Logo API Partner",
            slug="logo-api-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            public_profile_enabled=True,
        )
        self.other_organization = Organization.objects.create(
            name="Other Logo API Partner",
            slug="other-logo-api-partner",
        )
        self.owner = self.create_member(
            "owner",
            OrganizationMembership.Role.OWNER,
        )
        self.admin = self.create_member(
            "admin",
            OrganizationMembership.Role.ADMIN,
        )
        self.lead = self.create_member(
            "lead",
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self.suspended_owner = self.create_member(
            "suspended-owner",
            OrganizationMembership.Role.OWNER,
            status_value=OrganizationMembership.Status.SUSPENDED,
        )
        self.other_owner = self.create_member(
            "other-owner",
            OrganizationMembership.Role.OWNER,
            organization=self.other_organization,
        )
        self.url = reverse(
            "organization_public_profile_logo",
            kwargs={
                "organization_id": self.organization.id,
            },
        )
        self.public_url = reverse(
            "public_partner_detail",
            kwargs={
                "slug": self.organization.slug,
            },
        )
        self.storage = FakeOrganizationLogoStorage()

    def create_member(
        self,
        username,
        role,
        *,
        status_value=OrganizationMembership.Status.ACTIVE,
        organization=None,
    ):
        user = User.objects.create_user(
            username=f"logo-api-{username}",
            email=f"logo-api-{username}@example.com",
        )
        OrganizationMembership.objects.create(
            organization=organization or self.organization,
            user=user,
            role=role,
            status=status_value,
        )
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def upload_as(
        self,
        actor,
        *,
        uploaded_file=None,
    ):
        with patch(
            "api.organization_logo_service.get_organization_logo_storage",
            return_value=self.storage,
        ):
            return self.client_for(actor).post(
                self.url,
                {
                    "logo": uploaded_file or make_logo_file(),
                },
                format="multipart",
            )

    def test_owner_and_admin_can_upload_multipart_logo(self):
        for actor in [
            self.owner,
            self.admin,
        ]:
            with self.subTest(actor=actor.username):
                response = self.upload_as(actor)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(set(response.data), self.response_fields)
                self.assertTrue(response.data["logo_url"])

    def test_unauthenticated_upload_is_rejected(self):
        response = APIClient().post(
            self.url,
            {
                "logo": make_logo_file(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthorized_and_cross_organization_users_are_rejected(self):
        for actor in [
            self.lead,
            self.suspended_owner,
            self.other_owner,
        ]:
            with self.subTest(actor=actor.username):
                response = self.upload_as(actor)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_organization_returns_not_found(self):
        url = reverse(
            "organization_public_profile_logo",
            kwargs={
                "organization_id": uuid.uuid4(),
            },
        )
        response = self.client_for(self.owner).post(
            url,
            {
                "logo": make_logo_file(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_image_and_oversized_upload_are_rejected(self):
        invalid_files = [
            SimpleUploadedFile(
                "corrupt.png",
                b"not-an-image",
                content_type="image/png",
            ),
            SimpleUploadedFile(
                "oversized.png",
                b"x" * ((2 * 1024 * 1024) + 1),
                content_type="image/png",
            ),
        ]

        for uploaded_file in invalid_files:
            with self.subTest(filename=uploaded_file.name):
                response = self.upload_as(
                    self.owner,
                    uploaded_file=uploaded_file,
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_storage_failure_is_controlled(self):
        self.storage.fail_upload = True

        response = self.upload_as(self.owner)

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def test_upload_preserves_consent_flags_and_public_logo_rule(self):
        response = self.upload_as(self.owner)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["public_logo_enabled"])
        self.assertIsNone(APIClient().get(self.public_url).data["logo_url"])

        self.organization.public_logo_enabled = True
        self.organization.save(update_fields=["public_logo_enabled"])
        response = self.upload_as(self.owner)

        public_response = APIClient().get(self.public_url)
        self.assertEqual(
            public_response.data["logo_url"],
            response.data["logo_url"],
        )

    def test_delete_clears_logo_and_preserves_logo_consent(self):
        response = self.upload_as(self.owner)
        self.organization.public_logo_enabled = True
        self.organization.save(update_fields=["public_logo_enabled"])

        with patch(
            "api.organization_logo_service.get_organization_logo_storage",
            return_value=self.storage,
        ):
            response = self.client_for(self.owner).delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["logo_url"])
        self.assertTrue(response.data["public_logo_enabled"])
        self.assertIsNone(APIClient().get(self.public_url).data["logo_url"])

    def test_delete_uses_the_same_authorization_boundary(self):
        self.organization.logo_url = "https://external.example/logo.png"
        self.organization.save(update_fields=["logo_url"])

        self.assertEqual(
            APIClient().delete(self.url).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        for actor in [
            self.lead,
            self.suspended_owner,
            self.other_owner,
        ]:
            with self.subTest(actor=actor.username):
                response = self.client_for(actor).delete(self.url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.organization.refresh_from_db()
        self.assertEqual(
            self.organization.logo_url,
            "https://external.example/logo.png",
        )

    def test_only_post_and_delete_are_allowed(self):
        client = self.client_for(self.owner)

        for method in [
            "get",
            "patch",
            "put",
        ]:
            with self.subTest(method=method):
                response = getattr(client, method)(self.url)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_405_METHOD_NOT_ALLOWED,
                )
