from django.db import transaction

from .models import (
    OrganizationMembership,
)
from .organization_service import (
    PartnerCapability,
    get_manageable_membership_roles,
    has_capability,
)


class OrganizationMembershipManagementError(ValueError):
    pass


class OrganizationMembershipAuthorizationError(OrganizationMembershipManagementError):
    pass


class OrganizationMembershipConflict(OrganizationMembershipManagementError):
    pass


class OrganizationMembershipNotFound(OrganizationMembershipManagementError):
    pass


class InvalidOrganizationMembershipRole(OrganizationMembershipManagementError):
    pass


def _normalize_role(
    role,
):
    normalized = str(role or "").strip().upper()

    valid_roles = {value for value, _label in OrganizationMembership.Role.choices}

    if normalized not in valid_roles:
        raise InvalidOrganizationMembershipRole("Select a valid organization role.")

    return normalized


def _get_locked_management_context(
    *,
    organization,
    membership_id,
    actor,
):
    if not actor or not actor.is_authenticated:
        raise (
            OrganizationMembershipAuthorizationError(
                "You must sign in to manage " "organization memberships."
            )
        )

    if not has_capability(
        actor,
        PartnerCapability.MANAGE_ORGANIZATION,
        organization=organization,
    ):
        raise (
            OrganizationMembershipAuthorizationError(
                "You do not have permission " "to manage this organization."
            )
        )

    actor_membership = (
        OrganizationMembership.objects.select_for_update(
            of=("self",),
        )
        .filter(
            organization=organization,
            user=actor,
            status=(OrganizationMembership.Status.ACTIVE),
        )
        .first()
    )

    if not actor_membership:
        raise (
            OrganizationMembershipAuthorizationError(
                "You do not have an active "
                "management membership in "
                "this organization."
            )
        )

    target_membership = (
        OrganizationMembership.objects.select_for_update(
            of=("self",),
        )
        .select_related(
            "organization",
            "user",
            "approved_by",
        )
        .filter(
            id=membership_id,
            organization=organization,
        )
        .first()
    )

    if not target_membership:
        raise OrganizationMembershipNotFound("Organization membership not found.")

    manageable_roles = get_manageable_membership_roles(actor_membership)

    # Ownership is deliberately immutable through
    # ordinary membership administration.
    if target_membership.role == OrganizationMembership.Role.OWNER:
        raise (
            OrganizationMembershipAuthorizationError(
                "Organization ownership must "
                "be managed through a separate "
                "ownership-transfer workflow."
            )
        )

    if target_membership.role not in manageable_roles:
        raise (
            OrganizationMembershipAuthorizationError(
                "You cannot manage a member " "with this organization role."
            )
        )

    return {
        "actor_membership": actor_membership,
        "target_membership": target_membership,
        "manageable_roles": manageable_roles,
    }


@transaction.atomic
def change_organization_membership_role(
    *,
    organization,
    membership_id,
    role,
    actor,
):
    new_role = _normalize_role(
        role,
    )

    context = _get_locked_management_context(
        organization=organization,
        membership_id=membership_id,
        actor=actor,
    )

    membership = context["target_membership"]

    manageable_roles = context["manageable_roles"]

    if membership.status == OrganizationMembership.Status.LEFT:
        raise OrganizationMembershipConflict(
            "A former membership cannot have "
            "its role changed. Send a new "
            "invitation if the person should "
            "rejoin the organization."
        )

    if new_role == OrganizationMembership.Role.OWNER:
        raise InvalidOrganizationMembershipRole(
            "Organization ownership cannot "
            "be assigned through ordinary "
            "membership administration."
        )

    if new_role not in manageable_roles:
        raise InvalidOrganizationMembershipRole(
            "You cannot assign this " "organization role."
        )

    if membership.role == new_role:
        raise OrganizationMembershipConflict(
            "This member already has " "that organization role."
        )

    membership.role = new_role

    membership.save(
        update_fields=[
            "role",
        ]
    )

    return membership


@transaction.atomic
def suspend_organization_membership(
    *,
    organization,
    membership_id,
    actor,
):
    context = _get_locked_management_context(
        organization=organization,
        membership_id=membership_id,
        actor=actor,
    )

    membership = context["target_membership"]

    if membership.status != OrganizationMembership.Status.ACTIVE:
        raise OrganizationMembershipConflict(
            "Only an active membership " "can be suspended."
        )

    membership.status = OrganizationMembership.Status.SUSPENDED

    membership.save(
        update_fields=[
            "status",
        ]
    )

    return membership


@transaction.atomic
def restore_organization_membership(
    *,
    organization,
    membership_id,
    actor,
):
    context = _get_locked_management_context(
        organization=organization,
        membership_id=membership_id,
        actor=actor,
    )

    membership = context["target_membership"]

    if membership.status != OrganizationMembership.Status.SUSPENDED:
        raise OrganizationMembershipConflict(
            "Only a suspended membership " "can be restored."
        )

    membership.status = OrganizationMembership.Status.ACTIVE

    membership.save(
        update_fields=[
            "status",
        ]
    )

    return membership


@transaction.atomic
def remove_organization_membership(
    *,
    organization,
    membership_id,
    actor,
):
    context = _get_locked_management_context(
        organization=organization,
        membership_id=membership_id,
        actor=actor,
    )

    membership = context["target_membership"]

    if membership.status == OrganizationMembership.Status.LEFT:
        raise OrganizationMembershipConflict(
            "This person has already left " "the organization."
        )

    membership.status = OrganizationMembership.Status.LEFT

    membership.save(
        update_fields=[
            "status",
        ]
    )

    return membership
