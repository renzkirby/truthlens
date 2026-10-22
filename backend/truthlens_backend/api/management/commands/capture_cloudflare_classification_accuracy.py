"""Strict no-network default; live path needs NEW separate approval."""
import json

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import ClassificationAuditError
from api.verification.cloudflare_classification_accuracy_capture import (
    execute_accuracy_capture,
)


class Command(BaseCommand):
    help = (
        "Dry-run a private 32-case accuracy packet without network access. "
        "Live execution requires separate explicit authorization and dev gates."
    )

    def add_arguments(self, parser):
        parser.add_argument("--corpus", required=True)
        parser.add_argument("--packet-dir", required=True)
        parser.add_argument(
            "--execute-live", action="store_true",
            help="Requires NEW user approval; may incur provider charges.",
        )
        parser.add_argument(
            "--confirm-live", default="",
            help="Separate exact confirmation string; not valid in dry run.",
        )
        parser.add_argument("--json-summary", action="store_true")

    def handle(self, *args, **opts):
        if opts["confirm_live"] and not opts["execute_live"]:
            raise CommandError(
                "Live confirmation is invalid in a no-network dry run."
            )
        try:
            result = execute_accuracy_capture(
                opts["corpus"], opts["packet_dir"],
                execute_live=opts["execute_live"],
                confirmation=opts["confirm_live"],
            )
        except ClassificationAuditError as exc:
            raise CommandError(str(exc)) from None
        except OSError:
            raise CommandError(
                "Private accuracy capture filesystem unavailable; "
                "never delete the permanent lock or replay this packet."
            ) from None
        if opts["json_summary"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
            return
        if result["status"] == "DRY_RUN_READY_NO_PROVIDER_CALLS":
            self.stdout.write(
                "CLOUDFLARE_ACCURACY_DRY_RUN_READY cases=32 "
                "max_tokens=4096 calls=0."
            )
        else:
            self.stdout.write(
                "CLOUDFLARE_ACCURACY attempted={attempted_requests} "
                "valid={valid_responses} captured={captured_predictions} "
                "stopped_early={stopped_early}".format(**result)
            )
        self.stdout.write(
            "NO DATABASE WRITES; NO FALLBACK OR RETRIES; "
            "NO AUTOMATIC PARTNER ENFORCEMENT APPROVAL."
        )
