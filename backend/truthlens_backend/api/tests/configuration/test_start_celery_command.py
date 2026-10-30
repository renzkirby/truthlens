from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class StartCeleryCommandTests(SimpleTestCase):
    @override_settings(
        CELERY_WORKER_POOL="solo",
        CELERY_WORKER_CONCURRENCY=1,
        CELERY_WORKER_PREFETCH_MULTIPLIER=1,
    )
    @patch("api.management.commands.start_celery.subprocess.Popen")
    def test_default_worker_command_preserves_single_slot_behavior(self, popen):
        popen.return_value = SimpleNamespace(pid=1234)
        output = StringIO()

        call_command("start_celery", stdout=output)

        command = popen.call_args.args[0]
        self.assertIn("--pool=solo", command)
        self.assertIn("--concurrency=1", command)
        self.assertIn("pool=solo", output.getvalue())
        self.assertIn("concurrency=1", output.getvalue())
        self.assertIn("prefetch=1", output.getvalue())

    @override_settings(
        CELERY_WORKER_POOL="prefork",
        CELERY_WORKER_CONCURRENCY=2,
        CELERY_WORKER_PREFETCH_MULTIPLIER=1,
    )
    @patch("api.management.commands.start_celery.subprocess.Popen")
    def test_production_worker_can_opt_into_two_prefork_slots(self, popen):
        popen.return_value = SimpleNamespace(pid=5678)
        output = StringIO()

        call_command("start_celery", stdout=output)

        command = popen.call_args.args[0]
        self.assertIn("--pool=prefork", command)
        self.assertIn("--concurrency=2", command)
        self.assertIn("pool=prefork", output.getvalue())
        self.assertIn("concurrency=2", output.getvalue())
        self.assertIn("prefetch=1", output.getvalue())
