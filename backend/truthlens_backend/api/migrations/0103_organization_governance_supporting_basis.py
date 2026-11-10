# Generated manually for the Partner Organization governance implementation.

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0102_claimability_context_lifecycle"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationGovernanceSupportingBasis",
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
                ("summary", models.TextField()),
                ("references", models.JSONField(blank=True, default=list)),
                ("redacted_at", models.DateTimeField(blank=True, null=True)),
                ("redaction_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_organization_governance_supporting_bases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "governance_event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="governance_supporting_basis",
                        to="api.accountabilityevent",
                    ),
                ),
                (
                    "redacted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="redacted_organization_governance_supporting_bases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
