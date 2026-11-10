"""Partner Organization suspension reconsideration workflow."""

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from .accountability_service import record_accountability_event
from .models import (
    AccountabilityEvent,
    Organization,
    OrganizationGovernanceNoticeRecipient,
    OrganizationGovernanceReconsideration,
    OrganizationMembership,
)
from .organization_partnership_lifecycle_service import (
    MANAGE_PARTNER_ORGANIZATION,
    PARTNERSHIP_SUSPENDED_REASON,
    reinstate_partner_organization_partnership,
)


RECONSIDERATION_GROUND_CHOICES = (
    ("MATERIAL_FACTS_INCORRECT", "Material facts are incorrect"),
    ("RELEVANT_EVIDENCE_OVERLOOKED", "Relevant evidence was overlooked"),
    ("POLICY_MISAPPLIED", "Policy was incorrectly applied"),
    ("SIGNIFICANT_PROCEDURAL_ERROR", "A significant procedural error occurred"),
)

OPEN_RECONSIDERATION_STATUSES = {
    OrganizationGovernanceReconsideration.Status.SUBMITTED,
    OrganizationGovernanceReconsideration.Status.UNDER_REVIEW,
}


class GovernanceReconsiderationError(Exception):
    pass


class GovernanceReconsiderationAuthorizationError(GovernanceReconsiderationError):
    pass


class GovernanceReconsiderationConflict(GovernanceReconsiderationError):
    pass


class GovernanceReconsiderationValidationError(GovernanceReconsiderationError):
    def __init__(self, message, *, field=None):
        super().__init__(message)
        self.field = field


def _require_platform_admin(actor):
    if not (
        actor
        and actor.is_authenticated
        and actor.is_active
        and actor.is_superuser
    ):
        raise GovernanceReconsiderationAuthorizationError(
            "Platform management administrator access is required."
        )


def _latest_suspension_event(organization):
    return (
        AccountabilityEvent.objects.filter(
            subject_organization=organization,
            reason_code=PARTNERSHIP_SUSPENDED_REASON,
            resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        )
        .order_by("-created_at", "-id")
        .first()
    )


def _target_is_current(reconsideration):
    organization = reconsideration.organization
    latest = _latest_suspension_event(organization)
    return bool(
        organization.partner_status == Organization.PartnerStatus.SUSPENDED
        and latest is not None
        and latest.pk == reconsideration.suspension_event_id
    )


def _record_reconsideration_event(
    *,
    reconsideration,
    actor,
    reason_code,
    notes="",
):
    return record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=reconsideration.organization_id,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        subject_organization=reconsideration.organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state={},
        new_state={
            "reconsideration_status": reconsideration.status,
            "outcome": reconsideration.outcome or None,
        },
        reason_code=reason_code,
        notes=notes,
        context={
            "reconsideration_id": str(reconsideration.pk),
            "target_suspension_event_id": str(reconsideration.suspension_event_id),
            "grounds": list(reconsideration.grounds or []),
        },
    )


def organization_reconsideration_projection(reconsideration):
    return {
        "id": str(reconsideration.pk),
        "status": reconsideration.status,
        "grounds": list(reconsideration.grounds or []),
        "request_statement": reconsideration.request_statement,
        "supporting_references": list(reconsideration.supporting_references or []),
        "outcome": reconsideration.outcome or None,
        "resolution_rationale": reconsideration.resolution_rationale,
        "submitted_at": reconsideration.submitted_at,
        "review_started_at": reconsideration.review_started_at,
        "resolved_at": reconsideration.resolved_at,
    }


def management_reconsideration_projection(reconsideration):
    payload = organization_reconsideration_projection(reconsideration)
    payload.update(
        {
            "suspension_event_id": str(reconsideration.suspension_event_id),
            "requested_by": (
                reconsideration.requested_by.username
                if reconsideration.requested_by_id
                else None
            ),
            "reviewer": (
                reconsideration.reviewer.username
                if reconsideration.reviewer_id
                else None
            ),
            "original_decision_maker": (
                reconsideration.suspension_event.actor_username_snapshot or None
            ),
            "reviewer_independence_note": reconsideration.reviewer_independence_note,
            "independence_override_rationale": (
                reconsideration.independence_override_rationale
            ),
            "internal_supporting_basis": reconsideration.internal_supporting_basis,
        }
    )
    return payload


def can_request_reconsideration(*, notice, user):
    if (
        notice.audience != OrganizationGovernanceNoticeRecipient.Audience.ADMIN
        or notice.governance_event.reason_code != PARTNERSHIP_SUSPENDED_REASON
    ):
        return False

    organization = notice.governance_event.subject_organization
    if organization is None or organization.partner_status != Organization.PartnerStatus.SUSPENDED:
        return False

    latest = _latest_suspension_event(organization)
    if latest is None or latest.pk != notice.governance_event_id:
        return False

    is_current_admin = OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
        status=OrganizationMembership.Status.ACTIVE,
        role__in=[
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.OWNER,
        ],
    ).exists()
    if not is_current_admin:
        return False

    return not OrganizationGovernanceReconsideration.objects.filter(
        suspension_event=notice.governance_event,
        status__in=OPEN_RECONSIDERATION_STATUSES,
    ).exists()


