"""Development-only live A/B gate for Cloudflare assessment tail budgeting."""

from collections import Counter
from copy import deepcopy
import json
import os
import time
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.test.utils import override_settings

from api import services, tasks
from api.models import (
    Claim,
    VerificationEvidence,
    VerificationRun,
    VerificationTelemetryEvent,
)
from api.verification import evidence_assessment
from api.verification.evidence_dossier import (
    filter_reasoning_evidence_dossier_by_role,
    load_reasoning_evidence_dossier_for_run,
)
from api.verification.providers.google_fact_check import GoogleFactCheckProvider
from api.verification.providers.tavily import TavilyProvider


MAX_CLAIMS = 8
TAIL_BUDGET_FLAG = "ENABLE_CLOUDFLARE_ASSESSMENT_TAIL_BUDGET"
DECISIVE_VERDICTS = frozenset({"FACT", "FAKE", "MISLEADING", "SATIRE"})

_ORIGINAL_CLEAN_OCR_TEXT = tasks.clean_ocr_text
_ORIGINAL_GFC_COVERAGE = tasks.assess_fact_check_proposition_coverage
_ORIGINAL_GFC_SEARCH = GoogleFactCheckProvider.search_with_payload
_ORIGINAL_TAVILY_SEARCH = TavilyProvider.search_with_payload
_ORIGINAL_ASSESSMENT_CALL_LLM = evidence_assessment.call_llm_with_fallback


class UpstreamReplayMismatch(RuntimeError):
    """The budgeted arm diverged before the treatment stage."""


class _AssessmentGeminiQuotaError(RuntimeError):
    code = 402


class _UpstreamReplayTape:
    """Record baseline upstream results and replay them with equal wall-clock delay."""

    KEYS = ("claim_gate", "gfc_coverage", "gfc_search", "tavily_search")

    def __init__(self):
        self.records = {key: [] for key in self.KEYS}
        self.cursors = {key: 0 for key in self.KEYS}

    def begin_replay(self):
        self.cursors = {key: 0 for key in self.KEYS}

    def _record(self, key, args, kwargs, result, duration_ms):
        self.records[key].append({
            "args": deepcopy(args),
            "kwargs": deepcopy(kwargs),
            "result": deepcopy(result),
            "duration_ms": max(0, int(duration_ms)),
        })
        return result

    def _replay(self, key, args, kwargs):
        cursor = self.cursors[key]
        if cursor >= len(self.records[key]):
            raise UpstreamReplayMismatch(
                f"Budgeted arm made an extra upstream {key} call."
            )
        record = self.records[key][cursor]
        self.cursors[key] += 1
        if record["args"] != args or record["kwargs"] != kwargs:
            raise UpstreamReplayMismatch(
                f"Budgeted arm changed upstream {key} inputs."
            )
        if record["duration_ms"]:
            time.sleep(record["duration_ms"] / 1000)
        return deepcopy(record["result"])

    def call_function(self, key, original, replay, *args, **kwargs):
        safe_args = deepcopy(args)
        safe_kwargs = deepcopy(kwargs)
        if replay:
            return self._replay(key, safe_args, safe_kwargs)
        started = time.perf_counter()
        result = original(*args, **kwargs)
        return self._record(
            key,
            safe_args,
            safe_kwargs,
            result,
            int((time.perf_counter() - started) * 1000),
        )

    def call_method(self, key, original, replay, instance, *args, **kwargs):
        safe_args = deepcopy(args)
        safe_kwargs = deepcopy(kwargs)
        if replay:
            return self._replay(key, safe_args, safe_kwargs)
        started = time.perf_counter()
        result = original(instance, *args, **kwargs)
        return self._record(
            key,
            safe_args,
            safe_kwargs,
            result,
            int((time.perf_counter() - started) * 1000),
        )

    def replay_complete(self):
        return all(
            self.cursors[key] == len(self.records[key])
            for key in self.KEYS
        )

    def summary(self):
        return {
            key: {
                "recorded_calls": len(self.records[key]),
                "replayed_calls": self.cursors[key],
                "recorded_duration_ms": sum(
                    row["duration_ms"] for row in self.records[key]
                ),
            }
            for key in self.KEYS
        }


