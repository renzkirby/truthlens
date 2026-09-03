from .models import (
    ModerationCase,
    Organization,
    OrganizationMembership,
    UserProfile,
)


class PartnerCapability:
    REVIEW_SAFETY = "REVIEW_SAFETY"
    REVIEW_EVIDENCE = "REVIEW_EVIDENCE"
    ADJUDICATE = "ADJUDICATE"

    CREATE_FACT_CHECK_DRAFT = "CREATE_FACT_CHECK_DRAFT"

    PUBLISH_FACT_CHECK = "PUBLISH_FACT_CHECK"

    MANAGE_ORGANIZATION = "MANAGE_ORGANIZATION"

    CLAIM_VERIFICATION_WORK = "CLAIM_VERIFICATION_WORK"


SYSTEM_MODERATOR_CAPABILITIES = {
    PartnerCapability.REVIEW_SAFETY,
}

PARTNER_SCOPED_CAPABILITIES = {
    PartnerCapability.REVIEW_EVIDENCE,
    PartnerCapability.ADJUDICATE,
    PartnerCapability.CREATE_FACT_CHECK_DRAFT,
    PartnerCapability.PUBLISH_FACT_CHECK,
    PartnerCapability.MANAGE_ORGANIZATION,
    PartnerCapability.CLAIM_VERIFICATION_WORK,
}


MANAGEMENT_ROLE_CAPABILITIES = {
    OrganizationMembership.Role.OWNER: {
        PartnerCapability.MANAGE_ORGANIZATION,
    },
    OrganizationMembership.Role.ADMIN: {
        PartnerCapability.MANAGE_ORGANIZATION,
    },
}


VERIFIED_PARTNER_ROLE_CAPABILITIES = {
    OrganizationMembership.Role.LEAD_VERIFIER: {
        PartnerCapability.CLAIM_VERIFICATION_WORK,
        PartnerCapability.REVIEW_EVIDENCE,
        PartnerCapability.ADJUDICATE,
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        PartnerCapability.PUBLISH_FACT_CHECK,
    },
    OrganizationMembership.Role.MODERATOR: {
        PartnerCapability.REVIEW_EVIDENCE,
        PartnerCapability.ADJUDICATE,
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
    },
    OrganizationMembership.Role.RESEARCHER: {
        PartnerCapability.CREATE_FACT_CHECK_DRAFT,
    },
    OrganizationMembership.Role.CONTRIBUTOR: set(),
    OrganizationMembership.Role.OWNER: set(),
    OrganizationMembership.Role.ADMIN: set(),
}

CASE_TYPE_CAPABILITIES = {
    ModerationCase.CaseType.SAFETY: {
        PartnerCapability.REVIEW_SAFETY,
    },
    ModerationCase.CaseType.EVIDENCE: {
        PartnerCapability.REVIEW_EVIDENCE,
    },
    ModerationCase.CaseType.ADJUDICATION: {
        PartnerCapability.ADJUDICATE,
    },
}


def _has_system_moderator_role(user):
    if not user or not user.is_authenticated:
        return False

    profile = getattr(
        user,
        "profile",
        None,
    )

    if not profile:
        return False

    return profile.role in {
        UserProfile.Role.MOD,
        "MODERATOR",
    }


def is_verified_partner_membership(
    membership,
):
    return (
        membership.status == OrganizationMembership.Status.ACTIVE
        and membership.organization.verification_status
        == Organization.VerificationStatus.VERIFIED
        and membership.organization.partner_status == Organization.PartnerStatus.ACTIVE
    )


def get_membership_capabilities(
    membership,
):
    if membership.status != OrganizationMembership.Status.ACTIVE:
        return set()

    capabilities = set(
        MANAGEMENT_ROLE_CAPABILITIES.get(
            membership.role,
            set(),
        )
    )

    if is_verified_partner_membership(membership):
        capabilities.update(
            VERIFIED_PARTNER_ROLE_CAPABILITIES.get(
                membership.role,
                set(),
            )
        )

    return capabilities


def get_user_capabilities(
    user,
    *,
    organization=None,
):
    if not user or not user.is_authenticated:
        return set()

    capabilities = set()

    if _has_system_moderator_role(user):
        capabilities.update(SYSTEM_MODERATOR_CAPABILITIES)

    memberships = OrganizationMembership.objects.filter(
        user=user,
        status=(OrganizationMembership.Status.ACTIVE),
    ).select_related("organization")

    if organization is not None:
        memberships = memberships.filter(organization=organization)

    for membership in memberships:
        capabilities.update(get_membership_capabilities(membership))

    return capabilities