@transaction.atomic
def submit_reconsideration(
    *,
    notice,
    actor,
    grounds,
    request_statement,
    supporting_references,
):
    if not can_request_reconsideration(notice=notice, user=actor):
        raise GovernanceReconsiderationConflict(
            "Reconsideration is not available for this suspension notice."
        )

    try:
        reconsideration = OrganizationGovernanceReconsideration.objects.create(
            organization=notice.governance_event.subject_organization,
            suspension_event=notice.governance_event,
            notice_recipient=notice,
            requested_by=actor,
            grounds=grounds,
            request_statement=request_statement,
            supporting_references=supporting_references,
        )
    except IntegrityError as error:
        raise GovernanceReconsiderationConflict(
            "An open reconsideration already exists for this suspension."
        ) from error

    _record_reconsideration_event(
        reconsideration=reconsideration,
        actor=actor,
        reason_code="PARTNERSHIP_RECONSIDERATION_SUBMITTED",
        notes="The Organization Admin submitted a suspension reconsideration request.",
    )
    return reconsideration


def _mark_moot(reconsideration, *, actor):
    reconsideration.status = OrganizationGovernanceReconsideration.Status.MOOT
    reconsideration.resolved_at = timezone.now()
    reconsideration.save(update_fields=["status", "resolved_at"])
    _record_reconsideration_event(
        reconsideration=reconsideration,
        actor=actor,
        reason_code="PARTNERSHIP_RECONSIDERATION_MOOT",
        notes=(
            "The reconsideration became moot because the targeted suspension is "
            "no longer the organization's current suspension."
        ),
    )
    return reconsideration


@transaction.atomic
def start_reconsideration_review(
    *,
    reconsideration_id,
    organization_id,
    actor,
    reviewer_independence_note="",
    independence_override_rationale="",
):
    _require_platform_admin(actor)
    reconsideration = (
        OrganizationGovernanceReconsideration.objects.select_for_update()
        .select_related("organization", "suspension_event")
        .get(pk=reconsideration_id, organization_id=organization_id)
    )

    if reconsideration.status != OrganizationGovernanceReconsideration.Status.SUBMITTED:
        raise GovernanceReconsiderationConflict(
            "Only a submitted reconsideration can enter review."
        )
    if not _target_is_current(reconsideration):
        return _mark_moot(reconsideration, actor=actor)

    original_actor_id = reconsideration.suspension_event.actor_id
    if original_actor_id == actor.pk:
        another_admin_available = User.objects.filter(
            is_active=True,
            is_superuser=True,
        ).exclude(pk=actor.pk).exists()
        if another_admin_available and not independence_override_rationale.strip():
            raise GovernanceReconsiderationValidationError(
                (
                    "Another active Platform Admin is available. Self-review requires "
                    "a written independence override rationale."
                ),
                field="independence_override_rationale",
            )
        if not another_admin_available and not reviewer_independence_note.strip():
            raise GovernanceReconsiderationValidationError(
                (
                    "Record why independent review is unavailable before the original "
                    "decision-maker reviews this request."
                ),
                field="reviewer_independence_note",
            )

    reconsideration.status = OrganizationGovernanceReconsideration.Status.UNDER_REVIEW
    reconsideration.reviewer = actor
    reconsideration.reviewer_independence_note = reviewer_independence_note.strip()
    reconsideration.independence_override_rationale = (
        independence_override_rationale.strip()
    )
    reconsideration.review_started_at = timezone.now()
    reconsideration.save(
        update_fields=[
            "status",
            "reviewer",
            "reviewer_independence_note",
            "independence_override_rationale",
            "review_started_at",
        ]
    )
    _record_reconsideration_event(
        reconsideration=reconsideration,
        actor=actor,
        reason_code="PARTNERSHIP_RECONSIDERATION_REVIEW_STARTED",
        notes="A Platform Admin began review of the suspension reconsideration.",
    )
    return reconsideration


@transaction.atomic
def resolve_reconsideration(
    *,
    reconsideration_id,
    organization_id,
    actor,
    outcome,
    resolution_rationale,
    internal_supporting_basis,
):
    _require_platform_admin(actor)
    reconsideration = (
        OrganizationGovernanceReconsideration.objects.select_for_update()
        .select_related("organization", "suspension_event", "reviewer")
        .get(pk=reconsideration_id, organization_id=organization_id)
    )

    if reconsideration.status != OrganizationGovernanceReconsideration.Status.UNDER_REVIEW:
        raise GovernanceReconsiderationConflict(
            "Only a reconsideration under review can be resolved."
        )
    if reconsideration.reviewer_id != actor.pk:
        raise GovernanceReconsiderationAuthorizationError(
            "The Platform Admin who started this review must resolve it."
        )
    if not _target_is_current(reconsideration):
        return _mark_moot(reconsideration, actor=actor)

    if outcome == OrganizationGovernanceReconsideration.Outcome.REVOKED:
        reinstate_partner_organization_partnership(
            organization_id=reconsideration.organization_id,
            actor=actor,
            basis="INVESTIGATION_DID_NOT_JUSTIFY_CONTINUED_SUSPENSION",
            rationale=resolution_rationale,
            supporting_basis=internal_supporting_basis,
            supporting_references=[],
        )

    reconsideration.status = OrganizationGovernanceReconsideration.Status.RESOLVED
    reconsideration.outcome = outcome
    reconsideration.resolution_rationale = resolution_rationale
    reconsideration.internal_supporting_basis = internal_supporting_basis
    reconsideration.resolved_at = timezone.now()
    reconsideration.save(
        update_fields=[
            "status",
            "outcome",
            "resolution_rationale",
            "internal_supporting_basis",
            "resolved_at",
        ]
    )
    _record_reconsideration_event(
        reconsideration=reconsideration,
        actor=actor,
        reason_code=(
            "PARTNERSHIP_RECONSIDERATION_REVOKED"
            if outcome == OrganizationGovernanceReconsideration.Outcome.REVOKED
            else "PARTNERSHIP_RECONSIDERATION_UPHELD"
        ),
        notes=resolution_rationale,
    )
    return reconsideration
