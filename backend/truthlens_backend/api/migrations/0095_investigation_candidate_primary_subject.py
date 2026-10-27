"""Store the automatic classifier's explicit primary-subject candidate.

Shadow-mode candidates remain non-authoritative. Enforce mode may copy the
validated candidate into ClaimInvestigationClassification.primary_subject.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0094_claim_institution_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="investigationclassificationassessment",
            name="candidate_primary_subject",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Shadow/enforce candidate primary subject. It is authoritative only "
                    "when copied into ClaimInvestigationClassification in enforce mode."
                ),
                max_length=32,
                null=True,
            ),
        ),
    ]
