"""Development-only lossless Cloudflare assessment concurrency A/B.

Retrieve/persist evidence once, freeze the exact secondary evidence batch, then
compare:
- baseline: current production-style sequential four-item chunks
- control: repeat the same sequential chunks (A/A nondeterminism control)
- candidate: the exact same chunk prompts with at most two concurrent calls

The candidate runs the first two chunks concurrently and starts the third only
after the first wave succeeds. All arms assess every frozen evidence item. No
evidence reduction, prompt resizing, final verdict evaluation, recovery, Groq
fallback, or second retrieval is involved.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import time
from unittest.mock import patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings

from api import tasks
from api.models import Claim, VerificationEvidence
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.cloudflare_pilot import (
    ASSESSMENT_OPERATION,
    _ASSESSMENT_PREFIX,
    _assessment_chunk_plan,
    call_validated_cloudflare_assessment_chunks,
    call_validated_cloudflare_pilot,
    validate_pilot_response,
)
from api.verification.evidence_assessment import (
    EvidenceAssessment,
    _MATERIAL_SCOPE_INSTRUCTIONS,
    _SYSTEM_INSTRUCTIONS,
    _assessment_from_result,
    _enforce_deterministic_temporal_scope,
)
from api.verification.evidence_dossier import (
    filter_reasoning_evidence_dossier_by_role,
    load_reasoning_evidence_dossier_for_run,
)
from api.verification.runs import create_verification_run, start_verification_run


MAX_CLAIMS = 4
MIN_ITEMS = 9
MAX_ITEMS = 12
MAX_CONCURRENCY = 2
SCORE_SHIFT_REVIEW_THRESHOLD = 0.20
DECISIVE_STANCES = frozenset({
    VerificationEvidence.Stance.SUPPORTS,
    VerificationEvidence.Stance.REFUTES,
})


def _eligible_items(secondary_groups):
    return [
        item
        for group in secondary_groups
        for item in group.evidence
        if (
            item.stance == VerificationEvidence.Stance.UNKNOWN
            and item.relevance_score is None
            and item.directness_score is None
            and isinstance(item.content, str)
            and item.content.strip()
        )
    ]


def _material_scope_system_instructions():
    return (
        _SYSTEM_INSTRUCTIONS.rstrip()
        + "\n\n"
        + _MATERIAL_SCOPE_INSTRUCTIONS.strip()
        + "\n"
    )


def _full_prompt(claim_text, evidence_items):
    rows = [
        {
            "key": f"item_{index}",
            "evidence_content": item.content,
        }
        for index, item in enumerate(evidence_items)
    ]
    return _ASSESSMENT_PREFIX + json.dumps(
        {
            "claim_text": claim_text,
            "evidence_items": rows,
        },
        ensure_ascii=False,
    )


def _parse_assessments(
    claim_text,
    evidence_items,
    raw,
):
    unavailable = EvidenceAssessment(
        stance=VerificationEvidence.Stance.UNKNOWN,
        relevance_score=None,
        directness_score=None,
    )
    try:
        payload = json.loads(raw)
        rows = payload["assessments"]
    except (TypeError, ValueError, KeyError):
        return [unavailable for _ in evidence_items]

    by_key = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("key"), str):
            by_key.setdefault(row["key"], []).append(row)

    results = []
    for index, item in enumerate(evidence_items):
        key = f"item_{index}"
        matches = by_key.get(key, [])
        if len(matches) != 1:
            results.append(unavailable)
            continue
        assessment = _assessment_from_result(matches[0])
        assessment = _enforce_deterministic_temporal_scope(
            claim_text,
            item.content,
            assessment,
        )
        results.append(assessment)
    return results


def _aggregate_chunk_metadata(chunks):
    metadata = {"assessment_chunks_attempted": len(chunks)}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "reasoning_tokens",
    ):
        values = [chunk.get(key) for chunk in chunks]
        if values and all(
            type(value) is int and 0 <= value <= 10_000_000
            for value in values
        ):
            metadata[key] = sum(values)
    return metadata


def _run_baseline_arm(system_instructions, user_prompt, claim_text, evidence_items):
    metadata = {}
    started = time.perf_counter()
    try:
        raw = call_validated_cloudflare_assessment_chunks(
            system_instructions,
            user_prompt,
            audit_metadata=metadata,
        )
    except CloudflareEvaluationError as exc:
        return {
            "success": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "error_code": str(exc).split(" ", 1)[0],
            "chunks_attempted": metadata.get("assessment_chunks_attempted"),
            "metadata": metadata,
            "assessments": [],
        }

    return {
        "success": True,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "error_code": "",
        "chunks_attempted": metadata.get("assessment_chunks_attempted"),
        "metadata": metadata,
        "assessments": _parse_assessments(
            claim_text,
            evidence_items,
            raw,
        ),
    }



def _run_control_arm(system_instructions, user_prompt, claim_text, evidence_items):
    """Repeat the production-style four-item chunk path as an A/A control."""
    return _run_baseline_arm(
        system_instructions,
        user_prompt,
        claim_text,
        evidence_items,
    )

def _run_candidate_arm(
    system_instructions,
    user_prompt,
    claim_text,
    evidence_items,
):
    """Run the exact production chunk prompts with bounded two-call concurrency."""
    try:
        chunk_prompts, ordered_keys = _assessment_chunk_plan(
            system_instructions,
            user_prompt,
        )
    except CloudflareEvaluationError as exc:
        return {
            "success": False,
            "duration_ms": 0,
            "error_code": str(exc).split(" ", 1)[0],
            "chunks_attempted": 0,
            "metadata": {},
            "assessments": [],
        }

    if len(chunk_prompts) != 3:
        return {
            "success": False,
            "duration_ms": 0,
            "error_code": "CANDIDATE_NOT_THREE_CHUNKS",
            "chunks_attempted": 0,
            "metadata": {},
            "assessments": [],
        }

    started = time.perf_counter()
    completed = {}
    chunk_metadata = [{}, {}]
    first_wave_results = {}
    first_wave_error = None

    def run_chunk(index):
        raw = call_validated_cloudflare_pilot(
            system_instructions,
            chunk_prompts[index],
            operation=ASSESSMENT_OPERATION,
            audit_metadata=chunk_metadata[index],
        )
        return json.loads(raw)["assessments"]

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        futures = {
            executor.submit(run_chunk, index): index
            for index in (0, 1)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                first_wave_results[index] = future.result()
            except (
                CloudflareEvaluationError,
                TypeError,
                ValueError,
                KeyError,
            ) as exc:
                if first_wave_error is None:
                    first_wave_error = exc

    if first_wave_error is not None:
        code = (
            str(first_wave_error).split(" ", 1)[0]
            if isinstance(first_wave_error, CloudflareEvaluationError)
            else type(first_wave_error).__name__
        )
        metadata = _aggregate_chunk_metadata(chunk_metadata)
        metadata["max_concurrency"] = MAX_CONCURRENCY
        metadata["waves_attempted"] = 1
        return {
            "success": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "error_code": code,
            "chunks_attempted": 2,
            "metadata": metadata,
            "assessments": [],
        }

    for index in (0, 1):
        for row in first_wave_results[index]:
            key = row.get("key") if isinstance(row, dict) else None
            if key in completed:
                return {
                    "success": False,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "error_code": "INVALID_ASSESSMENT_JSON",
                    "chunks_attempted": 2,
                    "metadata": {
                        **_aggregate_chunk_metadata(chunk_metadata),
                        "max_concurrency": MAX_CONCURRENCY,
                        "waves_attempted": 1,
                    },
                    "assessments": [],
                }
            completed[key] = row

    chunk_metadata.append({})
    try:
        raw = call_validated_cloudflare_pilot(
            system_instructions,
            chunk_prompts[2],
            operation=ASSESSMENT_OPERATION,
            audit_metadata=chunk_metadata[2],
        )
        final_rows = json.loads(raw)["assessments"]
        for row in final_rows:
            key = row.get("key") if isinstance(row, dict) else None
            if key in completed:
                raise CloudflareEvaluationError("INVALID_ASSESSMENT_JSON")
            completed[key] = row
    except (CloudflareEvaluationError, TypeError, ValueError, KeyError) as exc:
        code = (
            str(exc).split(" ", 1)[0]
            if isinstance(exc, CloudflareEvaluationError)
            else type(exc).__name__
        )
        metadata = _aggregate_chunk_metadata(chunk_metadata)
        metadata["max_concurrency"] = MAX_CONCURRENCY
        metadata["waves_attempted"] = 2
        return {
            "success": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "error_code": code,
            "chunks_attempted": 3,
            "metadata": metadata,
            "assessments": [],
        }

    if set(completed) != set(ordered_keys):
        metadata = _aggregate_chunk_metadata(chunk_metadata)
        metadata["max_concurrency"] = MAX_CONCURRENCY
        metadata["waves_attempted"] = 2
        return {
            "success": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "error_code": "INVALID_ASSESSMENT_JSON",
            "chunks_attempted": 3,
            "metadata": metadata,
            "assessments": [],
        }

    combined = json.dumps(
        {"assessments": [completed[key] for key in ordered_keys]},
        ensure_ascii=False,
    )
    if not validate_pilot_response(
        ASSESSMENT_OPERATION,
        combined,
        user_prompt,
    ):
        metadata = _aggregate_chunk_metadata(chunk_metadata)
        metadata["max_concurrency"] = MAX_CONCURRENCY
        metadata["waves_attempted"] = 2
        return {
            "success": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "error_code": "INVALID_ASSESSMENT_JSON",
            "chunks_attempted": 3,
            "metadata": metadata,
            "assessments": [],
        }

    metadata = _aggregate_chunk_metadata(chunk_metadata)
    metadata["max_concurrency"] = MAX_CONCURRENCY
    metadata["waves_attempted"] = 2
    return {
        "success": True,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "error_code": "",
        "chunks_attempted": 3,
        "metadata": metadata,
        "assessments": _parse_assessments(
            claim_text,
            evidence_items,
            combined,
        ),
    }

def _is_http_429(arm):
    return (
        not arm.get("success")
        and isinstance(arm.get("error_code"), str)
        and arm["error_code"].startswith("HTTP_429")
    )


def _identity_groups(secondary_groups, evidence_items):
    allowed_ids = {item.evidence_link_id for item in evidence_items}
    groups = []
    for group in secondary_groups:
        members = [
            item for item in group.evidence
            if item.evidence_link_id in allowed_ids
        ]
        if members:
            groups.append((group.identity_id, members))
    return groups


def _assessment_available(value):
    return not (
        value.stance == VerificationEvidence.Stance.UNKNOWN
        and value.relevance_score is None
        and value.directness_score is None
    )


def _compare_arms(
    identity_groups,
    evidence_items,
    baseline,
    candidate,
    *,
    expected_candidate_chunks=3,
    candidate_label="CANDIDATE",
):
    reasons = []
    normalized_label = str(candidate_label or "CANDIDATE").upper()
    if not baseline["success"]:
        reasons.append("BASELINE_NOT_SUCCESSFUL")
    if baseline.get("chunks_attempted") != 3:
        reasons.append("BASELINE_NOT_THREE_CHUNKS")
    if not candidate["success"]:
        reasons.append(f"{normalized_label}_NOT_SUCCESSFUL")
    if candidate.get("chunks_attempted") != expected_candidate_chunks:
        reasons.append(
            f"{normalized_label}_NOT_{expected_candidate_chunks}_CHUNKS"
        )

    if reasons:
        return {
            "quality_gate": "INVALID",
            "review_reasons": reasons,
            "latency_delta_ms": (
                candidate.get("duration_ms", 0)
                - baseline.get("duration_ms", 0)
            ),
        }

    baseline_assessments = baseline["assessments"]
    candidate_assessments = candidate["assessments"]
    if (
        len(baseline_assessments) != len(evidence_items)
        or len(candidate_assessments) != len(evidence_items)
    ):
        return {
            "quality_gate": "INVALID",
            "review_reasons": ["ASSESSMENT_COUNT_MISMATCH"],
            "latency_delta_ms": candidate["duration_ms"] - baseline["duration_ms"],
        }

    item_rows = []
    baseline_by_id = {}
    candidate_by_id = {}
    max_relevance_delta = 0.0
    max_directness_delta = 0.0
    all_scores_available = True

    for index, (item, left, right) in enumerate(zip(
        evidence_items,
        baseline_assessments,
        candidate_assessments,
    )):
        left_available = _assessment_available(left)
        right_available = _assessment_available(right)
        stance_match = (
            left_available
            and right_available
            and left.stance == right.stance
        )
        if not left_available or not right_available:
            reasons.append("ITEM_ASSESSMENT_UNAVAILABLE")
        elif not stance_match:
            reasons.append("ITEM_STANCE_CHANGED")

        relevance_delta = None
        directness_delta = None
        if (
            left.relevance_score is not None
            and right.relevance_score is not None
        ):
            relevance_delta = abs(
                right.relevance_score - left.relevance_score
            )
            max_relevance_delta = max(
                max_relevance_delta,
                relevance_delta,
            )
        else:
            all_scores_available = False

        if (
            left.directness_score is not None
            and right.directness_score is not None
        ):
            directness_delta = abs(
                right.directness_score - left.directness_score
            )
            max_directness_delta = max(
                max_directness_delta,
                directness_delta,
            )
        else:
            all_scores_available = False

        baseline_by_id[item.evidence_link_id] = left
        candidate_by_id[item.evidence_link_id] = right
        item_rows.append({
            "item_index": index,
            "evidence_link_id": str(item.evidence_link_id),
            "baseline": {
                "stance": left.stance,
                "relevance_score": left.relevance_score,
                "directness_score": left.directness_score,
            },
            "candidate": {
                "stance": right.stance,
                "relevance_score": right.relevance_score,
                "directness_score": right.directness_score,
            },
            "stance_match": stance_match,
            "relevance_delta": relevance_delta,
            "directness_delta": directness_delta,
        })

    if (
        round(max_relevance_delta, 4) > SCORE_SHIFT_REVIEW_THRESHOLD
        or round(max_directness_delta, 4) > SCORE_SHIFT_REVIEW_THRESHOLD
    ):
        reasons.append("ITEM_SCORE_SHIFT_GT_0_20")

    identity_rows = []
    for identity_index, (identity_id, members) in enumerate(
        identity_groups,
        start=1,
    ):
        baseline_stances = {
            baseline_by_id[item.evidence_link_id].stance
            for item in members
            if _assessment_available(baseline_by_id[item.evidence_link_id])
        }
        candidate_stances = {
            candidate_by_id[item.evidence_link_id].stance
            for item in members
            if _assessment_available(candidate_by_id[item.evidence_link_id])
        }
        baseline_decisive = sorted(
            baseline_stances & DECISIVE_STANCES
        )
        candidate_decisive = sorted(
            candidate_stances & DECISIVE_STANCES
        )
        decisive_match = baseline_decisive == candidate_decisive
        if not decisive_match:
            reasons.append("DECISIVE_IDENTITY_TOPOLOGY_CHANGED")
        identity_rows.append({
            "identity_index": identity_index,
            "identity_id": str(identity_id),
            "item_count": len(members),
            "baseline_stances": sorted(baseline_stances),
            "candidate_stances": sorted(candidate_stances),
            "baseline_decisive_stances": baseline_decisive,
            "candidate_decisive_stances": candidate_decisive,
            "decisive_match": decisive_match,
        })

    reasons = sorted(set(reasons))
    gate = "PASS" if not reasons else "REVIEW"
    latency_delta_ms = candidate["duration_ms"] - baseline["duration_ms"]
    latency_change_pct = (
        round((latency_delta_ms / baseline["duration_ms"]) * 100, 1)
        if baseline["duration_ms"] > 0
        else None
    )

    return {
        "quality_gate": gate,
        "review_reasons": reasons,
        "all_items_assessed": all(
            _assessment_available(value)
            for value in baseline_assessments + candidate_assessments
        ),
        "all_item_stances_match": all(
            row["stance_match"] for row in item_rows
        ),
        "decisive_identity_topology_match": all(
            row["decisive_match"] for row in identity_rows
        ),
        "max_relevance_delta": (
            round(max_relevance_delta, 4)
            if all_scores_available else None
        ),
        "max_directness_delta": (
            round(max_directness_delta, 4)
            if all_scores_available else None
        ),
        "latency_delta_ms": latency_delta_ms,
        "latency_change_pct": latency_change_pct,
        "items": item_rows,
        "identities": identity_rows,
    }


def _causal_summary(control_comparison, candidate_comparison):
    """Classify whether observed drift can be attributed to concurrent execution."""
    if (
        control_comparison.get("quality_gate") == "INVALID"
        or candidate_comparison.get("quality_gate") == "INVALID"
    ):
        return {
            "quality_gate": "INVALID",
            "causal_interpretation": "INVALID_COMPARISON",
        }

    if control_comparison.get("quality_gate") != "PASS":
        return {
            "quality_gate": "INCONCLUSIVE",
            "causal_interpretation": "MODEL_NONDETERMINISM_PRESENT",
        }

    if candidate_comparison.get("quality_gate") != "PASS":
        return {
            "quality_gate": "REVIEW",
            "causal_interpretation": "CONCURRENCY_EFFECT_PLAUSIBLE",
        }

    return {
        "quality_gate": "PASS",
        "causal_interpretation": "NO_SEMANTIC_DRIFT_DETECTED",
    }


class Command(BaseCommand):
    help = (
        "Development-only lossless Cloudflare assessment A/B comparing "
        "sequential four-item chunks with the exact same chunks at max "
        "concurrency two."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--claim",
            dest="claims",
            action="append",
            help="TEXT claim. Repeat for up to four claims.",
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
                "Cloudflare chunk-size A/B is development-only."
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
        for claim_text in claims:
            report = self._run_rollback_isolated_claim(claim_text)
            reports.append(report)
            if report.get("quality_gate") == "BLOCKED":
                break

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

        # Keep claim normalization/retrieval preparation off Cloudflare so the
        # only Workers AI traffic in this experiment is the two assessment arms.
        with (
            override_settings(INVESTIGATION_CLASSIFICATION_MODE="off"),
            patch.dict(
                os.environ,
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
                    "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0",
                    "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "0",
                    "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "0",
                },
                clear=False,
            ),
        ):
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
                    query
                    for query in search_queries
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
            stage_prefix="lossless_chunk_ab_",
            verification_run=run,
        )
        retrieval_ms = int(
            (time.perf_counter() - retrieval_started) * 1000
        )

        dossier = load_reasoning_evidence_dossier_for_run(run)
        secondary_groups = filter_reasoning_evidence_dossier_by_role(
            dossier,
            VerificationEvidence.EvidenceRole.SECONDARY,
        )
        evidence_items = _eligible_items(secondary_groups)
        frozen = {
            "item_count": len(evidence_items),
            "identity_count": len(_identity_groups(
                secondary_groups,
                evidence_items,
            )),
            "retrieval_ms": retrieval_ms,
            "search_queries": search_queries,
        }

        if not MIN_ITEMS <= len(evidence_items) <= MAX_ITEMS:
            return {
                "claim": claim_text,
                "eligibility": "NOT_THREE_CHUNK_ELIGIBLE",
                "quality_gate": "SKIPPED",
                "frozen_evidence": frozen,
            }

        system_instructions = _material_scope_system_instructions()
        user_prompt = _full_prompt(cleaned_claim, evidence_items)

        try:
            baseline_plan, _ = _assessment_chunk_plan(
                system_instructions,
                user_prompt,
            )
            candidate_plan, _ = _assessment_chunk_plan(
                system_instructions,
                user_prompt,
            )
        except (CloudflareEvaluationError, ValueError) as exc:
            return {
                "claim": claim_text,
                "eligibility": "CHUNK_PLAN_UNAVAILABLE",
                "quality_gate": "SKIPPED",
                "plan_error": str(exc).split(" ", 1)[0],
                "frozen_evidence": frozen,
            }

        frozen["baseline_planned_chunks"] = len(baseline_plan)
        frozen["candidate_planned_chunks"] = len(candidate_plan)
        if len(baseline_plan) != 3 or candidate_plan != baseline_plan:
            return {
                "claim": claim_text,
                "eligibility": "NOT_THREE_TO_TWO_CHUNK_ELIGIBLE",
                "quality_gate": "SKIPPED",
                "frozen_evidence": frozen,
            }

        baseline = _run_baseline_arm(
            system_instructions,
            user_prompt,
            cleaned_claim,
            evidence_items,
        )
        if _is_http_429(baseline):
            return {
                "claim": claim_text,
                "eligibility": "ELIGIBLE",
                "quality_gate": "BLOCKED",
                "blocked_reason": "CLOUDFLARE_HTTP_429",
                "frozen_evidence": frozen,
                "baseline": {
                    key: value
                    for key, value in baseline.items()
                    if key != "assessments"
                },
            }

        control = _run_control_arm(
            system_instructions,
            user_prompt,
            cleaned_claim,
            evidence_items,
        )
        if _is_http_429(control):
            return {
                "claim": claim_text,
                "eligibility": "ELIGIBLE",
                "quality_gate": "BLOCKED",
                "blocked_reason": "CLOUDFLARE_HTTP_429",
                "frozen_evidence": frozen,
                "baseline": {
                    key: value
                    for key, value in baseline.items()
                    if key != "assessments"
                },
                "control": {
                    key: value
                    for key, value in control.items()
                    if key != "assessments"
                },
            }

        candidate = _run_candidate_arm(
            system_instructions,
            user_prompt,
            cleaned_claim,
            evidence_items,
        )
        if _is_http_429(candidate):
            return {
                "claim": claim_text,
                "eligibility": "ELIGIBLE",
                "quality_gate": "BLOCKED",
                "blocked_reason": "CLOUDFLARE_HTTP_429",
                "frozen_evidence": frozen,
                "baseline": {
                    key: value
                    for key, value in baseline.items()
                    if key != "assessments"
                },
                "control": {
                    key: value
                    for key, value in control.items()
                    if key != "assessments"
                },
                "candidate": {
                    key: value
                    for key, value in candidate.items()
                    if key != "assessments"
                },
            }

        identity_groups = _identity_groups(
            secondary_groups,
            evidence_items,
        )
        control_comparison = _compare_arms(
            identity_groups,
            evidence_items,
            baseline,
            control,
            expected_candidate_chunks=3,
            candidate_label="CONTROL",
        )
        comparison = _compare_arms(
            identity_groups,
            evidence_items,
            baseline,
            candidate,
        )
        causal = _causal_summary(
            control_comparison,
            comparison,
        )

        return {
            "claim": claim_text,
            "eligibility": "ELIGIBLE",
            "quality_gate": causal["quality_gate"],
            "causal_interpretation": causal["causal_interpretation"],
            "frozen_evidence": frozen,
            "baseline": {
                key: value
                for key, value in baseline.items()
                if key != "assessments"
            },
            "control": {
                key: value
                for key, value in control.items()
                if key != "assessments"
            },
            "candidate": {
                key: value
                for key, value in candidate.items()
                if key != "assessments"
            },
            "control_comparison": control_comparison,
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
                f"baseline_chunks={frozen.get('baseline_planned_chunks')} "
                f"candidate_chunks={frozen.get('candidate_planned_chunks')} "
                f"max_concurrency={MAX_CONCURRENCY}"
            )
        comparison = report.get("comparison")
        if comparison:
            control_comparison = report.get("control_comparison") or {}
            self.stdout.write(
                "A/A CONTROL "
                f"quality_gate={control_comparison.get('quality_gate')} "
                f"stances_match={control_comparison.get('all_item_stances_match')} "
                f"decisive_topology_match="
                f"{control_comparison.get('decisive_identity_topology_match')}"
            )
            self.stdout.write(
                "LOSSLESS CONCURRENCY A/B "
                f"latency_delta_ms={comparison['latency_delta_ms']} "
                f"stances_match={comparison['all_item_stances_match']} "
                f"decisive_topology_match="
                f"{comparison['decisive_identity_topology_match']}"
            )
            self.stdout.write(
                "CAUSAL_INTERPRETATION: "
                + str(report.get("causal_interpretation"))
            )
            self.stdout.write(
                "REASONS: "
                + json.dumps(comparison["review_reasons"])
            )
