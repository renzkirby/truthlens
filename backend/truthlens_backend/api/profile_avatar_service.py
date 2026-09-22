import base64
import binascii
from dataclasses import dataclass
from io import BytesIO
import os
import re
import uuid
import warnings

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError
from supabase import create_client

MAX_PROFILE_AVATAR_BYTES = 2 * 1024 * 1024
MAX_PROFILE_AVATAR_SOURCE_DIMENSION = 4096
MAX_PROFILE_AVATAR_OUTPUT_DIMENSION = 1024
PROFILE_AVATAR_DATA_URL = re.compile(
    r"^data:(image/(?:jpeg|png|gif));base64,([A-Za-z0-9+/=]+)$"
)
PROFILE_AVATAR_INPUT_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
}
NORMALIZED_PROFILE_AVATAR_CONTENT_TYPE = "image/png"
NORMALIZED_PROFILE_AVATAR_EXTENSION = "png"


class ProfileAvatarError(ValueError):
    pass


class ProfileAvatarValidationError(ProfileAvatarError):
    pass


class ProfileAvatarStorageError(ProfileAvatarError):
    pass


@dataclass(frozen=True)
class ValidatedProfileAvatar:
    content: bytes
    content_type: str
    extension: str


class SupabaseProfileAvatarStorage:
    def __init__(self):
        supabase_url = os.environ.get("SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_KEY")

        if not supabase_url or not service_key:
            raise ProfileAvatarStorageError("Profile avatar storage is not configured.")

        try:
            client = create_client(supabase_url, service_key)
            self.bucket = client.storage.from_(get_profile_avatar_bucket_name())
        except Exception as error:
            raise ProfileAvatarStorageError(
                "Profile avatar storage is unavailable."
            ) from error

    def upload(self, *, object_path, content, content_type):
        try:
            self.bucket.upload(
                object_path,
                content,
                {
                    "content-type": content_type,
                    "upsert": "false",
                },
            )
            public_url = self.bucket.get_public_url(object_path)
        except Exception as error:
            raise ProfileAvatarStorageError(
                "Unable to store the profile avatar."
            ) from error

        if not isinstance(public_url, str) or not public_url:
            raise ProfileAvatarStorageError(
                "Profile avatar storage did not return a public URL."
            )

        return public_url


def get_profile_avatar_bucket_name():
    return getattr(
        settings,
        "SUPABASE_PROFILE_AVATARS_BUCKET",
        "claim-images",
    )


def _normalize_profile_avatar(decoded_image):
    """Return sanitized, metadata-free static PNG bytes for a profile avatar."""
    # For animated GIFs, intentionally normalize only the first frame. Profile
    # avatars are static identity imagery; animation is not persisted.
    decoded_image.seek(0)
    image = ImageOps.exif_transpose(decoded_image)
    image.load()

    if image.mode in ("LA", "RGBA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        image = image.convert("RGBA")
    else:
        image = image.convert("RGB")

    image.thumbnail(
        (
            MAX_PROFILE_AVATAR_OUTPUT_DIMENSION,
            MAX_PROFILE_AVATAR_OUTPUT_DIMENSION,
        ),
        Image.Resampling.LANCZOS,
    )

    # Create a fresh image from pixel data so source EXIF/text/profile metadata
    # is not propagated into the public avatar object.
    sanitized = Image.new(image.mode, image.size)
    sanitized.paste(image)

    output = BytesIO()
    sanitized.save(
        output,
        format="PNG",
        optimize=True,
    )
    return output.getvalue()


def validate_profile_avatar_data_url(value):
    match = PROFILE_AVATAR_DATA_URL.fullmatch(value)
    if match is None:
        raise ProfileAvatarValidationError(
            "Upload a JPG, PNG, or GIF image using a valid data URL."
        )

    declared_content_type, encoded_image = match.groups()
    max_encoded_length = ((MAX_PROFILE_AVATAR_BYTES + 2) // 3) * 4
    if len(encoded_image) > max_encoded_length:
        raise ProfileAvatarValidationError("Avatar images must be 2 MB or smaller.")

    try:
        image_bytes = base64.b64decode(encoded_image, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ProfileAvatarValidationError(
            "Upload a JPG, PNG, or GIF image using a valid data URL."
        ) from error

    if not image_bytes:
        raise ProfileAvatarValidationError("The avatar image is empty.")
    if len(image_bytes) > MAX_PROFILE_AVATAR_BYTES:
        raise ProfileAvatarValidationError("Avatar images must be 2 MB or smaller.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(BytesIO(image_bytes)) as probe:
                source_format = (probe.format or "").upper()
                if source_format not in PROFILE_AVATAR_INPUT_FORMATS:
                    raise ProfileAvatarValidationError(
                        "Avatar images must be JPG, PNG, or GIF."
                    )

                if PROFILE_AVATAR_INPUT_FORMATS[source_format] != declared_content_type:
                    raise ProfileAvatarValidationError(
                        "The avatar content does not match its declared image type."
                    )

                width, height = probe.size
                if (
                    width > MAX_PROFILE_AVATAR_SOURCE_DIMENSION
                    or height > MAX_PROFILE_AVATAR_SOURCE_DIMENSION
                ):
                    raise ProfileAvatarValidationError(
                        "Avatar dimensions must not exceed 4096 by 4096 pixels."
                    )

                probe.verify()

            with Image.open(BytesIO(image_bytes)) as decoded_image:
                normalized_content = _normalize_profile_avatar(decoded_image)

    except ProfileAvatarValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
    ) as error:
        raise ProfileAvatarValidationError(
            "The uploaded file is not a valid supported avatar image."
        ) from error

    return ValidatedProfileAvatar(
        content=normalized_content,
        content_type=NORMALIZED_PROFILE_AVATAR_CONTENT_TYPE,
        extension=NORMALIZED_PROFILE_AVATAR_EXTENSION,
    )


def upload_profile_avatar(*, user_id, avatar, storage=None):
    object_path = f"profile-avatars/{user_id}/{uuid.uuid4()}.{avatar.extension}"

    try:
        avatar_storage = storage or SupabaseProfileAvatarStorage()
        public_url = avatar_storage.upload(
            object_path=object_path,
            content=avatar.content,
            content_type=avatar.content_type,
        )
    except ProfileAvatarStorageError:
        raise
    except Exception as error:
        raise ProfileAvatarStorageError(
            "Unable to store the profile avatar."
        ) from error

    if not isinstance(public_url, str) or not public_url:
        raise ProfileAvatarStorageError(
            "Profile avatar storage did not return a public URL."
        )

    return public_url
