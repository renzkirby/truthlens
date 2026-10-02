from django.db import transaction

from .models import Organization, OrganizationFollow
from .organization_public_presence_service import PUBLIC_PARTNER_ELIGIBILITY


class PublicPartnerFollowUnavailable(Exception):
    pass


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

    relationship = OrganizationFollow.objects.filter(
        organization=organization,
        user=user,
    ).first()

    if relationship is not None:
        relationship.delete()
        is_following = False
    else:
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
