"""Reliable delivery for durable Partner Organization governance notices."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import (
    OrganizationGovernanceNoticeRecipient,
    UserProfile,
)
from .notification_service import (
    Target,
    Type,
    create_notification_once,
)
from .organization_governance_notice_service import ACTION_LABELS

logger = logging.getLogger(__name__)


class GovernanceNoticeDeliveryError(RuntimeError):
    """One or more retryable governance-notice delivery channels failed."""


def governance_notice_url(notice_recipient_id):
    frontend_url = settings.FRONTEND_URL.rstrip("/")
    return f"{frontend_url}/governance/{notice_recipient_id}"


def _organization_name(recipient):
    organization = recipient.governance_event.subject_organization
    return organization.name if organization is not None else "your organization"


def _action_label(recipient):
    return ACTION_LABELS.get(
        recipient.governance_event.reason_code,
        "Partner Organization Governance Update",
    )


def _in_app_copy(recipient):
    organization_name = _organization_name(recipient)
    action_label = _action_label(recipient)

    if recipient.audience == OrganizationGovernanceNoticeRecipient.Audience.ADMIN:
        return (
            "Partner governance notice",
            (
                f"TruthLens recorded: {action_label} for {organization_name}. "
                "Review the secure governance notice for details and available next steps."
            ),
        )

    reason_code = recipient.governance_event.reason_code
    if reason_code == "PARTNERSHIP_SUSPENDED":
        message = (
            f"{organization_name}'s Partner status was suspended. Professional "
            "organization verification functions are temporarily unavailable. "
            "Your personal TruthLens Community account is not affected."
        )
    elif reason_code == "PARTNERSHIP_REINSTATED":
        message = (
            f"{organization_name}'s Partner status is active again. Professional "
            "organization functions may resume according to current permissions."
        )
    elif reason_code == "PARTNERSHIP_ENDED":
        message = (
            f"{organization_name}'s active Partner relationship has ended. "
            "Your personal TruthLens Community account is not affected."
        )
    else:
        message = f"TruthLens recorded an organization status update for {organization_name}."

    return ("Partner status update", message)


def _verified_email_address(user):
    if user is None or not user.email:
        return None
    is_verified = UserProfile.objects.filter(
        user_id=user.pk,
        is_email_verified=True,
    ).exists()
    return user.email if is_verified else None


def send_governance_notice_email(recipient):
    """Send a minimal Admin-only alert; detailed governance data stays behind login."""

    if recipient.audience != OrganizationGovernanceNoticeRecipient.Audience.ADMIN:
        return 0

    user = recipient.user
    email_address = _verified_email_address(user)
    if email_address is None:
        return 0

    action_label = _action_label(recipient)
    organization_name = _organization_name(recipient)
    notice_url = governance_notice_url(recipient.pk)
    effective_at = recipient.governance_event.created_at

    subject = "TruthLens Partner governance notice"
    text_body = (
        "TruthLens Partner governance notice\n\n"
        f"TruthLens issued a governance decision affecting {organization_name}.\n\n"
        f"Action: {action_label}\n"
        f"Effective: {effective_at:%Y-%m-%d %H:%M UTC}\n\n"
        "Sign in to TruthLens to securely review the governance notice "
        "and available next steps:\n"
        f"{notice_url}\n\n"
        "This email intentionally does not include confidential governance details."
    )
    html_body = render_to_string(
        "emails/organization_governance_notice.html",
        {
            "organization_name": organization_name,
            "action_label": action_label,
            "effective_at": effective_at,
            "notice_url": notice_url,
        },
    )

    message = EmailMultiAlternatives(
        subject=subject.replace("\r", " ").replace("\n", " "),
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email_address],
    )
    message.attach_alternative(html_body, "text/html")
    delivered_count = message.send(fail_silently=False)
    if delivered_count != 1:
        raise RuntimeError(
            "The governance notice email was not accepted by the configured email backend."
        )
    return delivered_count


def _save_delivery_fields(recipient, *fields):
    if "last_delivery_attempt_at" not in fields:
        fields = (*fields, "last_delivery_attempt_at")
    recipient.save(update_fields=list(dict.fromkeys(fields)))


def deliver_governance_notice_channels(notice_recipient_id):
    """Deliver each channel independently and persist retry-visible state."""

    recipient = (
        OrganizationGovernanceNoticeRecipient.objects.select_related(
            "user",
            "governance_event",
            "governance_event__subject_organization",
        )
        .filter(pk=notice_recipient_id)
        .first()
    )
    if recipient is None:
        return {"missing": True}

    from django.utils import timezone

    retryable_errors = []

    if recipient.user_id is None:
        changed = []
        if recipient.in_app_status != OrganizationGovernanceNoticeRecipient.DeliveryStatus.SKIPPED:
            recipient.in_app_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.SKIPPED
            changed.append("in_app_status")
        if recipient.email_status != OrganizationGovernanceNoticeRecipient.DeliveryStatus.SKIPPED:
            recipient.email_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.SKIPPED
            changed.append("email_status")
        if changed:
            recipient.last_delivery_attempt_at = timezone.now()
            changed.append("last_delivery_attempt_at")
            recipient.save(update_fields=changed)
        return {"missing_user": True}

    if recipient.in_app_status != OrganizationGovernanceNoticeRecipient.DeliveryStatus.SENT:
        recipient.in_app_attempts += 1
        recipient.last_delivery_attempt_at = timezone.now()
        try:
            title, message = _in_app_copy(recipient)
            create_notification_once(
                recipient_id=recipient.user_id,
                notification_type=Type.ORGANIZATION_GOVERNANCE_CHANGED,
                target_type=Target.GOVERNANCE_NOTICE,
                target_id=recipient.pk,
                dedupe_key=f"organization-governance:{recipient.pk}",
                title=title,
                message=message,
                organization_id=recipient.governance_event.subject_organization_id,
            )
            recipient.in_app_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.SENT
            if not retryable_errors:
                recipient.last_delivery_error = ""
            _save_delivery_fields(
                recipient,
                "in_app_attempts",
                "in_app_status",
                "last_delivery_error",
            )
        except Exception as error:
            recipient.in_app_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.FAILED
            recipient.last_delivery_error = f"In-app delivery failed: {error}"[:2000]
            _save_delivery_fields(
                recipient,
                "in_app_attempts",
                "in_app_status",
                "last_delivery_error",
            )
            retryable_errors.append(error)
            logger.exception(
                "Governance in-app notice delivery failed for recipient=%s",
                recipient.pk,
            )

    if recipient.audience != OrganizationGovernanceNoticeRecipient.Audience.ADMIN:
        if recipient.email_status != OrganizationGovernanceNoticeRecipient.DeliveryStatus.SKIPPED:
            recipient.email_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.SKIPPED
            recipient.last_delivery_attempt_at = timezone.now()
            _save_delivery_fields(recipient, "email_status")
    elif recipient.email_status != OrganizationGovernanceNoticeRecipient.DeliveryStatus.SENT:
        email_address = _verified_email_address(recipient.user)
        if email_address is None:
            recipient.email_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.SKIPPED
            recipient.last_delivery_attempt_at = timezone.now()
            _save_delivery_fields(recipient, "email_status")
        else:
            recipient.email_attempts += 1
            recipient.last_delivery_attempt_at = timezone.now()
            try:
                send_governance_notice_email(recipient)
                recipient.email_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.SENT
                if not retryable_errors:
                    recipient.last_delivery_error = ""
                _save_delivery_fields(
                    recipient,
                    "email_attempts",
                    "email_status",
                    "last_delivery_error",
                )
            except Exception as error:
                recipient.email_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.FAILED
                recipient.last_delivery_error = f"Email delivery failed: {error}"[:2000]
                _save_delivery_fields(
                    recipient,
                    "email_attempts",
                    "email_status",
                    "last_delivery_error",
                )
                retryable_errors.append(error)
                logger.exception(
                    "Governance email delivery failed for recipient=%s",
                    recipient.pk,
                )

    if retryable_errors:
        raise GovernanceNoticeDeliveryError(
            f"Governance notice delivery has {len(retryable_errors)} retryable channel failure(s)."
        )

    return {
        "missing": False,
        "in_app_status": recipient.in_app_status,
        "email_status": recipient.email_status,
    }


def enqueue_governance_notice_delivery(notice_recipient_ids):
    """Best-effort queueing; durable PENDING rows remain available if Redis is down."""

    from .tasks import deliver_organization_governance_notice_task

    for recipient_id in notice_recipient_ids:
        try:
            deliver_organization_governance_notice_task.delay(str(recipient_id))
        except Exception:
            logger.exception(
                "Could not queue governance notice delivery for recipient=%s",
                recipient_id,
            )
