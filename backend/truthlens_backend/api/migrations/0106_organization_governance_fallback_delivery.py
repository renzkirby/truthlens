# Generated manually for the Partner governance no-Admin fallback checkpoint.

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0105_governance_notification_semantics"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="governance_contact_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text=(
                    "Private fallback address for material Partner governance "
                    "communication when no active Organization Admin can receive "
                    "a secure notice."
                ),
                max_length=254,
            ),
        ),
        migrations.CreateModel(
            name="OrganizationGovernanceFallbackDelivery",
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
                ("contact_email", models.EmailField(blank=True, default="", max_length=254)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SENT", "Sent"),
                            ("FAILED", "Failed"),
                            ("NOT_DELIVERABLE", "Not deliverable"),
                            ("OUT_OF_BAND_RECORDED", "Out-of-band notice recorded"),
                        ],
                        default="PENDING",
                        max_length=32,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("out_of_band_method", models.CharField(blank=True, default="", max_length=80)),
                ("out_of_band_details", models.TextField(blank=True, default="")),
                ("recorded_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "governance_event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="governance_fallback_delivery",
                        to="api.accountabilityevent",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recorded_organization_governance_fallback_deliveries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="organizationgovernancefallbackdelivery",
            index=models.Index(
                fields=["status", "-created_at"],
                name="org_gov_fallback_status_idx",
            ),
        ),
    ]
