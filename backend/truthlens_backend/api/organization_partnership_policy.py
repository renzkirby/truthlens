from .models import Organization


def organization_has_prior_partner_work(organization):
    return (
        organization.verification_assignments.exists()
        or organization.official_fact_checks.exists()
    )


def get_organization_admin_onboarding_policy(
    organization,
    *,
    has_prior_partner_work=None,
):
    """
    Return whether platform-managed Organization Admin onboarding is valid.

    Admin onboarding is a setup/continuity action, so it remains available for
    legitimate onboarding, active partnerships, and suspended partnerships.
    It is blocked once a partnership has ended, while a legacy retirement is
    incomplete, or after institutional verification has been rejected.
    """

    if organization.partner_status == Organization.PartnerStatus.FORMER:
        return {
            "allowed": False,
            "code": "FORMER_PARTNER",
            "message": (
                "This organization is a Former Partner. Reinstate the partnership "
                "before provisioning or accepting a new Organization Admin."
            ),
        }

    if organization.partner_status == Organization.PartnerStatus.NONE:
        if has_prior_partner_work is None:
            has_prior_partner_work = organization_has_prior_partner_work(organization)

        if has_prior_partner_work:
            return {
                "allowed": False,
                "code": "RETIREMENT_REQUIRED",
                "message": (
                    "This organization has prior Partner verification work and must "
                    "complete the governed retirement lifecycle before Organization "
                    "Admin onboarding can resume."
                ),
            }

    if organization.verification_status == Organization.VerificationStatus.REJECTED:
        return {
            "allowed": False,
            "code": "VERIFICATION_REJECTED",
            "message": (
                "This organization's verification was rejected. Organization Admin "
                "onboarding is unavailable in the current lifecycle state."
            ),
        }

    return {
        "allowed": True,
        "code": None,
        "message": None,
    }
