# Generated manually for the TruthLens 4I B3B2 checkpoint.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0061_factualcorrectionrequest"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="moderationevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("CASE_CREATED", "Case Created"),
                    ("CASE_CLAIMED", "Case Claimed"),
                    ("CASE_ASSIGNED", "Case Assigned"),
                    ("CASE_UNASSIGNED", "Case Unassigned"),
                    ("REVIEW_STARTED", "Review Started"),
                    ("CASE_ESCALATED", "Case Escalated"),
                    ("CASE_RESOLVED", "Case Resolved"),
                    ("CASE_REOPENED", "Case Reopened"),
                    ("CASE_CANCELLED", "Case Cancelled"),
                    ("SAFETY_DISMISSED", "Safety Report Dismissed"),
                    ("SAFETY_VIOLATION_CONFIRMED", "Safety Violation Confirmed"),
                    ("CONTENT_REMOVED", "Content Removed"),
                    ("EVIDENCE_VERIFIED", "Evidence Verified"),
                    ("EVIDENCE_REJECTED", "Evidence Rejected"),
                    ("EVIDENCE_REOPENED", "Evidence Review Reopened"),
                    ("ADJUDICATION_STARTED", "Adjudication Started"),
                    ("VERDICT_ISSUED", "Verdict Issued"),
                    ("VERDICT_REOPENED", "Verdict Reopened"),
                    ("VERDICT_REVISED", "Verdict Revised"),
                    ("ARTICLE_DRAFT_CREATED", "Article Draft Created"),
                    ("ARTICLE_SUBMITTED", "Article Submitted for Review"),
                    ("ARTICLE_PUBLISHED", "Article Published"),
                    ("ARTICLE_REVISED", "Article Revised"),
                    ("FACTUAL_CORRECTION_REQUESTED", "Factual Correction Requested"),
                    (
                        "FACTUAL_CORRECTION_PROPOSAL_PREPARED",
                        "Factual Correction Proposal Prepared",
                    ),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
        migrations.CreateModel(
            name="FactualCorrectionProposal",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("DRAFT", "Draft"), ("PREPARED", "Prepared")],
                        db_index=True,
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "verdict",
                    models.CharField(
                        choices=[
                            ("FACT", "Fact"),
                            ("FAKE", "Fake"),
                            ("MISLEADING", "Misleading"),
                            ("SATIRE", "Satire"),
                            ("UNVERIFIED", "Unverified"),
                        ],
                        max_length=20,
                    ),
                ),
                ("canonical_claim", models.TextField()),
                ("rationale", models.TextField()),
                ("headline", models.CharField(max_length=300)),
                ("summary", models.TextField()),
                ("article_body", models.TextField()),
                ("source_urls", models.JSONField(default=list)),
                (
                    "prepared_payload_schema_version",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        editable=False,
                        null=True,
                    ),
                ),
                (
                    "prepared_payload",
                    models.JSONField(blank=True, editable=False, null=True),
                ),
                (
                    "prepared_by_snapshot",
                    models.JSONField(blank=True, editable=False, null=True),
                ),
                (
                    "organization_snapshot",
                    models.JSONField(blank=True, editable=False, null=True),
                ),
                (
                    "prepared_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "correction_request",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="proposal",
                        to="api.factualcorrectionrequest",
                    ),
                ),
                (
                    "prepared_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prepared_factual_correction_proposals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "verification_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="factual_correction_proposals",
                        to="api.verificationrun",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["status", "-created_at"],
                        name="fact_corr_proposal_status_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("version__gte", 1)),
                        name="fact_correction_proposal_version_positive",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("organization_snapshot__isnull", True),
                                ("prepared_at__isnull", True),
                                ("prepared_by__isnull", True),
                                ("prepared_by_snapshot__isnull", True),
                                ("prepared_payload__isnull", True),
                                ("prepared_payload_schema_version__isnull", True),
                                ("status", "DRAFT"),
                            )
                            | models.Q(
                                ("organization_snapshot__isnull", False),
                                ("prepared_at__isnull", False),
                                ("prepared_by_snapshot__isnull", False),
                                ("prepared_payload__isnull", False),
                                ("prepared_payload_schema_version__isnull", False),
                                ("status", "PREPARED"),
                            )
                        ),
                        name="fact_correction_proposal_lifecycle_payload",
                    ),
                ],
            },
        ),
    ]
