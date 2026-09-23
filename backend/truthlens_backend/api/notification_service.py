"""Explicit, non-authoritative persistent inbox delivery."""

import logging
from urllib.parse import quote

from django.db import transaction
from django.utils.html import strip_tags

from .models import Notification, OfficialFactCheck, VerificationRun

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


def notify_verification_finished(run):
    if run.triggered_by_id is None:
        return
    if run.status == VerificationRun.Status.FAILED:
        notification_type = Type.AUTOMATED_VERIFICATION_FAILED
        title = "TruthLens couldn't complete this analysis"
        message = "A technical problem interrupted verification. You can try again."
    elif run.status in (VerificationRun.Status.COMPLETED, VerificationRun.Status.ABSTAINED):
        notification_type = Type.AUTOMATED_VERIFICATION_COMPLETED
        title = "Your TruthLens analysis is ready"
        message = (
            "Analysis finished without enough evidence to reach a supported conclusion."
            if run.status == VerificationRun.Status.ABSTAINED
            else "Analysis is complete. Open the results to review the findings."
        )
    else:
        return
    # Generic completion also covers publication reuse, without copying a verdict.
    return create_notification_once(
        recipient_id=run.triggered_by_id, notification_type=notification_type,
        target_type=Target.CLAIM, target_id=run.claim_id,
        dedupe_key=f"verification-run:{run.pk}:finished", title=title, message=message,
    )


def _source_thread_author(publication, *, include_predecessors=False):
    claim_id = publication.claim_id
    visited = set()
    while publication is not None and publication.pk not in visited:
        visited.add(publication.pk)
        if publication.claim_id != claim_id:
            return None
        thread = publication.source_thread
        if thread is not None and thread.claim_id == claim_id:
            return thread.author_id
        if not include_predecessors:
            break
        publication = publication.supersedes
    return None


def notify_fact_check_published(fact_check, *, actor_id):
    if fact_check.publication_status != OfficialFactCheck.PublicationStatus.PUBLISHED:
        return
    common = dict(
        actor_id=actor_id, organization_id=fact_check.organization_id,
        target_type=Target.OFFICIAL_FACT_CHECK, target_id=fact_check.pk,
        dedupe_key=f"publication:{fact_check.pk}:published",
    )
    create_notification_once(
        **common, recipient_id=fact_check.drafted_by_id,
        notification_type=Type.FACT_CHECK_PUBLISHED,
        title="Your fact-check is published",
        message=f'"{plain_snapshot(fact_check.headline, 160)}" is now public.',
    )
    author_id = _source_thread_author(fact_check)
    if author_id is not None and author_id != fact_check.drafted_by_id:
        create_notification_once(
            **common, recipient_id=author_id,
            notification_type=Type.PARTNER_FACT_CHECK_PUBLISHED,
            title="A verification partner published a fact-check for your post",
            message="A verification partner published its review of your claim. Open the fact-check to read the findings.",
        )


def notify_article_returned_for_rework(fact_check, *, actor_id):
    return create_notification_once(
        recipient_id=fact_check.drafted_by_id, actor_id=actor_id,
        organization_id=fact_check.organization_id,
        notification_type=Type.ARTICLE_RETURNED_FOR_REWORK,
        target_type=Target.WORKSPACE, target_id=fact_check.pk,
        dedupe_key=f"publication:{fact_check.pk}:rework:{fact_check.edit_generation}",
        title="Your fact-check needs revisions",
        message=f'"{plain_snapshot(fact_check.headline, 160)}" was returned for rework. Open the Workspace to review the feedback.',
    )


def notify_factual_correction_published(successor, *, actor_id, workspace_recipient_ids):
    if successor.publication_status != OfficialFactCheck.PublicationStatus.PUBLISHED:
        return
    recipients = set(workspace_recipient_ids) - {None}
    common = dict(
        actor_id=actor_id, organization_id=successor.organization_id,
        target_type=Target.OFFICIAL_FACT_CHECK, target_id=successor.pk,
        dedupe_key=f"publication:{successor.pk}:corrected",
    )
    for recipient_id in sorted(recipients):
        create_notification_once(
            **common, recipient_id=recipient_id,
            notification_type=Type.FACTUAL_CORRECTION_PUBLISHED,
            title="A factual correction you worked on is published",
            message="The corrected fact-check is now public. Open it to review the published findings.",
        )
    author_id = _source_thread_author(successor, include_predecessors=True)
    if author_id is not None and author_id not in recipients:
        create_notification_once(
            **common, recipient_id=author_id,
            notification_type=Type.PARTNER_FACT_CHECK_CORRECTED,
            title="A fact-check related to your post was corrected",
            message="A verification partner published a factual correction to its fact-check.",
        )


def notify_membership_changed(membership, *, actor_id, event_id, change):
    messages = {
        "role_changed": "Your organization role has changed.",
        "suspended": "Your organization membership has been suspended.",
        "restored": "Your organization membership has been restored.",
        "removed": "Your organization membership has been removed.",
    }
    return create_notification_once(
        recipient_id=membership.user_id, actor_id=actor_id,
        organization_id=membership.organization_id,
        notification_type=Type.ORGANIZATION_MEMBERSHIP_CHANGED,
        target_type=Target.ORGANIZATION, target_id=membership.organization_id,
        dedupe_key=f"membership-event:{event_id}",
        title="Your organization membership changed", message=messages[change],
    )
