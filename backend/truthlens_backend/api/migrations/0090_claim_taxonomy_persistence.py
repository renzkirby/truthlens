"""Persist explicit primary subject and Campus Affairs context state.

Existing classifications remain null for both fields. This migration does not
infer a primary subject or campus relevance from historical domain lists.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0089_simplify_partner_role_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="claiminvestigationclassification",
            name="primary_subject",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Explicit primary subject for public topic projection. "
                    "Must also appear in domains; null means no primary was persisted."
                ),
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="claiminvestigationclassification",
            name="campus_context_state",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CONFIRMED", "Confirmed campus relevance"),
                    ("NOT_APPLICABLE", "Not applicable"),
                    ("UNCERTAIN", "Uncertain campus relevance"),
                ],
                help_text=(
                    "Authoritative campus relevance assessment. "
                    "Null means campus context has not been assessed."
                ),
                max_length=16,
                null=True,
            ),
        ),
    ]
