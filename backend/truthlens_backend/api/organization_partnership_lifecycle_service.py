from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .accountability_service import record_accountability_event
from .models import (
    AccountabilityEvent,
    FactualCorrectionRequest,
    ModerationCase,
    Organization,
    OrganizationGovernanceSupportingBasis,
    OrganizationInvitation,
    OrganizationMembership,
    VerificationAssignment,
)
from .organization_invitation_service import (
    generate_invitation_token,
    hash_invitation_token,
)
from .organization_governance_notice_service import (
    persist_governance_notice_recipients,
    snapshot_governance_notice_recipients,
)
from .organization_partnership_policy import (
    get_organization_admin_onboarding_policy,
    organization_has_prior_partner_work,
)


MANAGE_PARTNER_ORGANIZATION = "MANAGE_PARTNER_ORGANIZATION"
PARTNERSHIP_ENDED_REASON = "PARTNERSHIP_ENDED"
ORGANIZATION_VERIFIED_REASON = "ORGANIZATION_VERIFIED"
ORGANIZATION_VERIFICATION_REJECTED_REASON = "ORGANIZATION_VERIFICATION_REJECTED"
PARTNERSHIP_ACTIVATED_REASON = "PARTNERSHIP_ACTIVATED"
PARTNERSHIP_SUSPENDED_REASON = "PARTNERSHIP_SUSPENDED"
PARTNERSHIP_REINSTATED_REASON = "PARTNERSHIP_REINSTATED"

PARTNERSHIP_FACTOR_CHOICES = (
    ("VERIFICATION_STANDARDS", "Verification Standards Violation"),
    ("IMPARTIALITY_CONFLICT", "Impartiality or Conflict-of-Interest Violation"),
    ("TRANSPARENCY_MISREPRESENTATION", "Transparency or Misrepresentation Violation"),
    ("CORRECTIONS_ACCOUNTABILITY", "Correction or Accountability Failure"),
    ("PLATFORM_PARTNERSHIP", "Platform or Partnership Policy Violation"),
    ("GOVERNANCE_CAPACITY", "Organizational Governance or Capacity Concern"),
    ("SECURITY_INTEGRITY", "Security, Legal, or Institutional Integrity Risk"),
    ("INACTIVITY_RESPONSIVENESS", "Inactivity or Non-responsiveness"),
    ("OTHER", "Other"),
)
PARTNERSHIP_SEVERITY_CHOICES = (
    ("LOW", "Low"),
    ("MODERATE", "Moderate"),
    ("HIGH", "High"),
    ("CRITICAL", "Critical"),
)
PARTNERSHIP_SUSPENSION_TYPE_CHOICES = (
    ("REMEDIAL", "Remedial Suspension"),
    ("PRECAUTIONARY", "Precautionary Suspension"),
    ("ADMINISTRATIVE", "Administrative Suspension"),
)
PARTNERSHIP_ENDING_TYPE_CHOICES = (
    ("VOLUNTARY_WITHDRAWAL", "Voluntary Withdrawal"),
    ("ADMINISTRATIVE_CONCLUSION", "Administrative Conclusion"),
    ("TERMINATION_FOR_CAUSE", "Termination for Cause"),
)
PARTNERSHIP_ENDING_GROUND_CHOICES = (
    ("VOLUNTARY_WITHDRAWAL", "Voluntary Withdrawal"),
    ("PERMANENT_LOSS_ELIGIBILITY", "Permanent Loss of Eligibility or Capacity"),
    ("ORGANIZATION_DISSOLVED", "Organization Dissolved or Ceased Relevant Operations"),
    ("PROLONGED_ABANDONMENT", "Prolonged Inactivity or Partnership Abandonment"),
    ("SEVERE_NON_REMEDIABLE_VIOLATION", "Severe Non-remediable Violation"),
    ("REPEATED_SYSTEMIC_VIOLATIONS", "Repeated or Systemic Serious Violations"),
    ("FAILED_REMEDIATION", "Failed Remediation"),
)
PARTNERSHIP_REINSTATEMENT_BASIS_CHOICES = (
    ("REMEDIATION_COMPLETED", "Required Remediation Completed"),
    ("UNDERLYING_RISK_RESOLVED", "Underlying Risk Resolved"),
    (
        "INVESTIGATION_DID_NOT_JUSTIFY_CONTINUED_SUSPENSION",
        "Investigation Did Not Justify Continued Suspension",
    ),
    ("OPERATIONAL_REQUIREMENTS_RESTORED", "Operational Requirements Restored"),
    (
        "CONTINUED_RESTRICTION_NO_LONGER_PROPORTIONATE",
        "Continued Restriction No Longer Proportionate",
    ),
)

_PARTNERSHIP_FACTORS = {value for value, _label in PARTNERSHIP_FACTOR_CHOICES}
_PARTNERSHIP_SEVERITIES = {value for value, _label in PARTNERSHIP_SEVERITY_CHOICES}
_PARTNERSHIP_SUSPENSION_TYPES = {
    value for value, _label in PARTNERSHIP_SUSPENSION_TYPE_CHOICES
}
_PARTNERSHIP_ENDING_TYPES = {
    value for value, _label in PARTNERSHIP_ENDING_TYPE_CHOICES
}
_PARTNERSHIP_ENDING_GROUNDS = {
    value for value, _label in PARTNERSHIP_ENDING_GROUND_CHOICES
}
_PARTNERSHIP_REINSTATEMENT_BASES = {
    value for value, _label in PARTNERSHIP_REINSTATEMENT_BASIS_CHOICES
}
_PROHIBITED_RATIONALE_PLACEHOLDERS = {
    "policy violation",
    "bad organization",
    "admin decision",
    "failed verification",
    "failed standards",
    "other issues",
}
_ADMINISTRATIVE_ENDING_GROUNDS = {
    "PERMANENT_LOSS_ELIGIBILITY",
    "ORGANIZATION_DISSOLVED",
    "PROLONGED_ABANDONMENT",
}
_FOR_CAUSE_ENDING_GROUNDS = {
    "SEVERE_NON_REMEDIABLE_VIOLATION",
    "REPEATED_SYSTEMIC_VIOLATIONS",
    "FAILED_REMEDIATION",
}

