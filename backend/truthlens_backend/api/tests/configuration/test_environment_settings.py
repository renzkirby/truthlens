import json
import os
from pathlib import Path
import subprocess
import sys

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from truthlens_backend.environment import (
    normalize_supabase_pooler_port,
    resolve_app_environment,
    select_database_url,
    validate_debug_policy,
)


DEV_URL = "postgresql://dev_user:dev_password@dev.example.test/dev_db"
TEST_URL = "postgresql://test_user:test_password@test.example.test/test_db"
STAGING_URL = (
    "postgresql://staging_user:staging_password@staging.example.test/staging_db"
)
PRODUCTION_URL = (
    "postgresql://production_user:production_password@production.example.test/prod_db"
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_RESULT_PREFIX = "TRUTHLENS_SETTINGS_RESULT="
SETTINGS_PROBE = f"""
import json
import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False

from django.conf import settings

database = settings.DATABASES["default"]
print(
    {SETTINGS_RESULT_PREFIX!r}
    + json.dumps(
        {{
            "app_env": settings.APP_ENV,
            "debug": settings.DEBUG,
            "engine": database["ENGINE"],
            "name": str(database["NAME"]),
            "host": database.get("HOST", ""),
            "port": str(database.get("PORT", "")),
            "user": database.get("USER", ""),
        }}
    )
)
"""


def _isolated_process_environment(settings_module, overrides=None):
    """Build a minimal environment containing no inherited app configuration."""

    environment = {
        name: os.environ[name]
        for name in (
            "COMSPEC",
            "LANG",
            "LC_ALL",
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "TMPDIR",
            "VIRTUAL_ENV",
            "WINDIR",
        )
        if name in os.environ
    }
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": settings_module,
            "PYTHONIOENCODING": "utf-8",
            "SECRET_KEY": "synthetic-settings-initialization-key",
        }
    )
    environment.update(overrides or {})
    return environment


