from rest_framework.permissions import BasePermission


def can_access_management_console(user):
    """Return the narrow platform-management authority used by Django."""

    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.is_superuser
    )


class IsPlatformManagementAdmin(BasePermission):
    message = "Platform management administrator access is required."

    def has_permission(self, request, view):
        return can_access_management_console(request.user)
