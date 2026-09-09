import logging

from django.core.exceptions import (
    ValidationError,
)
from django.core.validators import (
    URLValidator,
)
from django.db import transaction
from django.utils import timezone

from .evidence_snapshot_schema import (
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)

from .models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    Claim,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OfficialFactCheckSource,
    OfficialFactCheckSourceEvidenceLink,
    Organization,
    OrganizationMembership,
    VerificationAssignment,
)

from .organization_service import (
    PartnerCapability,
    get_membership_capabilities,
)
from .verification_assignment_service import (
    VerificationAssignmentConflict,
    complete_verification_assignment,
    get_open_verification_assignment,
)

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


def _require_locked_capability(
    actor,
    capability,
    *,
    organization,
):
    if not actor or not actor.is_authenticated:
        raise PublishingAuthorizationError(
            "You do not have permission to perform this publication action."
        )

    membership = (
        OrganizationMembership.objects.select_related("organization")
        .select_for_update(of=("self",))
        .filter(
            user=actor,
            organization=organization,
        )
        .first()
    )
    capabilities = (
        get_membership_capabilities(membership) if membership is not None else set()
    )
    if capability in capabilities:
        return

    raise PublishingAuthorizationError(
        "You do not have permission to " "perform this publication action."
    )


def _publication_conflict():
    return PublishingConflict(
        "The adjudication decision used for this fact-check is no longer "
        "current. Create a new draft from the latest decision."
    )


def _get_decision_publication_identity(decision):
    identity = (
        AdjudicationDecision.objects.filter(pk=getattr(decision, "pk", None))
        .values(
            "claim_id",
            "organization_id",
        )
        .first()
    )
    if (
        identity is None
        or identity["claim_id"] is None
        or identity["organization_id"] is None
    ):
        raise _publication_conflict()
    return {
        **identity,
        "decision_id": decision.pk,
        "fact_check_id": None,
    }


def _get_fact_check_publication_identity(fact_check):
    identity = (
        OfficialFactCheck.objects.filter(pk=getattr(fact_check, "pk", None))
        .values(
            "claim_id",
            "organization_id",
            "adjudication_decision_id",
        )
        .first()
    )
    if (
        identity is None
        or identity["claim_id"] is None
        or identity["organization_id"] is None
        or identity["adjudication_decision_id"] is None
    ):
        raise _publication_conflict()
    return {
        "claim_id": identity["claim_id"],
        "organization_id": identity["organization_id"],
        "decision_id": identity["adjudication_decision_id"],
        "fact_check_id": fact_check.pk,
    }


def _lock_publication_context(*, identity, actor, capability):
    """Lock a publication mutation using the shared Claim-first protocol.

    The canonical order is Claim, open Assignment, Organization, actor
    Membership, current AdjudicationDecision, its evidence snapshot, all claim
    fact-checks, their source rows, their evidence-lineage rows, then sealed
    publication records. All service mutation paths use this helper, and the nested
    assignment-completion helper reacquires only Claim then Assignment.
    """

    try:
        locked_claim = Claim.objects.select_for_update().get(pk=identity["claim_id"])
    except Claim.DoesNotExist as error:
        raise _publication_conflict() from error

    assignment = get_open_verification_assignment(
        locked_claim,
        lock=True,
    )

    try:
        organization = Organization.objects.select_for_update().get(
            pk=identity["organization_id"]
        )
    except Organization.DoesNotExist as error:
        raise _publication_conflict() from error

    if assignment is not None and (
        assignment.status != VerificationAssignment.Status.ACTIVE
        or assignment.organization_id != organization.id
    ):
        raise PublishingConflict(
            "The organization responsible for this claim changed after the "
            "publication workflow was opened."
        )

    _require_locked_capability(
        actor,
        capability,
        organization=organization,
    )

    current_decision = (
        AdjudicationDecision.objects.select_for_update(of=("self",))
        .filter(
            claim=locked_claim,
            is_current=True,
        )
        .first()
    )
    if (
        current_decision is None
        or current_decision.id != identity["decision_id"]
        or current_decision.organization_id != organization.id
    ):
        raise PublishingConflict(
            "The adjudication decision used for this fact-check is no longer "
            "current. Create a new draft from the latest decision."
        )

    decision_snapshot = (
        AdjudicationDecisionEvidenceSnapshot.objects.select_for_update(of=("self",))
        .filter(decision=current_decision)
        .first()
    )
    snapshot_records = _validate_decision_snapshot(
        decision_snapshot,
        decision=current_decision,
        claim=locked_claim,
    )

    fact_checks = list(
        OfficialFactCheck.objects.select_for_update(of=("self",))
        .filter(claim=locked_claim)
        .order_by(
            "version",
            "created_at",
            "id",
        )
    )
    list(
        OfficialFactCheckSource.objects.select_for_update(of=("self",))
        .filter(fact_check__claim=locked_claim)
        .order_by(
            "fact_check_id",
            "created_at",
            "id",
        )
    )
    list(
        OfficialFactCheckSourceEvidenceLink.objects.select_for_update(of=("self",))
        .filter(source__fact_check__claim=locked_claim)
        .order_by(
            "source_id",
            "captured_evidence_id",
            "id",
        )
    )
    publication_snapshots = list(
        OfficialFactCheckPublicationSnapshot.objects.select_for_update(of=("self",))
        .filter(fact_check__claim=locked_claim)
        .order_by("fact_check_id", "id")
    )

    locked_fact_check = None
    if identity["fact_check_id"] is not None:
        locked_fact_check = next(
            (item for item in fact_checks if item.id == identity["fact_check_id"]),
            None,
        )
        if (
            locked_fact_check is None
            or locked_fact_check.organization_id != organization.id
            or locked_fact_check.adjudication_decision_id != current_decision.id
        ):
            raise _publication_conflict()

    return {
        "claim": locked_claim,
        "assignment": assignment,
        "organization": organization,
        "decision": current_decision,
        "decision_snapshot": decision_snapshot,
        "snapshot_records": snapshot_records,
        "fact_checks": fact_checks,
        "fact_check": locked_fact_check,
        "publication_snapshots": publication_snapshots,
    }


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


