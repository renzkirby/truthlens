"""OFFLINE ONLY: prepare fresh private 32-case Cloudflare accuracy packet."""
import json

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import ClassificationAuditError
from api.verification.cloudflare_classification_accuracy_capture import (
    prepare_private_accuracy_packet,
)


class Command(BaseCommand):
    help = (
        "Prepare private 32-case classification accuracy capture inputs. "
        "No network calls, no database writes, no live authorization."
    )

    def add_arguments(self, parser):
        parser.add_argument("--corpus", required=True)
        parser.add_argument(
            "--export-dir", required=True,
            help="A NEW private path outside the Git checkout; must not exist.",
        )
        parser.add_argument("--json-summary", action="store_true")

    def handle(self, *args, **opts):
        try:
            result = prepare_private_accuracy_packet(
                opts["corpus"], opts["export_dir"],
            )
        except ClassificationAuditError as exc:
            raise CommandError(str(exc)) from None
        if opts["json_summary"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
            return
        self.stdout.write(
            "CLOUDFLARE_ACCURACY_PREPARED 32 approved cases; "
            "zero provider calls, zero DB writes."
        )
        self.stdout.write(
            "PRIVATE PACKET CREATED; NO LIVE AUTHORIZATION OR "
            "PARTNER ENFORCEMENT APPROVAL."
        )
