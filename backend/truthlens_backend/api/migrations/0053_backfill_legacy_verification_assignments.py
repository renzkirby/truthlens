from django.db import migrations


def backfill_legacy_verification_assignments(
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

    VerificationAssignment = apps.get_model(
        "api",
        "VerificationAssignment",
    )

    db_alias = schema_editor.connection.alias

    # Only claims that have actually entered the
    # community investigation system are candidates.
    claim_ids_with_threads = (
        Thread.objects.using(db_alias)
        .values_list(
            "claim_id",
            flat=True,
        )
        .distinct()
    )

    claims = (
        Claim.objects.using(db_alias)
        .filter(
            id__in=claim_ids_with_threads,
        )
        .only(
            "id",
            "final_verdict",
        )
    )

    for claim in claims.iterator():
        # A claim with an authoritative final verdict
        # must not silently re-enter professional intake.
        if claim.final_verdict:
            continue

        # Only backfill genuinely legacy claims that
        # predate VerificationAssignment entirely.
        #
        # If any assignment history already exists,
        # leave that lifecycle untouched.
        assignment_exists = (
            VerificationAssignment.objects.using(db_alias)
            .filter(
                claim_id=claim.id,
            )
            .exists()
        )

        if assignment_exists:
            continue

        VerificationAssignment.objects.using(db_alias).create(
            claim_id=claim.id,
            status="AVAILABLE",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0052_verificationassignment"),
    ]

    operations = [
        migrations.RunPython(
            backfill_legacy_verification_assignments,
            migrations.RunPython.noop,
        ),
    ]
