"""Prepare a bounded private evaluation capture packet. NEVER call providers.

Use the existing audit_investigation_classification command to score real
captured response JSON later. This command never generates model predictions.
"""
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
)
from api.verification.classification_capture_plan import (
    PROVIDERS, build_capture_plan, summarize_capture_plan,
    write_private_capture_package,
)


class Command(BaseCommand):
    help = (
        "Offline only: validate an APPROVED private corpus and plan up to "
        "32 direct provider classification requests, without making them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--corpus", required=True,
            help="Absolute/local path to a separately approved review corpus.",
        )
        parser.add_argument(
            "--provider", required=True, choices=sorted(PROVIDERS),
            help="ONE named provider for an isolated future capture; no fallback.",
        )
        parser.add_argument(
            "--model-id", default="NOT_SELECTED",
            help="Model identifier for experiment provenance, not an API selector.",
        )
        parser.add_argument(
            "--limit", type=int, default=4,
            help="Up to 32 approved cases; default is 4 safety-focused canaries.",
        )
        parser.add_argument(
            "--case-ids", nargs="+",
            help="Optional exact approved case IDs, no repetitions.",
        )
        parser.add_argument(
            "--export-dir",
            help="Optional NEW private directory OUTSIDE the Git checkout. "
                 "Writes claim-input manifest and EMPTY capture template only.",
        )
        parser.add_argument("--json-summary", action="store_true")
        parser.add_argument(
            "--input-price-per-million", type=Decimal,
            help="Optional operator-supplied USD per million input tokens.",
        )
        parser.add_argument(
            "--output-price-per-million", type=Decimal,
            help="Optional operator-supplied USD per million output tokens.",
        )
        parser.add_argument(
            "--assumed-input-tokens", type=int,
            help="Optional token assumption per request, not measured.",
        )
        parser.add_argument(
            "--assumed-output-tokens", type=int,
            help="Optional token assumption per request (1–1024), not measured.",
        )

    def handle(self, *args, **opts):
        try:
            cases = load_classification_corpus(opts["corpus"])
            plan = build_capture_plan(
                cases,
                provider=opts["provider"],
                model_id=opts["model_id"],
                limit=opts["limit"],
                case_ids=opts["case_ids"],
                input_price_per_million=opts["input_price_per_million"],
                output_price_per_million=opts["output_price_per_million"],
                assumed_input_tokens=opts["assumed_input_tokens"],
                assumed_output_tokens=opts["assumed_output_tokens"],
            )
            path = None
            if opts["export_dir"]:
                path = write_private_capture_package(plan, opts["export_dir"])
        except ClassificationAuditError as exc:
            # No claim text, raw provider outputs, or stack traces in errors.
            raise CommandError(str(exc)) from None

        summary = summarize_capture_plan(plan)
        if path is not None:
            summary["private_capture_package_created"] = True
        if opts["json_summary"]:
            self.stdout.write(json.dumps(summary, sort_keys=True))
            return

        self.stdout.write(
            "OFFLINE_CAPTURE_PLAN provider={provider} model_id={model_id} "
            "approved={approved_references_in_source} requests={planned_requests} "
            "limit={limit}".format(**summary)
        )
        self.stdout.write("CASE_IDS " + ",".join(summary["case_ids"]))
        self.stdout.write("CORPUS_SHA256 " + summary["corpus_sha256"])
        if summary["cost"]["status"] == "ILLUSTRATIVE_ONLY":
            self.stdout.write(
                "ILLUSTRATIVE_USD {estimated_usd} (NOT a spending cap)"
                .format(**summary["cost"])
            )
        else:
            self.stdout.write("COST UNKNOWN: no verified current provider rates.")
        if path is not None:
            self.stdout.write(
                "PRIVATE_CAPTURE_PACKAGE CREATED (no responses or requests executed)"
            )
        self.stdout.write(
            "NO PROVIDER CALLS; NO DATABASE WRITES; NO PREDICTIONS CAPTURED; "
            "NO AUTOMATIC ENFORCEMENT APPROVAL."
        )
