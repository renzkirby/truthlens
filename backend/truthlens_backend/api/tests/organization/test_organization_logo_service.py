from io import BytesIO
import os
from unittest.mock import patch
import uuid

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import (
    TestCase,
    override_settings,
)
from PIL import Image

from api.models import (
    Organization,
    OrganizationMembership,
)
from api.organization_logo_service import (
    MAX_LOGO_UPLOAD_BYTES,
    OrganizationLogoStorageError,
    OrganizationLogoValidationError,
    normalize_organization_logo,
    remove_organization_logo,
    upload_organization_logo,
)
from api.organization_public_profile_service import (
    OrganizationPublicProfileAuthorizationError,
)
from api.organization_service import get_membership_capabilities


SUPABASE_URL = "https://truthlens-test.supabase.co"


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
            raise OrganizationLogoStorageError("Storage unavailable.")

        self.uploads.append(
            {
                "object_path": object_path,
                "content": content,
            }
        )
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


def make_logo_file(
    *,
    image_format="PNG",
    size=(80, 60),
    filename=None,
):
    output = BytesIO()
    mode = "RGBA" if image_format == "PNG" else "RGB"
    color = (20, 90, 180, 128) if mode == "RGBA" else (20, 90, 180)
    image = Image.new(
        mode,
        size,
        color,
    )
    image.save(
        output,
        format=image_format,
    )
    content_type = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }.get(
        image_format,
        "application/octet-stream",
    )

    return SimpleUploadedFile(
        filename or f"human-supplied-name.{image_format.lower()}",
        output.getvalue(),
        content_type=content_type,
    )


