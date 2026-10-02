from django.db.models import Prefetch

from .models import OrganizationMembership
from .organization_public_presence_service import PUBLIC_PARTNER_ELIGIBILITY


PUBLIC_PARTNER_MEMBERSHIPS_ATTR = "_public_partner_memberships"


def public_partner_membership_queryset():
    return (
        OrganizationMembership.objects.filter(
            status=OrganizationMembership.Status.ACTIVE,
            **{
                f"organization__{field_name}": expected_value
                for field_name, expected_value in PUBLIC_PARTNER_ELIGIBILITY.items()
            },
        )
        .select_related("organization")
        .order_by("organization__name", "organization_id")
    )


def public_partner_affiliation_prefetch(user_path=""):
    lookup = (
        f"{user_path}__organization_memberships"
        if user_path
        else "organization_memberships"
    )
    return Prefetch(
        lookup,
        queryset=public_partner_membership_queryset(),
        to_attr=PUBLIC_PARTNER_MEMBERSHIPS_ATTR,
    )


def prefetch_public_partner_affiliations(queryset, *user_paths):
    paths = user_paths or ("",)
    return queryset.prefetch_related(
        *(public_partner_affiliation_prefetch(path) for path in paths)
    )


def get_public_partner_affiliations(user):
    memberships = getattr(user, PUBLIC_PARTNER_MEMBERSHIPS_ATTR, None)
    if memberships is None:
        memberships = public_partner_membership_queryset().filter(user=user)

    return [
        {
            "id": str(membership.organization_id),
            "name": membership.organization.name,
            "slug": membership.organization.slug,
            "logo_url": (
                membership.organization.logo_url
                if membership.organization.public_logo_enabled
                and membership.organization.logo_url
                else None
            ),
        }
        for membership in memberships
    ]
