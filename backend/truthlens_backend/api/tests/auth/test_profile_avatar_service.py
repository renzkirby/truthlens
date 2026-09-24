import base64
from io import BytesIO

from django.test import SimpleTestCase
from PIL import Image

from api.profile_avatar_service import (
    MAX_PROFILE_AVATAR_BYTES,
    ProfileAvatarStorageError,
    ProfileAvatarValidationError,
    upload_profile_avatar,
    validate_profile_avatar_data_url,
)


def image_data_url(image_format, *, declared_content_type=None):
    output = BytesIO()
    Image.new("RGB", (3, 2), color="navy").save(output, format=image_format)
    content_types = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
    }
    content_type = declared_content_type or content_types[image_format]
    return (
        f"data:{content_type};base64," f"{base64.b64encode(output.getvalue()).decode()}"
    )


class RecordingAvatarStorage:
    def __init__(self, public_url="https://example.com/avatar"):
        self.public_url = public_url
        self.uploaded = None

    def upload(self, *, object_path, content, content_type):
        self.uploaded = {
            "object_path": object_path,
            "content": content,
            "content_type": content_type,
        }
        return self.public_url


class FailingAvatarStorage:
    def upload(self, **kwargs):
        raise RuntimeError("provider unavailable")


class ProfileAvatarServiceTests(SimpleTestCase):
    def test_supported_images_are_normalized_to_png_before_storage(self):
        cases = ["JPEG", "PNG", "GIF"]

        for image_format in cases:
            with self.subTest(image_format=image_format):
                avatar = validate_profile_avatar_data_url(image_data_url(image_format))

                self.assertEqual(avatar.content_type, "image/png")
                self.assertEqual(avatar.extension, "png")

                storage = RecordingAvatarStorage(
                    public_url="https://example.com/avatar.png"
                )

                public_url = upload_profile_avatar(
                    user_id=17,
                    avatar=avatar,
                    storage=storage,
                )

                self.assertEqual(
                    public_url,
                    "https://example.com/avatar.png",
                )
                self.assertTrue(
                    storage.uploaded["object_path"].startswith("profile-avatars/17/")
                )
                self.assertTrue(storage.uploaded["object_path"].endswith(".png"))
                self.assertEqual(
                    storage.uploaded["content_type"],
                    "image/png",
                )
                self.assertEqual(
                    storage.uploaded["content"],
                    avatar.content,
                )

                with Image.open(BytesIO(storage.uploaded["content"])) as decoded:
                    decoded.load()
                    self.assertEqual(decoded.format, "PNG")
                    self.assertLessEqual(decoded.width, 1024)
                    self.assertLessEqual(decoded.height, 1024)

    def test_large_valid_image_is_reduced_to_avatar_dimension_limit(self):
        output = BytesIO()
        Image.new(
            "RGB",
            (2000, 1500),
            color="navy",
        ).save(
            output,
            format="JPEG",
        )

        payload = (
            "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()
        )

        avatar = validate_profile_avatar_data_url(payload)

        self.assertEqual(avatar.content_type, "image/png")
        self.assertEqual(avatar.extension, "png")

        with Image.open(BytesIO(avatar.content)) as decoded:
            decoded.load()
            self.assertEqual(decoded.format, "PNG")
            self.assertLessEqual(decoded.width, 1024)
            self.assertLessEqual(decoded.height, 1024)

    def test_jpeg_metadata_is_not_preserved_in_normalized_avatar(self):
        output = BytesIO()

        image = Image.new(
            "RGB",
            (8, 8),
            color="navy",
        )
        exif = Image.Exif()
        exif[0x010E] = "private metadata"

        image.save(
            output,
            format="JPEG",
            exif=exif,
        )

        payload = (
            "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()
        )

        avatar = validate_profile_avatar_data_url(payload)

        with Image.open(BytesIO(avatar.content)) as decoded:
            decoded.load()
            self.assertEqual(decoded.format, "PNG")
            self.assertFalse(decoded.getexif())

    def test_rejects_magic_prefix_without_a_decodable_image(self):
        invalid_png = b"\x89PNG\r\n\x1a\nnot a real image"
        payload = "data:image/png;base64," + base64.b64encode(invalid_png).decode()

        with self.assertRaisesRegex(
            ProfileAvatarValidationError,
            "not a valid supported avatar image",
        ):
            validate_profile_avatar_data_url(payload)

    def test_rejects_declared_mime_that_does_not_match_decoded_format(self):
        payload = image_data_url(
            "PNG",
            declared_content_type="image/jpeg",
        )

        with self.assertRaisesRegex(
            ProfileAvatarValidationError,
            "does not match its declared image type",
        ):
            validate_profile_avatar_data_url(payload)

    def test_preserves_two_megabyte_decoded_input_cap(self):
        oversized = b"a" * (MAX_PROFILE_AVATAR_BYTES + 1)
        payload = "data:image/png;base64," + base64.b64encode(oversized).decode()

        with self.assertRaisesRegex(
            ProfileAvatarValidationError,
            "2 MB or smaller",
        ):
            validate_profile_avatar_data_url(payload)

    def test_wraps_storage_provider_exceptions(self):
        avatar = validate_profile_avatar_data_url(image_data_url("PNG"))

        with self.assertRaisesRegex(
            ProfileAvatarStorageError,
            "Unable to store the profile avatar",
        ):
            upload_profile_avatar(
                user_id=17,
                avatar=avatar,
                storage=FailingAvatarStorage(),
            )

    def test_supported_inputs_are_normalized_to_png_before_storage(self):
        cases = [
            "JPEG",
            "PNG",
            "GIF",
        ]

        for image_format in cases:
            with self.subTest(image_format=image_format):
                avatar = validate_profile_avatar_data_url(image_data_url(image_format))

                self.assertEqual(avatar.content_type, "image/png")
                self.assertEqual(avatar.extension, "png")

                storage = RecordingAvatarStorage(
                    public_url="https://example.com/avatar.png"
                )

                public_url = upload_profile_avatar(
                    user_id=17,
                    avatar=avatar,
                    storage=storage,
                )

                self.assertEqual(
                    public_url,
                    "https://example.com/avatar.png",
                )
                self.assertTrue(
                    storage.uploaded["object_path"].startswith("profile-avatars/17/")
                )
                self.assertTrue(storage.uploaded["object_path"].endswith(".png"))
                self.assertEqual(
                    storage.uploaded["content_type"],
                    "image/png",
                )

                with Image.open(BytesIO(storage.uploaded["content"])) as decoded:
                    decoded.load()
                    self.assertEqual(decoded.format, "PNG")
                    self.assertLessEqual(decoded.width, 1024)
                    self.assertLessEqual(decoded.height, 1024)

    def test_large_valid_image_is_reduced_to_avatar_dimension_limit(self):
        output = BytesIO()
        Image.new("RGB", (2000, 1500), color="navy").save(
            output,
            format="JPEG",
        )

        payload = (
            "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()
        )

        avatar = validate_profile_avatar_data_url(payload)

        with Image.open(BytesIO(avatar.content)) as decoded:
            decoded.load()
            self.assertEqual(decoded.format, "PNG")
            self.assertLessEqual(decoded.width, 1024)
            self.assertLessEqual(decoded.height, 1024)

    def test_jpeg_metadata_is_not_preserved_in_normalized_avatar(self):
        output = BytesIO()

        image = Image.new("RGB", (8, 8), color="navy")
        exif = Image.Exif()
        exif[0x010E] = "private metadata"

        image.save(
            output,
            format="JPEG",
            exif=exif,
        )

        payload = (
            "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()
        )

        avatar = validate_profile_avatar_data_url(payload)

        with Image.open(BytesIO(avatar.content)) as decoded:
            decoded.load()
            self.assertEqual(decoded.format, "PNG")
            self.assertFalse(decoded.getexif())