def _snapshot_conflict():
    return PublishingConflict(
        "The current adjudication decision does not have a valid decision-time "
        "evidence snapshot. Publication cannot continue."
    )


def _validate_decision_snapshot(snapshot, *, decision, claim):
    if (
        snapshot is None
        or snapshot.decision_id != decision.id
        or str(snapshot.claim_id) != str(claim.id)
    ):
        raise _snapshot_conflict()

    try:
        return validate_evidence_snapshot(
            schema_version=snapshot.schema_version,
            evidence_records=snapshot.evidence_records,
        )
    except EvidenceSnapshotSchemaError as error:
        raise _snapshot_conflict() from error


def _normalize_snapshot_source_url(raw_url):
    if not isinstance(raw_url, str):
        return None
    url = raw_url.strip()
    if not url or len(url) > 2000:
        return None
    try:
        _url_validator(url)
    except ValidationError:
        return None
    return url


def _snapshot_record_sort_key(record):
    submitted_at = record["submitted_at"]
    return (
        submitted_at is None,
        submitted_at or "",
        str(record["id"]),
    )


def _sync_snapshot_evidence_sources(
    fact_check,
    *,
    actor,
    snapshot,
    snapshot_records,
):
    records_by_url = {}
    for record in sorted(snapshot_records, key=_snapshot_record_sort_key):
        if record["evidence_status"] != "VERIFIED":
            continue
        url = _normalize_snapshot_source_url(record["evidence_url"])
        if url is not None:
            records_by_url.setdefault(url, []).append(record)

    for url, records in records_by_url.items():
        title = next(
            (
                record["evidence_caption"]
                for record in records
                if isinstance(record["evidence_caption"], str)
                and record["evidence_caption"].strip()
            ),
            None,
        )
        source, _created = OfficialFactCheckSource.objects.get_or_create(
            fact_check=fact_check,
            url=url,
            defaults={
                "title": title,
                "added_by": actor,
                "source_type": (OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE),
                "is_editorially_selected": False,
            },
        )
        for record in records:
            try:
                link, created = (
                    OfficialFactCheckSourceEvidenceLink.objects.get_or_create(
                        source=source,
                        captured_evidence_id=record["id"],
                        defaults={"snapshot": snapshot},
                    )
                )

                if link.snapshot_id != snapshot.id:
                    raise PublishingConflict(
                        "An existing source-lineage association belongs "
                        "to a different decision snapshot."
                    )

                if not created:
                    link.full_clean()

            except ValidationError as error:
                raise PublishingConflict(
                    "The existing source-lineage association is invalid."
                ) from error


def _add_editorial_sources(
    fact_check,
    *,
    actor,
    normalized_urls,
):
    for url in normalized_urls:
        source, created = OfficialFactCheckSource.objects.get_or_create(
            fact_check=fact_check,
            url=url,
            defaults={
                "added_by": actor,
                "source_type": OfficialFactCheckSource.SourceType.MODERATOR_ADDED,
                "is_editorially_selected": True,
            },
        )
        if not created and source.is_editorially_selected is not True:
            source.is_editorially_selected = True
            source.save(update_fields=["is_editorially_selected"])