ACTIVE_FACTUAL_CASE_STATUSES = {
    ModerationCase.Status.OPEN,
    ModerationCase.Status.IN_REVIEW,
    ModerationCase.Status.ESCALATED,
    ModerationCase.Status.REOPENED,
}


class OrganizationPartnershipLifecycleError(ValueError):
    pass


class OrganizationPartnershipLifecycleAuthorizationError(
    OrganizationPartnershipLifecycleError
):
    pass


class OrganizationPartnershipLifecycleConflict(OrganizationPartnershipLifecycleError):
    pass


def _normalize_required_text(value, *, field_name):
    normalized = str(value or "").strip()
    if not normalized:
        raise OrganizationPartnershipLifecycleConflict(
            f"{field_name} is required."
        )
    return normalized


def _normalize_optional_text(value):
    return str(value or "").strip()


def _normalize_rationale(value, *, field_name):
    rationale = _normalize_required_text(value, field_name=field_name)
    normalized_placeholder = " ".join(rationale.lower().rstrip(".:;").split())
    if len(rationale) < 20 or normalized_placeholder in _PROHIBITED_RATIONALE_PLACEHOLDERS:
        raise OrganizationPartnershipLifecycleConflict(
            f"{field_name} must provide a specific factual explanation."
        )
    return rationale


def _normalize_supporting_references(references):
    if references is None:
        return []
    if not isinstance(references, (list, tuple)):
        raise OrganizationPartnershipLifecycleConflict(
            "Supporting references must be provided as a list."
        )
    if len(references) > 10:
        raise OrganizationPartnershipLifecycleConflict(
            "No more than 10 supporting references may be recorded."
        )

    normalized = []
    for reference in references:
        value = str(reference or "").strip()
        if not value:
            continue
        if len(value) > 500:
            raise OrganizationPartnershipLifecycleConflict(
                "Each supporting reference must be 500 characters or fewer."
            )
        if value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_other_factor_explanation(*, factors, explanation):
    explanation = _normalize_optional_text(explanation)
    if "OTHER" in factors:
        if not explanation:
            raise OrganizationPartnershipLifecycleConflict(
                "Explain the underlying standard and why the established factors do not fit."
            )
        if len(explanation) < 20:
            raise OrganizationPartnershipLifecycleConflict(
                "Other-factor explanation must be specific enough to understand the standard used."
            )
        return explanation

    if explanation:
        raise OrganizationPartnershipLifecycleConflict(
            "Other-factor explanation is only valid when Other is selected."
        )
    return ""


def _normalize_factors(factors, *, required):
    if factors is None:
        factors = []
    if not isinstance(factors, (list, tuple)):
        raise OrganizationPartnershipLifecycleConflict(
            "Partnership factors must be provided as a list."
        )

    normalized = []
    for factor in factors:
        value = str(factor or "").strip()
        if value not in _PARTNERSHIP_FACTORS:
            raise OrganizationPartnershipLifecycleConflict(
                "Select a valid partnership factor."
            )
        if value not in normalized:
            normalized.append(value)

    if required and not normalized:
        raise OrganizationPartnershipLifecycleConflict(
            "At least one partnership factor is required."
        )
    return normalized


def _validate_suspension_governance_metadata(
    *,
    suspension_type,
    factors,
    severity,
    rationale,
    policy_basis,
    supporting_basis,
    supporting_references=None,
    other_factor_explanation="",
    remediation_problem="",
    remediation_required_action="",
    remediation_evidence_required="",
    remediation_deadline=None,
    remediation_review_method="",
    remediation_failure_consequence="",
    review_date=None,
):
    suspension_type = str(suspension_type or "").strip()
    if suspension_type not in _PARTNERSHIP_SUSPENSION_TYPES:
        raise OrganizationPartnershipLifecycleConflict(
            "Select a valid suspension type."
        )

    severity = str(severity or "").strip()
    if severity not in _PARTNERSHIP_SEVERITIES:
        raise OrganizationPartnershipLifecycleConflict(
            "Select a valid suspension severity."
        )

    factors = _normalize_factors(factors, required=True)
    rationale = _normalize_rationale(
        rationale,
        field_name="Suspension rationale",
    )
    policy_basis = _normalize_required_text(
        policy_basis,
        field_name="Policy basis",
    )
    supporting_basis = _normalize_required_text(
        supporting_basis,
        field_name="Internal supporting basis",
    )
    supporting_references = _normalize_supporting_references(
        supporting_references
    )
    other_factor_explanation = _normalize_other_factor_explanation(
        factors=factors,
        explanation=other_factor_explanation,
    )

    remediation = None
    remediation_values = {
        "problem": _normalize_optional_text(remediation_problem),
        "required_action": _normalize_optional_text(remediation_required_action),
        "evidence_required": _normalize_optional_text(remediation_evidence_required),
        "deadline": (
            remediation_deadline.isoformat()
            if remediation_deadline is not None
            else None
        ),
        "review_method": _normalize_optional_text(remediation_review_method),
        "failure_consequence": _normalize_optional_text(
            remediation_failure_consequence
        ),
    }
    has_remediation_values = any(
        value for value in remediation_values.values()
    )

    if suspension_type == "REMEDIAL":
        missing = [
            label
            for key, label in (
                ("problem", "Remediation problem"),
                ("required_action", "Required remediation action"),
                ("evidence_required", "Evidence of compliance"),
                ("review_method", "Remediation review method"),
                ("failure_consequence", "Consequence of remediation failure"),
            )
            if not remediation_values[key]
        ]
        if remediation_values["deadline"] is None:
            missing.append("Remediation deadline")
        if missing:
            raise OrganizationPartnershipLifecycleConflict(
                f"{', '.join(missing)} must be recorded for a remedial suspension."
            )
        remediation = remediation_values
    elif has_remediation_values:
        raise OrganizationPartnershipLifecycleConflict(
            "Structured remediation fields are only valid for a remedial suspension."
        )

    if suspension_type == "PRECAUTIONARY" and review_date is None:
        raise OrganizationPartnershipLifecycleConflict(
            "A review date is required for a precautionary suspension."
        )

    return {
        "suspension_type": suspension_type,
        "factors": factors,
        "severity": severity,
        "policy_basis": policy_basis,
        "other_factor_explanation": other_factor_explanation,
        "remediation": remediation,
        "review_date": review_date.isoformat() if review_date is not None else None,
    }, rationale, supporting_basis, supporting_references


