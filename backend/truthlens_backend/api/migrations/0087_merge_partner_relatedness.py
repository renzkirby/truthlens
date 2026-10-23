"""Join published partner-governance history with applied relatedness history.

Do not recreate relatedness tables: the separate 0081 migration is preserved
because it has already been applied to the shared development database.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0085_organization_specializations"),
        ("api", "0081_related_fact_check_decision"),
    ]

    operations = []
