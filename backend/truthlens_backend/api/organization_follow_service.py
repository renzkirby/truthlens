from django.db import transaction

from .community_account_enforcement_service import get_user_community_access
from .models import Organization, OrganizationFollow
from .organization_public_presence_service import PUBLIC_PARTNER_ELIGIBILITY


class PublicPartnerFollowUnavailable(Exception):
    pass


class PublicPartnerFollowRestricted(Exception):
    def __init__(self, access):
        super().__init__("Community contribution access is restricted.")
        self.access = access


@transaction.atomic
def toggle_public_partner_follow(*, slug, user):
    organization = (
        Organization.objects.select_for_update()
        .filter(
            slug=slug,
            **PUBLIC_PARTNER_ELIGIBILITY,
        )
        .first()
    )
    if organization is None:
        raise PublicPartnerFollowUnavailable

    relationship = (
        OrganizationFollow.objects.select_for_update()
        .filter(
            organization=organization,
            user=user,
        )
        .first()
    )

    if relationship is not None:
        relationship.delete()
        is_following = False
    else:
        access = get_user_community_access(user)
        if not access["can_contribute"]:
            raise PublicPartnerFollowRestricted(access)
        OrganizationFollow.objects.create(
            organization=organization,
            user=user,
        )
        is_following = True

    return {
        "is_following": is_following,
        "followers_count": OrganizationFollow.objects.filter(
            organization=organization,
        ).count(),
    }
