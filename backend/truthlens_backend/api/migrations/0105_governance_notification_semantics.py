# Generated manually for governance notification semantics.

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0104_organization_governance_notice_recipient"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="notification",
            name="notification_type_valid",
        ),
        migrations.RemoveConstraint(
            model_name="notification",
            name="notification_target_valid",
        ),
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("AUTOMATED_VERIFICATION_COMPLETED", "Analysis completed"),
                    ("AUTOMATED_VERIFICATION_FAILED", "Analysis failed"),
                    ("PARTNER_FACT_CHECK_PUBLISHED", "Partner fact-check published"),
                    ("PARTNER_FACT_CHECK_CORRECTED", "Partner fact-check corrected"),
                    ("ARTICLE_RETURNED_FOR_REWORK", "Article returned for rework"),
                    ("FACT_CHECK_PUBLISHED", "Fact-check published"),
                    ("FACTUAL_CORRECTION_PUBLISHED", "Factual correction published"),
                    ("ORGANIZATION_MEMBERSHIP_CHANGED", "Membership changed"),
                    (
                        "ORGANIZATION_GOVERNANCE_CHANGED",
                        "Organization governance changed",
                    ),
                    ("THREAD_COMMENTED", "Thread commented"),
                    ("EVIDENCE_REVIEWED", "Evidence reviewed"),
                    ("USER_FOLLOWED", "User followed"),
                ],
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("CLAIM", "Claim"),
                    ("THREAD", "Thread"),
                    ("OFFICIAL_FACT_CHECK", "Official fact-check"),
                    ("WORKSPACE", "Workspace"),
                    ("ORGANIZATION", "Organization"),
                    ("GOVERNANCE_NOTICE", "Governance notice"),
                    ("USER_PROFILE", "User profile"),
                ],
                max_length=24,
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=Q(
                    notification_type__in=[
                        "AUTOMATED_VERIFICATION_COMPLETED",
                        "AUTOMATED_VERIFICATION_FAILED",
                        "PARTNER_FACT_CHECK_PUBLISHED",
                        "PARTNER_FACT_CHECK_CORRECTED",
                        "ARTICLE_RETURNED_FOR_REWORK",
                        "FACT_CHECK_PUBLISHED",
                        "FACTUAL_CORRECTION_PUBLISHED",
                        "ORGANIZATION_MEMBERSHIP_CHANGED",
                        "ORGANIZATION_GOVERNANCE_CHANGED",
                        "THREAD_COMMENTED",
                        "EVIDENCE_REVIEWED",
                        "USER_FOLLOWED",
                    ]
                ),
                name="notification_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=Q(
                    target_type__in=[
                        "CLAIM",
                        "THREAD",
                        "OFFICIAL_FACT_CHECK",
                        "WORKSPACE",
                        "ORGANIZATION",
                        "GOVERNANCE_NOTICE",
                        "USER_PROFILE",
                    ]
                ),
                name="notification_target_valid",
            ),
        ),
    ]