def _validate_partnership_ending_governance_metadata(
    *,
    ending_type,
    ground,
    factors,
    severity,
    rationale,
    policy_basis,
    supporting_basis,
    supporting_references=None,
    other_factor_explanation="",
):
    ending_type = str(ending_type or "").strip()
    if ending_type not in _PARTNERSHIP_ENDING_TYPES:
        raise OrganizationPartnershipLifecycleConflict(
            "Select a valid partnership ending type."
        )

    ground = str(ground or "").strip()
    if ground not in _PARTNERSHIP_ENDING_GROUNDS:
        raise OrganizationPartnershipLifecycleConflict(
            "Select a valid partnership ending ground."
        )

    if ending_type == "VOLUNTARY_WITHDRAWAL":
        if ground != "VOLUNTARY_WITHDRAWAL":
            raise OrganizationPartnershipLifecycleConflict(
                "Voluntary withdrawal must use the voluntary-withdrawal ground."
            )
        factors = _normalize_factors(factors, required=False)
        if factors:
            raise OrganizationPartnershipLifecycleConflict(
                "Voluntary withdrawal must not be classified as a policy violation."
            )
        severity = ""
    elif ending_type == "ADMINISTRATIVE_CONCLUSION":
        if ground not in _ADMINISTRATIVE_ENDING_GROUNDS:
            raise OrganizationPartnershipLifecycleConflict(
                "Select an administrative partnership-ending ground."
            )
        factors = _normalize_factors(factors, required=False)
        severity = ""
    else:
        if ground not in _FOR_CAUSE_ENDING_GROUNDS:
            raise OrganizationPartnershipLifecycleConflict(
                "Select a termination-for-cause ground."
            )
        factors = _normalize_factors(factors, required=True)
        severity = str(severity or "").strip()
        if severity not in {"HIGH", "CRITICAL"}:
            raise OrganizationPartnershipLifecycleConflict(
                "Termination for cause requires High or Critical severity."
            )

    rationale = _normalize_rationale(
        rationale,
        field_name="Partnership-ending rationale",
    )
    policy_basis = _normalize_required_text(
        policy_basis,
        field_name="Policy basis",
    )
    supporting_basis = _normalize_required_text(
        supporting_basis,
        field_name="Internal supporting basis",
    )
    supporting_references = _normalize_supporting_references(
        supporting_references
    )
    other_factor_explanation = _normalize_other_factor_explanation(
        factors=factors,
        explanation=other_factor_explanation,
    )

    return {
        "ending_type": ending_type,
        "ground": ground,
        "factors": factors,
        "severity": severity or None,
        "policy_basis": policy_basis,
        "other_factor_explanation": other_factor_explanation,
    }, rationale, supporting_basis, supporting_references


def _validate_reinstatement_governance_metadata(
    *,
    basis,
    rationale,
    supporting_basis,
    supporting_references=None,
    completed_remediation="",
    continuing_conditions="",
    monitoring_end_date=None,
    monitoring_success_criteria="",
    monitoring_recurrence_consequence="",
):
    basis = str(basis or "").strip()
    if basis not in _PARTNERSHIP_REINSTATEMENT_BASES:
        raise OrganizationPartnershipLifecycleConflict(
            "Select a valid reinstatement basis."
        )

    rationale = _normalize_rationale(
        rationale,
        field_name="Reinstatement rationale",
    )
    supporting_basis = _normalize_required_text(
        supporting_basis,
        field_name="Internal supporting basis",
    )
    supporting_references = _normalize_supporting_references(
        supporting_references
    )
    completed_remediation = _normalize_optional_text(completed_remediation)
    if basis == "REMEDIATION_COMPLETED" and not completed_remediation:
        raise OrganizationPartnershipLifecycleConflict(
            "Completed remediation must be recorded for this reinstatement basis."
        )

    continuing_conditions = _normalize_optional_text(continuing_conditions)
    monitoring_success_criteria = _normalize_optional_text(
        monitoring_success_criteria
    )
    monitoring_recurrence_consequence = _normalize_optional_text(
        monitoring_recurrence_consequence
    )
    monitoring_values = (
        monitoring_end_date,
        monitoring_success_criteria,
        monitoring_recurrence_consequence,
    )
    if continuing_conditions:
        if (
            monitoring_end_date is None
            or not monitoring_success_criteria
            or not monitoring_recurrence_consequence
        ):
            raise OrganizationPartnershipLifecycleConflict(
                "Monitoring end date, success criteria, and recurrence consequence "
                "are required when continuing conditions apply."
            )
    elif any(monitoring_values):
        raise OrganizationPartnershipLifecycleConflict(
            "Monitoring details require continuing conditions."
        )

    return {
        "basis": basis,
        "completed_remediation": completed_remediation,
        "continuing_conditions": continuing_conditions,
        "monitoring_end_date": (
            monitoring_end_date.isoformat()
            if monitoring_end_date is not None
            else None
        ),
        "monitoring_success_criteria": monitoring_success_criteria,
        "monitoring_recurrence_consequence": monitoring_recurrence_consequence,
    }, rationale, supporting_basis, supporting_references

