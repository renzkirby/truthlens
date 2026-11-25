"""Local-only live A/B harness for the adaptive evidence assessment budget."""

from collections import Counter
from copy import deepcopy
import json
import os
import time
from unittest.mock import patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.test.utils import override_settings

from api import tasks
from api.models import Claim, VerificationEvidence, VerificationRun, VerificationTelemetryEvent
from api.verification.evidence_dossier import (
    filter_reasoning_evidence_dossier_by_role,
    load_reasoning_evidence_dossier_for_run,
)
from api.verification.providers.google_fact_check import GoogleFactCheckProvider
from api.verification.providers.tavily import TavilyProvider


MAX_CLAIMS = 10
DECISIVE_VERDICTS = frozenset({"FACT", "FAKE", "MISLEADING", "SATIRE"})

_ORIGINAL_CLEAN_OCR_TEXT = tasks.clean_ocr_text
_ORIGINAL_GFC_COVERAGE = tasks.assess_fact_check_proposition_coverage
_ORIGINAL_GFC_SEARCH = GoogleFactCheckProvider.search_with_payload
_ORIGINAL_TAVILY_SEARCH = TavilyProvider.search_with_payload


class UpstreamReplayMismatch(RuntimeError):
    """Baseline/adaptive upstream call sequence diverged during controlled A/B."""


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
                f"Adaptive arm made an extra upstream {key} call."
            )
        record = self.records[key][cursor]
        self.cursors[key] += 1
        if record["args"] != args or record["kwargs"] != kwargs:
            raise UpstreamReplayMismatch(
                f"Adaptive arm changed upstream {key} inputs."
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
        duration_ms = int((time.perf_counter() - started) * 1000)
        return self._record(
            key,
            safe_args,
            safe_kwargs,
            result,
            duration_ms,
        )

    def call_method(self, key, original, replay, instance, *args, **kwargs):
        safe_args = deepcopy(args)
        safe_kwargs = deepcopy(kwargs)
        if replay:
            return self._replay(key, safe_args, safe_kwargs)

        started = time.perf_counter()
        result = original(instance, *args, **kwargs)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return self._record(
            key,
            safe_args,
            safe_kwargs,
            result,
            duration_ms,
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
                    record["duration_ms"] for record in self.records[key]
                ),
            }
            for key in self.KEYS
        }


def _duration_ms(run, fallback_ms):
    if run is not None and run.started_at is not None and run.completed_at is not None:
        return max(0, int((run.completed_at - run.started_at).total_seconds() * 1000))
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
    """Count assessed stance signals at source-identity granularity."""
    counts = Counter()
    for evidence_group in secondary_groups:
        stances = {
            item.stance
            for item in evidence_group.evidence
            if item.stance
        }
        non_unknown = stances - {VerificationEvidence.Stance.UNKNOWN}
        if non_unknown:
            counts["ASSESSED"] += 1
        else:
            counts["UNKNOWN_ONLY"] += 1
        for stance in (
            VerificationEvidence.Stance.SUPPORTS,
            VerificationEvidence.Stance.REFUTES,
            VerificationEvidence.Stance.CONTEXT,
        ):
            if stance in stances:
                counts[stance] += 1
    return dict(sorted(counts.items()))


def _confidence_delta(baseline, adaptive):
    left = baseline.get("confidence")
    right = adaptive.get("confidence")
    if not isinstance(left, (int, float)) or isinstance(left, bool):
        return None
    if not isinstance(right, (int, float)) or isinstance(right, bool):
        return None
    return round(float(right) - float(left), 2)


def _assessment_provider_route(arm):
    return [
        (
            event.get("provider"),
            (event.get("metadata") or {}).get("model_id"),
            event.get("outcome"),
            event.get("error_label"),
        )
        for event in arm.get("assessment_provider_calls", [])
    ]


