"""Cloudflare-03 single-case diagnostic: default NO-NETWORK dry run."""
import json

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import ClassificationAuditError
from api.verification.cloudflare_classification_diagnostic import (
    execute_diagnostic,
)


class Command(BaseCommand):
    help = (
        "4096-token single-case Cloudflare diagnostic; NO-NETWORK dry run "
        "unless NEW separately approved live authorization is supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument("--corpus", required=True)
        parser.add_argument("--packet-dir", required=True)
        parser.add_argument(
            "--execute-live", action="store_true",
            help="DO NOT USE WITHOUT NEW USER AUTHORIZATION. May incur charges.",
        )
        parser.add_argument(
            "--confirm-live", default="",
            help="Distinct exact live permission phrase; dry runs never require it.",
        )
        parser.add_argument("--json-summary", action="store_true")

    def handle(self, *args, **opts):
        if opts["confirm_live"] and not opts["execute_live"]:
            raise CommandError("Unexpected live confirmation in dry-run mode.")
        try:
            summary = execute_diagnostic(
                opts["corpus"], opts["packet_dir"],
                execute_live=opts["execute_live"],
                confirmation=opts["confirm_live"],
            )
        except ClassificationAuditError as exc:
            raise CommandError(str(exc)) from None
        except OSError:
            raise CommandError(
                "Private diagnostic filesystem failed; do not attempt replay."
            ) from None
        if opts["json_summary"]:
            self.stdout.write(json.dumps(summary, sort_keys=True))
            return
        if summary["status"] == "DRY_RUN_READY_NO_PROVIDER_CALLS":
            self.stdout.write(
                "CLOUDFLARE_4096_DIAGNOSTIC DRY_RUN_READY "
                "case=cross_spacecraft calls=0 max_completion_tokens=4096"
            )
            self.stdout.write(
                "SYSTEM_PROMPT_SHA256 " + summary["system_prompt_sha256"]
            )
        else:
            self.stdout.write(
                "CLOUDFLARE_4096_DIAGNOSTIC attempts={attempted_requests} "
                "valid={valid_responses} captured={captured_predictions}"
                .format(**summary)
            )
        self.stdout.write(
            "NO DATABASE WRITES; NO GEMINI/GROQ FALLBACK; "
            "NO AUTOMATIC PARTNER ENFORCEMENT APPROVAL."
        )