def _run_settings_initialization(settings_module, overrides=None):
    return subprocess.run(
        [sys.executable, "-c", SETTINGS_PROBE],
        cwd=PROJECT_ROOT,
        env=_isolated_process_environment(settings_module, overrides),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def _settings_result(process):
    for line in process.stdout.splitlines():
        if line.startswith(SETTINGS_RESULT_PREFIX):
            return json.loads(line.removeprefix(SETTINGS_RESULT_PREFIX))
    raise AssertionError(
        "Settings subprocess did not emit a result.\n"
        f"stdout:\n{process.stdout}\n"
        f"stderr:\n{process.stderr}"
    )


class ApplicationEnvironmentSelectionTests(SimpleTestCase):
    def test_absent_app_env_preserves_local_development_default(self):
        self.assertEqual(resolve_app_environment({}), "development")

    def test_app_env_normalizes_surrounding_space_and_case(self):
        self.assertEqual(resolve_app_environment({"APP_ENV": " StAgInG "}), "staging")

    def test_empty_app_env_fails_closed(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "APP_ENV is empty"):
            resolve_app_environment({"APP_ENV": "  "})

    def test_invalid_app_env_fails_closed(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "Invalid APP_ENV value"):
            resolve_app_environment({"APP_ENV": "preview"})

    def test_debug_is_independent_in_development_and_test(self):
        validate_debug_policy("development", True)
        validate_debug_policy("development", False)
        validate_debug_policy("test", True)
        validate_debug_policy("test", False)

    def test_staging_and_production_require_debug_false(self):
        for app_env in ("staging", "production"):
            with self.subTest(app_env=app_env):
                validate_debug_policy(app_env, False)
                with self.assertRaisesMessage(
                    ImproperlyConfigured,
                    f"DEBUG must be False when APP_ENV is {app_env}",
                ):
                    validate_debug_policy(app_env, True)


class DatabaseEnvironmentSelectionTests(SimpleTestCase):
    def test_supabase_pooler_port_is_normalized(self):
        url = "postgresql://test@aws.pooler.supabase.com:5432/postgres"
        self.assertEqual(
            normalize_supabase_pooler_port(url),
            "postgresql://test@aws.pooler.supabase.com:6543/postgres",
        )

    def test_development_selects_only_development_database(self):
        variable, url = select_database_url(
            "development",
            {"SUPABASE_DEVELOPMENT_DB_URL": DEV_URL},
        )
        self.assertEqual(variable, "SUPABASE_DEVELOPMENT_DB_URL")
        self.assertEqual(url, DEV_URL)

    def test_staging_selects_staging_database_with_debug_false(self):
        validate_debug_policy("staging", False)
        variable, url = select_database_url(
            "staging",
            {
                "SUPABASE_STAGING_DB_URL": STAGING_URL,
                "SUPABASE_PRODUCTION_DB_URL": PRODUCTION_URL,
            },
        )
        self.assertEqual(variable, "SUPABASE_STAGING_DB_URL")
        self.assertEqual(url, STAGING_URL)

    def test_production_selects_production_database_with_debug_false(self):
        validate_debug_policy("production", False)
        variable, url = select_database_url(
            "production",
            {
                "SUPABASE_STAGING_DB_URL": STAGING_URL,
                "SUPABASE_PRODUCTION_DB_URL": PRODUCTION_URL,
            },
        )
        self.assertEqual(variable, "SUPABASE_PRODUCTION_DB_URL")
        self.assertEqual(url, PRODUCTION_URL)

    def test_test_environment_has_isolated_sqlite_fallback(self):
        self.assertEqual(select_database_url("test", {}), (None, None))

    def test_test_environment_can_select_dedicated_postgres_database(self):
        variable, url = select_database_url(
            "test",
            {"SUPABASE_TEST_DB_URL": TEST_URL},
        )
        self.assertEqual(variable, "SUPABASE_TEST_DB_URL")
        self.assertEqual(url, TEST_URL)

    def test_missing_development_database_fails_closed(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "Set SUPABASE_DEVELOPMENT_DB_URL",
        ):
            select_database_url("development", {})

    def test_missing_staging_database_does_not_fall_back_to_production(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "Set SUPABASE_STAGING_DB_URL",
        ):
            select_database_url(
                "staging",
                {"SUPABASE_PRODUCTION_DB_URL": PRODUCTION_URL},
            )

    def test_missing_production_database_does_not_fall_back(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "Set SUPABASE_PRODUCTION_DB_URL",
        ):
            select_database_url(
                "production",
                {
                    "SUPABASE_DEVELOPMENT_DB_URL": DEV_URL,
                    "SUPABASE_STAGING_DB_URL": STAGING_URL,
                },
            )

    def test_identical_staging_and_production_urls_are_rejected(self):
        duplicate_url = (
            "postgresql://synthetic:secret@shared.example.test/shared_db"
        )
        environment = {
            "SUPABASE_STAGING_DB_URL": duplicate_url,
            "SUPABASE_PRODUCTION_DB_URL": duplicate_url,
        }

        for app_env in ("staging", "production"):
            with self.subTest(app_env=app_env):
                with self.assertRaisesMessage(
                    ImproperlyConfigured,
                    "Database environment crossover detected",
                ):
                    select_database_url(app_env, environment)

    def test_pooler_port_alias_cannot_bypass_crossover_check(self):
        environment = {
            "SUPABASE_STAGING_DB_URL": (
                "postgresql://same:secret@aws.pooler.supabase.com:5432/postgres"
            ),
            "SUPABASE_PRODUCTION_DB_URL": (
                "postgresql://same:secret@aws.pooler.supabase.com:6543/postgres"
            ),
        }

        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "Database environment crossover detected",
        ):
            select_database_url("staging", environment)

    def test_test_database_cannot_equal_a_non_test_database(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "Database environment crossover detected",
        ):
            select_database_url(
                "test",
                {
                    "SUPABASE_TEST_DB_URL": TEST_URL,
                    "SUPABASE_PRODUCTION_DB_URL": TEST_URL,
                },
            )

    def test_crossover_error_does_not_expose_database_url(self):
        secret_url = "postgresql://secret_user:secret_password@db.example.test/db"
        with self.assertRaises(ImproperlyConfigured) as raised:
            select_database_url(
                "staging",
                {
                    "SUPABASE_STAGING_DB_URL": secret_url,
                    "SUPABASE_PRODUCTION_DB_URL": secret_url,
                },
            )

        self.assertNotIn(secret_url, str(raised.exception))
        self.assertNotIn("secret_password", str(raised.exception))

    def test_debug_value_does_not_change_database_selection(self):
        environment = {
            "SUPABASE_DEVELOPMENT_DB_URL": DEV_URL,
            "SUPABASE_PRODUCTION_DB_URL": PRODUCTION_URL,
        }
        selections = []

        for debug in (True, False):
            validate_debug_policy("development", debug)
            selections.append(select_database_url("development", environment))

        self.assertEqual(selections[0], selections[1])
        self.assertEqual(selections[0][0], "SUPABASE_DEVELOPMENT_DB_URL")


