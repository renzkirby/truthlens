from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone
import uuid


NOTIFICATION_TYPES = [
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
    "COMMUNITY_MODERATION_OUTCOME",
]

NOTIFICATION_TARGETS = [
    "CLAIM",
    "THREAD",
    "OFFICIAL_FACT_CHECK",
    "WORKSPACE",
    "ORGANIZATION",
    "GOVERNANCE_NOTICE",
    "USER_PROFILE",
    "MODERATION_OUTCOME",
]


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0097_reconcile_active_successor_evidence_handoffs"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommunitySafetyDecision",
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
                    "action",
                    models.CharField(
                        choices=[("DISMISS", "Dismiss"), ("REMOVE", "Remove")],
                        max_length=20,
                    ),
                ),
                ("violation_code", models.CharField(blank=True, default="", max_length=64)),
                ("policy_title_snapshot", models.CharField(max_length=160)),
                ("policy_version", models.CharField(max_length=20)),
                (
                    "violation_label_snapshot",
                    models.CharField(blank=True, default="", max_length=160),
                ),
                ("thread_id_snapshot", models.UUIDField()),
                (
                    "author_username_snapshot",
                    models.CharField(blank=True, default="", max_length=150),
                ),
                ("content_excerpt_snapshot", models.TextField(blank=True, default="")),
                ("rationale", models.TextField()),
                ("decided_at", models.DateTimeField(default=timezone.now, editable=False)),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_safety_decisions_made",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "moderation_case",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="community_safety_decision",
                        to="api.moderationcase",
                    ),
                ),
                (
                    "thread_author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_safety_decisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-decided_at"],
                "indexes": [
                    models.Index(
                        fields=["violation_code", "-decided_at"],
                        name="community_safety_violation_idx",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="flagresolutionlog",
            name="report_outcome",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CONFIRMED", "Confirmed"),
                    ("NOT_CONFIRMED", "Not confirmed"),
                    ("NO_VIOLATION", "No violation found"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="flagresolutionlog",
            name="safety_decision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="report_outcomes",
                to="api.communitysafetydecision",
            ),
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
                    ("ORGANIZATION_GOVERNANCE_CHANGED", "Organization governance changed"),
                    ("THREAD_COMMENTED", "Thread commented"),
                    ("EVIDENCE_REVIEWED", "Evidence reviewed"),
                    ("USER_FOLLOWED", "User followed"),
                    ("COMMUNITY_MODERATION_OUTCOME", "Community moderation outcome"),
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
                    ("MODERATION_OUTCOME", "Moderation outcome"),
                ],
                max_length=24,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="notification",
            name="notification_type_valid",
        ),
        migrations.RemoveConstraint(
            model_name="notification",
            name="notification_target_valid",
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=models.Q(notification_type__in=NOTIFICATION_TYPES),
                name="notification_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=models.Q(target_type__in=NOTIFICATION_TARGETS),
                name="notification_target_valid",
            ),
        ),
    ]
