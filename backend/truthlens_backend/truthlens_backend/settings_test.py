import os

# Set the environment identity and inert provider credentials before importing
# base settings so offline tests never depend on an ignored local .env file or
# accidentally use real development/staging/production provider credentials.
os.environ["APP_ENV"] = "test"
os.environ["GROQ_API_KEY"] = "truthlens-offline-test-groq-key"
os.environ["GEMINI_API_KEY"] = "truthlens-offline-test-gemini-key"
os.environ["INVESTIGATION_CLASSIFICATION_MODE"] = "off"
os.environ["INVESTIGATION_ROUTING_MODE"] = "off"

from .settings import *

# Test settings must not depend on an ignored local .env file. This value is
# intentionally test-only and must never be used by development/staging/production.
SECRET_KEY = os.environ.get("SECRET_KEY") or "truthlens-offline-test-secret-key"

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
