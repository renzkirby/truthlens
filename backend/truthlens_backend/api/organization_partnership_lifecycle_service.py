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
        reason_code=PARTNERSHIP_ENDED_REASON,
        context=context or {},
    )


def _ensure_endable_partnership(organization):
    if organization.partner_status == Organization.PartnerStatus.FORMER:
        raise OrganizationPartnershipLifecycleConflict(
            "This organization is already a former Partner Organization."
        )
    if organization.partner_status == Organization.PartnerStatus.NONE:
        raise OrganizationPartnershipLifecycleConflict(
            "This organization does not have an active or suspended partnership to end."
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
        ModerationCase.objects.select_for_update()
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
