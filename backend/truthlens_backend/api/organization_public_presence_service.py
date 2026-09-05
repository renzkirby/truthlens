from django.db.models import Q

from .models import Organization


def get_public_partner_organizations():
    """
    Return organizations that have explicitly opted in to public
    presence and currently satisfy partner eligibility.
    """

    return Organization.objects.filter(
        public_profile_enabled=True,
        verification_status=Organization.VerificationStatus.VERIFIED,
        partner_status=Organization.PartnerStatus.ACTIVE,
    ).order_by(
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
