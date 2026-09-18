# Generated manually for the TruthLens 4I-C1 checkpoint.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0062_factualcorrectionproposal"),
    ]

    operations = [
        migrations.AddField(
            model_name="officialfactcheck",
            name="edit_generation",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "Optimistic concurrency generation for mutable unpublished "
                    "article work."
                ),
            ),
        ),
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
                    (
                        "SAFETY_VIOLATION_CONFIRMED",
                        "Safety Violation Confirmed",
                    ),
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
                    (
                        "ARTICLE_RETURNED_FOR_REWORK",
                        "Article Returned for Rework",
                    ),
                    ("ARTICLE_ABANDONED", "Article Abandoned"),
                    ("ARTICLE_PUBLISHED", "Article Published"),
                    ("ARTICLE_REVISED", "Article Revised"),
                    (
                        "FACTUAL_CORRECTION_REQUESTED",
                        "Factual Correction Requested",
                    ),
                    (
                        "FACTUAL_CORRECTION_PROPOSAL_PREPARED",
                        "Factual Correction Proposal Prepared",
                    ),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
    ]
