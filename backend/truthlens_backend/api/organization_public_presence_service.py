from django.db.models import Q

from .models import OfficialFactCheck, Organization


PUBLIC_PARTNER_ELIGIBILITY = {
    "public_profile_enabled": True,
    "verification_status": Organization.VerificationStatus.VERIFIED,
    "partner_status": Organization.PartnerStatus.ACTIVE,
}


def is_public_partner_eligible(organization):
    return all(
        getattr(organization, field_name) == expected_value
        for field_name, expected_value in PUBLIC_PARTNER_ELIGIBILITY.items()
    )


def get_public_partner_organizations():
    """
    Return organizations that have explicitly opted in to public
    presence and currently satisfy partner eligibility.
    """

    return Organization.objects.filter(**PUBLIC_PARTNER_ELIGIBILITY).order_by(
        "name",
        "id",
    )


def get_public_partner_directory(
    *,
    search="",
    organization_type="",
):
    organizations = get_public_partner_organizations()

    if search:
        organizations = organizations.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    if organization_type:
        organizations = organizations.filter(
            organization_type=organization_type,
        )

    return organizations


def get_public_partner_by_slug(slug):
    return get_public_partner_organizations().filter(
        slug=slug,
    ).first()


def get_publication_organization_by_slug(slug):
    """
    Resolve an organization for historical public publication routes.

    Unlike Partner Directory/profile eligibility, this lookup is based on
    durable sealed published work. A former or suspended organization may lose
    its current public Partner profile while its published fact-checks remain
    readable and attributable.
    """

    return (
        Organization.objects.filter(
            slug=slug,
            official_fact_checks__publication_status=(
                OfficialFactCheck.PublicationStatus.PUBLISHED
            ),
            official_fact_checks__published_at__isnull=False,
            official_fact_checks__publication_snapshot__isnull=False,
            official_fact_checks__claim__isnull=False,
            official_fact_checks__adjudication_decision__isnull=False,
        )
        .distinct()
        .first()
    )
