"""Add durable optional-context decisions; no historical data backfill."""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0080_verificationtelemetryevent")]

    operations = [
        migrations.CreateModel(
            name="RelatedFactCheckDecision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("identity", models.CharField(max_length=64, unique=True)),
                ("proposition_fingerprint", models.CharField(max_length=64)),
                ("publication_version", models.PositiveIntegerField()),
                ("publication_digest", models.CharField(max_length=64)),
                ("representation_digest", models.CharField(max_length=64)),
                ("contract_version", models.CharField(max_length=32)),
                ("state", models.CharField(choices=[("PENDING", "Pending"), ("PROCESSING", "Processing"), ("COMPLETED", "Completed"), ("FAILED", "Failed")], default="PENDING", max_length=16)),
                ("classification", models.CharField(choices=[("EQUIVALENT", "Equivalent"), ("RELATED", "Related"), ("UNRELATED", "Unrelated"), ("UNCERTAIN", "Uncertain")], default="UNCERTAIN", max_length=16)),
                ("connection_category", models.CharField(default="NONE", max_length=32)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("failure_code", models.CharField(blank=True, max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("publication", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="api.officialfactcheck")),
                ("publication_snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="api.officialfactcheckpublicationsnapshot")),
            ],
        ),
        migrations.AddField(
            model_name="claim", name="relatedness_context",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
        migrations.AddField(
            model_name="claim", name="relatedness_decision",
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bound_claims", to="api.relatedfactcheckdecision"),
        ),
    ]
