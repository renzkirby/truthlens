"""Pure offline aggregation of genuine paired-budget provider observations."""
import json

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
)
from api.verification.cloudflare_budget_benchmark import (
    score_budget_benchmark, validate_benchmark_files,
)


class Command(BaseCommand):
    help = (
        "NO-NETWORK: compare recorded Cloudflare 1024/4096-token trial "
        "outcomes; incomplete trials stay missing. No accuracy authorization."
    )

    def add_arguments(self, parser):
        parser.add_argument("--corpus", required=True)
        parser.add_argument("--campaign-dir", required=True)
        parser.add_argument("--json-summary", action="store_true")

    def handle(self, *args, **opts):
        try:
            cases = load_classification_corpus(opts["corpus"])
            manifest, observations = validate_benchmark_files(
                cases, opts["campaign_dir"],
            )
            result = score_budget_benchmark(cases, manifest, observations)
        except ClassificationAuditError as exc:
            raise CommandError(str(exc)) from None
        if opts["json_summary"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
            return
        self.stdout.write(
            "OFFLINE_BUDGET_AUDIT observed={observed_trials} "
            "missing={unobserved_trials} complete={all_trials_observed}"
            .format(**result)
        )
        for arm, stats in result["per_budget"].items():
            self.stdout.write(
                f"ARM tokens={arm} observed={stats['observed']} "
                f"provider_failed={stats['provider_failed']} "
                f"invalid={stats['invalid_contract']} "
                f"exact_matches={stats['exact_matches']} "
                f"mean_accuracy=NOT_ESTABLISHED"
            )
        self.stdout.write(
            "NO PROVIDER CALLS; NO DATABASE WRITES; "
            "NO PRODUCTION ENFORCEMENT APPROVAL."
        )
