from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .accountability_service import record_accountability_event
from .models import (
    AccountabilityEvent,
    FactualCorrectionRequest,
    ModerationCase,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    VerificationAssignment,
)
from .organization_invitation_service import (
    generate_invitation_token,
    hash_invitation_token,
)


MANAGE_PARTNER_ORGANIZATION = "MANAGE_PARTNER_ORGANIZATION"
PARTNERSHIP_ENDED_REASON = "PARTNERSHIP_ENDED"
ORGANIZATION_VERIFIED_REASON = "ORGANIZATION_VERIFIED"
ORGANIZATION_VERIFICATION_REJECTED_REASON = "ORGANIZATION_VERIFICATION_REJECTED"
PARTNERSHIP_ACTIVATED_REASON = "PARTNERSHIP_ACTIVATED"
PARTNERSHIP_SUSPENDED_REASON = "PARTNERSHIP_SUSPENDED"
PARTNERSHIP_REINSTATED_REASON = "PARTNERSHIP_REINSTATED"

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
        context=context or {},
    )


def _has_prior_partner_work(organization):
    return (
        organization.verification_assignments.exists()
        or organization.official_fact_checks.exists()
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
    active_factual_corrections = organization.factual_correction_requests.filter(
        status=FactualCorrectionRequest.Status.ACTIVE
    ).count()
    has_prior_partner_work = _has_prior_partner_work(organization)

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
        organization.partner_status
        in {
            Organization.PartnerStatus.SUSPENDED,
            Organization.PartnerStatus.FORMER,
        }
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
        },
        "can_end_partnership": end_partnership_eligible and not blockers,
        "end_partnership_blockers": blockers,
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


def _record_organization_transition(*, organization, actor, previous_state, reason_code):
    return _record_platform_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        actor=actor,
        organization=organization,
        previous_state=previous_state,
        new_state=_organization_status_state(organization),
        reason_code=reason_code,
        context={"transition": reason_code},
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
        and _has_prior_partner_work(organization)
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
    if _has_prior_partner_work(organization):
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
    if _has_prior_partner_work(organization):
        raise OrganizationPartnershipLifecycleConflict(
            "This organization has prior Partner verification work and must complete "
            "the governed retirement flow before any later reinstatement."
        )

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
def suspend_partner_organization_partnership(*, organization_id, actor):
    _require_platform_management_authority(actor)
    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    if organization.partner_status != Organization.PartnerStatus.ACTIVE:
        raise OrganizationPartnershipLifecycleConflict(
            "Only an active Partner Organization can be suspended."
        )

    previous_state = _organization_status_state(organization)
    organization.partner_status = Organization.PartnerStatus.SUSPENDED
    organization.save(update_fields=["partner_status", "updated_at"])
    _record_organization_transition(
        organization=organization,
        actor=actor,
        previous_state=previous_state,
        reason_code=PARTNERSHIP_SUSPENDED_REASON,
    )
    return organization


@transaction.atomic
def reinstate_partner_organization_partnership(*, organization_id, actor):
    _require_platform_management_authority(actor)
    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    if organization.partner_status not in {
        Organization.PartnerStatus.SUSPENDED,
        Organization.PartnerStatus.FORMER,
    }:
        raise OrganizationPartnershipLifecycleConflict(
            "Only suspended or former Partner Organizations can be reinstated."
        )
    if organization.verification_status != Organization.VerificationStatus.VERIFIED:
        raise OrganizationPartnershipLifecycleConflict(
            "Verify this organization before reinstating its partnership."
        )

    previous_state = _organization_status_state(organization)
    organization.partner_status = Organization.PartnerStatus.ACTIVE
    organization.save(update_fields=["partner_status", "updated_at"])
    _record_organization_transition(
        organization=organization,
        actor=actor,
        previous_state=previous_state,
        reason_code=PARTNERSHIP_REINSTATED_REASON,
    )
    return organization


def _ensure_endable_partnership(organization):
    if organization.partner_status == Organization.PartnerStatus.FORMER:
        raise OrganizationPartnershipLifecycleConflict(
            "This organization is already a former Partner Organization."
        )
    if (
        organization.partner_status == Organization.PartnerStatus.NONE
        and not _has_prior_partner_work(organization)
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
def end_partner_organization_partnership(*, organization_id, actor):
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

    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=organization_id
    )
    _ensure_endable_partnership(organization)
    _ensure_no_active_factual_correction(organization)

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

    _record_platform_event(
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
        },
    )

    return {
        "organization": organization,
        "ended_memberships": len(ended_memberships),
        "cancelled_invitations": len(cancelled_invitations),
        "requeued_investigations": len(replacements),
    }
