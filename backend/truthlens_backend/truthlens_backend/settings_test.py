from .settings import *

# Use a local SQLite DB for isolated/offline test runs.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

# API migrations include PostgreSQL/pgvector-specific operations that are not valid on SQLite.
# For test runs, let Django build API tables directly from models.
MIGRATION_MODULES = {
    "api": None,
}

# Speed up test suite.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Keep email side effects in memory during tests.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Run Celery tasks synchronously in tests when invoked.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
