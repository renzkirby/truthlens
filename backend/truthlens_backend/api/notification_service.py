"""Explicit, non-authoritative persistent inbox delivery."""

import logging
from urllib.parse import quote

from django.db import transaction
from django.utils.html import strip_tags

from .models import Notification, OfficialFactCheck

logger = logging.getLogger(__name__)
Type = Notification.NotificationType
Target = Notification.TargetType

NOTIFICATION_METADATA = {
    Type.AUTOMATED_VERIFICATION_COMPLETED: ("VERIFICATION", "INFORMATIONAL"),
    Type.AUTOMATED_VERIFICATION_FAILED: ("VERIFICATION", "IMPORTANT"),
    Type.PARTNER_FACT_CHECK_PUBLISHED: ("VERIFICATION", "IMPORTANT"),
    Type.PARTNER_FACT_CHECK_CORRECTED: ("VERIFICATION", "IMPORTANT"),
    Type.ARTICLE_RETURNED_FOR_REWORK: ("WORKSPACE", "ACTION_REQUIRED"),
    Type.FACT_CHECK_PUBLISHED: ("WORKSPACE", "INFORMATIONAL"),
    Type.FACTUAL_CORRECTION_PUBLISHED: ("WORKSPACE", "IMPORTANT"),
    Type.ORGANIZATION_MEMBERSHIP_CHANGED: ("ORGANIZATION", "IMPORTANT"),
    Type.THREAD_COMMENTED: ("COMMUNITY", "SOCIAL"),
    Type.EVIDENCE_REVIEWED: ("COMMUNITY", "INFORMATIONAL"),
}


def plain_snapshot(value, limit):
    return " ".join(strip_tags(str(value)).split())[:limit]


def create_notification_once(*, recipient_id, notification_type, target_type,
                             dedupe_key, title, message, target_id=None,
                             actor_id=None, organization_id=None):
    """Internal primitive; database uniqueness resolves concurrent retries."""
    if recipient_id is None:
        return None
    if actor_id == recipient_id and notification_type != Type.ORGANIZATION_MEMBERSHIP_CHANGED:
        return None
    candidate = Notification(
        recipient_id=recipient_id, actor_id=actor_id, organization_id=organization_id,
        notification_type=notification_type, target_type=target_type, target_id=target_id,
        dedupe_key=dedupe_key, title=plain_snapshot(title, 180),
        message=plain_snapshot(message, 500),
    )
    candidate.clean_fields()
    notification, _ = Notification.objects.get_or_create(
        recipient_id=recipient_id, dedupe_key=dedupe_key,
        defaults={field: getattr(candidate, field) for field in (
            "actor_id", "organization_id", "notification_type", "target_type",
            "target_id", "title", "message",
        )},
    )
    return notification


def dispatch_after_commit(callback, *args, **kwargs):
    """Best effort: a process crash after commit can lose delivery (no outbox)."""
    def deliver():
        try:
            with transaction.atomic():
                callback(*args, **kwargs)
        except Exception:
            logger.exception("Persistent notification delivery failed")

    transaction.on_commit(deliver)


def notification_destination(notification):
    target = notification.target_type
    if target == Target.WORKSPACE:
        return "/workspace"
    if notification.target_id is None:
        return None
    if target == Target.CLAIM:
        return f"/analysis/{notification.target_id}"
    if target == Target.THREAD:
        return f"/thread/detail/{notification.target_id}"
    if target == Target.OFFICIAL_FACT_CHECK:
        publication = OfficialFactCheck.objects.select_related("organization").filter(
            pk=notification.target_id,
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
        ).first()
        if publication and publication.organization:
            from .organization_public_presence_service import is_public_partner_eligible
            if is_public_partner_eligible(publication.organization):
                slug = quote(publication.organization.slug, safe="")
                return f"/partners/{slug}/fact-checks/{publication.pk}"
    return None