def _require_platform_management_authority(actor):
    if not (
        actor
        and actor.is_authenticated
        and actor.is_active
        and actor.is_superuser
    ):
        raise OrganizationPartnershipLifecycleAuthorizationError(
            "Platform management administrator access is required."
        )


def _record_platform_event(
    *,
    action_type,
    resource_type,
    resource_id,
    actor,
    organization,
    previous_state=None,
    new_state=None,
    context=None,
    reason_code=PARTNERSHIP_ENDED_REASON,
    notes="",
):
    return record_accountability_event(
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        authority_organization=None,
        subject_organization=organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous_state or {},
        new_state=new_state or {},
        reason_code=reason_code,
        notes=notes,
        context=context or {},
    )


def _record_governance_supporting_basis(
    *,
    governance_event,
    actor,
    summary,
    references,
):
    return OrganizationGovernanceSupportingBasis.objects.create(
        governance_event=governance_event,
        summary=summary,
        references=references,
        created_by=actor,
    )


def get_partner_organization_lifecycle_projection(organization):
    """Return derived governance state without mutating organization records."""

    current_memberships = organization.memberships.exclude(
        status=OrganizationMembership.Status.LEFT
    ).count()
    pending_invitations = organization.invitations.filter(
        status=OrganizationInvitation.Status.PENDING
    ).count()
    active_investigations = organization.verification_assignments.filter(
        status=VerificationAssignment.Status.ACTIVE
    ).count()
    active_factual_correction_rows = list(
        organization.factual_correction_requests.filter(
            status=FactualCorrectionRequest.Status.ACTIVE
        )
        .select_related("predecessor_fact_check")
        .order_by("requested_at", "id")
    )
    active_factual_corrections = len(active_factual_correction_rows)
    has_prior_partner_work = organization_has_prior_partner_work(organization)
    admin_onboarding = get_organization_admin_onboarding_policy(
        organization,
        has_prior_partner_work=has_prior_partner_work,
    )

    if organization.partner_status == Organization.PartnerStatus.ACTIVE:
        lifecycle_state = "ACTIVE_PARTNER"
        operational_access = (
            "ENABLED"
            if organization.verification_status == Organization.VerificationStatus.VERIFIED
            else "DISABLED"
        )
    elif organization.partner_status == Organization.PartnerStatus.SUSPENDED:
        lifecycle_state = "SUSPENDED_PARTNER"
        operational_access = "DISABLED"
    elif organization.partner_status == Organization.PartnerStatus.FORMER:
        lifecycle_state = "FORMER_PARTNER"
        operational_access = "DISABLED"
    elif (
        organization.partner_status == Organization.PartnerStatus.NONE
        and has_prior_partner_work
    ):
        lifecycle_state = "RETIREMENT_REQUIRED"
        operational_access = "DISABLED"
    elif organization.verification_status == Organization.VerificationStatus.REJECTED:
        lifecycle_state = "REJECTED"
        operational_access = "DISABLED"
    else:
        lifecycle_state = "ONBOARDING"
        operational_access = "SETUP_ONLY"

    end_partnership_eligible = (
        organization.partner_status
        in {
            Organization.PartnerStatus.ACTIVE,
            Organization.PartnerStatus.SUSPENDED,
        }
        or (
            organization.partner_status == Organization.PartnerStatus.NONE
            and has_prior_partner_work
        )
    )
    blockers = []
    if active_factual_corrections:
        blockers.append(
            {
                "code": "ACTIVE_FACTUAL_CORRECTION",
                "count": active_factual_corrections,
                "message": (
                    "Resolve or cancel active factual corrections before ending "
                    "this partnership."
                ),
            }
        )

    if not end_partnership_eligible:
        blockers.append(
            {
                "code": "PARTNERSHIP_NOT_ENDABLE",
                "count": 0,
                "message": "Only active or suspended partnerships can be ended.",
            }
        )

    can_verify = (
        organization.verification_status != Organization.VerificationStatus.VERIFIED
        and not (
            organization.partner_status == Organization.PartnerStatus.NONE
            and has_prior_partner_work
        )
    )
    can_reject_verification = (
        organization.partner_status == Organization.PartnerStatus.NONE
        and not has_prior_partner_work
        and organization.verification_status
        in {
            Organization.VerificationStatus.UNVERIFIED,
            Organization.VerificationStatus.PENDING,
        }
    )
    can_activate_partnership = (
        organization.partner_status == Organization.PartnerStatus.NONE
        and organization.verification_status == Organization.VerificationStatus.VERIFIED
        and not has_prior_partner_work
    )
    can_suspend_partnership = (
        organization.partner_status == Organization.PartnerStatus.ACTIVE
    )
    can_reinstate_partnership = (
        organization.partner_status == Organization.PartnerStatus.SUSPENDED
        and organization.verification_status == Organization.VerificationStatus.VERIFIED
    )

    return {
        "state": lifecycle_state,
        "operational_access": operational_access,
        "actions": {
            "can_verify": can_verify,
            "can_reject_verification": can_reject_verification,
            "can_activate_partnership": can_activate_partnership,
            "can_suspend_partnership": can_suspend_partnership,
            "can_reinstate_partnership": can_reinstate_partnership,
            "can_end_partnership": end_partnership_eligible and not blockers,
            "can_provision_organization_admin": admin_onboarding["allowed"],
        },
        "admin_onboarding": admin_onboarding,
        "can_end_partnership": end_partnership_eligible and not blockers,
        "end_partnership_blockers": blockers,
        "active_factual_corrections": [
            {
                "id": str(correction.id),
                "predecessor_fact_check_id": str(
                    correction.predecessor_fact_check_id
                ),
                "predecessor_headline": correction.predecessor_fact_check.headline,
                "correction_reason": correction.correction_reason,
                "requested_at": correction.requested_at.isoformat(),
            }
            for correction in active_factual_correction_rows
        ],
        "impact": {
            "current_memberships": current_memberships,
            "pending_invitations": pending_invitations,
            "active_investigations": active_investigations,
            "active_factual_corrections": active_factual_corrections,
        },
    }


