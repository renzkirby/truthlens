from django.core.exceptions import (
    ValidationError,
)
from django.core.validators import (
    URLValidator,
)
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckSource,
)

from .organization_service import (
    PartnerCapability,
    has_capability,
)
from .verification_assignment_service import (
    complete_verification_assignment,
)
import logging

logger = logging.getLogger(__name__)


def _queue_fact_check_index(
    fact_check_id,
):
    """
    Best-effort background indexing.

    Publication has already committed at this
    point, so a broker/indexing failure must not
    undo or invalidate the publication.
    """

    try:
        from .tasks import (
            index_official_fact_check_task,
        )

        (index_official_fact_check_task.delay(str(fact_check_id)))

    except Exception as error:
        logger.exception(
            "Failed to queue fact-check " "indexing for %s: %s",
            fact_check_id,
            error,
        )


class PublishingError(Exception):
    pass


class PublishingAuthorizationError(PublishingError):
    pass


class InvalidPublicationTransition(PublishingError):
    pass


class InvalidFactCheckContent(PublishingError):
    pass


class PublishingConflict(PublishingError):
    pass


ACTIVE_DRAFT_STATUSES = {
    OfficialFactCheck.PublicationStatus.DRAFT,
    OfficialFactCheck.PublicationStatus.IN_REVIEW,
}


_url_validator = URLValidator(
    schemes=[
        "http",
        "https",
    ]
)


def _require_capability(
    user,
    capability,
    *,
    organization=None,
):
    if has_capability(
        user,
        capability,
        organization=organization,
    ):
        return

    raise PublishingAuthorizationError(
        "You do not have permission to " "perform this publication action."
    )


def _get_current_decision(
    claim,
    *,
    lock=False,
):
    queryset = AdjudicationDecision.objects.filter(
        claim=claim,
        is_current=True,
    )

    if lock:
        queryset = queryset.select_for_update()

    return queryset.first()


def _validate_current_decision(
    decision,
):
    current = (
        AdjudicationDecision.objects.select_for_update()
        .filter(
            claim_id=decision.claim_id,
            is_current=True,
        )
        .first()
    )

    if not current or current.id != decision.id:
        raise PublishingConflict(
            "The adjudication decision used "
            "for this fact-check is no longer "
            "current. Create a new draft from "
            "the latest decision."
        )

    return current


def _normalize_source_urls(
    source_urls,
):
    if source_urls is None:
        return []

    if not isinstance(
        source_urls,
        (
            list,
            tuple,
        ),
    ):
        raise InvalidFactCheckContent("source_urls must be a list.")

    normalized = []
    seen = set()

    for raw_url in source_urls:
        if not isinstance(
            raw_url,
            str,
        ):
            raise InvalidFactCheckContent("Every source URL must be " "a string.")

        url = raw_url.strip()

        if not url:
            continue

        if len(url) > 2000:
            raise InvalidFactCheckContent("A source URL exceeds the " "maximum length.")

        try:
            _url_validator(url)

        except ValidationError as error:
            raise InvalidFactCheckContent(f"Invalid source URL: {url}") from error

        if url in seen:
            continue

        seen.add(url)
        normalized.append(url)

    return normalized


def _sync_verified_evidence_sources(
    fact_check,
    *,
    actor,
):
    evidence_items = (
        EvidenceSubmission.objects.filter(
            thread__claim=(fact_check.claim),
            evidence_status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
        )
        .exclude(evidence_url__isnull=True)
        .exclude(evidence_url="")
        .select_related(
            "thread",
        )
        .order_by("submitted_at")
    )

    for evidence in evidence_items:
        url = (evidence.evidence_url or "").strip()

        if not url:
            continue

        source, created = OfficialFactCheckSource.objects.get_or_create(
            fact_check=fact_check,
            url=url,
            defaults={
                "title": (evidence.evidence_caption),
                "evidence_submission": evidence,
                "added_by": actor,
                "source_type": (OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE),
            },
        )

        if not created:
            changed_fields = []

            if source.evidence_submission_id is None:
                source.evidence_submission = evidence

                changed_fields.append("evidence_submission")

            if source.source_type != (
                OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE
            ):
                source.source_type = (
                    OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE
                )

                changed_fields.append("source_type")

            if not source.title and evidence.evidence_caption:
                source.title = evidence.evidence_caption

                changed_fields.append("title")

            if changed_fields:
                source.save(update_fields=(changed_fields))


