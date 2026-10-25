from django.db import transaction

from .models import (
    AccountabilityEvent,
    OrganizationMembership,
)
from .accountability_service import record_accountability_event
from .notification_service import dispatch_after_commit, notify_membership_changed
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


def _ensure_admin_continuity(*, membership, next_role=None, next_status=None):
    """Prevent an organization from losing its final active Admin."""

    if (
        membership.role != OrganizationMembership.Role.ADMIN
        or membership.status != OrganizationMembership.Status.ACTIVE
    ):
        return

    will_remain_active_admin = (
        (next_role is None or next_role == OrganizationMembership.Role.ADMIN)
        and (next_status is None or next_status == OrganizationMembership.Status.ACTIVE)
    )
    if will_remain_active_admin:
        return

    has_other_active_admin = OrganizationMembership.objects.select_for_update(
        of=("self",),
    ).filter(
        organization=membership.organization,
        role=OrganizationMembership.Role.ADMIN,
        status=OrganizationMembership.Status.ACTIVE,
    ).exclude(pk=membership.pk).exists()

    if not has_other_active_admin:
        raise OrganizationMembershipConflict(
            "An organization must keep at least one active Admin."
        )


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

    if new_role not in manageable_roles:
        raise InvalidOrganizationMembershipRole(
            "You cannot assign this " "organization role."
        )

    if membership.role == new_role:
        raise OrganizationMembershipConflict(
            "This member already has " "that organization role."
        )

    _ensure_admin_continuity(
        membership=membership,
        next_role=new_role,
    )

    previous_role = membership.role
    membership.role = new_role

    membership.save(
        update_fields=[
            "role",
        ]
    )

    event = record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_ROLE_CHANGED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_MEMBERSHIP,
        resource_id=membership.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=actor,
        authority_organization=organization,
        subject_organization=organization,
        capability=PartnerCapability.MANAGE_ORGANIZATION,
        previous_state={"role": previous_role, "status": membership.status},
        new_state={"role": membership.role, "status": membership.status},
    )

    dispatch_after_commit(
        notify_membership_changed, membership, actor_id=actor.pk,
        event_id=event.pk, change="role_changed",
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

    _ensure_admin_continuity(
        membership=membership,
        next_status=OrganizationMembership.Status.SUSPENDED,
    )

    previous_status = membership.status
    membership.status = OrganizationMembership.Status.SUSPENDED

    membership.save(
        update_fields=[
            "status",
        ]
    )

    event = record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_SUSPENDED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_MEMBERSHIP,
        resource_id=membership.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=actor,
        authority_organization=organization,
        subject_organization=organization,
        capability=PartnerCapability.MANAGE_ORGANIZATION,
        previous_state={"role": membership.role, "status": previous_status},
        new_state={"role": membership.role, "status": membership.status},
    )

    dispatch_after_commit(
        notify_membership_changed, membership, actor_id=actor.pk,
        event_id=event.pk, change="suspended",
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

    previous_status = membership.status
    membership.status = OrganizationMembership.Status.ACTIVE

    membership.save(
        update_fields=[
            "status",
        ]
    )

    event = record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_RESTORED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_MEMBERSHIP,
        resource_id=membership.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=actor,
        authority_organization=organization,
        subject_organization=organization,
        capability=PartnerCapability.MANAGE_ORGANIZATION,
        previous_state={"role": membership.role, "status": previous_status},
        new_state={"role": membership.role, "status": membership.status},
    )

    dispatch_after_commit(
        notify_membership_changed, membership, actor_id=actor.pk,
        event_id=event.pk, change="restored",
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

    _ensure_admin_continuity(
        membership=membership,
        next_status=OrganizationMembership.Status.LEFT,
    )

    previous_status = membership.status
    membership.status = OrganizationMembership.Status.LEFT

    membership.save(
        update_fields=[
            "status",
        ]
    )

    event = record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_REMOVED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_MEMBERSHIP,
        resource_id=membership.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=actor,
        authority_organization=organization,
        subject_organization=organization,
        capability=PartnerCapability.MANAGE_ORGANIZATION,
        previous_state={"role": membership.role, "status": previous_status},
        new_state={"role": membership.role, "status": membership.status},
    )

    dispatch_after_commit(
        notify_membership_changed, membership, actor_id=actor.pk,
        event_id=event.pk, change="removed",
    )
    return membership
