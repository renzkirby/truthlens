"""Offline only: compare captured model classifications with reviewed labels.

No AI requests, Celery scheduling, Django ORM access, or files written.
This command NEVER approves automatic partner investigation eligibility.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.verification.classification_quality_audit import (
    ClassificationAuditError,
    load_classification_corpus,
    load_classification_predictions,
    score_classification_predictions,
    summarize_classification_corpus,
)


DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[2]
    / "verification" / "fixtures" / "investigation_subject_review_v1.json"
)


class Command(BaseCommand):
    help = (
        "Inspect a synthetic subject-domain corpus or score captured responses "
        "against reviewer-approved labels, strictly offline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--corpus", default=str(DEFAULT_CORPUS),
            help="Local JSON corpus path; defaults to pending-review synthetic cases.",
        )
        parser.add_argument(
            "--predictions",
            help="Optional local JSON of previously captured raw classification responses.",
        )
        parser.add_argument(
            "--json-summary", action="store_true",
            help="Print sanitized aggregate JSON; never include claim text or responses.",
        )

    def handle(self, *args, **opts):
        try:
            cases = load_classification_corpus(opts["corpus"])
            summary = summarize_classification_corpus(cases)
            if opts["predictions"]:
                predictions = load_classification_predictions(
                    opts["predictions"], {item["id"] for item in cases},
                )
                report = score_classification_predictions(cases, predictions)
            else:
                report = None
        except ClassificationAuditError:
            raise CommandError(
                "Invalid local classification audit input; inspect corpus/prediction schema.",
            ) from None
        if opts["json_summary"]:
            self.stdout.write(json.dumps({
                "corpus": summary,
                "evaluation": report if summary["approved"] else None,
                "status": (
                    "NO_REVIEWED_REFERENCES"
                    if not summary["approved"]
                    else "NO_CAPTURED_PREDICTIONS"
                    if report is None else "DESCRIPTIVE_AUDIT_ONLY"
                ),
                "enforcement_approved": False,
            }, sort_keys=True))
            return

        self.stdout.write(
            "CORPUS cases={cases} approved={approved} pending={pending}".format(
                **summary,
            )
        )
        self.stdout.write(
            "DRAFT_COVERAGE domains={domains} categories={categories}".format(
                domains=sum(count > 0 for count in summary["draft_domain_counts"].values()),
                categories=sum(count > 0 for count in summary["tag_counts"].values()),
            )
        )
        if not summary["approved"]:
            self.stdout.write(
                "NOT SCORED: reference labels are pending independent review. "
                "A synthetic case set cannot establish model accuracy."
            )
        elif report is None:
            self.stdout.write(
                "NOT SCORED: supply --predictions with previously captured "
                "model outputs for approved reference cases."
            )
        else:
            self.stdout.write(
                "DESCRIPTIVE_AUDIT approved={approved} predicted={predicted} "
                "missing={missing} invalid={invalid_json_or_quotes} "
                "exact_matches={exact_matches} scope_risks={potential_scope_leaks} "
                "complete={coverage_complete} rate={exact_match_rate}".format(**report)
            )
            for problem, ids in report["problems_by_case_id"].items():
                if ids:
                    self.stdout.write(f"PROBLEM type={problem} case_ids={','.join(ids)}")
        self.stdout.write(
            "NO PROVIDER CALLS; NO DATABASE WRITES; NO MODEL ACCURACY "
            "OR PARTNER ENFORCEMENT APPROVAL."
        )
