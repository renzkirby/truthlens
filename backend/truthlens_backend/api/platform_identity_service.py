from django.db.models import Q

from .management_permissions import can_access_management_console
from .models import UserProfile


PLATFORM_SAFETY_PROFILE_ROLES = frozenset(
    {
        UserProfile.Role.MOD,
        "MODERATOR",  # Legacy rollout compatibility.
    }
)


def is_platform_management_admin(user):
    """Return whether this account is a Platform Admin identity."""

    return can_access_management_console(user)


def is_platform_safety_moderator(user):
    """Return whether this account is a Platform Safety Moderator identity."""

    if not user or not user.is_authenticated or not user.is_active:
        return False

    profile = getattr(user, "profile", None)
    return bool(profile and profile.role in PLATFORM_SAFETY_PROFILE_ROLES)


def is_platform_staff_identity(user):
    """Platform governance identities are not Community participant personas."""

    return is_platform_management_admin(user) or is_platform_safety_moderator(user)


def can_review_platform_safety(user):
    """Safety review is available to Platform Admins and Safety Moderators."""

    return is_platform_staff_identity(user)


def can_participate_in_community(user):
    """Only ordinary authenticated identities participate in Community reputation."""

    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and not is_platform_staff_identity(user)
    )


def get_community_identity_context(user):
    eligible = can_participate_in_community(user)

    if is_platform_management_admin(user):
        platform_role = "PLATFORM_ADMIN"
        platform_role_label = "Platform Admin"
    elif is_platform_safety_moderator(user):
        platform_role = "PLATFORM_SAFETY_MODERATOR"
        platform_role_label = "Platform Safety Moderator"
    else:
        platform_role = None
        platform_role_label = None

    return {
        "can_participate": eligible,
        "public_profile_available": eligible,
        "reputation_applicable": eligible,
        "platform_role": platform_role,
        "platform_role_label": platform_role_label,
    }


def platform_staff_identity_q(user_field=""):
    """Build a Q expression matching platform staff through an optional user relation."""

    prefix = f"{user_field}__" if user_field else ""
    return Q(**{f"{prefix}is_superuser": True}) | Q(
        **{
            f"{prefix}profile__role__in": tuple(
                PLATFORM_SAFETY_PROFILE_ROLES
            )
        }
    )


def exclude_platform_staff_identities(queryset, user_field=""):
    """Remove privileged platform identities from Community-facing querysets."""

    return queryset.exclude(platform_staff_identity_q(user_field))
