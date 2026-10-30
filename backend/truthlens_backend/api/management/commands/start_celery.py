import subprocess
import sys
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Starts the Celery worker alongside Django"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Starting Celery worker..."))

        pool = settings.CELERY_WORKER_POOL
        concurrency = settings.CELERY_WORKER_CONCURRENCY

        celery_cmd = [
            sys.executable, "-m", "celery",
            "-A", "truthlens_backend",
            "worker",
            "--loglevel=info",
            f"--pool={pool}",
            f"--concurrency={concurrency}",
        ]

        try:
            process = subprocess.Popen(
                celery_cmd,
                cwd=str(settings.BASE_DIR),
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Celery worker started with PID "
                    f"{process.pid} (pool={pool}, concurrency={concurrency}, "
                    f"prefetch={settings.CELERY_WORKER_PREFETCH_MULTIPLIER}, "
                    f"disable_prefetch={settings.CELERY_WORKER_DISABLE_PREFETCH})"
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to start Celery worker: {str(e)}")
            )