def _replace_moderator_sources(
    fact_check,
    *,
    actor,
    source_urls,
):
    normalized_urls = _normalize_source_urls(source_urls)

    (
        fact_check.source_items.filter(
            source_type=(OfficialFactCheckSource.SourceType.MODERATOR_ADDED)
        ).delete()
    )

    for url in normalized_urls:
        (
            OfficialFactCheckSource.objects.get_or_create(
                fact_check=fact_check,
                url=url,
                defaults={
                    "added_by": actor,
                    "source_type": (OfficialFactCheckSource.SourceType.MODERATOR_ADDED),
                },
            )
        )


def _sync_sources_cache(
    fact_check,
):
    urls = list(
        fact_check.source_items.order_by(
            "created_at",
            "id",
        ).values_list(
            "url",
            flat=True,
        )
    )

    fact_check.sources = urls

    fact_check.save(
        update_fields=[
            "sources",
            "updated_at",
        ]
    )


def _sync_fact_check_sources(
    fact_check,
    *,
    actor,
    source_urls=None,
    replace_moderator_sources=False,
):
    _sync_verified_evidence_sources(
        fact_check,
        actor=actor,
    )

    if replace_moderator_sources:
        _replace_moderator_sources(
            fact_check,
            actor=actor,
            source_urls=(source_urls or []),
        )

    elif source_urls:
        for url in _normalize_source_urls(source_urls):
            (
                OfficialFactCheckSource.objects.get_or_create(
                    fact_check=(fact_check),
                    url=url,
                    defaults={
                        "added_by": actor,
                        "source_type": (
                            OfficialFactCheckSource.SourceType.MODERATOR_ADDED
                        ),
                    },
                )
            )

    _sync_sources_cache(fact_check)


def _validate_publication_content(
    fact_check,
):
    if not (fact_check.headline or "").strip():
        raise InvalidFactCheckContent(
            "A headline is required before " "review or publication."
        )

    if not (fact_check.summary or "").strip():
        raise InvalidFactCheckContent(
            "A summary is required before " "review or publication."
        )

    if not (fact_check.article_body or "").strip():
        raise InvalidFactCheckContent(
            "Article analysis is required " "before review or publication."
        )

    if not (fact_check.source_items.exists()):
        raise InvalidFactCheckContent(
            "At least one source is required " "before review or publication."
        )


def _record_publication_event(
    fact_check,
    *,
    actor,
    event_type,
    from_status=None,
    to_status=None,
    metadata=None,
):
    decision = fact_check.adjudication_decision

    if not decision or not decision.moderation_case_id:
        return None

    return ModerationEvent.objects.create(
        case=decision.moderation_case,
        actor=actor,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        metadata={
            "fact_check_id": str(fact_check.id),
            "claim_id": str(fact_check.claim_id),
            "version": (fact_check.version),
            **(metadata or {}),
        },
    )


