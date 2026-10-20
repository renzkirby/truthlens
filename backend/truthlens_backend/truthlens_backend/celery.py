import logging
import os

from celery import Celery
from celery.signals import worker_ready

logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "truthlens_backend.settings")

app = Celery("truthlens_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_ready.connect
def report_cloudflare_pilot_worker_readiness(sender=None, **kwargs):
    """Log config *presence* at worker start; no API call or secret values.

    Worker runtime configuration can differ from the shell that launched
    manage.py. Never log these statuses outside local development.
    """
    from django.conf import settings

    if not (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
    ):
        return

    from api.verification.cloudflare_evaluation import ACCOUNT_ID_PATTERN
    from api.verification.cloudflare_pilot import cloudflare_pilot_enabled

    logger.info(
        "CLOUDFLARE_PILOT_WORKER_READY pid=%s enabled=%s "
        "account_id_valid=%s api_token_present=%s",
        os.getpid(),
        cloudflare_pilot_enabled("persisted_evidence_evaluation"),
        bool(ACCOUNT_ID_PATTERN.fullmatch(
            os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        )),
        bool(os.getenv("CLOUDFLARE_API_TOKEN", "").strip()),
    )
