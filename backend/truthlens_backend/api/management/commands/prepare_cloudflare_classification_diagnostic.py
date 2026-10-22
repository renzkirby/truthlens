"""Export a new private Cloudflare-03 single-case 4096-token packet, OFFLINE."""
import json

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import ClassificationAuditError
from api.verification.cloudflare_classification_diagnostic import (
    prepare_private_diagnostic,
)


class Command(BaseCommand):
    help = "No-network: create a NEW private one-case Cloudflare 4096-token packet."

    def add_arguments(self, parser):
        parser.add_argument("--corpus", required=True)
        parser.add_argument(
            "--export-dir", required=True,
            help="New private folder outside the Git checkout. Must not exist.",
        )
        parser.add_argument("--json-summary", action="store_true")

    def handle(self, *args, **opts):
        try:
            summary = prepare_private_diagnostic(
                opts["corpus"], opts["export_dir"],
            )
        except ClassificationAuditError as exc:
            raise CommandError(str(exc)) from None
        if opts["json_summary"]:
            self.stdout.write(json.dumps(summary, sort_keys=True))
            return
        self.stdout.write(
            "CLOUDFLARE_DIAGNOSTIC_PREPARED model={model_id} case={case} "
            "max_tokens={max_completion_tokens} requests={planned_requests}"
            .format(case=summary["case_ids"][0], **summary)
        )
        self.stdout.write(
            "PRIVATE PACKET CREATED; NO PROVIDER CALLS; "
            "NO DATABASE WRITES; NO ENFORCEMENT AUTHORIZATION."
        )
