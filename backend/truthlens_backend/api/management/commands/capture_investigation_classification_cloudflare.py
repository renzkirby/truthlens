"""Inspect or (with explicit independent permission) capture four Cloudflare cases.

Default invocation is a strictly no-network dry run. There is no fallback,
no ORM/Celery and no automatic partner-classification authority.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import ClassificationAuditError
from api.verification.cloudflare_classification_capture import (
    CONFIRMATION, execute_direct_cloudflare_capture,
)


class Command(BaseCommand):
    help = (
        "Direct Cloudflare classification capture; defaults to NO-NETWORK "
        "dry run. Separate live approval and multiple dev-only gates required."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--corpus", required=True,
            help="Locally approved 32-case review JSON, not the pending fixture.",
        )
        parser.add_argument(
            "--packet-dir", required=True,
            help="Existing private Cloudflare-02 folder outside Git checkout.",
        )
        parser.add_argument(
            "--execute-live", action="store_true",
            help="DANGEROUS: allows up to four real Cloudflare API calls only "
                 "with development settings, environment opt-in and exact confirmation. "
                 "Do not use without separate user authorization.",
        )
        parser.add_argument(
            "--confirm-live", default="",
            help="Additional deliberate consent string required ONLY for live use. "
                 "Dry run does not use it.",
        )
        parser.add_argument("--json-summary", action="store_true")

    def handle(self, *args, **opts):
        if not opts["execute_live"] and opts["confirm_live"]:
            raise CommandError("Live confirmation is invalid without --execute-live.")
        try:
            summary = execute_direct_cloudflare_capture(
                opts["corpus"], opts["packet_dir"],
                execute_live=opts["execute_live"],
                confirmation=opts["confirm_live"],
            )
        except ClassificationAuditError as exc:
            raise CommandError(str(exc)) from None
        except OSError:
            raise CommandError(
                "Private capture filesystem unavailable; do not replay this packet."
            ) from None
        if opts["json_summary"]:
            self.stdout.write(json.dumps(summary, sort_keys=True))
            return
        else:
            if summary["status"] == "DRY_RUN_READY_NO_PROVIDER_CALLS":
                self.stdout.write(
                    "CLOUDFLARE_CAPTURE DRY_RUN_READY model={model_id} "
                    "requests={planned_requests} no_provider_calls=true"
                    .format(**summary)
                )
                self.stdout.write("CASE_IDS " + ",".join(summary["case_ids"]))
                self.stdout.write(
                    "SYSTEM_PROMPT_SHA256 " + summary["system_prompt_sha256"]
                )
            else:
                self.stdout.write(
                    "CLOUDFLARE_CAPTURE completed_attempts={attempted_requests} "
                    "valid={valid_responses} recorded={captured_predictions} "
                    "stopped_early={stopped_early}".format(**summary)
                )
                self.stdout.write(
                    "Results written to private cloudflare_* files; "
                    "never paste raw responses or credentials into public issues."
                )
        self.stdout.write(
            "NO DATABASE WRITES; NO FALLBACK; NO AUTO-CLASSIFICATION; "
            "NO PARTNER ENFORCEMENT APPROVAL."
        )