class DjangoSettingsInitializationTests(SimpleTestCase):
    settings_module = "truthlens_backend.settings"

    def assert_initialization_succeeds(self, environment):
        process = _run_settings_initialization(
            self.settings_module,
            environment,
        )
        self.assertEqual(
            process.returncode,
            0,
            msg=(
                "Django settings initialization failed.\n"
                f"stdout:\n{process.stdout}\n"
                f"stderr:\n{process.stderr}"
            ),
        )
        return _settings_result(process)

    def assert_initialization_fails(self, environment, expected_message):
        process = _run_settings_initialization(
            self.settings_module,
            environment,
        )
        self.assertNotEqual(
            process.returncode,
            0,
            msg=f"Settings initialization unexpectedly succeeded: {process.stdout}",
        )
        self.assertIn(expected_message, process.stderr)
        self.assertNotIn("password@", process.stderr)

    def test_staging_settings_initialize_with_staging_database(self):
        result = self.assert_initialization_succeeds(
            {
                "APP_ENV": "staging",
                "DEBUG": "False",
                "SUPABASE_STAGING_DB_URL": STAGING_URL,
            }
        )

        self.assertEqual(result["app_env"], "staging")
        self.assertIs(result["debug"], False)
        self.assertEqual(result["engine"], "django.db.backends.postgresql")
        self.assertEqual(result["name"], "staging_db")
        self.assertEqual(result["host"], "staging.example.test")
        self.assertEqual(result["user"], "staging_user")

    def test_production_settings_initialize_with_production_database(self):
        result = self.assert_initialization_succeeds(
            {
                "APP_ENV": "production",
                "DEBUG": "False",
                "SUPABASE_PRODUCTION_DB_URL": PRODUCTION_URL,
            }
        )

        self.assertEqual(result["app_env"], "production")
        self.assertIs(result["debug"], False)
        self.assertEqual(result["engine"], "django.db.backends.postgresql")
        self.assertEqual(result["name"], "prod_db")
        self.assertEqual(result["host"], "production.example.test")
        self.assertEqual(result["user"], "production_user")

    def test_staging_initialization_does_not_fall_back_to_production(self):
        self.assert_initialization_fails(
            {
                "APP_ENV": "staging",
                "DEBUG": "False",
                "SUPABASE_PRODUCTION_DB_URL": PRODUCTION_URL,
            },
            "Set SUPABASE_STAGING_DB_URL",
        )

    def test_settings_test_initializes_offline_without_supabase_credentials(self):
        process = _run_settings_initialization(
            "truthlens_backend.settings_test",
        )
        self.assertEqual(
            process.returncode,
            0,
            msg=(
                "Offline test settings initialization failed.\n"
                f"stdout:\n{process.stdout}\n"
                f"stderr:\n{process.stderr}"
            ),
        )

        result = _settings_result(process)
        self.assertEqual(result["app_env"], "test")
        self.assertIs(result["debug"], False)
        self.assertEqual(result["engine"], "django.db.backends.sqlite3")
        self.assertTrue(result["name"].endswith("test_db.sqlite3"))
        self.assertEqual(result["host"], "")
        self.assertEqual(result["user"], "")

    def test_staging_and_production_initialization_reject_debug_true(self):
        for app_env, database_variable, database_url in (
            ("staging", "SUPABASE_STAGING_DB_URL", STAGING_URL),
            ("production", "SUPABASE_PRODUCTION_DB_URL", PRODUCTION_URL),
        ):
            with self.subTest(app_env=app_env):
                self.assert_initialization_fails(
                    {
                        "APP_ENV": app_env,
                        "DEBUG": "True",
                        database_variable: database_url,
                    },
                    f"DEBUG must be False when APP_ENV is {app_env}",
                )