@override_settings(SUPABASE_ORGANIZATION_LOGOS_BUCKET="organization-logos")
class OrganizationLogoServiceTests(TestCase):
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
            name="Managed Logo Partner",
            slug="managed-logo-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.other_organization = Organization.objects.create(
            name="Other Managed Logo Partner",
            slug="other-managed-logo-partner",
        )
        self.storage = FakeOrganizationLogoStorage()

        self.members = {}

        for role in OrganizationMembership.Role.values:
            self.members[role] = self.create_member(
                role.lower(),
                role,
            )

        self.suspended_owner = self.create_member(
            "suspended-owner",
            OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.SUSPENDED,
        )
        self.left_admin = self.create_member(
            "left-admin",
            OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.LEFT,
        )
        self.other_owner = self.create_member(
            "other-owner",
            OrganizationMembership.Role.OWNER,
            organization=self.other_organization,
        )

    def create_member(
        self,
        username,
        role,
        *,
        status=OrganizationMembership.Status.ACTIVE,
        organization=None,
    ):
        user = User.objects.create_user(
            username=f"logo-{username}",
            email=f"logo-{username}@example.com",
        )
        OrganizationMembership.objects.create(
            organization=organization or self.organization,
            user=user,
            role=role,
            status=status,
        )
        return user

    def upload_as(
        self,
        actor,
        *,
        uploaded_file=None,
    ):
        return upload_organization_logo(
            organization=self.organization,
            actor=actor,
            uploaded_file=uploaded_file or make_logo_file(),
            storage=self.storage,
        )

    def test_owner_upload_uses_generated_scoped_png_and_persists_url(self):
        updated = self.upload_as(
            self.members[OrganizationMembership.Role.OWNER],
            uploaded_file=make_logo_file(
                filename="do-not-use-this-name.png",
                size=(2048, 1024),
            ),
        )

        upload = self.storage.uploads[0]
        prefix = f"organizations/{self.organization.id}/"

        self.assertTrue(upload["object_path"].startswith(prefix))
        self.assertTrue(upload["object_path"].endswith(".png"))
        self.assertNotIn("do-not-use-this-name", upload["object_path"])
        uuid.UUID(upload["object_path"].removeprefix(prefix).removesuffix(".png"))

        with Image.open(BytesIO(upload["content"])) as normalized:
            self.assertEqual(normalized.format, "PNG")
            self.assertEqual(normalized.size, (1024, 512))
            self.assertEqual(normalized.mode, "RGBA")

        self.organization.refresh_from_db()
        self.assertEqual(updated.logo_url, self.organization.logo_url)
        self.assertEqual(
            self.organization.logo_url,
            (
                f"{SUPABASE_URL}/storage/v1/object/public/"
                f"organization-logos/{upload['object_path']}"
            ),
        )

    def test_admin_can_upload_logo(self):
        updated = self.upload_as(
            self.members[OrganizationMembership.Role.ADMIN],
        )

        self.assertTrue(updated.logo_url)

    def test_non_management_roles_cannot_upload(self):
        for role in [
            OrganizationMembership.Role.LEAD_VERIFIER,
            OrganizationMembership.Role.MODERATOR,
            OrganizationMembership.Role.RESEARCHER,
            OrganizationMembership.Role.CONTRIBUTOR,
        ]:
            with self.subTest(role=role):
                with self.assertRaises(
                    OrganizationPublicProfileAuthorizationError
                ):
                    self.upload_as(self.members[role])

        self.assertEqual(self.storage.uploads, [])

    def test_inactive_and_cross_organization_managers_cannot_upload(self):
        for actor in [
            self.suspended_owner,
            self.left_admin,
            self.other_owner,
        ]:
            with self.subTest(actor=actor.username):
                with self.assertRaises(
                    OrganizationPublicProfileAuthorizationError
                ):
                    self.upload_as(actor)

        self.assertEqual(self.storage.uploads, [])

    def test_png_jpeg_and_webp_are_accepted_and_normalized_to_png(self):
        for image_format in [
            "PNG",
            "JPEG",
            "WEBP",
        ]:
            with self.subTest(image_format=image_format):
                normalized = normalize_organization_logo(
                    make_logo_file(image_format=image_format)
                )

                with Image.open(BytesIO(normalized.content)) as image:
                    self.assertEqual(image.format, "PNG")

    def test_gif_svg_and_corrupt_payloads_are_rejected(self):
        gif_output = BytesIO()
        Image.new("RGB", (20, 20), "red").save(
            gif_output,
            format="GIF",
        )
        invalid_files = [
            SimpleUploadedFile(
                "logo.gif",
                gif_output.getvalue(),
                content_type="image/gif",
            ),
            SimpleUploadedFile(
                "logo.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
                content_type="image/svg+xml",
            ),
            SimpleUploadedFile(
                "logo.png",
                b"not-an-image",
                content_type="image/png",
            ),
        ]

        for uploaded_file in invalid_files:
            with self.subTest(filename=uploaded_file.name):
                with self.assertRaises(OrganizationLogoValidationError):
                    normalize_organization_logo(uploaded_file)

    def test_oversized_file_and_dimensions_are_rejected(self):
        oversized_file = SimpleUploadedFile(
            "large.png",
            b"x" * (MAX_LOGO_UPLOAD_BYTES + 1),
            content_type="image/png",
        )

        with self.assertRaises(OrganizationLogoValidationError):
            normalize_organization_logo(oversized_file)

        with self.assertRaises(OrganizationLogoValidationError):
            normalize_organization_logo(
                make_logo_file(size=(4097, 1))
            )

    def test_animated_webp_is_rejected_when_supported(self):
        output = BytesIO()
        frames = [
            Image.new("RGB", (20, 20), "red"),
            Image.new("RGB", (20, 20), "blue"),
        ]
        try:
            frames[0].save(
                output,
                format="WEBP",
                save_all=True,
                append_images=frames[1:],
                duration=100,
                loop=0,
            )
        except OSError:
            self.skipTest("Pillow cannot encode animated WebP in this environment.")

        with self.assertRaises(OrganizationLogoValidationError):
            normalize_organization_logo(
                SimpleUploadedFile(
                    "animated.webp",
                    output.getvalue(),
                    content_type="image/webp",
                )
            )

    def test_upload_does_not_change_consent_status_or_memberships(self):
        memberships_before = list(
            OrganizationMembership.objects.filter(
                organization=self.organization,
            )
            .order_by("id")
            .values_list(
                "id",
                "role",
                "status",
            )
        )
        lead_membership = OrganizationMembership.objects.get(
            organization=self.organization,
            user=self.members[OrganizationMembership.Role.LEAD_VERIFIER],
        )
        capabilities_before = get_membership_capabilities(lead_membership)

        self.upload_as(self.members[OrganizationMembership.Role.OWNER])

        self.organization.refresh_from_db()
        self.assertFalse(self.organization.public_profile_enabled)
        self.assertFalse(self.organization.public_logo_enabled)
        self.assertEqual(
            self.organization.verification_status,
            Organization.VerificationStatus.VERIFIED,
        )
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )
        self.assertEqual(
            list(
                OrganizationMembership.objects.filter(
                    organization=self.organization,
                )
                .order_by("id")
                .values_list(
                    "id",
                    "role",
                    "status",
                )
            ),
            memberships_before,
        )
        lead_membership.refresh_from_db()
        self.assertEqual(
            get_membership_capabilities(lead_membership),
            capabilities_before,
        )

    def test_replacement_cleans_managed_logo_but_not_external_url(self):
        old_object_path = (
            f"organizations/{self.organization.id}/{uuid.uuid4()}.png"
        )
        self.organization.logo_url = (
            f"{SUPABASE_URL}/storage/v1/object/public/"
            f"organization-logos/{old_object_path}"
        )
        self.organization.save(update_fields=["logo_url"])

        self.upload_as(self.members[OrganizationMembership.Role.OWNER])

        self.assertEqual(self.storage.deletions, [old_object_path])

        self.storage.deletions.clear()
        self.organization.logo_url = "https://external.example/logo.png"
        self.organization.save(update_fields=["logo_url"])

        self.upload_as(self.members[OrganizationMembership.Role.OWNER])

        self.assertEqual(self.storage.deletions, [])

    def test_new_object_cleanup_is_attempted_when_database_update_fails(self):
        with patch.object(
            Organization,
            "save",
            side_effect=DatabaseError("database unavailable"),
        ):
            with self.assertRaises(DatabaseError):
                self.upload_as(self.members[OrganizationMembership.Role.OWNER])

        self.assertEqual(
            self.storage.deletions,
            [self.storage.uploads[0]["object_path"]],
        )

    def test_remove_clears_logo_without_changing_consent(self):
        old_object_path = (
            f"organizations/{self.organization.id}/{uuid.uuid4()}.png"
        )
        self.organization.logo_url = (
            f"{SUPABASE_URL}/storage/v1/object/public/"
            f"organization-logos/{old_object_path}"
        )
        self.organization.public_logo_enabled = True
        self.organization.save(
            update_fields=[
                "logo_url",
                "public_logo_enabled",
            ]
        )

        remove_organization_logo(
            organization=self.organization,
            actor=self.members[OrganizationMembership.Role.OWNER],
            storage=self.storage,
        )

        self.organization.refresh_from_db()
        self.assertIsNone(self.organization.logo_url)
        self.assertTrue(self.organization.public_logo_enabled)
        self.assertEqual(self.storage.deletions, [old_object_path])

    def test_remove_external_logo_does_not_attempt_storage_deletion(self):
        self.organization.logo_url = "https://external.example/logo.png"
        self.organization.save(update_fields=["logo_url"])

        remove_organization_logo(
            organization=self.organization,
            actor=self.members[OrganizationMembership.Role.ADMIN],
            storage=self.storage,
        )

        self.organization.refresh_from_db()
        self.assertIsNone(self.organization.logo_url)
        self.assertEqual(self.storage.deletions, [])
