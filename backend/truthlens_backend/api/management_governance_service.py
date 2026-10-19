from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_slug
from django.db import IntegrityError, transaction

from .accountability_service import record_accountability_event
from .models import AccountabilityEvent, Organization


MANAGE_PARTNER_ORGANIZATION = "MANAGE_PARTNER_ORGANIZATION"


class ManagementGovernanceError(ValueError):
    pass


class ManagementGovernanceAuthorizationError(ManagementGovernanceError):
    pass


class ManagementGovernanceValidationError(ManagementGovernanceError):
    def __init__(self, message, *, field=None):
        super().__init__(message)
        self.field = field


class ManagementGovernanceConflict(ManagementGovernanceError):
    def __init__(self, message, *, field=None):
        super().__init__(message)
        self.field = field


def _require_platform_management_authority(actor):
    if not (
        actor
        and actor.is_authenticated
        and actor.is_active
        and actor.is_superuser
    ):
        raise ManagementGovernanceAuthorizationError(
            "Platform management administrator access is required."
        )


def _organization_state(organization):
    return {
        "name": organization.name,
        "slug": organization.slug,
        "organization_type": organization.organization_type,
        "verification_status": organization.verification_status,
        "partner_status": organization.partner_status,
    }


def _validate_choice(value, choices, field):
    if value not in {choice for choice, _label in choices}:
        raise ManagementGovernanceValidationError(
            "Select a valid choice.",
            field=field,
        )


def _validate_creation_values(*, name, slug, organization_type, verification_status, partner_status):
    if not isinstance(name, str) or not name.strip():
        raise ManagementGovernanceValidationError(
            "Organization name must not be blank.",
            field="name",
        )
    if len(name.strip()) > 255:
        raise ManagementGovernanceValidationError(
            "Organization name must be 255 characters or fewer.",
            field="name",
        )
    if not isinstance(slug, str) or not slug.strip():
        raise ManagementGovernanceValidationError(
            "Slug must not be blank.",
            field="slug",
        )
    if len(slug.strip()) > 255:
        raise ManagementGovernanceValidationError(
            "Slug must be 255 characters or fewer.",
            field="slug",
        )
    try:
        validate_slug(slug.strip())
    except DjangoValidationError as error:
        raise ManagementGovernanceValidationError(
            "Enter a valid slug.",
            field="slug",
        ) from error

    _validate_choice(
        organization_type,
        Organization.OrganizationType.choices,
        "organization_type",
    )
    _validate_choice(
        verification_status,
        Organization.VerificationStatus.choices,
        "verification_status",
    )
    _validate_choice(
        partner_status,
        Organization.PartnerStatus.choices,
        "partner_status",
    )

    # Creation establishes institutional identity; approval is a later,
    # separately authorized and audited platform-governance transition.
    if verification_status != Organization.VerificationStatus.UNVERIFIED:
        raise ManagementGovernanceValidationError(
            "New organizations must start Unverified. Update status after creation.",
            field="verification_status",
        )
    if partner_status != Organization.PartnerStatus.NONE:
        raise ManagementGovernanceValidationError(
            "New organizations must start Not a Partner. Update status after creation.",
            field="partner_status",
        )


def _ensure_unique_organization_identity(*, name, slug, exclude_id=None):
    organizations = Organization.objects.all()
    if exclude_id is not None:
        organizations = organizations.exclude(pk=exclude_id)

    if organizations.filter(name__iexact=name).exists():
        raise ManagementGovernanceConflict(
            "An organization with this name already exists.",
            field="name",
        )
    if organizations.filter(slug=slug).exists():
        raise ManagementGovernanceConflict(
            "An organization with this slug already exists.",
            field="slug",
        )


def _record_organization_created(*, organization, actor):
    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_CREATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        authority_organization=None,
        subject_organization=organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        new_state=_organization_state(organization),
    )


def _persist_new_organization(*, organization, actor):
    _ensure_unique_organization_identity(
        name=organization.name,
        slug=organization.slug,
    )
    try:
        with transaction.atomic():
            organization.save()
    except IntegrityError as error:
        raise ManagementGovernanceConflict(
            "An organization with this name or slug already exists."
        ) from error

    _record_organization_created(organization=organization, actor=actor)
    return organization


@transaction.atomic
def create_partner_organization(
    *,
    name,
    slug,
    organization_type,
    verification_status=Organization.VerificationStatus.UNVERIFIED,
    partner_status=Organization.PartnerStatus.NONE,
    actor,
):
    _require_platform_management_authority(actor)
    name = name.strip() if isinstance(name, str) else name
    slug = slug.strip() if isinstance(slug, str) else slug
    _validate_creation_values(
        name=name,
        slug=slug,
        organization_type=organization_type,
        verification_status=verification_status,
        partner_status=partner_status,
    )

    organization = Organization(
        name=name,
        slug=slug,
        organization_type=organization_type,
        verification_status=verification_status,
        partner_status=partner_status,
    )
    return _persist_new_organization(organization=organization, actor=actor)


