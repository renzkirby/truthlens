"""Durable Partner Organization governance notice access and projection."""

from django.db import transaction

from .models import (
    OrganizationGovernanceNoticeRecipient,
    OrganizationMembership,
)


ADMIN_MEMBERSHIP_ROLES = {
    OrganizationMembership.Role.ADMIN,
    OrganizationMembership.Role.OWNER,
}

ACTION_LABELS = {
    "PARTNERSHIP_SUSPENDED": "Partnership Suspended",
    "PARTNERSHIP_REINSTATED": "Partnership Reinstated",
    "PARTNERSHIP_ENDED": "Partnership Ended",
}

ADMIN_GOVERNANCE_FIELDS = (
    "suspension_type",
    "ending_type",
    "ground",
    "factors",
    "severity",
    "policy_basis",
    "other_factor_explanation",
    "remediation",
    "review_date",
    "basis",
    "completed_remediation",
    "continuing_conditions",
    "monitoring_end_date",
    "monitoring_success_criteria",
    "monitoring_recurrence_consequence",
    "prior_suspension_event_id",
)


class GovernanceNoticeNotFound(Exception):
    pass


def snapshot_governance_notice_recipients(organization):
    """Capture current active membership recipients before lifecycle mutation."""

    recipients = {}
    memberships = (
        OrganizationMembership.objects.filter(
            organization=organization,
            status=OrganizationMembership.Status.ACTIVE,
            user__isnull=False,
        )
        .order_by("user_id", "id")
        .values("user_id", "role")
    )

    for membership in memberships:
        user_id = membership["user_id"]
        audience = (
            OrganizationGovernanceNoticeRecipient.Audience.ADMIN
            if membership["role"] in ADMIN_MEMBERSHIP_ROLES
            else OrganizationGovernanceNoticeRecipient.Audience.MEMBER
        )
        current = recipients.get(user_id)
        if (
            current is None
            or audience == OrganizationGovernanceNoticeRecipient.Audience.ADMIN
        ):
            recipients[user_id] = {
                "user_id": user_id,
                "audience": audience,
            }

    return list(recipients.values())


def persist_governance_notice_recipients(*, governance_event, recipients):
    """Persist the decision-time audience in the same transaction as the event."""

    rows = [
        OrganizationGovernanceNoticeRecipient(
            governance_event=governance_event,
            user_id=recipient["user_id"],
            audience=recipient["audience"],
            can_read_notice=True,
        )
        for recipient in recipients
    ]
    if not rows:
        return []

    return OrganizationGovernanceNoticeRecipient.objects.bulk_create(
        rows,
        ignore_conflicts=True,
    )


def list_governance_notices_for_user(user):
    if user is None or not user.is_authenticated:
        return OrganizationGovernanceNoticeRecipient.objects.none()

    return (
        OrganizationGovernanceNoticeRecipient.objects.filter(
            user=user,
            can_read_notice=True,
        )
        .select_related(
            "governance_event",
            "governance_event__subject_organization",
        )
        .order_by("-governance_event__created_at", "-id")
    )


def get_governance_notice_for_user(*, notice_id, user):
    if user is None or not user.is_authenticated:
        raise GovernanceNoticeNotFound("Governance notice not found.")

    notice = (
        list_governance_notices_for_user(user)
        .filter(pk=notice_id)
        .first()
    )
    if notice is None:
        # Deliberately do not reveal whether another user's notice exists.
        raise GovernanceNoticeNotFound("Governance notice not found.")
    return notice


def _safe_governance_metadata(event):
    source = (event.context or {}).get("governance") or {}
    if not isinstance(source, dict):
        return {}

    return {
        field: source.get(field)
        for field in ADMIN_GOVERNANCE_FIELDS
        if field in source
    }


def _organization_projection(event):
    organization = event.subject_organization
    if organization is None:
        return None
    return {
        "id": str(organization.pk),
        "name": organization.name,
        "slug": organization.slug,
    }


def _member_status_message(event):
    reason_code = event.reason_code
    if reason_code == "PARTNERSHIP_SUSPENDED":
        return (
            "Professional organization verification functions are temporarily "
            "unavailable. Your personal TruthLens Community account is not "
            "affected, and legitimate historical work remains preserved."
        )
    if reason_code == "PARTNERSHIP_REINSTATED":
        return (
            "The organization's Partner status is active again. Professional "
            "organization functions may resume according to current permissions."
        )
    if reason_code == "PARTNERSHIP_ENDED":
        return (
            "The active Partner relationship has ended. Your personal TruthLens "
            "Community account is not affected, and legitimate historical work "
            "and attribution remain preserved."
        )
    return "TruthLens recorded an organization governance update."


def serialize_governance_notice(notice):
    """Return an audience-safe projection; unknown context keys stay hidden."""

    event = notice.governance_event
    payload = {
        "id": str(notice.pk),
        "audience": notice.audience,
        "action": {
            "code": event.reason_code,
            "label": ACTION_LABELS.get(
                event.reason_code,
                "Partner Organization Governance Update",
            ),
        },
        "organization": _organization_projection(event),
        "effective_at": event.created_at.isoformat(),
        "partner_status": (event.new_state or {}).get("partner_status"),
        "viewed_at": notice.viewed_at.isoformat() if notice.viewed_at else None,
    }

    if notice.audience == OrganizationGovernanceNoticeRecipient.Audience.ADMIN:
        payload.update(
            {
                "rationale": event.notes or "",
                "governance": _safe_governance_metadata(event),
            }
        )
    else:
        payload["message"] = _member_status_message(event)

    return payload


@transaction.atomic
def mark_governance_notice_viewed(*, notice_id, user, viewed_at):
    notice = (
        OrganizationGovernanceNoticeRecipient.objects.select_for_update()
        .filter(
            pk=notice_id,
            user=user,
            can_read_notice=True,
        )
        .first()
    )
    if notice is None:
        raise GovernanceNoticeNotFound("Governance notice not found.")
    if notice.viewed_at is None:
        notice.viewed_at = viewed_at
        notice.save(update_fields=["viewed_at"])
    return notice