def _forced_cloudflare_assessment(*args, **kwargs):
    """Force only evidence assessment onto Cloudflare without leaking degradation.

    The nested provider scope ensures the synthetic Gemini 402 and any Cloudflare
    provider state are discarded when the assessment call returns, so later
    verdict stages retain the outer verification job's real provider state.
    """
    gemini = Mock()
    gemini.models.generate_content.side_effect = _AssessmentGeminiQuotaError(
        "synthetic assessment Gemini unavailable"
    )
    with (
        patch("api.services.gemini_client", gemini),
        services.llm_provider_scope(),
    ):
        return _ORIGINAL_ASSESSMENT_CALL_LLM(*args, **kwargs)


def _duration_ms(run, fallback_ms):
    if run is not None and run.started_at is not None and run.completed_at is not None:
        return max(
            0,
            int((run.completed_at - run.started_at).total_seconds() * 1000),
        )
    return max(0, int(fallback_ms))


def _event_dict(event):
    return {
        "name": event.name,
        "provider": event.provider,
        "outcome": event.outcome,
        "error_label": event.error_label,
        "duration_ms": event.duration_ms,
        "metadata": event.metadata if isinstance(event.metadata, dict) else {},
    }


def _secondary_identity_stance_counts(secondary_groups):
    counts = Counter()
    for group in secondary_groups:
        stances = {item.stance for item in group.evidence if item.stance}
        non_unknown = stances - {VerificationEvidence.Stance.UNKNOWN}
        counts["ASSESSED" if non_unknown else "UNKNOWN_ONLY"] += 1
        for stance in (
            VerificationEvidence.Stance.SUPPORTS,
            VerificationEvidence.Stance.REFUTES,
            VerificationEvidence.Stance.CONTEXT,
        ):
            if stance in stances:
                counts[stance] += 1
    return dict(sorted(counts.items()))


def _confidence_delta(baseline, budgeted):
    left = baseline.get("confidence")
    right = budgeted.get("confidence")
    if not isinstance(left, (int, float)) or isinstance(left, bool):
        return None
    if not isinstance(right, (int, float)) or isinstance(right, bool):
        return None
    return round(float(right) - float(left), 2)


def _assessment_route(arm):
    return [
        (
            event.get("provider"),
            event.get("outcome"),
            event.get("error_label"),
        )
        for event in arm.get("assessment_provider_calls", [])
    ]


def _final_route(arm):
    return [
        (
            event.get("provider"),
            event.get("outcome"),
            event.get("error_label"),
        )
        for event in arm.get("final_provider_calls", [])
    ]


def _tail_budget_metadata(arm):
    for event in reversed(arm.get("assessment_provider_calls", [])):
        if event.get("provider") != "cloudflare":
            continue
        metadata = event.get("metadata") or {}
        if metadata.get("assessment_tail_budget_applied") is True:
            return {
                "applied": True,
                "original_items": metadata.get("assessment_items_original"),
                "selected_items": metadata.get("assessment_items_selected"),
                "chunks": metadata.get("assessment_chunks_attempted"),
            }
    return {
        "applied": False,
        "original_items": None,
        "selected_items": None,
        "chunks": None,
    }


