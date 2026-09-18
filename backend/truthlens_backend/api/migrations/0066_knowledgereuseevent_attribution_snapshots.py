from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0065_accountabilityevent_actor_id_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgereuseevent",
            name="source_organization_id_snapshot",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="knowledgereuseevent",
            name="target_claim_id_snapshot",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
    ]
