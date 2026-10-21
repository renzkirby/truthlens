"""Repair a database-only Claim column left by older local schema versions.

The current Claim model and Django migration state do not contain
relatedness_context. An existing PostgreSQL table may still require it as
NOT NULL without a default, making all new Claim inserts fail. Loosen only
that obsolete database constraint; never drop the column or change its data.

Fresh databases without the column and already-repaired databases are no-ops.
"""
from django.db import migrations


LEGACY_COLUMN = "relatedness_context"


def relax_unmodeled_relatedness_constraint(apps, schema_editor):
    Claim = apps.get_model("api", "Claim")

    # If a future rebase adds this field to Django's managed model, stop:
    # its nullability must be controlled by that model's real migrations.
    if any(
        field.column == LEGACY_COLUMN
        for field in Claim._meta.concrete_fields
    ):
        raise RuntimeError(
            "Claim.relatedness_context is modeled; review schema ownership "
            "before applying the legacy database-only repair."
        )

    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        # The observed drift is PostgreSQL-only. Other databases must not
        # receive a silent, unportable constraint change.
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.attnotnull, pg_get_expr(d.adbin, d.adrelid)
              FROM pg_catalog.pg_attribute AS a
              LEFT JOIN pg_catalog.pg_attrdef AS d
                ON d.adrelid = a.attrelid AND d.adnum = a.attnum
             WHERE a.attrelid = to_regclass(%s)
               AND a.attname = %s
               AND a.attnum > 0
               AND NOT a.attisdropped
            """,
            [Claim._meta.db_table, LEGACY_COLUMN],
        )
        column = cursor.fetchone()
        if column is None:
            # Fresh Django-created databases never had this column.
            return

        not_null, db_default = column
        if not not_null or db_default is not None:
            # Already nullable, or has a real server-side default and
            # therefore does not need this particular repair.
            return

        cursor.execute(
            "ALTER TABLE {} ALTER COLUMN {} DROP NOT NULL".format(
                schema_editor.quote_name(Claim._meta.db_table),
                schema_editor.quote_name(LEGACY_COLUMN),
            )
        )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0085_organization_specializations"),
    ]

    operations = [
        migrations.RunPython(
            relax_unmodeled_relatedness_constraint,
            migrations.RunPython.noop,
        ),
    ]
