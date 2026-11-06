import os

# Set the environment identity and inert provider credentials before importing
# base settings so offline tests never depend on an ignored local .env file or
# accidentally use real development/staging/production provider credentials.
os.environ["APP_ENV"] = "test"
os.environ["GROQ_API_KEY"] = "truthlens-offline-test-groq-key"
os.environ["GEMINI_API_KEY"] = "truthlens-offline-test-gemini-key"
os.environ["INVESTIGATION_CLASSIFICATION_MODE"] = "off"
os.environ["INVESTIGATION_ROUTING_MODE"] = "off"
# Offline tests must never inherit or reload a developer/CI Redis endpoint.
os.environ["CACHE_REDIS_URL"] = ""

from .settings import *

# The full test suite reuses low user primary keys across isolated TestCase
# transactions. Keep the global anonymous/user throttles enabled but give them
# effectively non-limiting test rates so throttle history from one unrelated
# test cannot cause 429 responses in another. Endpoint-specific scopes retain
# their production-like rates and are exercised by their dedicated tests.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        "anon": "1000000/minute",
        "user": "1000000/minute",
    },
}

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