def create_fact_check_draft(
    *,
    decision,
    actor,
    headline,
    summary,
    article_body="",
    source_urls=None,
):
    headline = (headline or "").strip()

    summary = (summary or "").strip()

    article_body = (article_body or "").strip()

    if not headline:
        raise InvalidFactCheckContent("A headline is required.")

    if not summary:
        raise InvalidFactCheckContent("A summary is required.")

    if len(headline) > 300:
        raise InvalidFactCheckContent("Headline must be 300 " "characters or fewer.")

    with transaction.atomic():
        # Match the adjudication lock order:
        # Claim first, then AdjudicationDecision.
        #
        # Do not combine select_for_update()
        # with nullable select_related() joins.
        locked_claim = Claim.objects.select_for_update().get(pk=decision.claim_id)

        locked_decision = AdjudicationDecision.objects.select_for_update().get(
            pk=decision.pk
        )

        current_decision = _validate_current_decision(locked_decision)

        _require_capability(
            actor,
            (PartnerCapability.CREATE_FACT_CHECK_DRAFT),
            organization=(current_decision.organization),
        )

        active_drafts = list(
            OfficialFactCheck.objects.select_for_update()
            .filter(
                claim=locked_claim,
                publication_status__in=(ACTIVE_DRAFT_STATUSES),
            )
            .order_by(
                "version",
                "created_at",
            )
        )

        same_decision_draft = next(
            (
                item
                for item in active_drafts
                if (item.adjudication_decision_id == current_decision.id)
            ),
            None,
        )

        if same_decision_draft:
            raise PublishingConflict(
                "An active fact-check draft "
                "already exists for this "
                "adjudication decision."
            )

        # Any remaining active drafts belong to
        # an older adjudication revision. They
        # can no longer be published, so retire
        # them before allocating the new version.
        if active_drafts:
            archived_at = timezone.now()

            for stale_draft in active_drafts:
                stale_draft.publication_status = (
                    OfficialFactCheck.PublicationStatus.ARCHIVED
                )

                stale_draft.archived_at = archived_at

                stale_draft.save(
                    update_fields=[
                        "publication_status",
                        "archived_at",
                        "updated_at",
                    ]
                )

        max_version = (
            OfficialFactCheck.objects.filter(claim=locked_claim).aggregate(
                maximum=Max("version")
            )["maximum"]
            or 0
        )

        draft = OfficialFactCheck(
            claim=locked_claim,
            adjudication_decision=(current_decision),
            organization=(current_decision.organization),
            canonical_claim=(current_decision.canonical_claim),
            verdict=(current_decision.verdict),
            headline=headline,
            summary=summary,
            article_body=article_body,
            publication_status=(OfficialFactCheck.PublicationStatus.DRAFT),
            version=max_version + 1,
            drafted_by=actor,
        )

        draft.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )

        draft.save()

        _sync_fact_check_sources(
            draft,
            actor=actor,
            source_urls=source_urls,
        )

        _record_publication_event(
            draft,
            actor=actor,
            event_type=(ModerationEvent.EventType.ARTICLE_DRAFT_CREATED),
            to_status=(OfficialFactCheck.PublicationStatus.DRAFT),
        )

        return draft


def update_fact_check_draft(
    *,
    fact_check,
    actor,
    headline=None,
    summary=None,
    article_body=None,
    source_urls=None,
):
    with transaction.atomic():
        locked_fact_check = OfficialFactCheck.objects.select_for_update().get(
            pk=fact_check.pk
        )

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.DRAFT
        ):
            raise InvalidPublicationTransition(
                "Only draft fact-checks " "can be edited."
            )

        _validate_current_decision(locked_fact_check.adjudication_decision)

        _require_capability(
            actor,
            (PartnerCapability.CREATE_FACT_CHECK_DRAFT),
            organization=(locked_fact_check.organization),
        )

        if headline is not None:
            headline = headline.strip()

            if not headline:
                raise InvalidFactCheckContent("Headline cannot be empty.")

            if len(headline) > 300:
                raise InvalidFactCheckContent(
                    "Headline must be 300 " "characters or fewer."
                )

            locked_fact_check.headline = headline

        if summary is not None:
            summary = summary.strip()

            if not summary:
                raise InvalidFactCheckContent("Summary cannot be empty.")

            locked_fact_check.summary = summary

        if article_body is not None:
            locked_fact_check.article_body = article_body.strip()

        locked_fact_check.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )

        locked_fact_check.save()

        _sync_fact_check_sources(
            locked_fact_check,
            actor=actor,
            source_urls=source_urls,
            replace_moderator_sources=(source_urls is not None),
        )

        return locked_fact_check


