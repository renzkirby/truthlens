"""Frozen-evidence live A/B for Cloudflare assessment tail budgeting.

Development only. Retrieval/ingestion runs once per claim inside a rollback-only
transaction. The exact persisted secondary evidence snapshot is then assessed
twice in memory:

- baseline: full 9-12 item Cloudflare assessment
- budgeted: the production source-diverse 8-item Cloudflare candidate

No final verdict evaluator, recovery cycle, or second retrieval is invoked.
"""

from collections import Counter
import json
import os
import time
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings

from api import services, tasks
from api.models import Claim, VerificationEvidence
from api.verification.evidence_assessment import (
    assess_reasoning_evidence_batch_against_claim,
)
from api.verification.evidence_dossier import (
    filter_reasoning_evidence_dossier_by_role,
    load_reasoning_evidence_dossier_for_run,
)
from api.verification.runs import create_verification_run, start_verification_run


MAX_CLAIMS = 8
TAIL_BUDGET_FLAG = "ENABLE_CLOUDFLARE_ASSESSMENT_TAIL_BUDGET"
DECISIVE_STANCES = frozenset({
    VerificationEvidence.Stance.SUPPORTS,
    VerificationEvidence.Stance.REFUTES,
})


class _AssessmentGeminiQuotaError(RuntimeError):
    code = 402


def _assessment_available(assessment):
    return not (
        assessment.stance == VerificationEvidence.Stance.UNKNOWN
        and assessment.relevance_score is None
        and assessment.directness_score is None
    )


def _assessment_payload(assessment):
    return {
        "stance": assessment.stance,
        "relevance_score": assessment.relevance_score,
        "directness_score": assessment.directness_score,
        "available": _assessment_available(assessment),
    }


def _provider_events(record):
    events = []
    for call in record.call_args_list:
        if len(call.args) < 5:
            continue
        events.append({
            "operation": call.args[0],
            "provider": call.args[1],
            "duration_ms": call.args[3],
            "outcome": call.args[4],
            "error_label": call.args[5] if len(call.args) > 5 else "",
            "metadata": call.kwargs.get("metadata", {}) or {},
        })
    return events


def _successful_cloudflare_event(events):
    for event in reversed(events):
        if (
            event["provider"] == "cloudflare"
            and event["outcome"] == "success"
        ):
            return event
    return None


def _groq_attempts(events):
    return sum(
        1
        for event in events
        if event["provider"] == "groq"
    )


