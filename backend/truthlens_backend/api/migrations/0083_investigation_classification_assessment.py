from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0082_organization_scope_requests"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="claiminvestigationclassification", name="source",
            field=models.CharField(
                max_length=16, default="MANUAL",
                choices=[
                    ("MANUAL", "Manual legacy classification"),
                    ("AUTOMATIC", "Validated automated classification"),
                ],
            ),
        ),
        migrations.CreateModel(
            name="InvestigationClassificationAssessment",
            fields=[
                ("claim", models.OneToOneField(
                    primary_key=True, serialize=False,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="classification_assessment", to="api.claim",
                )),
                ("status", models.CharField(
                    max_length=16, choices=[
                        ("SUGGESTED", "Shadow-mode suggestion only"),
                        ("APPLIED", "Validated automatic result applied"),
                        ("ABSTAINED", "Insufficient classification evidence"),
                        ("FAILED", "Classification unavailable"),
                    ],
                )),
                ("candidate_domains", models.JSONField(default=list, blank=True)),
                ("candidate_jurisdiction", models.CharField(max_length=32, blank=True)),
                ("reason_code", models.CharField(max_length=64, blank=True)),
                ("classifier_version", models.CharField(max_length=32, default="v1")),
                ("input_fingerprint", models.CharField(max_length=64, blank=True)),
                ("assessed_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
    ]