def _organization_status_state(organization):
    return {
        "verification_status": organization.verification_status,
        "partner_status": organization.partner_status,
    }


def _record_organization_transition(
    *,
    organization,
    actor,
    previous_state,
    reason_code,
    notes="",
    context=None,
):
    event_context = {"transition": reason_code}
    if context:
        event_context.update(context)
    return _record_platform_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        actor=actor,
        organization=organization,
        previous_state=previous_state,
        new_state=_organization_status_state(organization),
        reason_code=reason_code,
        notes=notes,
        context=event_context,
    )


@transaction.atomic
def verify_partner_organization(*, organization_id, actor):
    _require_platform_management_authority(actor)
    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    if organization.verification_status == Organization.VerificationStatus.VERIFIED:
        raise OrganizationPartnershipLifecycleConflict(
            "This organization is already verified."
        )
    if (
        organization.partner_status == Organization.PartnerStatus.NONE
        and organization_has_prior_partner_work(organization)
    ):
        raise OrganizationPartnershipLifecycleConflict(
            "This organization has prior Partner verification work and must complete "
            "the governed retirement flow before verification can change."
        )

    previous_state = _organization_status_state(organization)
    organization.verification_status = Organization.VerificationStatus.VERIFIED
    organization.save(update_fields=["verification_status", "updated_at"])
    _record_organization_transition(
        organization=organization,
        actor=actor,
        previous_state=previous_state,
        reason_code=ORGANIZATION_VERIFIED_REASON,
    )
    return organization


@transaction.atomic
def reject_partner_organization_verification(*, organization_id, actor):
    _require_platform_management_authority(actor)
    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    if organization.partner_status != Organization.PartnerStatus.NONE:
        raise OrganizationPartnershipLifecycleConflict(
            "End or resolve the current partnership lifecycle before rejecting "
            "verification."
        )
    if organization_has_prior_partner_work(organization):
        raise OrganizationPartnershipLifecycleConflict(
            "This organization has prior Partner verification work and must use "
            "the governed retirement flow instead."
        )
    if organization.verification_status not in {
        Organization.VerificationStatus.UNVERIFIED,
        Organization.VerificationStatus.PENDING,
    }:
        raise OrganizationPartnershipLifecycleConflict(
            "Only unverified or pending organizations can be rejected."
        )

    previous_state = _organization_status_state(organization)
    organization.verification_status = Organization.VerificationStatus.REJECTED
    organization.save(update_fields=["verification_status", "updated_at"])
    _record_organization_transition(
        organization=organization,
        actor=actor,
        previous_state=previous_state,
        reason_code=ORGANIZATION_VERIFICATION_REJECTED_REASON,
    )
    return organization


@transaction.atomic
def activate_partner_organization_partnership(*, organization_id, actor):
    _require_platform_management_authority(actor)
    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    if organization.partner_status != Organization.PartnerStatus.NONE:
        raise OrganizationPartnershipLifecycleConflict(
            "Only an organization that is not currently a Partner can be activated."
        )
    if organization.verification_status != Organization.VerificationStatus.VERIFIED:
        raise OrganizationPartnershipLifecycleConflict(
            "Verify this organization before activating its partnership."
        )
    if organization_has_prior_partner_work(organization):
        raise OrganizationPartnershipLifecycleConflict(
            "This organization has prior Partner verification work and must complete "
            "the governed retirement flow before any later reinstatement."
        )

    notice_recipients = snapshot_governance_notice_recipients(organization)
    previous_state = _organization_status_state(organization)
    organization.partner_status = Organization.PartnerStatus.ACTIVE
    organization.save(update_fields=["partner_status", "updated_at"])
    _record_organization_transition(
        organization=organization,
        actor=actor,
        previous_state=previous_state,
        reason_code=PARTNERSHIP_ACTIVATED_REASON,
    )
    return organization


