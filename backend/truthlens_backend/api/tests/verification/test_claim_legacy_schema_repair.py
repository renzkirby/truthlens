"""No-live-DB tests of the legacy PostgreSQL Claim schema repair."""
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from django.test import SimpleTestCase


repair = import_module(
    "api.migrations.0086_relax_unmodeled_claim_relatedness_not_null"
)


def context(*, vendor="postgresql", modeled=False, column=(True, None)):
    model_columns = ["id", "context_text"]
    if modeled:
        model_columns.append("relatedness_context")
    claim = SimpleNamespace(
        _meta=SimpleNamespace(
            db_table="api_claim",
            concrete_fields=[
                SimpleNamespace(column=name) for name in model_columns
            ],
        )
    )
    apps = Mock()
    apps.get_model.return_value = claim
    connection = Mock(vendor=vendor)
    cursor = MagicMock()
    cursor.fetchone.return_value = column
    connection.cursor.return_value.__enter__.return_value = cursor
    editor = Mock(connection=connection)
    editor.quote_name.side_effect = lambda name: f'"{name}"'
    return apps, editor, cursor


class LegacyClaimRelatednessRepairTests(SimpleTestCase):
    def test_observed_legacy_not_null_no_default_is_relaxed_not_deleted(self):
        apps, editor, cursor = context(column=(True, None))
        repair.relax_unmodeled_relatedness_constraint(apps, editor)

        self.assertEqual(cursor.execute.call_count, 2)
        select = cursor.execute.call_args_list[0]
        self.assertIn("pg_attribute", select.args[0])
        self.assertEqual(
            select.args[1], ["api_claim", "relatedness_context"],
        )
        ddl = cursor.execute.call_args_list[1].args[0]
        self.assertEqual(
            ddl,
            'ALTER TABLE "api_claim" ALTER COLUMN "relatedness_context" '
            'DROP NOT NULL',
        )
        self.assertNotIn("DROP COLUMN", ddl)

    def test_fresh_schema_missing_column_is_noop(self):
        apps, editor, cursor = context(column=None)
        repair.relax_unmodeled_relatedness_constraint(apps, editor)
        cursor.execute.assert_called_once()

    def test_already_nullable_schema_is_noop(self):
        apps, editor, cursor = context(column=(False, None))
        repair.relax_unmodeled_relatedness_constraint(apps, editor)
        cursor.execute.assert_called_once()

    def test_column_with_server_default_is_not_modified(self):
        apps, editor, cursor = context(column=(True, "''::text"))
        repair.relax_unmodeled_relatedness_constraint(apps, editor)
        cursor.execute.assert_called_once()

    def test_nonpostgres_database_is_untouched(self):
        apps, editor, cursor = context(vendor="sqlite")
        repair.relax_unmodeled_relatedness_constraint(apps, editor)
        editor.connection.cursor.assert_not_called()

    def test_future_modeled_field_requires_review_not_silent_mutation(self):
        apps, editor, cursor = context(modeled=True)
        with self.assertRaisesRegex(RuntimeError, "schema ownership"):
            repair.relax_unmodeled_relatedness_constraint(apps, editor)
        editor.connection.cursor.assert_not_called()

    def test_migration_is_a_single_database_only_forward_operation(self):
        operations = repair.Migration.operations
        self.assertEqual(len(operations), 1)
        self.assertEqual(
            operations[0].code,
            repair.relax_unmodeled_relatedness_constraint,
        )
        self.assertIs(operations[0].reverse_code, repair.migrations.RunPython.noop)