def _run_assessment_arm(
    claim_text,
    evidence_items,
    *,
    budgeted,
    selected_ids,
    material_scope_hardening=True,
):
    gemini = Mock()
    gemini.models.generate_content.side_effect = _AssessmentGeminiQuotaError(
        "synthetic assessment Gemini unavailable"
    )
    groq = Mock()
    groq.with_options.return_value.chat.completions.create.side_effect = (
        AssertionError("Frozen-evidence A/B must not require Groq.")
    )

    env = {
        "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
        "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
        "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
        "ENABLE_GEMINI_TRANSIENT_MODEL_FALLBACK": "0",
        "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
        "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "1",
        TAIL_BUDGET_FLAG: "1" if budgeted else "0",
    }

    started = time.perf_counter()
    with (
        patch.dict(os.environ, env, clear=False),
        patch("api.services.gemini_client", gemini),
        patch("api.services.groq_client", groq),
        patch("api.services.record_llm_provider_call") as telemetry,
        services.llm_provider_scope(),
    ):
        assessments = assess_reasoning_evidence_batch_against_claim(
            claim_text,
            evidence_items,
            enforce_material_scope=material_scope_hardening,
            cloudflare_fallback_evidence_link_ids=(
                selected_ids if budgeted else None
            ),
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    events = _provider_events(telemetry)
    cloudflare = _successful_cloudflare_event(events)
    metadata = cloudflare["metadata"] if cloudflare is not None else {}
    return {
        "budgeted": budgeted,
        "duration_ms": elapsed_ms,
        "assessments": assessments,
        "provider_events": events,
        "cloudflare_success": cloudflare is not None,
        "cloudflare_chunks": metadata.get("assessment_chunks_attempted"),
        "tail_budget_applied": (
            metadata.get("assessment_tail_budget_applied") is True
        ),
        "assessment_items_original": metadata.get("assessment_items_original"),
        "assessment_items_selected": metadata.get("assessment_items_selected"),
        "groq_attempts": _groq_attempts(events),
    }


def _identity_rows(eligible_groups, baseline, budgeted, selected_id_set):
    baseline_by_id = {
        item.evidence_link_id: assessment
        for (_identity_id, items), assessments in zip(
            eligible_groups,
            _split_assessments_by_group(eligible_groups, baseline["assessments"]),
        )
        for item, assessment in zip(items, assessments)
    }
    budgeted_by_id = {
        item.evidence_link_id: assessment
        for (_identity_id, items), assessments in zip(
            eligible_groups,
            _split_assessments_by_group(eligible_groups, budgeted["assessments"]),
        )
        for item, assessment in zip(items, assessments)
    }

    rows = []
    for identity_index, (identity_id, items) in enumerate(eligible_groups, start=1):
        baseline_assessments = [baseline_by_id[item.evidence_link_id] for item in items]
        budgeted_assessments = [budgeted_by_id[item.evidence_link_id] for item in items]

        baseline_stances = {
            assessment.stance
            for assessment in baseline_assessments
            if _assessment_available(assessment)
        }
        budgeted_stances = {
            assessment.stance
            for assessment in budgeted_assessments
            if _assessment_available(assessment)
        }
        baseline_decisive = sorted(baseline_stances & DECISIVE_STANCES)
        budgeted_decisive = sorted(budgeted_stances & DECISIVE_STANCES)

        rows.append({
            "identity_index": identity_index,
            "identity_id": str(identity_id),
            "item_count": len(items),
            "selected_count": sum(
                item.evidence_link_id in selected_id_set for item in items
            ),
            "baseline_assessed_count": sum(
                _assessment_available(value) for value in baseline_assessments
            ),
            "budgeted_assessed_count": sum(
                _assessment_available(value) for value in budgeted_assessments
            ),
            "baseline_stances": sorted(baseline_stances),
            "budgeted_stances": sorted(budgeted_stances),
            "baseline_decisive_stances": baseline_decisive,
            "budgeted_decisive_stances": budgeted_decisive,
            "decisive_match": baseline_decisive == budgeted_decisive,
            "context_match": (
                (VerificationEvidence.Stance.CONTEXT in baseline_stances)
                == (VerificationEvidence.Stance.CONTEXT in budgeted_stances)
            ),
        })
    return rows


def _split_assessments_by_group(eligible_groups, assessments):
    grouped = []
    cursor = 0
    for _identity_id, items in eligible_groups:
        count = len(items)
        grouped.append(assessments[cursor:cursor + count])
        cursor += count
    return grouped


def _item_rows(eligible_groups, baseline, budgeted, selected_id_set):
    flattened = [
        (identity_index, item)
        for identity_index, (_identity_id, items) in enumerate(
            eligible_groups,
            start=1,
        )
        for item in items
    ]
    rows = []
    for index, ((identity_index, item), left, right) in enumerate(
        zip(flattened, baseline["assessments"], budgeted["assessments"])
    ):
        selected = item.evidence_link_id in selected_id_set
        rows.append({
            "item_index": index,
            "identity_index": identity_index,
            "evidence_link_id": str(item.evidence_link_id),
            "selected_for_budget": selected,
            "baseline": _assessment_payload(left),
            "budgeted": _assessment_payload(right),
            "selected_stance_match": (
                not selected
                or (
                    _assessment_available(left)
                    and _assessment_available(right)
                    and left.stance == right.stance
                )
            ),
        })
    return rows


def _score_delta_summary(item_rows):
    relevance = []
    directness = []
    for row in item_rows:
        if not row["selected_for_budget"]:
            continue
        left = row["baseline"]
        right = row["budgeted"]
        if not left["available"] or not right["available"]:
            continue
        if (
            isinstance(left["relevance_score"], (int, float))
            and isinstance(right["relevance_score"], (int, float))
        ):
            relevance.append(abs(
                float(right["relevance_score"])
                - float(left["relevance_score"])
            ))
        if (
            isinstance(left["directness_score"], (int, float))
            and isinstance(right["directness_score"], (int, float))
        ):
            directness.append(abs(
                float(right["directness_score"])
                - float(left["directness_score"])
            ))
    return {
        "max_relevance_delta": round(max(relevance), 4) if relevance else None,
        "max_directness_delta": round(max(directness), 4) if directness else None,
    }


def _compare_frozen_arms(
    eligible_groups,
    baseline,
    budgeted,
    selected_ids,
):
    selected_id_set = set(selected_ids)
    identity_rows = _identity_rows(
        eligible_groups,
        baseline,
        budgeted,
        selected_id_set,
    )
    item_rows = _item_rows(
        eligible_groups,
        baseline,
        budgeted,
        selected_id_set,
    )
    reasons = []

    if not baseline["cloudflare_success"]:
        reasons.append("BASELINE_CLOUDFLARE_NOT_SUCCESSFUL")
    if baseline["cloudflare_chunks"] != 3:
        reasons.append("BASELINE_NOT_THREE_CHUNKS")
    if baseline["groq_attempts"]:
        reasons.append("BASELINE_GROQ_REACHED")

    if not budgeted["cloudflare_success"]:
        reasons.append("BUDGETED_CLOUDFLARE_NOT_SUCCESSFUL")
    if budgeted["cloudflare_chunks"] != 2:
        reasons.append("BUDGETED_NOT_TWO_CHUNKS")
    if not budgeted["tail_budget_applied"]:
        reasons.append("TAIL_BUDGET_NOT_APPLIED")
    if budgeted["assessment_items_original"] != sum(
        len(items) for _identity_id, items in eligible_groups
    ):
        reasons.append("TAIL_BUDGET_ORIGINAL_COUNT_MISMATCH")
    if budgeted["assessment_items_selected"] != len(selected_ids):
        reasons.append("TAIL_BUDGET_SELECTED_COUNT_MISMATCH")
    if budgeted["groq_attempts"]:
        reasons.append("BUDGETED_GROQ_REACHED")

    identity_coverage_preserved = all(
        row["budgeted_assessed_count"] >= 1
        for row in identity_rows
    )
    decisive_topology_match = all(
        row["decisive_match"] for row in identity_rows
    )
    selected_stance_match = all(
        row["selected_stance_match"] for row in item_rows
    )
    context_changed_identities = [
        row["identity_index"]
        for row in identity_rows
        if not row["context_match"]
    ]

    if not identity_coverage_preserved:
        reasons.append("SOURCE_IDENTITY_ASSESSMENT_COVERAGE_LOST")
    if not decisive_topology_match:
        reasons.append("DECISIVE_IDENTITY_TOPOLOGY_CHANGED")
    if not selected_stance_match:
        reasons.append("SELECTED_ITEM_STANCE_CHANGED")

    score_deltas = _score_delta_summary(item_rows)
    for key in ("max_relevance_delta", "max_directness_delta"):
        value = score_deltas[key]
        if value is not None and value > 0.20:
            reasons.append("SELECTED_ITEM_SCORE_SHIFT_GT_0_20")
            break

    hard_invalid_reasons = {
        "BASELINE_CLOUDFLARE_NOT_SUCCESSFUL",
        "BASELINE_NOT_THREE_CHUNKS",
        "BASELINE_GROQ_REACHED",
        "BUDGETED_CLOUDFLARE_NOT_SUCCESSFUL",
        "BUDGETED_NOT_TWO_CHUNKS",
        "TAIL_BUDGET_NOT_APPLIED",
        "TAIL_BUDGET_ORIGINAL_COUNT_MISMATCH",
        "TAIL_BUDGET_SELECTED_COUNT_MISMATCH",
        "BUDGETED_GROQ_REACHED",
    }
    if any(reason in hard_invalid_reasons for reason in reasons):
        gate = "INVALID"
    elif reasons:
        gate = "REVIEW"
    else:
        gate = "PASS"

    return {
        "quality_gate": gate,
        "review_reasons": reasons,
        "identity_coverage_preserved": identity_coverage_preserved,
        "decisive_identity_topology_match": decisive_topology_match,
        "selected_item_stance_match": selected_stance_match,
        "context_topology_changed": bool(context_changed_identities),
        "context_changed_identity_indexes": context_changed_identities,
        **score_deltas,
        "latency_delta_ms": (
            budgeted["duration_ms"] - baseline["duration_ms"]
        ),
        "latency_change_pct": (
            round(
                (
                    (budgeted["duration_ms"] - baseline["duration_ms"])
                    / baseline["duration_ms"]
                ) * 100,
                1,
            )
            if baseline["duration_ms"] > 0
            else None
        ),
        "identities": identity_rows,
        "items": item_rows,
    }


class Command(BaseCommand):
    help = (
        "Development-only frozen-evidence Cloudflare assessment A/B. "
        "Retrieves and persists evidence once, then compares full vs budgeted "
        "Cloudflare assessment against the identical evidence snapshot."
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
            help="Emit JSON only.",
        )

    def handle(self, *args, **options):
        if not (
            getattr(settings, "APP_ENV", None) == "development"
            and getattr(settings, "DEBUG", False) is True
        ):
            raise CommandError(
                "Frozen-evidence Cloudflare assessment A/B is development-only."
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

        reports = [
            self._run_rollback_isolated_claim(claim)
            for claim in claims
        ]

        if options["json"]:
            self.stdout.write(json.dumps(reports, indent=2, sort_keys=True))
            return

        for report in reports:
            self._print_report(report)

    def _run_rollback_isolated_claim(self, claim_text):
        with transaction.atomic():
            try:
                report = self._run_claim(claim_text)
                report["database_isolated"] = True
                return report
            finally:
                transaction.set_rollback(True)

    def _run_claim(self, claim_text):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=claim_text,
        )
        run = start_verification_run(create_verification_run(claim))

        with override_settings(INVESTIGATION_CLASSIFICATION_MODE="off"):
            cleaned = tasks.clean_ocr_text(claim_text)

        if not isinstance(cleaned, dict):
            return {
                "claim": claim_text,
                "eligibility": "INVALID_CLAIM_GATE_RESULT",
                "quality_gate": "INVALID",
            }

        cleaned_claim = " ".join(claim_text.split())
        search_queries = tasks._claim_gate_retrieval_queries(cleaned)
        if cleaned_claim and (
            not search_queries
            or search_queries[0].casefold() != cleaned_claim[:200].casefold()
        ):
            search_queries = [
                cleaned_claim[:200],
                *[
                    query for query in search_queries
                    if query.casefold() != cleaned_claim[:200].casefold()
                ],
            ][:3]

        if not search_queries:
            return {
                "claim": claim_text,
                "eligibility": "NO_RETRIEVAL_QUERY",
                "quality_gate": "INVALID",
            }

        retrieval_started = time.perf_counter()
        tasks._retrieve_and_ingest_tavily_queries(
            search_queries,
            claim.pk,
            stage_prefix="frozen_ab_",
            verification_run=run,
        )
        retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)

        dossier = load_reasoning_evidence_dossier_for_run(run)
        secondary_groups = filter_reasoning_evidence_dossier_by_role(
            dossier,
            VerificationEvidence.EvidenceRole.SECONDARY,
        )
        eligible_groups = tasks._eligible_evidence_assessment_groups(
            secondary_groups
        )
        eligible_items = [
            item
            for _identity_id, items in eligible_groups
            for item in items
        ]
        selected_ids = tasks._cloudflare_tail_assessment_evidence_link_ids(
            eligible_groups
        )

        frozen = {
            "item_count": len(eligible_items),
            "identity_count": len(eligible_groups),
            "identity_item_counts": [
                len(items) for _identity_id, items in eligible_groups
            ],
            "selected_item_count": len(selected_ids),
            "retrieval_ms": retrieval_ms,
            "search_queries": search_queries,
        }

        if not selected_ids:
            return {
                "claim": claim_text,
                "eligibility": "NOT_TAIL_BUDGET_ELIGIBLE",
                "quality_gate": "INVALID",
                "frozen_evidence": frozen,
            }

        baseline = _run_assessment_arm(
            cleaned_claim,
            eligible_items,
            budgeted=False,
            selected_ids=selected_ids,
        )
        budgeted = _run_assessment_arm(
            cleaned_claim,
            eligible_items,
            budgeted=True,
            selected_ids=selected_ids,
        )
        comparison = _compare_frozen_arms(
            eligible_groups,
            baseline,
            budgeted,
            selected_ids,
        )

        return {
            "claim": claim_text,
            "eligibility": "ELIGIBLE",
            "quality_gate": comparison["quality_gate"],
            "frozen_evidence": frozen,
            "baseline": {
                key: value
                for key, value in baseline.items()
                if key != "assessments"
            },
            "budgeted": {
                key: value
                for key, value in budgeted.items()
                if key != "assessments"
            },
            "comparison": comparison,
        }

    def _print_report(self, report):
        self.stdout.write("")
        self.stdout.write(f"CLAIM: {report['claim']}")
        self.stdout.write(
            f"ELIGIBILITY: {report.get('eligibility')} "
            f"QUALITY_GATE: {report.get('quality_gate')}"
        )
        frozen = report.get("frozen_evidence") or {}
        if frozen:
            self.stdout.write(
                "FROZEN EVIDENCE "
                f"items={frozen.get('item_count')} "
                f"identities={frozen.get('identity_count')} "
                f"selected={frozen.get('selected_item_count')} "
                f"retrieval_ms={frozen.get('retrieval_ms')}"
            )
        comparison = report.get("comparison")
        if comparison:
            self.stdout.write(
                "ASSESSMENT A/B "
                f"latency_delta_ms={comparison['latency_delta_ms']} "
                f"decisive_topology_match="
                f"{comparison['decisive_identity_topology_match']} "
                f"identity_coverage="
                f"{comparison['identity_coverage_preserved']} "
                f"context_changed={comparison['context_topology_changed']}"
            )
            self.stdout.write(
                "REASONS: "
                + json.dumps(comparison["review_reasons"])
            )
