from django.db import transaction

from .accountability_service import record_accountability_event
from .models import AccountabilityEvent, Organization
from .organization_service import (
    PartnerCapability,
    has_capability,
)


PUBLIC_PROFILE_MUTABLE_FIELDS = frozenset(
    {
        "description",
        "website",
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

    changed_fields = [
        field_name
        for field_name, value in changes.items()
        if getattr(locked_organization, field_name) != value
    ]
    safe_fields = {
        "website",
        "expertise_areas",
        "public_profile_enabled",
        "public_logo_enabled",
    }
    previous_state = {
        field_name: getattr(locked_organization, field_name)
        for field_name in changed_fields
        if field_name in safe_fields
    }

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

    if changed_fields:
        record_accountability_event(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_PUBLIC_PROFILE_UPDATED,
            resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
            resource_id=locked_organization.pk,
            authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
            actor=actor,
            authority_organization=locked_organization,
            subject_organization=locked_organization,
            capability=PartnerCapability.MANAGE_ORGANIZATION,
            previous_state=previous_state,
            new_state={
                field_name: getattr(locked_organization, field_name)
                for field_name in changed_fields
                if field_name in safe_fields
            },
            context={"changed_fields": sorted(changed_fields)},
        )

    return locked_organization
