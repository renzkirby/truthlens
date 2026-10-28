from django.db.models import Prefetch

from .models import Organization, OrganizationMembership
from .organization_public_presence_service import is_public_partner_eligible


PROFESSIONAL_MEMBERSHIPS_ATTR = "_partner_professional_memberships"
PROFESSIONAL_MEMBERSHIP_STATUSES = (
    OrganizationMembership.Status.ACTIVE,
    OrganizationMembership.Status.SUSPENDED,
)
PROFESSIONAL_PARTNER_STATUSES = (
    Organization.PartnerStatus.ACTIVE,
    Organization.PartnerStatus.SUSPENDED,
)

LEGACY_ROLE_LABELS = {
    "OWNER": "Administrator",
    "MODERATOR": "Verification Reviewer",
    "CONTRIBUTOR": "Former Contributor",
}


def get_organization_membership_role_label(role):
    return dict(OrganizationMembership.Role.choices).get(
        role,
        LEGACY_ROLE_LABELS.get(role, role),
    )


def partner_professional_membership_queryset():
    return (
        OrganizationMembership.objects.filter(
            status__in=PROFESSIONAL_MEMBERSHIP_STATUSES,
            organization__verification_status=Organization.VerificationStatus.VERIFIED,
            organization__partner_status__in=PROFESSIONAL_PARTNER_STATUSES,
        )
        .select_related("organization")
        .order_by("joined_at", "id")
    )


def partner_professional_membership_prefetch(user_path=""):
    lookup = (
        f"{user_path}__organization_memberships"
        if user_path
        else "organization_memberships"
    )
    return Prefetch(
        lookup,
        queryset=partner_professional_membership_queryset(),
        to_attr=PROFESSIONAL_MEMBERSHIPS_ATTR,
    )


def get_partner_professional_identity(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None

    memberships = getattr(user, PROFESSIONAL_MEMBERSHIPS_ATTR, None)
    if memberships is None:
        membership = partner_professional_membership_queryset().filter(user=user).first()
    else:
        membership = memberships[0] if memberships else None

    if membership is None:
        return None

    organization = membership.organization
    role_label = get_organization_membership_role_label(membership.role)
    authority_active = (
        membership.status == OrganizationMembership.Status.ACTIVE
        and organization.partner_status == Organization.PartnerStatus.ACTIVE
    )

    return {
        "role": membership.role,
        "role_label": role_label,
        "membership_status": membership.status,
        "membership_status_label": membership.get_status_display(),
        "authority_active": authority_active,
        "display_label": f"{role_label} at {organization.name}",
        "organization": {
            "id": str(organization.id),
            "name": organization.name,
            "slug": organization.slug,
            "logo_url": (
                organization.logo_url
                if organization.public_logo_enabled and organization.logo_url
                else None
            ),
            "partner_status": organization.partner_status,
            "partner_status_label": organization.get_partner_status_display(),
            "public_profile_available": is_public_partner_eligible(organization),
        },
    }
