from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0064_accountabilityevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountabilityevent",
            name="actor_id_snapshot",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
    ]