def _compare_arms(baseline, budgeted):
    reasons = []
    if baseline["status"] != VerificationRun.Status.COMPLETED:
        reasons.append("BASELINE_NOT_COMPLETED")
    if budgeted["status"] != VerificationRun.Status.COMPLETED:
        reasons.append("BUDGETED_NOT_COMPLETED")
    if baseline.get("exception_type"):
        reasons.append("BASELINE_EXCEPTION")
    if budgeted.get("exception_type"):
        reasons.append("BUDGETED_EXCEPTION")
    if baseline["status"] != budgeted["status"]:
        reasons.append("STATUS_CHANGED")
    if _assessment_route(baseline) != _assessment_route(budgeted):
        reasons.append("ASSESSMENT_PROVIDER_ROUTE_CHANGED")
    if _final_route(baseline) != _final_route(budgeted):
        reasons.append("FINAL_PROVIDER_ROUTE_CHANGED")
    if baseline["verdict"] != budgeted["verdict"]:
        reasons.append("VERDICT_CHANGED")
    if baseline.get("summary") != budgeted.get("summary"):
        reasons.append("SUMMARY_CHANGED_MANUAL_REVIEW")
    if (
        baseline["verdict"] == "UNVERIFIED"
        and budgeted["verdict"] in DECISIVE_VERDICTS
    ):
        reasons.append("BUDGETED_MORE_DECISIVE")

    confidence_delta = _confidence_delta(baseline, budgeted)
    if confidence_delta is not None and abs(confidence_delta) > 15:
        reasons.append("CONFIDENCE_SHIFT_GT_15")
    if baseline["source_identity_count"] != budgeted["source_identity_count"]:
        reasons.append("SOURCE_IDENTITY_COUNT_CHANGED")
    if baseline["evidence_total"] != budgeted["evidence_total"]:
        reasons.append("EVIDENCE_COUNT_CHANGED")
    if baseline["evidence_role_counts"] != budgeted["evidence_role_counts"]:
        reasons.append("EVIDENCE_ROLE_COUNTS_CHANGED")
    if (
        baseline["secondary_identity_stance_counts"]
        != budgeted["secondary_identity_stance_counts"]
    ):
        reasons.append("IDENTITY_STANCE_TOPOLOGY_CHANGED")
    if not baseline.get("database_isolated", False):
        reasons.append("BASELINE_DATABASE_NOT_ISOLATED")
    if not budgeted.get("database_isolated", False):
        reasons.append("BUDGETED_DATABASE_NOT_ISOLATED")
    if budgeted.get("upstream_replay_complete") is False:
        reasons.append("UPSTREAM_REPLAY_DIVERGED")

    budget = _tail_budget_metadata(budgeted)
    if not budget["applied"]:
        reasons.append("TAIL_BUDGET_NOT_APPLIED")

    # Contextual outcomes deserve a human reading of the two summaries even
    # when all deterministic topology checks match.
    if baseline["verdict"] in {"MISLEADING", "SATIRE"} or budgeted["verdict"] in {
        "MISLEADING", "SATIRE"
    }:
        reasons.append("CONTEXTUAL_VERDICT_MANUAL_REVIEW")

    baseline_ms = baseline["duration_ms"]
    budgeted_ms = budgeted["duration_ms"]
    latency_delta_ms = budgeted_ms - baseline_ms
    latency_change_pct = None
    if baseline_ms > 0:
        latency_change_pct = round((latency_delta_ms / baseline_ms) * 100, 1)

    return {
        "automated_gate": "PASS" if not reasons else "REVIEW",
        "review_reasons": reasons,
        "verdict_match": baseline["verdict"] == budgeted["verdict"],
        "status_match": baseline["status"] == budgeted["status"],
        "summary_exact_match": baseline["summary"] == budgeted["summary"],
        "confidence_delta": confidence_delta,
        "latency_delta_ms": latency_delta_ms,
        "latency_change_pct": latency_change_pct,
        "tail_budget": budget,
    }


