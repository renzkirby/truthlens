import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0106_organization_governance_fallback_delivery"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationGovernanceReconsideration",
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
                ("grounds", models.JSONField(default=list)),
                ("request_statement", models.TextField()),
                ("supporting_references", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("UNDER_REVIEW", "Under review"),
                            ("RESOLVED", "Resolved"),
                            ("MOOT", "Moot"),
                        ],
                        db_index=True,
                        default="SUBMITTED",
                        max_length=20,
                    ),
                ),
                ("reviewer_independence_note", models.TextField(blank=True, default="")),
                ("independence_override_rationale", models.TextField(blank=True, default="")),
                (
                    "outcome",
                    models.CharField(
                        blank=True,
                        choices=[("UPHELD", "Upheld"), ("REVOKED", "Revoked")],
                        default="",
                        max_length=16,
                    ),
                ),
                ("resolution_rationale", models.TextField(blank=True, default="")),
                ("internal_supporting_basis", models.TextField(blank=True, default="")),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("review_started_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "notice_recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reconsiderations",
                        to="api.organizationgovernancenoticerecipient",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="governance_reconsiderations",
                        to="api.organization",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requested_governance_reconsiderations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_governance_reconsiderations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "suspension_event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="governance_reconsiderations",
                        to="api.accountabilityevent",
                    ),
                ),
            ],
            options={"ordering": ["-submitted_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="organizationgovernancereconsideration",
            constraint=models.UniqueConstraint(
                condition=Q(status__in=["SUBMITTED", "UNDER_REVIEW"]),
                fields=("suspension_event",),
                name="org_gov_reconsideration_one_open",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationgovernancereconsideration",
            index=models.Index(
                fields=["organization", "status", "-submitted_at"],
                name="org_gov_reconsider_org_idx",
            ),
        ),
    ]
