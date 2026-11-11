from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0107_organization_governance_reconsideration"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="workspace_guide_version_seen",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
