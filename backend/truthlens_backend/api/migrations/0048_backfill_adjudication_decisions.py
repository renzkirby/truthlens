from django.db import migrations

SUPPORTED_VERDICTS = {
    "FACT",
    "FAKE",
    "MISLEADING",
    "SATIRE",
    "UNVERIFIED",
}


def backfill_adjudication_decisions(
    apps,
    schema_editor,
):
    Claim = apps.get_model(
        "api",
        "Claim",
    )

    Thread = apps.get_model(
        "api",
        "Thread",
    )

    OfficialFactCheck = apps.get_model(
        "api",
        "OfficialFactCheck",
    )

    AdjudicationDecision = apps.get_model(
        "api",
        "AdjudicationDecision",
    )

    claims = Claim.objects.exclude(final_verdict__isnull=True).exclude(final_verdict="")

    for claim in claims.iterator():
        verdict = claim.final_verdict

        if verdict not in SUPPORTED_VERDICTS:
            continue

        if AdjudicationDecision.objects.filter(
            claim_id=claim.id,
            is_current=True,
        ).exists():
            continue

        thread = (
            Thread.objects.filter(
                claim_id=claim.id,
                moderator_verdict__isnull=False,
            )
            .order_by(
                "-moderated_at",
                "-created_at",
            )
            .first()
        )

        official_fact_check = (
            OfficialFactCheck.objects.filter(source_thread__claim_id=(claim.id))
            .order_by("-created_at")
            .first()
        )

        canonical_claim = ""

        if official_fact_check:
            canonical_claim = official_fact_check.canonical_claim or ""

        if not canonical_claim:
            canonical_claim = claim.context_text or ""

        rationale = ""

        if thread:
            rationale = thread.moderator_notes or ""

        if not rationale and official_fact_check:
            rationale = official_fact_check.summary or ""

        decided_by_id = thread.moderated_by_id if thread else None

        decided_at = (
            thread.moderated_at
            if (thread and thread.moderated_at)
            else claim.last_updated
        )

        AdjudicationDecision.objects.create(
            claim_id=claim.id,
            verdict=verdict,
            canonical_claim=canonical_claim,
            rationale=rationale,
            decided_by_id=decided_by_id,
            ai_verdict_snapshot=(claim.ai_verdict),
            ai_confidence_snapshot=(claim.consensus_score),
            ai_summary_snapshot=(claim.ai_summary),
            decision_source=("LEGACY_MIGRATION"),
            revision_number=1,
            is_current=True,
            decided_at=decided_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "api",
            "0047_adjudicationdecision",
        ),
    ]

    operations = [
        migrations.RunPython(
            backfill_adjudication_decisions,
            migrations.RunPython.noop,
        ),
    ]
