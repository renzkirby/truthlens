from django.db import migrations, models


LEGACY_BASE_SCORE = 50.0


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def backfill_legacy_vote_reputation_weights(apps, schema_editor):
    Vote = apps.get_model("api", "Vote")

    pending = []
    for vote in Vote.objects.all().iterator(chunk_size=500):
        snapshot = (
            LEGACY_BASE_SCORE
            if vote.vote_trust_snapshot is None
            else float(vote.vote_trust_snapshot)
        )
        snapshot = _clamp(snapshot, 0.0, 100.0)

        # Existing votes predate resolved/validated history snapshots.
        # Preserve their historical vote-time Trust influence instead of
        # inventing action counts that were never stored.
        vote.vote_reputation_weight_snapshot = (
            0.5 + (snapshot / 200.0)
        )
        pending.append(vote)

        if len(pending) >= 500:
            Vote.objects.bulk_update(
                pending,
                ["vote_reputation_weight_snapshot"],
            )
            pending = []

    if pending:
        Vote.objects.bulk_update(
            pending,
            ["vote_reputation_weight_snapshot"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0098_investigation_candidate_primary_subject"),
    ]

    operations = [
        migrations.AddField(
            model_name="vote",
            name="vote_reputation_weight_snapshot",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="vote",
            name="vote_resolved_actions_snapshot",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="vote",
            name="vote_validated_actions_snapshot",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(
            backfill_legacy_vote_reputation_weights,
            migrations.RunPython.noop,
        ),
    ]