@transaction.atomic
def update_organization_platform_trust(
    *,
    organization_id,
    actor,
    verification_status=None,
    partner_status=None,
):
    _require_platform_management_authority(actor)

    if verification_status is None and partner_status is None:
        raise ManagementGovernanceValidationError(
            "Supply verification_status, partner_status, or both."
        )
    if verification_status is not None:
        _validate_choice(
            verification_status,
            Organization.VerificationStatus.choices,
            "verification_status",
        )
    if partner_status is not None:
        _validate_choice(
            partner_status,
            Organization.PartnerStatus.choices,
            "partner_status",
        )

    organization = Organization.objects.select_for_update(
        of=("self",),
    ).get(pk=organization_id)
    previous_state = {
        "verification_status": organization.verification_status,
        "partner_status": organization.partner_status,
    }
    changed_fields = []

    if (
        verification_status is not None
        and verification_status != organization.verification_status
    ):
        organization.verification_status = verification_status
        changed_fields.append("verification_status")
    if partner_status is not None and partner_status != organization.partner_status:
        organization.partner_status = partner_status
        changed_fields.append("partner_status")

    if not changed_fields:
        return organization

    organization.save(update_fields=[*changed_fields, "updated_at"])
    record_accountability_event(
        action_type=(
            AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
        ),
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        authority_organization=None,
        subject_organization=organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous_state,
        new_state={
            "verification_status": organization.verification_status,
            "partner_status": organization.partner_status,
        },
    )

    return organization


@transaction.atomic
def persist_developer_console_organization(*, organization, actor, is_creation):
    """Persist the Django Admin Organization form through governance controls."""

    _require_platform_management_authority(actor)

    if is_creation:
        organization.name = (
            organization.name.strip()
            if isinstance(organization.name, str)
            else organization.name
        )
        organization.slug = (
            organization.slug.strip()
            if isinstance(organization.slug, str)
            else organization.slug
        )
        _validate_creation_values(
            name=organization.name,
            slug=organization.slug,
            organization_type=organization.organization_type,
            verification_status=organization.verification_status,
            partner_status=organization.partner_status,
        )
        return _persist_new_organization(
            organization=organization,
            actor=actor,
        )

    return update_organization_platform_trust(
        organization_id=organization.pk,
        actor=actor,
        verification_status=organization.verification_status,
        partner_status=organization.partner_status,
    )

@transaction.atomic
def approve_organization_verification_scope(
    *, organization_id, actor, domains, jurisdictions, rationale
):
    """Only a platform administrator can approve jurisdiction/domain authority."""
    from django.core.exceptions import ValidationError
    from .verification_domain_policy import validate_domains, validate_jurisdictions

    _require_platform_management_authority(actor)
    if not isinstance(rationale, str) or not (12 <= len(rationale.strip()) <= 2000):
        raise ManagementGovernanceValidationError(
            "Explain the approval or restriction (12–2000 characters).",
            field="rationale",
        )
    try:
        domains = validate_domains(domains, allow_empty=True)
        jurisdictions = validate_jurisdictions(jurisdictions, allow_empty=True)
    except ValidationError as error:
        raise ManagementGovernanceValidationError(str(error)) from error
    if bool(domains) != bool(jurisdictions):
        raise ManagementGovernanceValidationError(
            "Approved domains and jurisdictions must both be present, or both empty."
        )

    organization = Organization.objects.select_for_update().get(pk=organization_id)
    previous = {
        "domains": organization.approved_verification_domains,
        "jurisdictions": organization.approved_verification_jurisdictions,
    }
    target = {"domains": domains, "jurisdictions": jurisdictions}
    if previous == target:
        return organization

    organization.approved_verification_domains = domains
    organization.approved_verification_jurisdictions = jurisdictions
    organization.save(update_fields=[
        "approved_verification_domains",
        "approved_verification_jurisdictions",
        "updated_at",
    ])
    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_APPROVED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        subject_organization=organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous,
        new_state=target,
        notes=rationale.strip(),
    )
    return organization


@transaction.atomic
def classify_claim_for_investigation(
    *, claim_id, actor, domains, jurisdiction, rationale
):
    """A platform reviewer classifies the existing claim; never rewrites its text."""
    from django.core.exceptions import ValidationError
    from django.utils import timezone
    from .models import Claim, ClaimInvestigationClassification, VerificationAssignment
    from .verification_domain_policy import validate_domains, validate_jurisdiction

    _require_platform_management_authority(actor)
    if not isinstance(rationale, str) or not (12 <= len(rationale.strip()) <= 2000):
        raise ManagementGovernanceValidationError(
            "Provide a classification rationale (12–2000 characters).",
            field="rationale",
        )
    try:
        domains = validate_domains(domains)
        jurisdiction = validate_jurisdiction(jurisdiction)
    except ValidationError as error:
        raise ManagementGovernanceValidationError(str(error)) from error

    claim = Claim.objects.select_for_update().get(pk=claim_id)
    if VerificationAssignment.objects.filter(
        claim=claim,
        status__in=(
            VerificationAssignment.Status.ACTIVE,
            VerificationAssignment.Status.COMPLETED,
        ),
    ).exists():
        raise ManagementGovernanceConflict(
            "Claim classification cannot change after institutional verification begins."
        )
    classification = ClaimInvestigationClassification.objects.filter(claim=claim).first()
    previous = (
        {"domains": classification.domains, "jurisdiction": classification.jurisdiction}
        if classification else {}
    )
    target = {"domains": domains, "jurisdiction": jurisdiction}
    if previous == target:
        return classification
    if classification is None:
        classification = ClaimInvestigationClassification(claim=claim)
    classification.domains = domains
    classification.jurisdiction = jurisdiction
    classification.rationale = rationale.strip()
    classification.classified_by = actor
    classification.classified_at = timezone.now()
    classification.full_clean()
    classification.save()
    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
        resource_type=AccountabilityEvent.ResourceType.CLAIM,
        resource_id=claim.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous,
        new_state=target,
        notes=rationale.strip(),
    )
    return classification
