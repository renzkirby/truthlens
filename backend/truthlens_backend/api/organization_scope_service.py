"""Primary Admin-owned investigation specializations, audited and domain-only."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .accountability_service import record_accountability_event
from .models import AccountabilityEvent, Organization, OrganizationMembership
from .verification_domain_policy import validate_domains, organization_specializations


MANAGE_VERIFICATION_SPECIALIZATIONS = "MANAGE_VERIFICATION_SPECIALIZATIONS"


class OrganizationScopeError(ValueError):
    pass


class OrganizationScopeForbidden(OrganizationScopeError):
    pass


class OrganizationScopeInvalid(OrganizationScopeError):
    pass


def can_view_specializations(*, organization, actor):
    return bool(
        actor and actor.is_authenticated and OrganizationMembership.objects.filter(
            organization=organization,
            user=actor,
            status=OrganizationMembership.Status.ACTIVE,
            role__in=[OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN],
        ).exists()
    )


def can_manage_specializations(*, organization, actor):
    # The Primary Admin alone controls institutional specialization; an Admin
    # does not inherit this authority merely through MANAGE_ORGANIZATION.
    return bool(
        actor and actor.is_authenticated and OrganizationMembership.objects.filter(
            organization=organization,
            user=actor,
            status=OrganizationMembership.Status.ACTIVE,
            role=OrganizationMembership.Role.OWNER,
        ).exists()
    )


def ensure_scope_manager(*, organization, actor):
    if not can_manage_specializations(organization=organization, actor=actor):
        raise OrganizationScopeForbidden(
            "Only the active Primary Admin may manage verification specializations."
        )


@transaction.atomic
def update_organization_specializations(*, organization, actor, domains, rationale):
    if not isinstance(rationale, str) or not 12 <= len(rationale.strip()) <= 2000:
        raise OrganizationScopeInvalid("Explain the change (12–2000 characters).")
    try:
        selected = validate_domains(domains, allow_empty=True)
    except ValidationError as error:
        raise OrganizationScopeInvalid(str(error)) from error
    locked = Organization.objects.select_for_update().get(pk=organization.pk)
    ensure_scope_manager(organization=locked, actor=actor)
    previous = organization_specializations(locked)
    if previous == selected:
        return locked
    locked.verification_specializations = selected
    locked.save(update_fields=["verification_specializations", "updated_at"])
    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SPECIALIZATIONS_UPDATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=locked.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=actor,
        authority_organization=locked,
        capability=MANAGE_VERIFICATION_SPECIALIZATIONS,
        previous_state={"domains": previous},
        new_state={"domains": selected},
        notes=rationale.strip(),
    )
    return locked


def serialize_organization_scope(organization, *, actor=None):
    return {
        "organization_id": str(organization.pk),
        "specializations": organization_specializations(organization),
        "can_manage": can_manage_specializations(organization=organization, actor=actor),
    }
