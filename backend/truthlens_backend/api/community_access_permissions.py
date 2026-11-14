"""Community contribution permission separate from identity eligibility."""

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .community_account_enforcement_service import get_user_community_access


WITHDRAWAL_METHODS = {"DELETE"}


class CanContributeToCommunity(BasePermission):
    """Block new/edited Community contributions while allowing read/withdrawal."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS or request.method in WITHDRAWAL_METHODS:
            return True

        access = get_user_community_access(request.user)
        if access["can_contribute"]:
            return True

        status = access["status"]
        if status == "TEMPORARILY_RESTRICTED":
            detail = "Your Community contribution access is temporarily restricted."
        else:
            detail = "Your Community contribution access is indefinitely restricted."

        raise PermissionDenied(
            {
                "code": "COMMUNITY_CONTRIBUTION_RESTRICTED",
                "detail": detail,
                "restriction_ends_at": access["restriction_ends_at"],
                "standing_url": "/dashboard#community-standing",
            }
        )