@transaction.atomic
def suspend_partner_organization_partnership(
    *,
    organization_id,
    actor,
    suspension_type,
    factors,
    severity,
    rationale,
    policy_basis,
    supporting_basis,
    supporting_references=None,
    other_factor_explanation="",
    remediation_problem="",
    remediation_required_action="",
    remediation_evidence_required="",
    remediation_deadline=None,
    remediation_review_method="",
    remediation_failure_consequence="",
    review_date=None,
):
    _require_platform_management_authority(actor)
    (
        governance_metadata,
        rationale,
        supporting_basis,
        supporting_references,
    ) = _validate_suspension_governance_metadata(
        suspension_type=suspension_type,
        factors=factors,
        severity=severity,
        rationale=rationale,
        policy_basis=policy_basis,
        supporting_basis=supporting_basis,
        supporting_references=supporting_references,
        other_factor_explanation=other_factor_explanation,
        remediation_problem=remediation_problem,
        remediation_required_action=remediation_required_action,
        remediation_evidence_required=remediation_evidence_required,
        remediation_deadline=remediation_deadline,
        remediation_review_method=remediation_review_method,
        remediation_failure_consequence=remediation_failure_consequence,
        review_date=review_date,
    )
    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    if organization.partner_status != Organization.PartnerStatus.ACTIVE:
        raise OrganizationPartnershipLifecycleConflict(
            "Only an active Partner Organization can be suspended."
        )

    notice_recipients = snapshot_governance_notice_recipients(organization)
    previous_state = _organization_status_state(organization)
    organization.partner_status = Organization.PartnerStatus.SUSPENDED
    organization.save(update_fields=["partner_status", "updated_at"])
    event = _record_organization_transition(
        organization=organization,
        actor=actor,
        previous_state=previous_state,
        reason_code=PARTNERSHIP_SUSPENDED_REASON,
        notes=rationale,
        context={"governance": governance_metadata},
    )
    _record_governance_supporting_basis(
        governance_event=event,
        actor=actor,
        summary=supporting_basis,
        references=supporting_references,
    )
    persist_governance_notice_recipients(
        governance_event=event,
        recipients=notice_recipients,
    )
    return organization


