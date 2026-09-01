from django.db import migrations


def _extract_source(value):
    if isinstance(value, str):
        url = value.strip()

        if url.startswith(("http://", "https://")):
            return url, None

        return None, None

    if isinstance(value, dict):
        url = value.get("url")

        if not isinstance(url, str):
            return None, None

        url = url.strip()

        if not url.startswith(("http://", "https://")):
            return None, None

        title = value.get("title")

        if not isinstance(title, str):
            title = None

        return url, title

    return None, None


def _backfill_sources(
    fact_check,
    *,
    OfficialFactCheckSource,
    EvidenceSubmission,
):
    raw_sources = (
        fact_check.sources
        if isinstance(
            fact_check.sources,
            list,
        )
        else []
    )

    seen_urls = set()

    for raw_source in raw_sources:
        url, title = _extract_source(raw_source)

        if not url:
            continue

        if len(url) > 2000:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        evidence = None

        if fact_check.source_thread_id:
            evidence = EvidenceSubmission.objects.filter(
                thread_id=(fact_check.source_thread_id),
                evidence_url=url,
                evidence_status="VERIFIED",
            ).first()

        source_type = "VERIFIED_EVIDENCE" if evidence else "LEGACY_IMPORT"

        OfficialFactCheckSource.objects.get_or_create(
            fact_check_id=fact_check.id,
            url=url,
            defaults={
                "title": title,
                "evidence_submission_id": (evidence.id if evidence else None),
                "source_type": source_type,
            },
        )


def backfill_fact_check_publication(
    apps,
    schema_editor,
):
    OfficialFactCheck = apps.get_model(
        "api",
        "OfficialFactCheck",
    )

    OfficialFactCheckSource = apps.get_model(
        "api",
        "OfficialFactCheckSource",
    )

    EvidenceSubmission = apps.get_model(
        "api",
        "EvidenceSubmission",
    )

    AdjudicationDecision = apps.get_model(
        "api",
        "AdjudicationDecision",
    )

    # ---------------------------------
    # Legacy rows that can be linked
    # through source_thread → claim.
    # ---------------------------------

    claim_ids = (
        OfficialFactCheck.objects.exclude(source_thread_id__isnull=True)
        .values_list(
            "source_thread__claim_id",
            flat=True,
        )
        .distinct()
    )

    for claim_id in claim_ids:
        if not claim_id:
            continue

        fact_checks = list(
            OfficialFactCheck.objects.filter(
                source_thread__claim_id=(claim_id)
            ).order_by(
                "created_at",
                "id",
            )
        )

        if not fact_checks:
            continue

        latest_created_at = fact_checks[-1].created_at

        current_decision = AdjudicationDecision.objects.filter(
            claim_id=claim_id,
            is_current=True,
        ).first()

        total = len(fact_checks)

        for index, fact_check in enumerate(
            fact_checks,
            start=1,
        ):
            is_latest = index == total

            fact_check.claim_id = claim_id
            fact_check.version = index

            fact_check.headline = fact_check.canonical_claim[:300]

            fact_check.article_body = fact_check.summary or ""

            fact_check.drafted_by_id = fact_check.published_by_id

            fact_check.reviewed_by_id = fact_check.published_by_id

            fact_check.submitted_for_review_at = fact_check.created_at

            fact_check.reviewed_at = fact_check.created_at

            fact_check.published_at = fact_check.created_at

            if is_latest:
                fact_check.publication_status = "PUBLISHED"

                fact_check.archived_at = None

                if current_decision and (
                    current_decision.verdict == fact_check.verdict
                ):
                    fact_check.adjudication_decision_id = current_decision.id

                    fact_check.organization_id = current_decision.organization_id

            else:
                # Older duplicate legacy
                # publications are retained,
                # but no longer treated as
                # the current public article.
                fact_check.publication_status = "ARCHIVED"

                fact_check.archived_at = latest_created_at

            fact_check.save(
                update_fields=[
                    "claim",
                    "version",
                    "headline",
                    "article_body",
                    "drafted_by",
                    "reviewed_by",
                    ("submitted_for_" "review_at"),
                    "reviewed_at",
                    "published_at",
                    "publication_status",
                    "archived_at",
                    "adjudication_decision",
                    "organization",
                ]
            )

            _backfill_sources(
                fact_check,
                OfficialFactCheckSource=(OfficialFactCheckSource),
                EvidenceSubmission=(EvidenceSubmission),
            )

    # ---------------------------------
    # Preserve orphan legacy articles.
    #
    # We do not invent a Claim or
    # AdjudicationDecision link.
    # ---------------------------------

    orphan_fact_checks = OfficialFactCheck.objects.filter(claim_id__isnull=True)

    for fact_check in orphan_fact_checks.iterator():
        fact_check.publication_status = "PUBLISHED"

        fact_check.version = 1

        fact_check.headline = fact_check.canonical_claim[:300]

        fact_check.article_body = fact_check.summary or ""

        fact_check.drafted_by_id = fact_check.published_by_id

        fact_check.reviewed_by_id = fact_check.published_by_id

        fact_check.submitted_for_review_at = fact_check.created_at

        fact_check.reviewed_at = fact_check.created_at

        fact_check.published_at = fact_check.created_at

        fact_check.save(
            update_fields=[
                "publication_status",
                "version",
                "headline",
                "article_body",
                "drafted_by",
                "reviewed_by",
                ("submitted_for_" "review_at"),
                "reviewed_at",
                "published_at",
            ]
        )

        _backfill_sources(
            fact_check,
            OfficialFactCheckSource=(OfficialFactCheckSource),
            EvidenceSubmission=(EvidenceSubmission),
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "api",
            "0049_officialfactchecksource_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            backfill_fact_check_publication,
            migrations.RunPython.noop,
        ),
    ]
