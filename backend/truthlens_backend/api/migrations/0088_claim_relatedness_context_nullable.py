"""Match historic Claim.relatedness_context SQL NULL allowance.

The removed development-only 0086 schema repair already dropped the NOT NULL
constraint in the shared dev database. Fresh databases need this managed
AlterField, while existing databases can apply it without dropping rows.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0087_merge_partner_relatedness"),
    ]

    operations = [
        migrations.AlterField(
            model_name="claim",
            name="relatedness_context",
            field=models.JSONField(blank=True, default=dict, editable=False, null=True),
        ),
    ]
