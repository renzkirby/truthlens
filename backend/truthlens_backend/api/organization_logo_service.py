from dataclasses import dataclass
from io import BytesIO
import logging
import os
from urllib.parse import (
    quote,
    unquote,
    urlsplit,
)
import uuid
import warnings

from django.conf import settings
from django.db import transaction
from PIL import (
    Image,
    ImageOps,
    UnidentifiedImageError,
)
from supabase import create_client

from .models import Organization
from .organization_public_profile_service import (
    ensure_can_manage_organization_public_profile,
)


logger = logging.getLogger(__name__)

MAX_LOGO_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_LOGO_SOURCE_DIMENSION = 4096
MAX_LOGO_OUTPUT_DIMENSION = 1024
SUPPORTED_LOGO_FORMATS = frozenset(
    {
        "JPEG",
        "PNG",
        "WEBP",
    }
)


class OrganizationLogoError(ValueError):
    pass


class OrganizationLogoValidationError(OrganizationLogoError):
    pass


class OrganizationLogoStorageError(OrganizationLogoError):
    pass


@dataclass(frozen=True)
class NormalizedOrganizationLogo:
    content: bytes
    width: int
    height: int


class SupabaseOrganizationLogoStorage:
    def __init__(self):
        supabase_url = os.environ.get("SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_KEY")

        if not supabase_url or not service_key:
            raise OrganizationLogoStorageError(
                "Organization logo storage is not configured."
            )

        try:
            client = create_client(
                supabase_url,
                service_key,
            )
            self.bucket = client.storage.from_(
                get_organization_logos_bucket_name()
            )
        except Exception as error:
            raise OrganizationLogoStorageError(
                "Organization logo storage is unavailable."
            ) from error

    def upload(
        self,
        *,
        object_path,
        content,
    ):
        try:
            self.bucket.upload(
                object_path,
                content,
                {
                    "content-type": "image/png",
                    "upsert": "false",
                },
            )
            public_url = self.bucket.get_public_url(object_path)
        except Exception as error:
            raise OrganizationLogoStorageError(
                "Unable to store the organization logo."
            ) from error

        if not isinstance(public_url, str) or not public_url:
            raise OrganizationLogoStorageError(
                "Organization logo storage did not return a public URL."
            )

        return public_url

    def delete(
        self,
        *,
        object_path,
    ):
        try:
            self.bucket.remove([object_path])
        except Exception as error:
            raise OrganizationLogoStorageError(
                "Unable to remove the stored organization logo."
            ) from error


def get_organization_logos_bucket_name():
    return getattr(
        settings,
        "SUPABASE_ORGANIZATION_LOGOS_BUCKET",
        "organization-logos",
    )


def get_organization_logo_storage():
    return SupabaseOrganizationLogoStorage()


def normalize_organization_logo(uploaded_file):
    if uploaded_file is None:
        raise OrganizationLogoValidationError("Choose a logo image to upload.")

    declared_size = getattr(
        uploaded_file,
        "size",
        None,
    )

    if declared_size is not None and declared_size > MAX_LOGO_UPLOAD_BYTES:
        raise OrganizationLogoValidationError(
            "Logo images must be 2 MiB or smaller."
        )

    source = uploaded_file.read(MAX_LOGO_UPLOAD_BYTES + 1)

    if not source:
        raise OrganizationLogoValidationError("The uploaded logo is empty.")

    if len(source) > MAX_LOGO_UPLOAD_BYTES:
        raise OrganizationLogoValidationError(
            "Logo images must be 2 MiB or smaller."
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning,
            )

            with Image.open(BytesIO(source)) as probe:
                source_format = (probe.format or "").upper()

                if source_format not in SUPPORTED_LOGO_FORMATS:
                    raise OrganizationLogoValidationError(
                        "Logo images must be PNG, JPEG, or WebP."
                    )

                if getattr(probe, "is_animated", False) or getattr(
                    probe,
                    "n_frames",
                    1,
                ) > 1:
                    raise OrganizationLogoValidationError(
                        "Animated logo images are not supported."
                    )

                width, height = probe.size

                if (
                    width > MAX_LOGO_SOURCE_DIMENSION
                    or height > MAX_LOGO_SOURCE_DIMENSION
                ):
                    raise OrganizationLogoValidationError(
                        "Logo dimensions must not exceed 4096 by 4096 pixels."
                    )

                probe.verify()

            with Image.open(BytesIO(source)) as decoded_image:
                image = ImageOps.exif_transpose(decoded_image)
                image.load()

                if image.mode in (
                    "LA",
                    "RGBA",
                ) or (
                    image.mode == "P"
                    and "transparency" in image.info
                ):
                    image = image.convert("RGBA")
                else:
                    image = image.convert("RGB")

                image.thumbnail(
                    (
                        MAX_LOGO_OUTPUT_DIMENSION,
                        MAX_LOGO_OUTPUT_DIMENSION,
                    ),
                    Image.Resampling.LANCZOS,
                )

                output = BytesIO()
                image.save(
                    output,
                    format="PNG",
                    optimize=True,
                )

                return NormalizedOrganizationLogo(
                    content=output.getvalue(),
                    width=image.width,
                    height=image.height,
                )

    except OrganizationLogoValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
    ) as error:
        raise OrganizationLogoValidationError(
            "The uploaded file is not a valid supported logo image."
        ) from error


