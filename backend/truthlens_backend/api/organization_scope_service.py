"""Organization-managed requests and active scope, never self-approval."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .accountability_service import record_accountability_event
from .models import AccountabilityEvent, Organization
from .organization_service import PartnerCapability, has_capability
from .verification_domain_policy import (
    validate_domains, validate_jurisdictions, effective_organization_scope,
)


class OrganizationScopeError(ValueError):
    pass


class OrganizationScopeForbidden(OrganizationScopeError):
    pass


class OrganizationScopeInvalid(OrganizationScopeError):
    pass


def ensure_scope_manager(*, organization, actor):
    if not has_capability(
        actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization
    ):
        raise OrganizationScopeForbidden(
            "Only an active organization Primary Admin or Admin may manage scope."
        )


def _valid_reason(reason):
    if not isinstance(reason, str) or not 12 <= len(reason.strip()) <= 2000:
        raise OrganizationScopeInvalid("A review rationale (12–2000 characters) is required.")
    return reason.strip()


def _valid_scope(domains, jurisdictions, *, allow_empty):
    try:
        domains = validate_domains(domains, allow_empty=allow_empty)
        jurisdictions = validate_jurisdictions(jurisdictions, allow_empty=allow_empty)
    except ValidationError as error:
        raise OrganizationScopeInvalid(str(error)) from error
    if bool(domains) != bool(jurisdictions):
        raise OrganizationScopeInvalid(
            "Domains and jurisdictions must both be supplied or both be empty."
        )
    return domains, jurisdictions


@transaction.atomic
def submit_scope_request(*, organization, actor, domains, jurisdictions, rationale):
    """Submitting a request never expands effective investigation authority."""
    reason = _valid_reason(rationale)
    domains, jurisdictions = _valid_scope(domains, jurisdictions, allow_empty=True)
    locked = Organization.objects.select_for_update().get(pk=organization.pk)
    ensure_scope_manager(organization=locked, actor=actor)
    previous = {
        "domains": locked.requested_verification_domains,
        "jurisdictions": locked.requested_verification_jurisdictions,
    }
    target = {"domains": domains, "jurisdictions": jurisdictions}
    if target == previous:
        return locked
    locked.requested_verification_domains = domains
    locked.requested_verification_jurisdictions = jurisdictions
    # Turn legacy implicit activation into explicit current selection before
    # asking for additional approval. New grants remain inactive by default.
    if not locked.active_scope_configured:
        old_domains, old_jurisdictions = effective_organization_scope(locked)
        locked.active_verification_domains = old_domains
        locked.active_verification_jurisdictions = old_jurisdictions
        locked.active_scope_configured = True
    locked.save(update_fields=[
        "requested_verification_domains",
        "requested_verification_jurisdictions",
        "active_verification_domains",
        "active_verification_jurisdictions",
        "active_scope_configured",
        "updated_at",
    ])
    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_REQUESTED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=locked.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=actor,
        authority_organization=locked,
        capability=PartnerCapability.MANAGE_ORGANIZATION,
        previous_state=previous,
        new_state=target,
        notes=reason,
    )
    return locked


@transaction.atomic
def configure_active_scope(*, organization, actor, domains, jurisdictions, rationale):
    """Organization autonomy is limited to an approved subset; revocation is immediate."""
    reason = _valid_reason(rationale)
    domains, jurisdictions = _valid_scope(domains, jurisdictions, allow_empty=True)
    locked = Organization.objects.select_for_update().get(pk=organization.pk)
    ensure_scope_manager(organization=locked, actor=actor)
    if (
        not set(domains).issubset(set(locked.approved_verification_domains))
        or not set(jurisdictions).issubset(set(locked.approved_verification_jurisdictions))
    ):
        raise OrganizationScopeInvalid(
            "An active specialization or jurisdiction cannot exceed platform approval."
        )
    old_domains, old_jurisdictions = effective_organization_scope(locked)
    if old_domains == domains and old_jurisdictions == jurisdictions:
        return locked
    locked.active_verification_domains = domains
    locked.active_verification_jurisdictions = jurisdictions
    locked.active_scope_configured = True
    locked.save(update_fields=[
        "active_verification_domains",
        "active_verification_jurisdictions",
        "active_scope_configured",
        "updated_at",
    ])
    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_ACTIVATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=locked.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=actor,
        authority_organization=locked,
        capability=PartnerCapability.MANAGE_ORGANIZATION,
        previous_state={"domains": old_domains, "jurisdictions": old_jurisdictions},
        new_state={"domains": domains, "jurisdictions": jurisdictions},
        notes=reason,
    )
    return locked


def serialize_organization_scope(organization):
    active_domains, active_jurisdictions = effective_organization_scope(organization)
    return {
        "organization_id": str(organization.pk),
        "requested_domains": organization.requested_verification_domains,
        "requested_jurisdictions": organization.requested_verification_jurisdictions,
        "approved_domains": organization.approved_verification_domains,
        "approved_jurisdictions": organization.approved_verification_jurisdictions,
        "active_domains": active_domains,
        "active_jurisdictions": active_jurisdictions,
    }