def _compare_arms(baseline, adaptive):
    reasons = []
    if baseline["status"] != VerificationRun.Status.COMPLETED:
        reasons.append("BASELINE_NOT_COMPLETED")
    if adaptive["status"] != VerificationRun.Status.COMPLETED:
        reasons.append("ADAPTIVE_NOT_COMPLETED")
    if baseline.get("exception_type"):
        reasons.append("BASELINE_EXCEPTION")
    if adaptive.get("exception_type"):
        reasons.append("ADAPTIVE_EXCEPTION")
    if baseline["status"] != adaptive["status"]:
        reasons.append("STATUS_CHANGED")
    if _assessment_provider_route(baseline) != _assessment_provider_route(adaptive):
        reasons.append("ASSESSMENT_PROVIDER_ROUTE_CHANGED")
    if baseline["verdict"] != adaptive["verdict"]:
        reasons.append("VERDICT_CHANGED")
    if (
        baseline["verdict"] == "UNVERIFIED"
        and adaptive["verdict"] in DECISIVE_VERDICTS
    ):
        reasons.append("ADAPTIVE_MORE_DECISIVE")
    confidence_delta = _confidence_delta(baseline, adaptive)
    if confidence_delta is not None and abs(confidence_delta) > 15:
        reasons.append("CONFIDENCE_SHIFT_GT_15")
    if baseline["source_identity_count"] != adaptive["source_identity_count"]:
        reasons.append("SOURCE_IDENTITY_COUNT_CHANGED")
    if baseline["evidence_total"] != adaptive["evidence_total"]:
        reasons.append("EVIDENCE_COUNT_CHANGED")
    if baseline.get("evidence_role_counts") != adaptive.get("evidence_role_counts"):
        reasons.append("EVIDENCE_ROLE_COUNTS_CHANGED")
    if (
        baseline.get("secondary_identity_stance_counts")
        != adaptive.get("secondary_identity_stance_counts")
    ):
        reasons.append("IDENTITY_STANCE_TOPOLOGY_CHANGED")
    if not baseline.get("database_isolated", False):
        reasons.append("BASELINE_DATABASE_NOT_ISOLATED")
    if not adaptive.get("database_isolated", False):
        reasons.append("ADAPTIVE_DATABASE_NOT_ISOLATED")
    if adaptive.get("upstream_replay_complete") is False:
        reasons.append("UPSTREAM_REPLAY_DIVERGED")
    if baseline["verdict"] in {"MISLEADING", "SATIRE"} or adaptive["verdict"] in {
        "MISLEADING", "SATIRE"
    }:
        reasons.append("CONTEXTUAL_VERDICT_MANUAL_REVIEW")

    baseline_ms = baseline["duration_ms"]
    adaptive_ms = adaptive["duration_ms"]
    latency_delta_ms = adaptive_ms - baseline_ms
    latency_change_pct = None
    if baseline_ms > 0:
        latency_change_pct = round((latency_delta_ms / baseline_ms) * 100, 1)

    return {
        "automated_gate": "PASS" if not reasons else "REVIEW",
        "review_reasons": reasons,
        "verdict_match": baseline["verdict"] == adaptive["verdict"],
        "status_match": baseline["status"] == adaptive["status"],
        "confidence_delta": confidence_delta,
        "latency_delta_ms": latency_delta_ms,
        "latency_change_pct": latency_change_pct,
    }


