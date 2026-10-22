"""Offline-only deterministic paired Cloudflare token-budget study design."""
import json

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
)
from api.verification.cloudflare_budget_benchmark import (
    build_budget_benchmark, export_private_benchmark,
    safe_benchmark_summary,
)


class Command(BaseCommand):
    help = (
        "Prepare NO-NETWORK paired 1024/4096-token study design: "
        "four cases, two repetitions, sixteen hypothetical trials."
    )

    def add_arguments(self, parser):
        parser.add_argument("--corpus", required=True)
        parser.add_argument(
            "--export-dir",
            help="Optional NEW private outside-Git folder; no model calls.",
        )
        parser.add_argument("--json-summary", action="store_true")

    def handle(self, *args, **opts):
        try:
            cases = load_classification_corpus(opts["corpus"])
            plan = build_budget_benchmark(cases)
            result = safe_benchmark_summary(plan)
            if opts["export_dir"]:
                export_private_benchmark(plan, opts["export_dir"])
                result["private_package_created"] = True
        except ClassificationAuditError as exc:
            raise CommandError(str(exc)) from None
        if opts["json_summary"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
            return
        self.stdout.write(
            "CLOUDFLARE_BUDGET_STUDY OFFLINE_ONLY cases=4 arms=2 "
            "repeats=2 prospective_trials=16 real_calls=0"
        )
        self.stdout.write("CASE_IDS " + ",".join(result["case_ids"]))
        self.stdout.write(
            "MANIFEST_SHA256 " + result["manifest_sha256"]
        )
        if result.get("private_package_created"):
            self.stdout.write(
                "PRIVATE PACKAGE CREATED, EMPTY OBSERVATIONS; NO LIVE RUNNER"
            )
        self.stdout.write(
            "NO PROVIDER CALLS, NO DATABASE WRITES, "
            "NO MODEL ACCURACY OR PARTNER ENFORCEMENT APPROVAL."
        )
