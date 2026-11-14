"""Community contribution permission separate from identity eligibility."""

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .community_account_enforcement_service import get_user_community_access


WITHDRAWAL_METHODS = {"DELETE"}


class CommunityContributionRestrictedError(Exception):
    def __init__(self, payload):
        super().__init__(payload["detail"])
        self.payload = payload


def community_contribution_restriction_payload(user):
    access = get_user_community_access(user)
    if access["can_contribute"]:
        return None

    if access["status"] == "TEMPORARILY_RESTRICTED":
        detail = "Your Community contribution access is temporarily restricted."
    else:
        detail = "Your Community contribution access is indefinitely restricted."

    return {
        "code": "COMMUNITY_CONTRIBUTION_RESTRICTED",
        "detail": detail,
        "restriction_ends_at": access["restriction_ends_at"],
        "standing_url": "/dashboard#community-standing",
    }


def ensure_can_start_community_contribution(user):
    payload = community_contribution_restriction_payload(user)
    if payload is not None:
        raise CommunityContributionRestrictedError(payload)


class CanContributeToCommunity(BasePermission):
    """Block new/edited Community contributions while allowing read/withdrawal."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS or request.method in WITHDRAWAL_METHODS:
            return True

        payload = community_contribution_restriction_payload(request.user)
        if payload is None:
            return True
        raise PermissionDenied(payload)