class Command(BaseCommand):
    help = (
        "Run local live baseline-vs-adaptive verification arms with cache/Vault "
        "reuse disabled, then compare quality signals and latency."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--claim",
            dest="claims",
            action="append",
            help="TEXT claim to evaluate. Repeat for multiple claims.",
        )
        parser.add_argument(
            "--keep-artifacts",
            action="store_true",
            help=(
                "Deprecated for this harness; controlled A/B runs are always "
                "rollback-isolated and this option is rejected."
            ),
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
                "This live A/B harness is restricted to local development."
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
        if options["keep_artifacts"]:
            raise CommandError(
                "--keep-artifacts is incompatible with rollback-isolated A/B runs."
            )

        reports = []
        for index, claim_text in enumerate(claims, start=1):
            if not options["json"]:
                self.stdout.write(
                    self.style.MIGRATE_HEADING(
                        f"Claim {index}/{len(claims)}: {claim_text}"
                    )
                )
                self.stdout.write("Running BASELINE (adaptive budget off)...")
            replay_tape = _UpstreamReplayTape()
            baseline = self._run_isolated_arm(
                claim_text,
                adaptive=False,
                replay_tape=replay_tape,
                replay_upstream=False,
            )

            replay_tape.begin_replay()
            if not options["json"]:
                self.stdout.write(
                    "Running ADAPTIVE (adaptive budget on; upstream replayed)..."
                )
            adaptive = self._run_isolated_arm(
                claim_text,
                adaptive=True,
                replay_tape=replay_tape,
                replay_upstream=True,
            )
            adaptive["upstream_replay_complete"] = replay_tape.replay_complete()
            adaptive["upstream_replay"] = replay_tape.summary()
            baseline["upstream_replay_complete"] = True
            baseline["upstream_replay"] = replay_tape.summary()

            comparison = _compare_arms(baseline, adaptive)
            report = {
                "claim": claim_text,
                "baseline": baseline,
                "adaptive": adaptive,
                "comparison": comparison,
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
        adaptive,
        replay_tape,
        replay_upstream,
    ):
        """Run one arm and roll back every database write before returning."""
        with transaction.atomic():
            try:
                result = self._run_arm(
                    claim_text,
                    adaptive=adaptive,
                    keep_artifacts=False,
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
        adaptive,
        keep_artifacts,
        replay_tape,
        replay_upstream,
    ):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=claim_text,
        )
        started = time.perf_counter()
        exception_type = ""

        try:
            with (
                override_settings(INVESTIGATION_CLASSIFICATION_MODE="off"),
                patch.dict(
                    os.environ,
                    {
                        tasks.EVIDENCE_ASSESSMENT_BUDGET_FLAG: (
                            "1" if adaptive else "0"
                        )
                    },
                    clear=False,
                ),
                patch("api.claim_matching.find_matching_claim", return_value=None),
                patch("api.tasks.search_official_vault", return_value=None),
                patch("api.tasks._resolve_exact_published_claim", return_value=False),
                patch(
                    "api.tasks._resolve_equivalent_published_claim",
                    return_value=False,
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
            result = {
                "adaptive": adaptive,
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
                "run_id": str(claim.pk) if keep_artifacts else None,
            }
            if not keep_artifacts:
                claim.delete()
            return result

        evidence = VerificationEvidence.objects.filter(verification_run=run)
        evidence_total = evidence.count()
        evidence_assessed = evidence.filter(
            Q(relevance_score__isnull=False)
            | Q(directness_score__isnull=False)
            | ~Q(stance=VerificationEvidence.Stance.UNKNOWN)
        ).count()
        stance_counts = Counter(evidence.values_list("stance", flat=True))
        evidence_role_counts = Counter(evidence.values_list("evidence_role", flat=True))

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
                name__endswith="tavily_evidence_assessment_batch",
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

        result = {
            "adaptive": adaptive,
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
            "run_id": str(run.pk) if keep_artifacts else None,
        }

        if not keep_artifacts:
            claim.delete()
        return result

    def _print_report(self, report):
        baseline = report["baseline"]
        adaptive = report["adaptive"]
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
            "ADAPTIVE "
            f"status={adaptive['status']} verdict={adaptive['verdict']} "
            f"confidence={adaptive['confidence']} duration_ms={adaptive['duration_ms']} "
            f"evidence={adaptive['evidence_total']} "
            f"assessed={adaptive['evidence_assessed']} "
            f"identities={adaptive['source_identity_count']}"
        )

        for label, arm in (("BASELINE", baseline), ("ADAPTIVE", adaptive)):
            for event in arm["assessment_stages"]:
                metadata = event["metadata"]
                self.stdout.write(
                    f"{label}_ASSESSMENT "
                    f"duration_ms={event['duration_ms']} "
                    f"eligible={metadata.get('eligible_items', 'n/a')} "
                    f"selected={metadata.get('selected_items', 'n/a')} "
                    f"deferred={metadata.get('deferred_items', 'n/a')} "
                    f"waves={metadata.get('assessment_waves', 'n/a')} "
                    f"early_stopped={metadata.get('early_stopped', 'n/a')}"
                )
            for event in arm["assessment_provider_calls"]:
                self.stdout.write(
                    f"{label}_PROVIDER "
                    f"provider={event['provider']} outcome={event['outcome']} "
                    f"duration_ms={event['duration_ms']}"
                )

        delta = comparison["latency_delta_ms"]
        pct = comparison["latency_change_pct"]
        self.stdout.write(
            f"COMPARISON gate={comparison['automated_gate']} "
            f"verdict_match={comparison['verdict_match']} "
            f"confidence_delta={comparison['confidence_delta']} "
            f"latency_delta_ms={delta} latency_change_pct={pct}"
        )
        if comparison["review_reasons"]:
            self.stdout.write(
                "REVIEW_REASONS " + ",".join(comparison["review_reasons"])
            )
        replay = adaptive.get("upstream_replay", {})
        replay_complete = adaptive.get("upstream_replay_complete")
        self.stdout.write(
            f"UPSTREAM_REPLAY complete={replay_complete} "
            + " ".join(
                f"{key}={value.get('replayed_calls', 0)}/"
                f"{value.get('recorded_calls', 0)}"
                for key, value in sorted(replay.items())
            )
        )
        self.stdout.write(
            "IDENTITY_STANCES "
            f"baseline={baseline.get('secondary_identity_stance_counts', {})} "
            f"adaptive={adaptive.get('secondary_identity_stance_counts', {})}"
        )
        self.stdout.write(
            "NOTE Each arm is rollback-isolated to the same starting database state. "
            "Baseline ClaimGate/GFC/Tavily upstream results are replayed to the "
            "adaptive arm with their recorded delays. Downstream LLM responses can "
            "still vary, so contextual/verdict or identity-topology changes require review."
        )
        self.stdout.write("")
