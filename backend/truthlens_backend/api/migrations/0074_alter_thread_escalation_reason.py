from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0073_thread_comment_replies_and_likes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="thread",
            name="escalation_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("INCORRECT_VERDICT", "AI assessment may be incorrect"),
                    ("LOW_CONFIDENCE", "AI confidence score is too low"),
                    ("UNVERIFIED_RESULT", "Claim remains unverified"),
                    (
                        "MISSING_CONTEXT",
                        "The context provided is incomplete or missing",
                    ),
                    (
                        "OUTDATED_INFO",
                        "The AI relied on outdated information or news",
                    ),
                    ("OTHER", "Other"),
                ],
                max_length=20,
                null=True,
            ),
        ),
    ]