def _replace_moderator_sources(
    fact_check,
    *,
    actor,
    source_urls,
):
    normalized_urls = _normalize_source_urls(source_urls)
    requested_urls = set(normalized_urls)
    lineage_source_ids = set(
        OfficialFactCheckSourceEvidenceLink.objects.filter(
            source__fact_check=fact_check
        ).values_list("source_id", flat=True)
    )

    for source in fact_check.source_items.filter(is_editorially_selected=True):
        if source.url in requested_urls:
            continue
        if source.id in lineage_source_ids:
            source.is_editorially_selected = False
            source.save(update_fields=["is_editorially_selected"])
        else:
            source.delete()

    _add_editorial_sources(
        fact_check,
        actor=actor,
        normalized_urls=normalized_urls,
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
    snapshot,
    snapshot_records,
    source_urls=None,
    replace_moderator_sources=False,
):
    _sync_snapshot_evidence_sources(
        fact_check,
        actor=actor,
        snapshot=snapshot,
        snapshot_records=snapshot_records,
    )

    if replace_moderator_sources:
        _replace_moderator_sources(
            fact_check,
            actor=actor,
            source_urls=(source_urls or []),
        )

    elif source_urls:
        _add_editorial_sources(
            fact_check,
            actor=actor,
            normalized_urls=_normalize_source_urls(source_urls),
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

    identity = _get_decision_publication_identity(decision)

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        locked_claim = context["claim"]
        current_decision = context["decision"]

        active_drafts = [
            item
            for item in context["fact_checks"]
            if item.publication_status in ACTIVE_DRAFT_STATUSES
        ]

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

        max_version = max(
            (item.version for item in context["fact_checks"]),
            default=0,
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
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
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
    identity = _get_fact_check_publication_identity(fact_check)

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        locked_fact_check = context["fact_check"]

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.DRAFT
        ):
            raise InvalidPublicationTransition(
                "Only draft fact-checks " "can be edited."
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
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
            source_urls=source_urls,
            replace_moderator_sources=(source_urls is not None),
        )

        return locked_fact_check


def submit_fact_check_for_review(
    *,
    fact_check,
    actor,
):
    identity = _get_fact_check_publication_identity(fact_check)

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        locked_fact_check = context["fact_check"]

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.DRAFT
        ):
            raise InvalidPublicationTransition(
                "Only a draft can be " "submitted for review."
            )

        _sync_fact_check_sources(
            locked_fact_check,
            actor=actor,
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
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
    identity = _get_fact_check_publication_identity(fact_check)

    with transaction.atomic():
        context = _lock_publication_context(
            identity=identity,
            actor=actor,
            capability=PartnerCapability.PUBLISH_FACT_CHECK,
        )
        locked_fact_check = context["fact_check"]
        current_decision = context["decision"]

        if locked_fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.IN_REVIEW
        ):
            raise InvalidPublicationTransition(
                "Only a fact-check in review " "can be published."
            )

        if locked_fact_check.verdict != current_decision.verdict or (
            locked_fact_check.canonical_claim != current_decision.canonical_claim
        ):
            raise PublishingConflict(
                "The fact-check no longer "
                "matches the authoritative "
                "adjudication decision."
            )

        previous_published = next(
            (
                item
                for item in context["fact_checks"]
                if item.publication_status
                == OfficialFactCheck.PublicationStatus.PUBLISHED
                and item.id != locked_fact_check.id
            ),
            None,
        )
        if previous_published:
            raise PublishingConflict(
                "This claim already has a published fact-check. An explicit "
                "correction or revision workflow is required before it can "
                "be replaced."
            )

        if any(
            snapshot.fact_check_id == locked_fact_check.id
            for snapshot in context["publication_snapshots"]
        ):
            raise PublishingConflict(
                "This fact-check already has a sealed publication record."
            )

        _sync_fact_check_sources(
            locked_fact_check,
            actor=actor,
            snapshot=context["decision_snapshot"],
            snapshot_records=context["snapshot_records"],
        )

        _validate_publication_content(locked_fact_check)

        now = timezone.now()
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

        _record_publication_event(
            locked_fact_check,
            actor=actor,
            event_type=ModerationEvent.EventType.ARTICLE_PUBLISHED,
            from_status=previous_status,
            to_status=(OfficialFactCheck.PublicationStatus.PUBLISHED),
        )

        try:
            completed_assignment = complete_verification_assignment(
                claim=context["claim"],
                organization=context["organization"],
            )
        except VerificationAssignmentConflict as error:
            raise PublishingConflict(str(error)) from error

        if context["assignment"] is not None and completed_assignment is None:
            raise PublishingConflict(
                "The verification assignment changed before publication "
                "could be completed."
            )

        try:
            sealed_payload = OfficialFactCheckPublicationSnapshot.build_payload(
                fact_check=locked_fact_check,
                decision_snapshot=context["decision_snapshot"],
            )
            OfficialFactCheckPublicationSnapshot.objects.create(
                fact_check=locked_fact_check,
                decision_snapshot=context["decision_snapshot"],
                captured_at=now,
                payload=sealed_payload,
            )
        except ValidationError as error:
            raise PublishingConflict(
                "The publication record could not be sealed because its "
                "source provenance is inconsistent."
            ) from error

        published_fact_check_id = locked_fact_check.id

        transaction.on_commit(lambda: _queue_fact_check_index(published_fact_check_id))

        return {
            "fact_check": locked_fact_check,
            "archived_fact_check": previous_published,
        }
