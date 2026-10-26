from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator, validate_slug
from django.db import IntegrityError, transaction
from django.utils import timezone

from .accountability_service import record_accountability_event
from .management_governance_service import (
    MANAGE_PARTNER_ORGANIZATION,
    ManagementGovernanceAuthorizationError,
    ManagementGovernanceConflict,
    ManagementGovernanceValidationError,
)
from .models import (
    AccountabilityEvent,
    Institution,
    Organization,
    OrganizationInstitutionAffiliation,
)


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


def _institution_state(institution):
    return {
        "name": institution.name,
        "slug": institution.slug,
        "website": institution.website,
        "is_active": institution.is_active,
    }


def _affiliation_state(affiliation):
    if affiliation is None:
        return {}
    return {
        "institution_id": str(affiliation.institution_id),
        "institution_name": affiliation.institution.name,
        "coverage_scope": affiliation.coverage_scope,
        "verification_status": affiliation.verification_status,
        "rationale": affiliation.rationale,
    }


@transaction.atomic
def create_institution(*, name, slug, website=None, actor):
    _require_platform_management_authority(actor)

    name = name.strip() if isinstance(name, str) else name
    slug = slug.strip() if isinstance(slug, str) else slug
    website = website.strip() if isinstance(website, str) else website
    website = website or None

    if not isinstance(name, str) or not name:
        raise ManagementGovernanceValidationError(
            "Institution name must not be blank.",
            field="name",
        )
    if len(name) > 255:
        raise ManagementGovernanceValidationError(
            "Institution name must be 255 characters or fewer.",
            field="name",
        )
    if not isinstance(slug, str) or not slug:
        raise ManagementGovernanceValidationError(
            "Slug must not be blank.",
            field="slug",
        )
    try:
        validate_slug(slug)
    except DjangoValidationError as error:
        raise ManagementGovernanceValidationError(
            "Enter a valid slug.",
            field="slug",
        ) from error
    if website is not None:
        try:
            URLValidator()(website)
        except DjangoValidationError as error:
            raise ManagementGovernanceValidationError(
                "Enter a valid URL.",
                field="website",
            ) from error

    if Institution.objects.filter(name__iexact=name).exists():
        raise ManagementGovernanceConflict(
            "An institution with this name already exists.",
            field="name",
        )
    if Institution.objects.filter(slug=slug).exists():
        raise ManagementGovernanceConflict(
            "An institution with this slug already exists.",
            field="slug",
        )

    institution = Institution(name=name, slug=slug, website=website)
    try:
        institution.full_clean()
        institution.save()
    except IntegrityError as error:
        raise ManagementGovernanceConflict(
            "An institution with this name or slug already exists."
        ) from error

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.INSTITUTION_CREATED,
        resource_type=AccountabilityEvent.ResourceType.INSTITUTION,
        resource_id=institution.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        authority_organization=None,
        subject_organization=None,
        capability=MANAGE_PARTNER_ORGANIZATION,
        new_state=_institution_state(institution),
    )
    return institution


@transaction.atomic
def set_organization_institution_affiliation(
    *,
    organization_id,
    institution_id,
    verification_status,
    rationale="",
    actor,
):
    _require_platform_management_authority(actor)

    valid_statuses = {
        value
        for value, _label in OrganizationInstitutionAffiliation.VerificationStatus.choices
    }
    if verification_status not in valid_statuses:
        raise ManagementGovernanceValidationError(
            "Select a valid affiliation verification status.",
            field="verification_status",
        )

    rationale = rationale.strip() if isinstance(rationale, str) else rationale
    if not isinstance(rationale, str):
        raise ManagementGovernanceValidationError(
            "Rationale must be text.",
            field="rationale",
        )
    if len(rationale) > 2000:
        raise ManagementGovernanceValidationError(
            "Rationale must be 2000 characters or fewer.",
            field="rationale",
        )
    if (
        verification_status
        in {
            OrganizationInstitutionAffiliation.VerificationStatus.VERIFIED,
            OrganizationInstitutionAffiliation.VerificationStatus.REJECTED,
        }
        and not rationale
    ):
        raise ManagementGovernanceValidationError(
            "A rationale is required for a reviewed affiliation.",
            field="rationale",
        )

    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    institution = Institution.objects.select_for_update(of=("self",)).get(
        pk=institution_id
    )

    if organization.organization_type != Organization.OrganizationType.NEWS:
        raise ManagementGovernanceValidationError(
            "Student Publication affiliation requires a News Organization.",
            field="organization_id",
        )
    if not institution.is_active:
        raise ManagementGovernanceValidationError(
            "Institution must be active.",
            field="institution_id",
        )

    affiliation = (
        OrganizationInstitutionAffiliation.objects.select_for_update()
        .select_related("institution")
        .filter(organization=organization)
        .first()
    )
    previous_state = _affiliation_state(affiliation)

    desired_state = {
        "institution_id": str(institution.pk),
        "institution_name": institution.name,
        "coverage_scope": (
            OrganizationInstitutionAffiliation.CoverageScope.INSTITUTION_WIDE
        ),
        "verification_status": verification_status,
        "rationale": rationale,
    }
    if affiliation is not None and previous_state == desired_state:
        return affiliation

    if organization.organization_subtype != Organization.OrganizationSubtype.STUDENT_PUBLICATION:
        organization.organization_subtype = (
            Organization.OrganizationSubtype.STUDENT_PUBLICATION
        )
        organization.full_clean()
        organization.save(update_fields=["organization_subtype", "updated_at"])

    if affiliation is None:
        affiliation = OrganizationInstitutionAffiliation(
            organization=organization,
        )

    affiliation.institution = institution
    affiliation.coverage_scope = (
        OrganizationInstitutionAffiliation.CoverageScope.INSTITUTION_WIDE
    )
    affiliation.verification_status = verification_status
    affiliation.rationale = rationale
    if verification_status == OrganizationInstitutionAffiliation.VerificationStatus.PENDING:
        affiliation.reviewed_by = None
        affiliation.reviewed_at = None
    else:
        affiliation.reviewed_by = actor
        affiliation.reviewed_at = timezone.now()

    affiliation.full_clean()
    affiliation.save()

    record_accountability_event(
        action_type=(
            AccountabilityEvent.ActionType.ORGANIZATION_INSTITUTION_AFFILIATION_UPDATED
        ),
        resource_type=(
            AccountabilityEvent.ResourceType.ORGANIZATION_INSTITUTION_AFFILIATION
        ),
        resource_id=affiliation.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        authority_organization=None,
        subject_organization=organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous_state,
        new_state=_affiliation_state(affiliation),
    )
    return affiliation
