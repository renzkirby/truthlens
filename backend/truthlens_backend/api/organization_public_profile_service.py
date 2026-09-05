from django.db import transaction

from .models import Organization
from .organization_service import (
    PartnerCapability,
    has_capability,
)


PUBLIC_PROFILE_MUTABLE_FIELDS = frozenset(
    {
        "description",
        "website",
        "logo_url",
        "expertise_areas",
        "public_profile_enabled",
        "public_logo_enabled",
    }
)


class OrganizationPublicProfileError(ValueError):
    pass


class OrganizationPublicProfileAuthorizationError(OrganizationPublicProfileError):
    pass


class InvalidOrganizationPublicProfileChanges(OrganizationPublicProfileError):
    pass


def ensure_can_manage_organization_public_profile(
    *,
    organization,
    actor,
):
    if not actor or not actor.is_authenticated:
        raise OrganizationPublicProfileAuthorizationError(
            "You must sign in to manage this organization's public profile."
        )

    if not has_capability(
        actor,
        PartnerCapability.MANAGE_ORGANIZATION,
        organization=organization,
    ):
        raise OrganizationPublicProfileAuthorizationError(
            "You do not have permission to manage this organization."
        )

    return organization


@transaction.atomic
def update_organization_public_profile(
    *,
    organization,
    actor,
    changes,
):
    unsupported_fields = set(changes) - PUBLIC_PROFILE_MUTABLE_FIELDS

    if unsupported_fields:
        field_list = ", ".join(sorted(unsupported_fields))

        raise InvalidOrganizationPublicProfileChanges(
            f"Unsupported public-profile fields: {field_list}."
        )

    locked_organization = Organization.objects.select_for_update(
        of=("self",),
    ).get(
        id=organization.id,
    )

    ensure_can_manage_organization_public_profile(
        organization=locked_organization,
        actor=actor,
    )

    if not changes:
        return locked_organization

    for field_name, value in changes.items():
        setattr(
            locked_organization,
            field_name,
            value,
        )

    locked_organization.save(
        update_fields=[
            *changes.keys(),
            "updated_at",
        ]
    )

    return locked_organization
