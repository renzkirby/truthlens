import subprocess
import sys
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Starts the Celery worker alongside Django"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Starting Celery worker..."))

        celery_cmd = [
            sys.executable, "-m", "celery",
            "-A", "truthlens_backend",
            "worker",
            "--loglevel=info",
            "--pool=solo",
        ]

        try:
            process = subprocess.Popen(
                celery_cmd,
                cwd=str(settings.BASE_DIR),
            )
            self.stdout.write(
                self.style.SUCCESS(f"Celery worker started with PID {process.pid}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to start Celery worker: {str(e)}")
            )