@transaction.atomic
def reinstate_partner_organization_partnership(
    *,
    organization_id,
    actor,
    basis,
    rationale,
    supporting_basis,
    supporting_references=None,
    completed_remediation="",
    continuing_conditions="",
    monitoring_end_date=None,
    monitoring_success_criteria="",
    monitoring_recurrence_consequence="",
):
    _require_platform_management_authority(actor)
    (
        governance_metadata,
        rationale,
        supporting_basis,
        supporting_references,
    ) = _validate_reinstatement_governance_metadata(
        basis=basis,
        rationale=rationale,
        supporting_basis=supporting_basis,
        supporting_references=supporting_references,
        completed_remediation=completed_remediation,
        continuing_conditions=continuing_conditions,
        monitoring_end_date=monitoring_end_date,
        monitoring_success_criteria=monitoring_success_criteria,
        monitoring_recurrence_consequence=monitoring_recurrence_consequence,
    )
    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    if organization.partner_status != Organization.PartnerStatus.SUSPENDED:
        raise OrganizationPartnershipLifecycleConflict(
            "Only a suspended Partner Organization can be reinstated."
        )
    if organization.verification_status != Organization.VerificationStatus.VERIFIED:
        raise OrganizationPartnershipLifecycleConflict(
            "Verify this organization before reinstating its partnership."
        )

    prior_suspension = (
        AccountabilityEvent.objects.filter(
            subject_organization=organization,
            reason_code=PARTNERSHIP_SUSPENDED_REASON,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    governance_metadata["prior_suspension_event_id"] = (
        str(prior_suspension.pk) if prior_suspension is not None else None
    )

    previous_state = _organization_status_state(organization)
    organization.partner_status = Organization.PartnerStatus.ACTIVE
    organization.save(update_fields=["partner_status", "updated_at"])
    event = _record_organization_transition(
        organization=organization,
        actor=actor,
        previous_state=previous_state,
        reason_code=PARTNERSHIP_REINSTATED_REASON,
        notes=rationale,
        context={"governance": governance_metadata},
    )
    _record_governance_supporting_basis(
        governance_event=event,
        actor=actor,
        summary=supporting_basis,
        references=supporting_references,
    )
    persist_governance_notice_recipients(
        governance_event=event,
        recipients=notice_recipients,
    )
    return organization


def _ensure_endable_partnership(organization):
    if organization.partner_status == Organization.PartnerStatus.FORMER:
        raise OrganizationPartnershipLifecycleConflict(
            "This organization is already a former Partner Organization."
        )
    if (
        organization.partner_status == Organization.PartnerStatus.NONE
        and not organization_has_prior_partner_work(organization)
    ):
        raise OrganizationPartnershipLifecycleConflict(
            "This organization has no prior Partner verification work to retire."
        )


def _ensure_no_active_factual_correction(organization):
    active_request = (
        FactualCorrectionRequest.objects.select_for_update(of=("self",))
        .filter(
            organization=organization,
            status=FactualCorrectionRequest.Status.ACTIVE,
        )
        .first()
    )
    if active_request is not None:
        raise OrganizationPartnershipLifecycleConflict(
            "Resolve or cancel the active factual correction before ending this "
            "organization's partnership."
        )


def _relinquish_active_investigations(*, organization, actor, now):
    assignments = list(
        VerificationAssignment.objects.select_for_update(of=("self",))
        .filter(
            organization=organization,
            status=VerificationAssignment.Status.ACTIVE,
        )
        .select_related("claim", "claimed_by")
        .order_by("created_at", "id")
    )

    if not assignments:
        return []

    claim_ids = [assignment.claim_id for assignment in assignments]

    cases = list(
        ModerationCase.objects.select_for_update(of=("self",))
        .filter(
            organization=organization,
            status__in=ACTIVE_FACTUAL_CASE_STATUSES,
        )
        .filter(
            Q(
                case_type=ModerationCase.CaseType.ADJUDICATION,
                claim_id__in=claim_ids,
            )
            | Q(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission__thread__claim_id__in=claim_ids,
            )
        )
    )

    for case in cases:
        case.organization = None
        case.assigned_to = None
        case.assigned_at = None
        case.save(
            update_fields=[
                "organization",
                "assigned_to",
                "assigned_at",
                "updated_at",
            ]
        )

    replacements = []
    for assignment in assignments:
        assignment.status = VerificationAssignment.Status.RELEASED
        assignment.released_at = now
        assignment.save(
            update_fields=[
                "status",
                "released_at",
                "updated_at",
            ]
        )

        replacement = VerificationAssignment.objects.create(
            claim=assignment.claim,
            status=VerificationAssignment.Status.AVAILABLE,
        )
        replacements.append(replacement)

        _record_platform_event(
            action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_RELEASED,
            resource_type=AccountabilityEvent.ResourceType.VERIFICATION_ASSIGNMENT,
            resource_id=assignment.pk,
            actor=actor,
            organization=organization,
            previous_state={
                "status": VerificationAssignment.Status.ACTIVE,
                "organization_id": str(organization.pk),
                "claimed_by_id": (
                    str(assignment.claimed_by_id)
                    if assignment.claimed_by_id is not None
                    else None
                ),
            },
            new_state={
                "status": VerificationAssignment.Status.RELEASED,
                "organization_id": str(organization.pk),
                "claimed_by_id": (
                    str(assignment.claimed_by_id)
                    if assignment.claimed_by_id is not None
                    else None
                ),
            },
            context={
                "claim_id": str(assignment.claim_id),
                "replacement_assignment_id": str(replacement.pk),
            },
        )

        record_accountability_event(
            action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CREATED,
            resource_type=AccountabilityEvent.ResourceType.VERIFICATION_ASSIGNMENT,
            resource_id=replacement.pk,
            authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
            new_state={
                "status": replacement.status,
                "claim_id": str(assignment.claim_id),
            },
            reason_code=PARTNERSHIP_ENDED_REASON,
            context={
                "replaces_assignment_id": str(assignment.pk),
                "former_organization_id": str(organization.pk),
            },
        )

    return replacements


def _end_current_memberships(*, organization, actor):
    memberships = list(
        OrganizationMembership.objects.select_for_update(of=("self",))
        .filter(organization=organization)
        .exclude(status=OrganizationMembership.Status.LEFT)
        .select_related("user")
        .order_by("joined_at", "id")
    )

    for membership in memberships:
        previous_status = membership.status
        membership.status = OrganizationMembership.Status.LEFT
        membership.save(update_fields=["status"])

        _record_platform_event(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_REMOVED,
            resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_MEMBERSHIP,
            resource_id=membership.pk,
            actor=actor,
            organization=organization,
            previous_state={
                "role": membership.role,
                "status": previous_status,
            },
            new_state={
                "role": membership.role,
                "status": membership.status,
            },
            context={"user_id": str(membership.user_id)},
        )

    return memberships


def _cancel_pending_invitations(*, organization, actor, now):
    invitations = list(
        OrganizationInvitation.objects.select_for_update(of=("self",))
        .filter(
            organization=organization,
            status=OrganizationInvitation.Status.PENDING,
        )
        .order_by("created_at", "id")
    )

    for invitation in invitations:
        invitation.status = OrganizationInvitation.Status.CANCELLED
        invitation.cancelled_by = actor
        invitation.cancelled_at = now
        invitation.token_digest = hash_invitation_token(
            generate_invitation_token()
        )
        invitation.save(
            update_fields=[
                "status",
                "cancelled_by",
                "cancelled_at",
                "token_digest",
                "updated_at",
            ]
        )

        _record_platform_event(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED,
            resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
            resource_id=invitation.pk,
            actor=actor,
            organization=organization,
            previous_state={
                "status": OrganizationInvitation.Status.PENDING,
                "invitation_purpose": invitation.purpose,
                "invited_role": invitation.invited_role,
                "send_count": invitation.send_count,
            },
            new_state={
                "status": invitation.status,
                "invitation_purpose": invitation.purpose,
                "invited_role": invitation.invited_role,
                "send_count": invitation.send_count,
            },
        )

    return invitations


@transaction.atomic
def end_partner_organization_partnership(
    *,
    organization_id,
    actor,
    ending_type,
    ground,
    factors,
    severity,
    rationale,
    policy_basis,
    supporting_basis,
    supporting_references=None,
    other_factor_explanation="",
):
    """
    End a current partnership without deleting institutional history.

    Completed verification records, adjudications, publications, and authorship
    are intentionally untouched. Current memberships and invitations are closed,
    while active investigation ownership is relinquished back to shared intake.

    An active factual correction blocks the transition because it belongs to an
    already-published institutional record and requires an explicit resolution
    rather than silent abandonment.
    """

    _require_platform_management_authority(actor)
    (
        governance_metadata,
        rationale,
        supporting_basis,
        supporting_references,
    ) = _validate_partnership_ending_governance_metadata(
        ending_type=ending_type,
        ground=ground,
        factors=factors,
        severity=severity,
        rationale=rationale,
        policy_basis=policy_basis,
        supporting_basis=supporting_basis,
        supporting_references=supporting_references,
        other_factor_explanation=other_factor_explanation,
    )

    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    _ensure_endable_partnership(organization)
    _ensure_no_active_factual_correction(organization)

    notice_recipients = snapshot_governance_notice_recipients(organization)
    previous_state = {
        "verification_status": organization.verification_status,
        "partner_status": organization.partner_status,
    }
    now = timezone.now()

    replacements = _relinquish_active_investigations(
        organization=organization,
        actor=actor,
        now=now,
    )
    ended_memberships = _end_current_memberships(
        organization=organization,
        actor=actor,
    )
    cancelled_invitations = _cancel_pending_invitations(
        organization=organization,
        actor=actor,
        now=now,
    )

    organization.partner_status = Organization.PartnerStatus.FORMER
    organization.save(update_fields=["partner_status", "updated_at"])

    event = _record_platform_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        actor=actor,
        organization=organization,
        previous_state=previous_state,
        new_state={
            "verification_status": organization.verification_status,
            "partner_status": organization.partner_status,
        },
        context={
            "transition": PARTNERSHIP_ENDED_REASON,
            "ended_memberships": len(ended_memberships),
            "cancelled_invitations": len(cancelled_invitations),
            "requeued_investigations": len(replacements),
            "governance": governance_metadata,
        },
        notes=rationale,
    )
    _record_governance_supporting_basis(
        governance_event=event,
        actor=actor,
        summary=supporting_basis,
        references=supporting_references,
    )

    persist_governance_notice_recipients(
        governance_event=event,
        recipients=notice_recipients,
    )

    return {
        "organization": organization,
        "ended_memberships": len(ended_memberships),
        "cancelled_invitations": len(cancelled_invitations),
        "requeued_investigations": len(replacements),
    }



@transaction.atomic
def apply_legacy_platform_trust_transition(
    *,
    organization_id,
    actor,
    verification_status=None,
    partner_status=None,
):
    """
    Compatibility adapter for the pre-lifecycle Management Console endpoint.

    This deliberately does not write status fields directly. Requested legacy
    target values are translated into the same explicit governed transitions
    used by the current Management Console. Unsupported historical target
    combinations fail closed.
    """

    _require_platform_management_authority(actor)

    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    requested_verification = (
        verification_status
        if verification_status is not None
        else organization.verification_status
    )
    requested_partner = (
        partner_status
        if partner_status is not None
        else organization.partner_status
    )

    if requested_verification not in {
        organization.verification_status,
        Organization.VerificationStatus.VERIFIED,
        Organization.VerificationStatus.REJECTED,
    }:
        raise OrganizationPartnershipLifecycleConflict(
            "This verification status change requires an explicit governance "
            "workflow and cannot be applied through the legacy endpoint."
        )

    if requested_partner == Organization.PartnerStatus.FORMER:
        raise OrganizationPartnershipLifecycleConflict(
            "Use the governed End Partnership action to retire a Partner "
            "Organization."
        )
    if requested_partner not in {
        organization.partner_status,
        Organization.PartnerStatus.ACTIVE,
        Organization.PartnerStatus.SUSPENDED,
        Organization.PartnerStatus.NONE,
    }:
        raise OrganizationPartnershipLifecycleConflict(
            "This partnership status change is not supported by the legacy endpoint."
        )
    if (
        requested_partner == Organization.PartnerStatus.NONE
        and organization.partner_status != Organization.PartnerStatus.NONE
    ):
        raise OrganizationPartnershipLifecycleConflict(
            "A current partnership cannot be reset to Not a Partner. Use Suspend "
            "or End Partnership."
        )
    if (
        requested_verification == Organization.VerificationStatus.REJECTED
        and requested_partner != Organization.PartnerStatus.NONE
    ):
        raise OrganizationPartnershipLifecycleConflict(
            "A rejected organization cannot be activated or retained as a current "
            "Partner."
        )

    if requested_verification != organization.verification_status:
        if requested_verification == Organization.VerificationStatus.VERIFIED:
            organization = verify_partner_organization(
                organization_id=organization.pk,
                actor=actor,
            )
        else:
            organization = reject_partner_organization_verification(
                organization_id=organization.pk,
                actor=actor,
            )

    organization.refresh_from_db()

    if requested_partner != organization.partner_status:
        if requested_partner == Organization.PartnerStatus.ACTIVE:
            if organization.partner_status == Organization.PartnerStatus.NONE:
                organization = activate_partner_organization_partnership(
                    organization_id=organization.pk,
                    actor=actor,
                )
            elif organization.partner_status == Organization.PartnerStatus.SUSPENDED:
                raise OrganizationPartnershipLifecycleConflict(
                    "Use the governed Reinstate Partnership action so the reinstatement "
                    "basis and supporting record are documented."
                )
            elif organization.partner_status == Organization.PartnerStatus.FORMER:
                raise OrganizationPartnershipLifecycleConflict(
                    "A former partnership cannot be reinstated. A future partnership "
                    "requires a fresh eligibility and activation process."
                )
            else:
                raise OrganizationPartnershipLifecycleConflict(
                    "This organization cannot be activated from its current state."
                )
        elif requested_partner == Organization.PartnerStatus.SUSPENDED:
            raise OrganizationPartnershipLifecycleConflict(
                "Use the governed Suspend Partnership action so the suspension "
                "type, factors, severity, and reason are recorded."
            )
        else:
            raise OrganizationPartnershipLifecycleConflict(
                "This partnership status change requires an explicit governance "
                "workflow."
            )

    return organization
