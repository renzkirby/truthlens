# Generated for the Community reporting taxonomy refinement.

from django.db import migrations, models


REPORT_REASON_CHOICES = [
    ("INAPPROPRIATE", "Inappropriate Content"),
    ("SPAM", "Spam or unwanted promotion"),
    ("HARASSMENT", "Harassment or bullying"),
    ("HATE", "Hate or discrimination"),
    ("VIOLENCE_DANGEROUS", "Violence, threats, or dangerous content"),
    ("PRIVACY", "Sharing private information"),
    ("SEXUAL_EXPLOITATIVE", "Sexual or exploitative content"),
    ("IMPERSONATION_FRAUD", "Impersonation, scam, or fraud"),
    ("OTHER", "Others"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0114_community_account_enforcement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="communityreport",
            name="reason",
            field=models.CharField(
                choices=REPORT_REASON_CHOICES,
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="communityreportoutcome",
            name="reason",
            field=models.CharField(
                choices=REPORT_REASON_CHOICES,
                max_length=32,
            ),
        ),
    ]