class Command(BaseCommand):
    help = (
        "Development-only live quality A/B for the Cloudflare evidence-assessment "
        "tail budget. Baseline retrieval is replayed into the budgeted arm and "
        "all database writes are rolled back."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--claim",
            dest="claims",
            action="append",
            help="TEXT claim to evaluate. Repeat for up to eight claims.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit one JSON report after all claims complete.",
        )

    def handle(self, *args, **options):
        if not (
            getattr(settings, "APP_ENV", None) == "development"
            and getattr(settings, "DEBUG", False) is True
        ):
            raise CommandError(
                "Cloudflare assessment quality A/B is development-only."
            )

        claims = [
            " ".join(value.split())
            for value in (options.get("claims") or [])
            if isinstance(value, str) and value.strip()
        ]
        if not claims:
            raise CommandError("Provide at least one --claim.")
        if len(claims) > MAX_CLAIMS:
            raise CommandError(f"At most {MAX_CLAIMS} claims may be run at once.")

        reports = []
        for index, claim_text in enumerate(claims, start=1):
            if not options["json"]:
                self.stdout.write(
                    self.style.MIGRATE_HEADING(
                        f"Claim {index}/{len(claims)}: {claim_text}"
                    )
                )
                self.stdout.write("Running BASELINE (tail budget off)...")

            tape = _UpstreamReplayTape()
            baseline = self._run_isolated_arm(
                claim_text,
                budgeted=False,
                replay_tape=tape,
                replay_upstream=False,
            )

            tape.begin_replay()
            if not options["json"]:
                self.stdout.write(
                    "Running BUDGETED (tail budget on; upstream replayed)..."
                )
            budgeted = self._run_isolated_arm(
                claim_text,
                budgeted=True,
                replay_tape=tape,
                replay_upstream=True,
            )

            baseline["upstream_replay_complete"] = True
            budgeted["upstream_replay_complete"] = tape.replay_complete()
            replay_summary = tape.summary()
            baseline["upstream_replay"] = replay_summary
            budgeted["upstream_replay"] = replay_summary

            report = {
                "claim": claim_text,
                "baseline": baseline,
                "budgeted": budgeted,
                "comparison": _compare_arms(baseline, budgeted),
            }
            reports.append(report)
            if not options["json"]:
                self._print_report(report)

        if options["json"]:
            self.stdout.write(json.dumps(reports, indent=2, sort_keys=True))

    def _run_isolated_arm(
        self,
        claim_text,
        *,
        budgeted,
        replay_tape,
        replay_upstream,
    ):
        with transaction.atomic():
            try:
                result = self._run_arm(
                    claim_text,
                    budgeted=budgeted,
                    replay_tape=replay_tape,
                    replay_upstream=replay_upstream,
                )
                result["database_isolated"] = True
                return result
            finally:
                transaction.set_rollback(True)

    def _run_arm(
        self,
        claim_text,
        *,
        budgeted,
        replay_tape,
        replay_upstream,
    ):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=claim_text,
        )
        started = time.perf_counter()
        exception_type = ""

        env = {
            "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
            "ENABLE_GEMINI_TRANSIENT_MODEL_FALLBACK": "0",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "1",
            TAIL_BUDGET_FLAG: "1" if budgeted else "0",
        }

        try:
            with (
                override_settings(INVESTIGATION_CLASSIFICATION_MODE="off"),
                patch.dict(os.environ, env, clear=False),
                patch("api.claim_matching.find_matching_claim", return_value=None),
                patch("api.tasks.search_official_vault", return_value=None),
                patch("api.tasks._resolve_exact_published_claim", return_value=False),
                patch(
                    "api.tasks._resolve_equivalent_published_claim",
                    return_value=False,
                ),
                patch(
                    "api.verification.evidence_assessment.call_llm_with_fallback",
                    side_effect=_forced_cloudflare_assessment,
                ),
                patch(
                    "api.tasks.clean_ocr_text",
                    side_effect=lambda *call_args, **call_kwargs: (
                        replay_tape.call_function(
                            "claim_gate",
                            _ORIGINAL_CLEAN_OCR_TEXT,
                            replay_upstream,
                            *call_args,
                            **call_kwargs,
                        )
                    ),
                ),
                patch(
                    "api.tasks.assess_fact_check_proposition_coverage",
                    side_effect=lambda *call_args, **call_kwargs: (
                        replay_tape.call_function(
                            "gfc_coverage",
                            _ORIGINAL_GFC_COVERAGE,
                            replay_upstream,
                            *call_args,
                            **call_kwargs,
                        )
                    ),
                ),
                patch.object(
                    GoogleFactCheckProvider,
                    "search_with_payload",
                    autospec=True,
                    side_effect=lambda instance, *call_args, **call_kwargs: (
                        replay_tape.call_method(
                            "gfc_search",
                            _ORIGINAL_GFC_SEARCH,
                            replay_upstream,
                            instance,
                            *call_args,
                            **call_kwargs,
                        )
                    ),
                ),
                patch.object(
                    TavilyProvider,
                    "search_with_payload",
                    autospec=True,
                    side_effect=lambda instance, *call_args, **call_kwargs: (
                        replay_tape.call_method(
                            "tavily_search",
                            _ORIGINAL_TAVILY_SEARCH,
                            replay_upstream,
                            instance,
                            *call_args,
                            **call_kwargs,
                        )
                    ),
                ),
                patch("api.verification.runs.dispatch_after_commit"),
            ):
                tasks.execute_core_text_pipeline(
                    claim_text,
                    claim.pk,
                    triggered_by_id=None,
                )
        except Exception as exc:
            exception_type = type(exc).__name__

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        claim.refresh_from_db()
        run = claim.verification_runs.order_by("-created_at").first()

        if run is None:
            return {
                "budgeted": budgeted,
                "status": "NO_RUN",
                "verdict": claim.ai_verdict,
                "confidence": claim.consensus_score,
                "summary": claim.ai_summary,
                "score_context": claim.score_context,
                "duration_ms": elapsed_ms,
                "exception_type": exception_type,
                "evidence_total": 0,
                "evidence_assessed": 0,
                "source_identity_count": 0,
                "stance_counts": {},
                "evidence_role_counts": {},
                "secondary_identity_stance_counts": {},
                "assessment_stages": [],
                "assessment_provider_calls": [],
                "final_provider_calls": [],
            }

        evidence = VerificationEvidence.objects.filter(verification_run=run)
        evidence_total = evidence.count()
        evidence_assessed = evidence.filter(
            Q(relevance_score__isnull=False)
            | Q(directness_score__isnull=False)
            | ~Q(stance=VerificationEvidence.Stance.UNKNOWN)
        ).count()
        stance_counts = Counter(evidence.values_list("stance", flat=True))
        evidence_role_counts = Counter(
            evidence.values_list("evidence_role", flat=True)
        )

        try:
            dossier = load_reasoning_evidence_dossier_for_run(run)
            secondary_groups = filter_reasoning_evidence_dossier_by_role(
                dossier,
                VerificationEvidence.EvidenceRole.SECONDARY,
            )
            source_identity_count = len(secondary_groups)
            secondary_identity_stance_counts = _secondary_identity_stance_counts(
                secondary_groups,
            )
        except Exception:
            source_identity_count = 0
            secondary_identity_stance_counts = {}

        assessment_stages = [
            _event_dict(event)
            for event in VerificationTelemetryEvent.objects.filter(
                verification_run=run,
                event_type=VerificationTelemetryEvent.EventType.PIPELINE_STAGE,
                name__endswith="evidence_assessment_batch",
            ).order_by("sequence")
        ]
        assessment_provider_calls = [
            _event_dict(event)
            for event in VerificationTelemetryEvent.objects.filter(
                verification_run=run,
                event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
                name="evidence_assessment",
            ).order_by("sequence")
        ]
        final_provider_calls = [
            _event_dict(event)
            for event in VerificationTelemetryEvent.objects.filter(
                verification_run=run,
                event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
                name="persisted_evidence_evaluation",
            ).order_by("sequence")
        ]

        return {
            "budgeted": budgeted,
            "status": run.status,
            "verdict": claim.ai_verdict,
            "confidence": claim.consensus_score,
            "summary": claim.ai_summary,
            "score_context": claim.score_context,
            "duration_ms": _duration_ms(run, elapsed_ms),
            "exception_type": exception_type,
            "evidence_total": evidence_total,
            "evidence_assessed": evidence_assessed,
            "source_identity_count": source_identity_count,
            "stance_counts": dict(sorted(stance_counts.items())),
            "evidence_role_counts": dict(sorted(evidence_role_counts.items())),
            "secondary_identity_stance_counts": secondary_identity_stance_counts,
            "assessment_stages": assessment_stages,
            "assessment_provider_calls": assessment_provider_calls,
            "final_provider_calls": final_provider_calls,
        }

    def _print_report(self, report):
        baseline = report["baseline"]
        budgeted = report["budgeted"]
        comparison = report["comparison"]

        self.stdout.write("")
        self.stdout.write(
            "BASELINE "
            f"status={baseline['status']} verdict={baseline['verdict']} "
            f"confidence={baseline['confidence']} duration_ms={baseline['duration_ms']} "
            f"evidence={baseline['evidence_total']} "
            f"assessed={baseline['evidence_assessed']} "
            f"identities={baseline['source_identity_count']}"
        )
        self.stdout.write(
            "BUDGETED "
            f"status={budgeted['status']} verdict={budgeted['verdict']} "
            f"confidence={budgeted['confidence']} duration_ms={budgeted['duration_ms']} "
            f"evidence={budgeted['evidence_total']} "
            f"assessed={budgeted['evidence_assessed']} "
            f"identities={budgeted['source_identity_count']}"
        )
        self.stdout.write(
            "TAIL BUDGET "
            + json.dumps(comparison["tail_budget"], sort_keys=True)
        )
        self.stdout.write(
            "QUALITY GATE "
            f"{comparison['automated_gate']} "
            f"reasons={comparison['review_reasons']}"
        )
        self.stdout.write(
            "SUMMARY BASELINE: " + str(baseline.get("summary") or "")
        )
        self.stdout.write(
            "SUMMARY BUDGETED: " + str(budgeted.get("summary") or "")
        )
        self.stdout.write("")
