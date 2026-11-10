# Generated manually for the Partner Organization governance notice foundation.

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0103_organization_governance_supporting_basis"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationGovernanceNoticeRecipient",
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
                    "audience",
                    models.CharField(
                        choices=[
                            ("ADMIN", "Organization Admin"),
                            ("MEMBER", "Organization Member"),
                        ],
                        max_length=16,
                    ),
                ),
                ("can_read_notice", models.BooleanField(default=True)),
                (
                    "in_app_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SENT", "Sent"),
                            ("FAILED", "Failed"),
                            ("SKIPPED", "Skipped"),
                        ],
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                (
                    "email_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SENT", "Sent"),
                            ("FAILED", "Failed"),
                            ("SKIPPED", "Skipped"),
                        ],
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                ("in_app_attempts", models.PositiveSmallIntegerField(default=0)),
                ("email_attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_delivery_error", models.TextField(blank=True, default="")),
                ("last_delivery_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("viewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "governance_event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="governance_notice_recipients",
                        to="api.accountabilityevent",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="organization_governance_notice_recipients",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["user", "-created_at"],
                        name="org_gov_notice_user_idx",
                    ),
                    models.Index(
                        fields=["governance_event", "audience"],
                        name="org_gov_notice_event_aud_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("governance_event", "user"),
                        name="org_gov_notice_event_user_uniq",
                    ),
                ],
            },
        ),
    ]