def has_capability(
    user,
    capability,
    *,
    organization=None,
):
    """
    Authorization-safe capability check.

    System moderators have their platform-wide capabilities.

    Organization-derived capabilities are valid only when
    the organization being acted on is explicitly supplied.
    This prevents capabilities from one partner organization
    leaking into another organization's resources.
    """

    if not user or not user.is_authenticated:
        return False

    if _has_system_moderator_role(user) and capability in SYSTEM_MODERATOR_CAPABILITIES:
        return True

    if capability in PARTNER_SCOPED_CAPABILITIES:
        if organization is None:
            return False

        membership = (
            OrganizationMembership.objects.filter(
                user=user,
                organization=organization,
                status=(OrganizationMembership.Status.ACTIVE),
            )
            .select_related("organization")
            .first()
        )

        if not membership:
            return False

        return capability in get_membership_capabilities(membership)

    return False


def has_case_capability(
    user,
    case,
    capability,
):
    """
    Determine whether a user may perform a capability
    against a specific moderation case.

    Platform Safety Moderators have platform-wide
    Safety authority only.

    Partner factual authority is scoped to the
    organization responsible for the case.
    """

    if not user or not user.is_authenticated:
        return False

    allowed_capabilities = CASE_TYPE_CAPABILITIES.get(
        case.case_type,
        set(),
    )

    if capability not in allowed_capabilities:
        return False

    if _has_system_moderator_role(user) and capability in SYSTEM_MODERATOR_CAPABILITIES:
        return True

    if not case.organization_id:
        return False

    return has_capability(
        user,
        capability,
        organization=case.organization,
    )


WORKSPACE_CAPABILITIES = {
    PartnerCapability.REVIEW_SAFETY,
    PartnerCapability.CLAIM_VERIFICATION_WORK,
    PartnerCapability.REVIEW_EVIDENCE,
    PartnerCapability.ADJUDICATE,
    PartnerCapability.CREATE_FACT_CHECK_DRAFT,
    PartnerCapability.PUBLISH_FACT_CHECK,
    PartnerCapability.MANAGE_ORGANIZATION,
}


def get_workspace_access_context(user):
    """
    Build the authorization context used by the
    verification workspace frontend.

    Platform Safety authority remains separate from
    organization-scoped factual verification authority.
    """

    if not user or not user.is_authenticated:
        return {
            "can_access": False,
            "is_platform_safety_moderator": False,
            "platform_capabilities": [],
            "memberships": [],
            "default_organization_id": None,
        }

    is_platform_safety_moderator = _has_system_moderator_role(user)

    platform_capabilities = []

    if is_platform_safety_moderator:
        platform_capabilities = sorted(
            capability
            for capability in SYSTEM_MODERATOR_CAPABILITIES
            if capability in WORKSPACE_CAPABILITIES
        )

    memberships = (
        OrganizationMembership.objects.filter(
            user=user,
            status=(OrganizationMembership.Status.ACTIVE),
        )
        .select_related("organization")
        .order_by(
            "organization__name",
            "joined_at",
            "id",
        )
    )

    membership_contexts = []

    for membership in memberships:
        capabilities = sorted(
            capability
            for capability in get_membership_capabilities(membership)
            if capability in WORKSPACE_CAPABILITIES
        )

        if not capabilities:
            continue

        organization = membership.organization

        membership_contexts.append(
            {
                "organization": {
                    "id": str(organization.id),
                    "name": organization.name,
                    "slug": organization.slug,
                    "verification_status": (organization.verification_status),
                    "partner_status": (organization.partner_status),
                },
                "role": membership.role,
                "capabilities": capabilities,
            }
        )

    default_organization_id = None

    if membership_contexts:
        default_organization_id = membership_contexts[0]["organization"]["id"]

    can_access = bool(platform_capabilities or membership_contexts)

    return {
        "can_access": can_access,
        "is_platform_safety_moderator": (is_platform_safety_moderator),
        "platform_capabilities": (platform_capabilities),
        "memberships": membership_contexts,
        "default_organization_id": (default_organization_id),
    }
