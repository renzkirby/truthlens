"""Development-only, three-claim live canary for shadow classification.

The command is dry-run by default. Live execution requires:
- APP_ENV=development and DEBUG=True
- INVESTIGATION_CLASSIFICATION_MODE=shadow
- the shared Gemini -> Cloudflare -> Groq hierarchy flags
- an exact one-time confirmation string

No authoritative ClaimInvestigationClassification row may be created.
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.investigation_classifier import classification_mode
from api.models import (
    Claim,
    ClaimInvestigationClassification,
    InvestigationClassificationAssessment,
)
from api.tasks import classify_investigation_claim_task
from api.verification.classification_contract import CLASSIFICATION_OPERATION
from api.verification.cloudflare_pilot import cloudflare_pilot_enabled
from api.verification.provider_hierarchy import hierarchy_enabled
from api.verification.telemetry import (
    get_current_collector,
    verification_telemetry_scope,
)


CANARY_SOURCE = "CLASSIFICATION_SHADOW_CANARY_2026_10_22"
CONFIRMATION = "I_APPROVE_THREE_CLAIM_SHADOW_CANARY"

CANARY_CASES = (
    {
        "case_id": "single_science",
        "claim_text": (
            "Researchers reported that a laboratory science experiment "
            "reproduced the same result in three independent trials."
        ),
        "expected_decision": "CLASSIFY",
        "expected_domains": ["SCIENCE"],
    },
    {
        "case_id": "cross_health_economy",
        "claim_text": (
            "A hospital increased patient service fees after the central bank "
            "raised interest rates, according to its published notice."
        ),
        "expected_decision": "CLASSIFY",
        "expected_domains": ["ECONOMY", "HEALTH"],
    },
    {
        "case_id": "ambiguous_plan",
        "claim_text": "A group announced that a new plan will begin next month.",
        "expected_decision": "ABSTAIN",
        "expected_domains": [],
    },
)


def _safe_provider_event(event):
    return {
        "provider": event.get("provider", ""),
        "outcome": event.get("outcome", ""),
        "error_label": event.get("error_label", ""),
        "duration_ms": event.get("duration_ms", 0),
        "metadata": event.get("metadata", {}),
    }


@verification_telemetry_scope()
def _run_one_with_trace(claim_id):
    result = classify_investigation_claim_task.run(str(claim_id))
    collector = get_current_collector()
    events = []
    if collector is not None:
        events = [
            _safe_provider_event(event)
            for event in collector.events
            if event.get("name") == CLASSIFICATION_OPERATION
        ]
    return result, events


def _preflight():
    return {
        "app_env": getattr(settings, "APP_ENV", None),
        "debug": getattr(settings, "DEBUG", False) is True,
        "classification_mode": classification_mode(),
        "hierarchy_enabled": hierarchy_enabled(),
        "cloudflare_classification_enabled": cloudflare_pilot_enabled(
            CLASSIFICATION_OPERATION
        ),
        "gemini_api_key_present": bool(os.getenv("GEMINI_API_KEY")),
        "cloudflare_account_id_present": bool(os.getenv("CLOUDFLARE_ACCOUNT_ID")),
        "cloudflare_api_token_present": bool(os.getenv("CLOUDFLARE_API_TOKEN")),
        "groq_api_key_present": bool(os.getenv("GROQ_API_KEY")),
    }


def _assert_live_preconditions():
    p = _preflight()
    if p["app_env"] != "development" or not p["debug"]:
        raise CommandError("Shadow canary is development-only with DEBUG=True.")
    if p["classification_mode"] != "shadow":
        raise CommandError(
            "Set INVESTIGATION_CLASSIFICATION_MODE=shadow before live canary."
        )
    if not p["hierarchy_enabled"]:
        raise CommandError("Shared AI provider hierarchy is not enabled.")
    if not p["cloudflare_classification_enabled"]:
        raise CommandError(
            "Cloudflare classification fallback is not enabled for this hierarchy."
        )
    missing = [
        name for name, key in (
            ("GEMINI_API_KEY", "gemini_api_key_present"),
            ("CLOUDFLARE_ACCOUNT_ID", "cloudflare_account_id_present"),
            ("CLOUDFLARE_API_TOKEN", "cloudflare_api_token_present"),
            ("GROQ_API_KEY", "groq_api_key_present"),
        )
        if not p[key]
    ]
    if missing:
        raise CommandError(
            "Missing provider configuration: " + ", ".join(missing)
        )
    if Claim.objects.filter(source_type=CANARY_SOURCE).exists():
        raise CommandError(
            "This three-claim canary already exists in the local database. "
            "Do not replay it."
        )
    return p


class Command(BaseCommand):
    help = (
        "Dry-run or execute the approved three-claim development shadow "
        "classification canary using Gemini -> Cloudflare -> Groq."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute-live",
            action="store_true",
            help="Make live model requests and persist three synthetic shadow claims.",
        )
        parser.add_argument(
            "--confirm-live",
            default="",
            help="Exact confirmation string required with --execute-live.",
        )
        parser.add_argument("--json-summary", action="store_true")

    def handle(self, *args, **options):
        preflight = _preflight()
        if not options["execute_live"]:
            if options["confirm_live"]:
                raise CommandError(
                    "Live confirmation is invalid without --execute-live."
                )
            summary = {
                "status": "SHADOW_CANARY_DRY_RUN_NO_PROVIDER_CALLS",
                "source_marker": CANARY_SOURCE,
                "cases": [
                    {
                        "case_id": c["case_id"],
                        "expected_decision": c["expected_decision"],
                        "expected_domains": c["expected_domains"],
                    }
                    for c in CANARY_CASES
                ],
                "planned_claims": 3,
                "max_provider_stage_attempts": 9,
                "provider_calls": 0,
                "db_writes": 0,
                "preflight": preflight,
                "enforcement_enabled": False,
            }
            self._emit(summary, options["json_summary"])
            return

        if options["confirm_live"] != CONFIRMATION:
            raise CommandError(
                "Exact fresh live-canary confirmation string is required."
            )
        preflight = _assert_live_preconditions()

        results = []
        total_provider_attempts = 0
        for case in CANARY_CASES:
            claim = Claim.objects.create(
                claim_type=Claim.ClaimType.TEXT,
                context_text=case["claim_text"],
                source_type=CANARY_SOURCE,
                is_ai_generated=True,
            )
            outcome, provider_events = _run_one_with_trace(claim.pk)
            total_provider_attempts += len(provider_events)
            if total_provider_attempts > 9:
                raise CommandError(
                    "Safety invariant violated: more than nine provider-stage "
                    "attempts observed. Stop and inspect locally."
                )

            assessment = InvestigationClassificationAssessment.objects.filter(
                claim=claim
            ).values(
                "status", "candidate_domains", "reason_code", "classifier_version"
            ).first()
            authoritative = ClaimInvestigationClassification.objects.filter(
                claim=claim
            ).values("domains", "source").first()
            claim.refresh_from_db()

            if authoritative is not None:
                raise CommandError(
                    "SAFETY INVARIANT VIOLATION: shadow canary created an "
                    "authoritative classification. Stop immediately."
                )
            if claim.ai_verdict is not None or claim.final_verdict is not None:
                raise CommandError(
                    "SAFETY INVARIANT VIOLATION: classification modified a "
                    "factual verdict field. Stop immediately."
                )

            candidate_domains = (
                sorted(assessment["candidate_domains"]) if assessment else []
            )
            expected_domains = sorted(case["expected_domains"])
            if case["expected_decision"] == "ABSTAIN":
                exact_match = bool(
                    assessment
                    and assessment["status"] == "ABSTAINED"
                    and candidate_domains == []
                    and assessment["reason_code"] == "MODEL_ABSTAINED"
                )
            else:
                exact_match = bool(
                    assessment
                    and assessment["status"] == "SUGGESTED"
                    and candidate_domains == expected_domains
                )

            results.append({
                "case_id": case["case_id"],
                "claim_id": str(claim.pk),
                "expected_decision": case["expected_decision"],
                "expected_domains": expected_domains,
                "task_outcome": outcome,
                "assessment": assessment,
                "exact_match": exact_match,
                "authoritative_classification": None,
                "provider_trace": provider_events,
            })

        summary = {
            "status": "SHADOW_CANARY_FINISHED",
            "source_marker": CANARY_SOURCE,
            "claims_created": len(results),
            "provider_stage_attempts": total_provider_attempts,
            "max_provider_stage_attempts": 9,
            "exact_matches": sum(r["exact_match"] for r in results),
            "all_exact": all(r["exact_match"] for r in results),
            "authoritative_rows": 0,
            "factual_verdicts_changed": 0,
            "enforcement_enabled": False,
            "preflight": preflight,
            "results": results,
        }
        self._emit(summary, options["json_summary"])

    def _emit(self, summary, json_summary):
        if json_summary:
            self.stdout.write(json.dumps(summary, sort_keys=True))
            return
        self.stdout.write(
            "SHADOW_CANARY status={status} exact={exact_matches}/3 "
            "provider_stage_attempts={provider_stage_attempts} "
            "authoritative_rows={authoritative_rows}".format(**summary)
        )
