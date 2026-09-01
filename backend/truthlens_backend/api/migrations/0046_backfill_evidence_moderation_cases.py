from django.db import migrations


ACTIVE_STATUSES = [
    "OPEN",
    "IN_REVIEW",
    "ESCALATED",
    "REOPENED",
]


def backfill_evidence_cases(
    apps,
    schema_editor,
):
    EvidenceSubmission = apps.get_model(
        "api",
        "EvidenceSubmission",
    )

    ModerationCase = apps.get_model(
        "api",
        "ModerationCase",
    )

    ModerationEvent = apps.get_model(
        "api",
        "ModerationEvent",
    )

    evidence_ids = (
        EvidenceSubmission.objects
        .filter(
            evidence_status="UNVERIFIED"
        )
        .values_list(
            "id",
            flat=True,
        )
    )

    for evidence_id in evidence_ids:
        existing_case = (
            ModerationCase.objects
            .filter(
                case_type="EVIDENCE",
                evidence_submission_id=(
                    evidence_id
                ),
                status__in=ACTIVE_STATUSES,
            )
            .first()
        )

        if existing_case:
            continue

        case = ModerationCase.objects.create(
            case_type="EVIDENCE",
            status="OPEN",
            priority="NORMAL",
            source="EVIDENCE_SUBMISSION",
            evidence_submission_id=(
                evidence_id
            ),
        )

        ModerationEvent.objects.create(
            case_id=case.id,
            event_type="CASE_CREATED",
            to_status="OPEN",
            metadata={
                "source":
                    "EVIDENCE_SUBMISSION",
                "priority": "NORMAL",
                "legacy_backfill": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "api",
            "0045_evidencesubmission_rejection_reason",
        ),
    ]

    operations = [
        migrations.RunPython(
            backfill_evidence_cases,
            migrations.RunPython.noop,
        ),
    ]