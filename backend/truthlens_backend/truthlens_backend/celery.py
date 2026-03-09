import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "truthlens_backend.settings")

app = Celery("truthlens_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
