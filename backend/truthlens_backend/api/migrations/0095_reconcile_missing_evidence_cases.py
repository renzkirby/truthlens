from django.db import migrations


ACTIVE_CASE_STATUSES = [
    "OPEN",
    "IN_REVIEW",
    "ESCALATED",
    "REOPENED",
]


def reconcile_missing_evidence_cases(apps, schema_editor):
    EvidenceSubmission = apps.get_model("api", "EvidenceSubmission")
    ModerationCase = apps.get_model("api", "ModerationCase")
    ModerationEvent = apps.get_model("api", "ModerationEvent")
    VerificationAssignment = apps.get_model("api", "VerificationAssignment")

    organization_by_claim = dict(
        VerificationAssignment.objects.filter(
            status="ACTIVE",
            organization_id__isnull=False,
        ).values_list("claim_id", "organization_id")
    )
    if not organization_by_claim:
        return

    evidence_rows = (
        EvidenceSubmission.objects.filter(
            evidence_status="UNVERIFIED",
            thread__claim_id__in=organization_by_claim,
        )
        .values_list("id", "thread__claim_id")
        .order_by("submitted_at", "id")
    )

    for evidence_id, claim_id in evidence_rows:
        # Never rewrite or resurrect any existing Evidence review history.
        if ModerationCase.objects.filter(
            case_type="EVIDENCE",
            evidence_submission_id=evidence_id,
        ).exists():
            continue

        organization_id = organization_by_claim.get(claim_id)
        if organization_id is None:
            continue

        case = ModerationCase.objects.create(
            case_type="EVIDENCE",
            status="OPEN",
            priority="NORMAL",
            source="EVIDENCE_SUBMISSION",
            evidence_submission_id=evidence_id,
            organization_id=organization_id,
        )
        ModerationEvent.objects.create(
            case_id=case.id,
            event_type="CASE_CREATED",
            to_status="OPEN",
            metadata={
                "source": "EVIDENCE_SUBMISSION",
                "priority": "NORMAL",
                "legacy_repair": "0095_reconcile_missing_evidence_cases",
                "organization_id": str(organization_id),
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0094_claim_institution_identity"),
    ]

    operations = [
        migrations.RunPython(
            reconcile_missing_evidence_cases,
            migrations.RunPython.noop,
        ),
    ]
