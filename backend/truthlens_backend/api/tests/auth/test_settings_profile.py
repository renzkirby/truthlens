import base64
from io import BytesIO
from unittest.mock import ANY, patch

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.profile_avatar_service import ProfileAvatarStorageError


PROFILE_UPDATE_URL = "/api/auth/profile/update/"
CURRENT_USER_URL = "/api/auth/me/"


def build_avatar_data_url(*, image_format="PNG", declared_content_type=None):
    output = BytesIO()
    Image.new("RGB", (2, 2), color="navy").save(output, format=image_format)
    content_types = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
    }
    content_type = declared_content_type or content_types[image_format]
    return (
        f"data:{content_type};base64,"
        f"{base64.b64encode(output.getvalue()).decode()}"
    )


class ProfileUpdateApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="current-user",
            email="current@example.com",
            password="pass1234",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_profile_update_requires_authentication(self):
        response = APIClient().patch(
            PROFILE_UPDATE_URL,
            {"bio": "Updated bio"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_update_changes_supported_fields_and_allows_current_username(self):
        response = self.client.patch(
            PROFILE_UPDATE_URL,
            {
                "username": self.user.username,
                "bio": "Evidence matters.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.username, "current-user")
        self.assertEqual(self.user.profile.bio, "Evidence matters.")
        self.assertEqual(response.json()["username"], "current-user")

    def test_profile_update_rejects_email_mutation_instead_of_ignoring_it(self):
        response = self.client.patch(
            PROFILE_UPDATE_URL,
            {"email": "changed@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["email"],
            ["Email cannot be changed through profile updates."],
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "current@example.com")

    def test_profile_update_rejects_unknown_fields(self):
        response = self.client.patch(
            PROFILE_UPDATE_URL,
            {"is_staff": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["is_staff"],
            ["This profile field is not supported."],
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_profile_update_rejects_case_insensitive_duplicate_username(self):
        User.objects.create_user(
            username="ExistingName",
            email="other@example.com",
            password="pass1234",
        )

        response = self.client.patch(
            PROFILE_UPDATE_URL,
            {"username": "existingname"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["username"], ["This username is already taken."])
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "current-user")

    def test_profile_update_rejects_blank_and_invalid_usernames(self):
        invalid_usernames = ["   ", "contains spaces"]

        for username in invalid_usernames:
            with self.subTest(username=username):
                response = self.client.patch(
                    PROFILE_UPDATE_URL,
                    {"username": username},
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("username", response.json())

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "current-user")

    @patch("api.views.upload_profile_avatar")
    def test_profile_update_keeps_user_profile_bio_and_avatar_flow(self, upload_avatar):
        upload_avatar.return_value = "https://example.com/avatar.png"
        avatar_data_url = build_avatar_data_url()

        response = self.client.patch(
            PROFILE_UPDATE_URL,
            {
                "bio": "Updated from the profile editor.",
                "avatar_base64": avatar_data_url,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        upload_avatar.assert_called_once_with(
            user_id=self.user.pk,
            avatar=ANY,
        )
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.bio, "Updated from the profile editor.")
        self.assertEqual(self.user.profile.avatar_url, "https://example.com/avatar.png")

    @patch("api.views.upload_profile_avatar")
    def test_profile_update_rejects_invalid_avatar_payloads_before_upload(self, upload_avatar):
        oversized_bytes = b"\x89PNG\r\n\x1a\n" + (b"a" * (2 * 1024 * 1024))
        cases = [
            "not-a-data-url",
            "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
            "data:image/png;base64,not-valid-base64!",
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\nnot a decodable png").decode(),
            build_avatar_data_url(
                image_format="PNG",
                declared_content_type="image/jpeg",
            ),
            "data:image/png;base64," + base64.b64encode(oversized_bytes).decode(),
        ]

        for avatar_payload in cases:
            with self.subTest(payload_prefix=avatar_payload[:40]):
                response = self.client.patch(
                    PROFILE_UPDATE_URL,
                    {"avatar_base64": avatar_payload},
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("avatar_base64", response.json())

        upload_avatar.assert_not_called()

    @patch("api.views.upload_profile_avatar")
    def test_invalid_avatar_does_not_partially_update_username(self, upload_avatar):
        response = self.client.patch(
            PROFILE_UPDATE_URL,
            {
                "username": "changed-name",
                "avatar_base64": "data:image/png;base64,bm90IGEgcG5n",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        upload_avatar.assert_not_called()
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "current-user")

    @patch("api.views.upload_profile_avatar")
    def test_avatar_storage_failure_does_not_partially_update_profile(self, upload_avatar):
        self.user.profile.bio = "Original bio"
        self.user.profile.save(update_fields=["bio"])
        upload_avatar.side_effect = ProfileAvatarStorageError(
            "Unable to store the profile avatar."
        )

        response = self.client.patch(
            PROFILE_UPDATE_URL,
            {
                "username": "changed-name",
                "bio": "Changed bio",
                "avatar_base64": build_avatar_data_url(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.json()["avatar_base64"],
            ["Unable to store the avatar image right now."],
        )
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.username, "current-user")
        self.assertEqual(self.user.profile.bio, "Original bio")
        self.assertIsNone(self.user.profile.avatar_url)


class CurrentUserAuthMethodTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="method-user",
            email="method@example.com",
            password="pass1234",
        )
        self.client.force_authenticate(user=self.user)

    def test_current_user_projects_password_and_social_sign_in_methods(self):
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-method-user",
        )

        response = self.client.get(CURRENT_USER_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["auth_methods"], ["password", "google"])

    def test_current_user_omits_password_when_password_is_unusable(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-only-user",
        )

        response = self.client.get(CURRENT_USER_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["auth_methods"], ["google"])