def build_organization_logo_object_path(organization_id):
    return f"organizations/{organization_id}/{uuid.uuid4()}.png"


def get_managed_organization_logo_object_path(
    logo_url,
    *,
    organization_id,
):
    supabase_url = os.environ.get("SUPABASE_URL")

    if not logo_url or not supabase_url:
        return None

    bucket_name = get_organization_logos_bucket_name()

    try:
        storage_url = urlsplit(logo_url)
        configured_url = urlsplit(supabase_url)
    except ValueError:
        return None

    if (
        storage_url.scheme != configured_url.scheme
        or storage_url.netloc != configured_url.netloc
        or storage_url.query
        or storage_url.fragment
    ):
        return None

    public_path_prefix = (
        f"{configured_url.path.rstrip('/')}"
        f"/storage/v1/object/public/{quote(bucket_name, safe='')}/"
    )

    if not storage_url.path.startswith(public_path_prefix):
        return None

    object_path = unquote(
        storage_url.path[len(public_path_prefix) :]
    )
    path_parts = object_path.split("/")

    if len(path_parts) != 3 or path_parts[:2] != [
        "organizations",
        str(organization_id),
    ]:
        return None

    file_name = path_parts[2]

    if not file_name.endswith(".png"):
        return None

    try:
        uuid.UUID(file_name.removesuffix(".png"))
    except ValueError:
        return None

    return object_path


def _delete_logo_object_best_effort(
    storage,
    object_path,
):
    try:
        storage.delete(object_path=object_path)
    except Exception:
        logger.warning(
            "Unable to clean up organization logo object %s.",
            object_path,
            exc_info=True,
        )


def upload_organization_logo(
    *,
    organization,
    actor,
    uploaded_file,
    storage=None,
):
    ensure_can_manage_organization_public_profile(
        organization=organization,
        actor=actor,
    )

    normalized_logo = normalize_organization_logo(uploaded_file)
    object_path = build_organization_logo_object_path(organization.id)
    logo_storage = storage or get_organization_logo_storage()

    try:
        public_url = logo_storage.upload(
            object_path=object_path,
            content=normalized_logo.content,
        )
    except Exception:
        _delete_logo_object_best_effort(
            logo_storage,
            object_path,
        )
        raise

    if get_managed_organization_logo_object_path(
        public_url,
        organization_id=organization.id,
    ) != object_path:
        _delete_logo_object_best_effort(
            logo_storage,
            object_path,
        )
        raise OrganizationLogoStorageError(
            "Organization logo storage returned an unexpected public URL."
        )

    try:
        with transaction.atomic():
            locked_organization = Organization.objects.select_for_update(
                of=("self",),
            ).get(
                id=organization.id,
            )

            ensure_can_manage_organization_public_profile(
                organization=locked_organization,
                actor=actor,
            )

            previous_logo_url = locked_organization.logo_url
            locked_organization.logo_url = public_url
            locked_organization.save(
                update_fields=[
                    "logo_url",
                    "updated_at",
                ]
            )

    except Exception:
        _delete_logo_object_best_effort(
            logo_storage,
            object_path,
        )
        raise

    previous_object_path = get_managed_organization_logo_object_path(
        previous_logo_url,
        organization_id=locked_organization.id,
    )

    if previous_object_path and previous_object_path != object_path:
        _delete_logo_object_best_effort(
            logo_storage,
            previous_object_path,
        )

    return locked_organization


def remove_organization_logo(
    *,
    organization,
    actor,
    storage=None,
):
    ensure_can_manage_organization_public_profile(
        organization=organization,
        actor=actor,
    )

    with transaction.atomic():
        locked_organization = Organization.objects.select_for_update(
            of=("self",),
        ).get(
            id=organization.id,
        )

        ensure_can_manage_organization_public_profile(
            organization=locked_organization,
            actor=actor,
        )

        previous_logo_url = locked_organization.logo_url
        locked_organization.logo_url = None
        locked_organization.save(
            update_fields=[
                "logo_url",
                "updated_at",
            ]
        )

    previous_object_path = get_managed_organization_logo_object_path(
        previous_logo_url,
        organization_id=locked_organization.id,
    )

    if previous_object_path:
        try:
            logo_storage = storage or get_organization_logo_storage()
        except OrganizationLogoStorageError:
            logger.warning(
                "Unable to initialize storage while cleaning up organization logo %s.",
                previous_object_path,
                exc_info=True,
            )
        else:
            _delete_logo_object_best_effort(
                logo_storage,
                previous_object_path,
            )

    return locked_organization
