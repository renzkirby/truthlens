from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0099_vote_reputation_weight_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_safety_status",
            field=models.CharField(
                choices=[
                    ("NOT_CHECKED", "Not checked"),
                    ("NO_KNOWN_THREATS", "No known threats detected"),
                    ("KNOWN_THREAT", "Known threat"),
                    ("CHECK_UNAVAILABLE", "Safety check unavailable"),
                ],
                default="NOT_CHECKED",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_safety_provider",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_safety_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_safety_threat_types",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_safety_reason",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_preview_status",
            field=models.CharField(
                choices=[
                    ("NOT_REQUESTED", "Not requested"),
                    ("PENDING", "Pending"),
                    ("READY", "Ready"),
                    ("UNAVAILABLE", "Unavailable"),
                    ("BLOCKED", "Blocked"),
                ],
                default="NOT_REQUESTED",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_preview_title",
            field=models.CharField(blank=True, default="", max_length=300),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_preview_description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_preview_site_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_preview_final_url",
            field=models.URLField(blank=True, max_length=2000, null=True),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_preview_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="url_preview_failure_reason",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
