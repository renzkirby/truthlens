from django.db import migrations


ACTIVE_CASE_STATUSES = [
    "OPEN",
    "IN_REVIEW",
    "ESCALATED",
    "REOPENED",
]


def reconcile_active_successor_evidence_handoffs(apps, schema_editor):
    EvidenceReviewDecision = apps.get_model("api", "EvidenceReviewDecision")
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
            thread__claim_id__in=organization_by_claim,
            evidence_status__in=["VERIFIED", "REJECTED"],
        )
        .values_list("id", "thread__claim_id", "evidence_status")
        .order_by("submitted_at", "id")
    )

    for evidence_id, claim_id, evidence_status in evidence_rows:
        organization_id = organization_by_claim.get(claim_id)
        if organization_id is None:
            continue

        # Only repair evidence with persisted institutional review provenance.
        # Factual-correction-only evidence is intentionally excluded by 0096.
        if not EvidenceReviewDecision.objects.filter(
            evidence_submission_id=evidence_id,
        ).exists():
            continue

        current_basis = (
            EvidenceReviewDecision.objects.filter(
                evidence_submission_id=evidence_id,
                organization_id=organization_id,
            )
            .order_by("-reviewed_at", "-id")
            .values_list("disposition", flat=True)
            .first()
        )
        if current_basis == evidence_status:
            continue

        # Never steal or duplicate an active Evidence case. Runtime ownership
        # reconciliation remains responsible for cases that already exist.
        if ModerationCase.objects.filter(
            case_type="EVIDENCE",
            evidence_submission_id=evidence_id,
            status__in=ACTIVE_CASE_STATUSES,
        ).exists():
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
                "legacy_repair": "0097_reconcile_active_successor_evidence_handoffs",
                "organization_id": str(organization_id),
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0096_institutional_evidence_review_provenance"),
    ]

    operations = [
        migrations.RunPython(
            reconcile_active_successor_evidence_handoffs,
            migrations.RunPython.noop,
        ),
    ]
