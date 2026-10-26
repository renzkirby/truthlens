from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q

from .accountability_service import record_accountability_event
from .management_permissions import can_access_management_console
from .models import AccountabilityEvent, UserProfile
from .platform_identity_service import PLATFORM_SAFETY_PROFILE_ROLES


MANAGE_PLATFORM_STAFF = "MANAGE_PLATFORM_STAFF"


class PlatformStaffError(Exception):
    pass


class PlatformStaffAuthorizationError(PlatformStaffError):
    pass


class PlatformStaffValidationError(PlatformStaffError):
    pass


class PlatformStaffConflict(PlatformStaffError):
    pass


class PlatformStaffNotFound(PlatformStaffError):
    pass


def _require_platform_admin(actor):
    if not can_access_management_console(actor):
        raise PlatformStaffAuthorizationError(
            "Platform Admin access is required to manage platform staff."
        )


def list_platform_staff(*, actor, query=""):
    _require_platform_admin(actor)
    queryset = (
        User.objects.select_related("profile")
        .filter(
            Q(is_superuser=True)
            | Q(profile__role__in=tuple(PLATFORM_SAFETY_PROFILE_ROLES))
        )
        .order_by("-is_superuser", "username", "id")
        .distinct()
    )
    normalized = str(query or "").strip()
    if normalized:
        queryset = queryset.filter(
            Q(username__icontains=normalized) | Q(email__icontains=normalized)
        )
    return queryset


def _record_platform_staff_change(*, actor, target_user, action_type, previous_role, new_role):
    record_accountability_event(
        action_type=action_type,
        resource_type=AccountabilityEvent.ResourceType.USER_ACCOUNT,
        resource_id=target_user.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        capability=MANAGE_PLATFORM_STAFF,
        previous_state={
            "platform_role": previous_role,
        },
        new_state={
            "platform_role": new_role,
        },
        context={
            "target_username": target_user.username,
        },
    )


@transaction.atomic
def revoke_platform_safety_moderator(*, actor, user_id):
    _require_platform_admin(actor)

    try:
        target_user = User.objects.select_for_update().get(pk=user_id)
    except User.DoesNotExist as error:
        raise PlatformStaffNotFound("User account not found.") from error

    if target_user.is_superuser:
        raise PlatformStaffConflict(
            "Platform Admin access cannot be changed through Safety Moderator management."
        )

    profile = (
        UserProfile.objects.select_for_update()
        .filter(user=target_user)
        .first()
    )
    if profile is None or profile.role not in PLATFORM_SAFETY_PROFILE_ROLES:
        raise PlatformStaffConflict(
            "This account is not a Platform Safety Moderator."
        )

    profile.role = UserProfile.Role.USER
    profile.save(update_fields=["role"])

    _record_platform_staff_change(
        actor=actor,
        target_user=target_user,
        action_type=AccountabilityEvent.ActionType.PLATFORM_SAFETY_MODERATOR_REVOKED,
        previous_role="PLATFORM_SAFETY_MODERATOR",
        new_role="COMMUNITY_USER",
    )

    return User.objects.select_related("profile").get(pk=target_user.pk)
