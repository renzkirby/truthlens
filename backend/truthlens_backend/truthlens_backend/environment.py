"""Environment and database-selection safeguards for Django settings.

This module is deliberately independent of Django's settings initialization so
its selection rules can be unit tested without opening a database connection.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured

SUPPORTED_APP_ENVIRONMENTS = (
    "development",
    "test",
    "staging",
    "production",
)

DATABASE_URL_ENV_BY_APP_ENV = {
    "development": "SUPABASE_DEVELOPMENT_DB_URL",
    "test": "SUPABASE_TEST_DB_URL",
    "staging": "SUPABASE_STAGING_DB_URL",
    "production": "SUPABASE_PRODUCTION_DB_URL",
}


def normalize_supabase_pooler_port(database_url: str) -> str:
    """Preserve the Supabase connection mode selected by the configured URL."""

    return database_url


def _database_url_isolation_identity(database_url: str) -> str:
    """Canonicalize Supabase pooler aliases only for environment isolation checks."""

    return database_url.replace(
        ".pooler.supabase.com:5432",
        ".pooler.supabase.com:6543",
    )


def resolve_app_environment(environ: Mapping[str, str] | None = None) -> str:
    """Return the normalized application environment.

    An absent APP_ENV preserves the established local-development workflow by
    selecting ``development``. An explicitly empty value is treated as a
    configuration error. Non-empty values are stripped and lower-cased before
    validation, and no unsupported value is guessed or coerced.
    """

    environment = os.environ if environ is None else environ
    raw_value = environment.get("APP_ENV")

    if raw_value is None:
        return "development"

    normalized = raw_value.strip().lower()
    if not normalized:
        raise ImproperlyConfigured(
            "APP_ENV is empty. Set it to development, test, staging, or production."
        )

    if normalized not in SUPPORTED_APP_ENVIRONMENTS:
        supported = ", ".join(SUPPORTED_APP_ENVIRONMENTS)
        raise ImproperlyConfigured(
            f"Invalid APP_ENV value. Supported values are: {supported}."
        )

    return normalized


def validate_debug_policy(app_env: str, debug: bool) -> None:
    """Reject DEBUG=True in staging and production."""

    if app_env in {"staging", "production"} and debug:
        raise ImproperlyConfigured(f"DEBUG must be False when APP_ENV is {app_env}.")


def _configured_database_urls(
    environ: Mapping[str, str],
) -> dict[str, tuple[str, str]]:
    configured = {}
    for app_env, variable_name in DATABASE_URL_ENV_BY_APP_ENV.items():
        value = environ.get(variable_name)
        if value and value.strip():
            configured[app_env] = (
                variable_name,
                normalize_supabase_pooler_port(value.strip()),
            )
    return configured


def _validate_database_url_isolation(
    selected_app_env: str,
    configured: Mapping[str, tuple[str, str]],
) -> None:
    """Reject obvious cross-environment reuse without exposing URL values.

    Exact URL equality is only a bounded safeguard. Deployment validation must
    separately prove distinct project/database identity and credentials.
    """

    selected = configured.get(selected_app_env)
    if selected is None:
        return

    selected_variable, selected_url = selected
    selected_identity = _database_url_isolation_identity(selected_url)

    for other_app_env, (other_variable, other_url) in configured.items():
        if other_app_env == selected_app_env:
            continue

        other_identity = _database_url_isolation_identity(other_url)

        if selected_identity == other_identity:
            raise ImproperlyConfigured(
                "Database environment crossover detected: "
                f"{selected_variable} and {other_variable} must not be identical."
            )


def select_database_url(
    app_env: str,
    environ: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Select only the database variable assigned to ``app_env``.

    The test environment may omit SUPABASE_TEST_DB_URL, in which case callers
    must configure an isolated SQLite database. Every other environment
    requires its dedicated URL and has no fallback.
    """

    if app_env not in SUPPORTED_APP_ENVIRONMENTS:
        raise ImproperlyConfigured(
            "Database selection requires a validated APP_ENV value."
        )

    environment = os.environ if environ is None else environ
    variable_name = DATABASE_URL_ENV_BY_APP_ENV[app_env]
    configured = _configured_database_urls(environment)
    selected = configured.get(app_env)

    if selected is None:
        if app_env == "test":
            return None, None
        raise ImproperlyConfigured(
            f"No database URL configured for APP_ENV={app_env}. Set {variable_name}."
        )

    _validate_database_url_isolation(app_env, configured)
    return selected
