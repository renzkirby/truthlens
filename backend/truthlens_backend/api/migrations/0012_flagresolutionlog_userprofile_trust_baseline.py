from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0011_userprofile_email_verification_token_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="trust_score",
            field=models.FloatField(default=50.0),
        ),
        migrations.CreateModel(
            name="FlagResolutionLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("INAPPROPRIATE", "Inappropriate Content"),
                            ("SPAM", "Spam"),
                            ("HARASSMENT", "Harassment"),
                            ("OTHER", "Other"),
                        ],
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, null=True)),
                ("flagged_at", models.DateTimeField()),
                (
                    "resolved_action",
                    models.CharField(
                        choices=[
                            ("DISMISS", "Dismiss"),
                            ("REMOVE", "Remove"),
                            ("ESCALATE", "Escalate"),
                        ],
                        max_length=20,
                    ),
                ),
                ("is_valid_report", models.BooleanField(default=False)),
                ("resolved_at", models.DateTimeField(auto_now_add=True)),
                (
                    "flagged_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="resolved_thread_flags",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_flags_moderated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="flag_resolution_logs",
                        to="api.thread",
                    ),
                ),
            ],
            options={"ordering": ["-resolved_at"]},
        ),
    ]