def submit_fact_check_for_review(
    *,
    fact_check,
    actor,
):
    with transaction.atomic():
        locked_fact_check = OfficialFactCheck.objects.select_for_update().get(
            pk=fact_check.pk
        )

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.DRAFT
        ):
            raise InvalidPublicationTransition(
                "Only a draft can be " "submitted for review."
            )

        _validate_current_decision(locked_fact_check.adjudication_decision)

        _require_capability(
            actor,
            (PartnerCapability.CREATE_FACT_CHECK_DRAFT),
            organization=(locked_fact_check.organization),
        )

        _sync_fact_check_sources(
            locked_fact_check,
            actor=actor,
        )

        _validate_publication_content(locked_fact_check)

        previous_status = locked_fact_check.publication_status

        locked_fact_check.publication_status = (
            OfficialFactCheck.PublicationStatus.IN_REVIEW
        )

        locked_fact_check.submitted_for_review_at = timezone.now()

        locked_fact_check.save(
            update_fields=[
                "publication_status",
                ("submitted_for_" "review_at"),
                "updated_at",
            ]
        )

        _record_publication_event(
            locked_fact_check,
            actor=actor,
            event_type=(ModerationEvent.EventType.ARTICLE_SUBMITTED),
            from_status=previous_status,
            to_status=(OfficialFactCheck.PublicationStatus.IN_REVIEW),
        )

        return locked_fact_check


def publish_fact_check(
    *,
    fact_check,
    actor,
):
    with transaction.atomic():
        locked_fact_check = OfficialFactCheck.objects.select_for_update().get(
            pk=fact_check.pk
        )

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.IN_REVIEW
        ):
            raise InvalidPublicationTransition(
                "Only a fact-check in review " "can be published."
            )

        current_decision = _validate_current_decision(
            locked_fact_check.adjudication_decision
        )

        _require_capability(
            actor,
            (PartnerCapability.PUBLISH_FACT_CHECK),
            organization=(locked_fact_check.organization),
        )

        if locked_fact_check.verdict != current_decision.verdict or (
            locked_fact_check.canonical_claim != current_decision.canonical_claim
        ):
            raise PublishingConflict(
                "The fact-check no longer "
                "matches the authoritative "
                "adjudication decision."
            )

        _sync_fact_check_sources(
            locked_fact_check,
            actor=actor,
        )

        _validate_publication_content(locked_fact_check)

        now = timezone.now()

        previous_published = (
            OfficialFactCheck.objects.select_for_update()
            .filter(
                claim=(locked_fact_check.claim),
                publication_status=(OfficialFactCheck.PublicationStatus.PUBLISHED),
            )
            .exclude(pk=locked_fact_check.pk)
            .first()
        )

        if previous_published:
            previous_published.publication_status = (
                OfficialFactCheck.PublicationStatus.ARCHIVED
            )

            previous_published.archived_at = now

            previous_published.save(
                update_fields=[
                    "publication_status",
                    "archived_at",
                    "updated_at",
                ]
            )

        previous_status = locked_fact_check.publication_status

        locked_fact_check.publication_status = (
            OfficialFactCheck.PublicationStatus.PUBLISHED
        )

        locked_fact_check.reviewed_by = actor
        locked_fact_check.reviewed_at = now
        locked_fact_check.published_by = actor
        locked_fact_check.published_at = now
        locked_fact_check.archived_at = None

        locked_fact_check.save(
            update_fields=[
                "publication_status",
                "reviewed_by",
                "reviewed_at",
                "published_by",
                "published_at",
                "archived_at",
                "updated_at",
            ]
        )

        event_type = (
            ModerationEvent.EventType.ARTICLE_REVISED
            if previous_published
            else (ModerationEvent.EventType.ARTICLE_PUBLISHED)
        )

        _record_publication_event(
            locked_fact_check,
            actor=actor,
            event_type=event_type,
            from_status=previous_status,
            to_status=(OfficialFactCheck.PublicationStatus.PUBLISHED),
            metadata={
                "previous_fact_check_id": (
                    str(previous_published.id) if previous_published else None
                ),
                "previous_version": (
                    previous_published.version if previous_published else None
                ),
            },
        )

        complete_verification_assignment(
            claim=locked_fact_check.claim,
            organization=locked_fact_check.organization,
        )

        published_fact_check_id = locked_fact_check.id

        transaction.on_commit(lambda: _queue_fact_check_index(published_fact_check_id))

        return {
            "fact_check": locked_fact_check,
            "archived_fact_check": previous_published,
        }
