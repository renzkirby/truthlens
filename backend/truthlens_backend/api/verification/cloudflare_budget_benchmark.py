"""Offline, fail-closed paired budget benchmark: NO provider calls or DB access.

Four approved claims x two completion caps x two repeats = 16 prospective
independent trials. Neither this module nor its CLI can execute inference.
Only genuine, separately captured outputs may be supplied for scoring.
"""
import hashlib
import json
import os
import re
import statistics
from pathlib import Path

from ..investigation_classifier import classification_system_prompt
from .classification_capture_plan import _private_output_directory, build_capture_plan
from .classification_contract import validate_classification_response
from .classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
    score_classification_predictions,
)
from .cloudflare_evaluation import DEFAULT_MODEL


PROFILE = "gemma4_paired_budget_v1"
EXPECTED_APPROVED_CORPUS_SHA256 = (
    "40974b32aa0d7a32ec201f85bc703c14650c3c34d5bae9dbd01bb83ac53bb6af"
)
CASE_IDS = (
    "cross_spacecraft",
    "cross_school_sport",
    "ambiguous_plan",
    "injection_civic",
)
BUDGETS = (1024, 4096)
REPETITIONS = (1, 2)
PLANNED_TRIALS = len(CASE_IDS) * len(BUDGETS) * len(REPETITIONS)
MAX_LOCAL_BYTES = 512_000
MANIFEST_NAME = "benchmark_manifest.json"
OBSERVATIONS_NAME = "benchmark_observations.json"
ERROR_CODES = frozenset({
    "EMPTY_PROVIDER_RESPONSE", "INVALID_PROVIDER_RESPONSE",
    "INVALID_CLASSIFICATION_JSON", "MISSING_API_TOKEN",
    "MISSING_OR_INVALID_ACCOUNT_ID", "HTTP_429_CAPACITY",
    "HTTP_429_ALLOCATION", "TRANSPORT_ReadTimeout",
    "TRANSPORT_ConnectTimeout", "TRANSPORT_ConnectionError",
    "OTHER_CLOUDFLARE_ERROR", "UNEXPECTED_PROVIDER_FAILURE",
    "INVALID_PROMPT", "PROMPT_TOO_LONG", "UNAPPROVED_MODEL",
})
_FINISH_REASONS = frozenset({
    "stop", "length", "tool_calls", "content_filter", "other",
})


def _canonical_bytes(data):
    return json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def build_budget_benchmark(cases):
    """Fixed fully-approved private corpus, pinned source prompt and arms."""
    if len(cases) != 32 or any(
        c["review"]["status"] != "APPROVED" for c in cases
    ):
        raise ClassificationAuditError("All 32 reference cases must be APPROVED.")
    base = build_capture_plan(
        cases, provider="cloudflare", model_id=DEFAULT_MODEL,
        limit=len(CASE_IDS), case_ids=list(CASE_IDS),
    )
    if base["corpus_sha256"] != EXPECTED_APPROVED_CORPUS_SHA256:
        raise ClassificationAuditError(
            "Approved reference fingerprint differs from the reviewed corpus."
        )
    requests = {r["case_id"]: r for r in base["requests"]}
    # Alternate token arm order within a case across repetitions. The
    # schedule is predeclared, not selected based on observed model quality.
    trials = []
    for repetition in REPETITIONS:
        for i, cid in enumerate(CASE_IDS):
            arms = BUDGETS if (i + repetition) % 2 else tuple(reversed(BUDGETS))
            for budget in arms:
                trials.append({
                    "trial_id": f"{cid}__r{repetition}__t{budget}",
                    "case_id": cid,
                    "repeat": repetition,
                    "max_completion_tokens": budget,
                    "claim_text": requests[cid]["claim_text"],
                    "claim_sha256": requests[cid]["claim_sha256"],
                })
    envelope = {
        "schema_version": 1,
        "status": "OFFLINE_DESIGN_ONLY",
        "profile": PROFILE,
        "provider": "cloudflare",
        "model_id": DEFAULT_MODEL,
        "approved_reference_count": 32,
        "corpus_sha256": base["corpus_sha256"],
        "system_prompt_sha256": _sha(classification_system_prompt().encode("utf-8")),
        "request_settings": {
            "temperature": 0.1,
            "response_format": "json_object",
            "stream": False,
            "reject_if_busy": True,
            "http_timeout_connect_sec": 3,
            "http_timeout_read_inactivity_sec": 45,
            "fallback": False,
            "retries": 0,
        },
        "planned_trials": PLANNED_TRIALS,
        "trials": trials,
    }
    envelope["manifest_sha256"] = _sha(_canonical_bytes(envelope))
    return envelope


def safe_benchmark_summary(manifest):
    return {
        "status": "OFFLINE_DESIGN_ONLY",
        "profile": PROFILE,
        "provider": "cloudflare",
        "model_id": DEFAULT_MODEL,
        "case_ids": list(CASE_IDS),
        "completion_budgets": list(BUDGETS),
        "repetitions_per_case_per_budget": len(REPETITIONS),
        "planned_trials": PLANNED_TRIALS,
        "per_budget_planned": len(CASE_IDS) * len(REPETITIONS),
        "corpus_sha256": manifest["corpus_sha256"],
        "system_prompt_sha256": manifest["system_prompt_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "provider_calls": 0,
        "db_writes": 0,
        "enforcement_approved": False,
        "live_execution_implemented": False,
    }


def _write_exclusive_text(folder, name, body):
    fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(body)


def export_private_benchmark(manifest, export_dir):
    """Create a new private folder outside checkout; empty observations only."""
    folder = _private_output_directory(export_dir)
    try:
        folder.mkdir(mode=0o700)
        _write_exclusive_text(
            folder, MANIFEST_NAME,
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        _write_exclusive_text(
            folder, OBSERVATIONS_NAME,
            json.dumps({
                "schema_version": 1, "profile": PROFILE,
                "manifest_sha256": manifest["manifest_sha256"],
                "observations": [],
            }, indent=2) + "\n",
        )
        _write_exclusive_text(
            folder, "README.txt",
            "PRIVATE, OFFLINE ONLY. 16 POTENTIAL FUTURE TRIALS, ZERO AUTHORIZED "
            "PROVIDER REQUESTS.\n"
            "Never use Cloudflare-02/03 again: they are permanently locked.\n"
            "No executable benchmark capture or live switch exists in this "
            "package. Every future trial needs fresh explicit authorization "
            "and a non-replayable capture packet.\n"
            "Do not edit raw model response strings or manufacture ABSTAIN.\n"
            "Preserve original signed-off corpus and prompt versions.\n"
            "Keep raw claim inputs, responses and credentials out of GitHub.\n",
        )
    except OSError:
        raise ClassificationAuditError(
            "Private export failed; inspect partial local folder, never overwrite."
        ) from None
    return folder


def _read_local_json(path):
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size > MAX_LOCAL_BYTES:
            raise ClassificationAuditError("Missing or oversized local benchmark file.")
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ClassificationAuditError("Invalid local benchmark JSON.") from None


def validate_benchmark_files(cases, directory):
    """Re-derive the exact immutable design and parse observation envelope."""
    folder = Path(directory).expanduser().resolve()
    if folder.is_relative_to(Path(__file__).resolve().parents[4]):
        raise ClassificationAuditError("Private benchmark folder must stay outside Git.")
    expected = build_budget_benchmark(cases)
    if _read_local_json(folder / MANIFEST_NAME) != expected:
        raise ClassificationAuditError("Private benchmark manifest mismatch.")
    data = _read_local_json(folder / OBSERVATIONS_NAME)
    if (type(data) is not dict
            or set(data) != {
                "schema_version", "profile", "manifest_sha256", "observations",
            }
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["profile"] != PROFILE
            or data["manifest_sha256"] != expected["manifest_sha256"]
            or type(data["observations"]) is not list
            or len(data["observations"]) > PLANNED_TRIALS):
        raise ClassificationAuditError("Invalid benchmark observation envelope.")
    return expected, data["observations"]


def validate_observations(manifest, observations):
    """Never accept fabricated IDs, vendor text in errors or repaired outputs."""
    trials = {trial["trial_id"]: trial for trial in manifest["trials"]}
    found = {}
    for record in observations:
        if (type(record) is not dict or set(record) != {
            "trial_id", "status", "raw_response", "error_code",
            "duration_ms", "usage",
        }):
            raise ClassificationAuditError("Invalid observation record fields.")
        key = record["trial_id"]
        if type(key) is not str or key not in trials or key in found:
            raise ClassificationAuditError("Unknown or duplicate trial ID.")
        if (type(record["duration_ms"]) is not int
                or not 0 <= record["duration_ms"] <= 3_600_000):
            raise ClassificationAuditError("Invalid observation duration.")
        usage = record["usage"]
        if (type(usage) is not dict or set(usage) != {
            "finish_reason", "prompt_tokens", "completion_tokens",
            "total_tokens", "reasoning_tokens", "reasoning_present",
        } or usage["finish_reason"] not in _FINISH_REASONS | {None}
                or type(usage["reasoning_present"]) not in {bool, type(None)}):
            raise ClassificationAuditError("Invalid sanitized usage metadata.")
        for name in (
            "prompt_tokens", "completion_tokens", "total_tokens",
            "reasoning_tokens",
        ):
            value = usage[name]
            if value is not None and (
                type(value) is not int or not 0 <= value <= 10_000_000
            ):
                raise ClassificationAuditError("Invalid reported token usage.")
        if record["status"] == "CAPTURED":
            if (type(record["raw_response"]) is not str
                    or not 1 <= len(record["raw_response"]) <= 32_768
                    or record["error_code"] is not None):
                raise ClassificationAuditError("Invalid unmodified capture record.")
        elif record["status"] == "PROVIDER_FAILED":
            code = record["error_code"]
            if (record["raw_response"] is not None
                    or type(code) is not str
                    or not (code in ERROR_CODES or re.fullmatch(
                        r"HTTP_[45][0-9]{2}", code,
                    ))):
                raise ClassificationAuditError("Invalid sanitized provider failure.")
        else:
            raise ClassificationAuditError("Only attempted outcomes may be recorded.")
        found[key] = record
    return found


def score_budget_benchmark(cases, manifest, observations):
    """Descriptive outcomes; incomplete trials never disappear from denominators."""
    found = validate_observations(manifest, observations)
    references = {c["id"]: c for c in cases}
    by_budget = {}
    per_case = {cid: {
        "planned": len(BUDGETS) * len(REPETITIONS),
        "observed": 0,
        "valid_contract": 0,
        "exact_matches": 0,
    } for cid in CASE_IDS}
    for budget in BUDGETS:
        counts = {
            "planned": len(CASE_IDS) * len(REPETITIONS),
            "observed": 0, "missing": 0,
            "provider_failed": 0, "captured": 0,
            "invalid_contract": 0, "valid_contract": 0,
            "exact_matches": 0, "wrong_domains": 0,
            "overclassified_abstentions": 0, "missed_classifications": 0,
            "potential_scope_leaks": 0, "potential_scope_exclusions": 0,
        }
        elapsed = []
        completions = []
        for trial in manifest["trials"]:
            if trial["max_completion_tokens"] != budget:
                continue
            cid, key = trial["case_id"], trial["trial_id"]
            record = found.get(key)
            if record is None:
                counts["missing"] += 1
                continue
            counts["observed"] += 1
            per_case[cid]["observed"] += 1
            elapsed.append(record["duration_ms"])
            ct = record["usage"]["completion_tokens"]
            if ct is not None:
                completions.append(ct)
            if record["status"] == "PROVIDER_FAILED":
                counts["provider_failed"] += 1
                continue
            counts["captured"] += 1
            if not validate_classification_response(
                record["raw_response"], references[cid]["claim_text"],
            ):
                counts["invalid_contract"] += 1
                continue
            counts["valid_contract"] += 1
            per_case[cid]["valid_contract"] += 1
            scored = score_classification_predictions(
                [references[cid]], {cid: record["raw_response"]},
            )
            for field in (
                "exact_matches", "wrong_domains", "overclassified_abstentions",
                "missed_classifications", "potential_scope_leaks",
                "potential_scope_exclusions",
            ):
                counts[field] += scored[field]
            per_case[cid]["exact_matches"] += scored["exact_matches"]
        counts["observed_exact_match_rate"] = (
            round(counts["exact_matches"] / counts["observed"], 4)
            if counts["observed"] else None
        )
        counts["median_observed_duration_ms"] = (
            round(statistics.median(elapsed)) if elapsed else None
        )
        counts["max_observed_completion_tokens"] = (
            max(completions) if completions else None
        )
        counts["full_arm_coverage"] = counts["missing"] == 0
        by_budget[str(budget)] = counts
    attempted = sum(s["observed"] for s in by_budget.values())
    return {
        "status": "DESCRIPTIVE_PAIRED_BUDGET_BENCHMARK_ONLY",
        "profile": PROFILE,
        "model_id": DEFAULT_MODEL,
        "planned_trials": PLANNED_TRIALS,
        "observed_trials": attempted,
        "unobserved_trials": PLANNED_TRIALS - attempted,
        "all_trials_observed": attempted == PLANNED_TRIALS,
        "complete_case_pairs": sum(
            info["observed"] == len(BUDGETS) * len(REPETITIONS)
            for info in per_case.values()
        ),
        "per_budget": by_budget,
        "per_case": per_case,
        "baseline_02_03_excluded": True,
        "statistically_generalizable": False,
        "enforcement_approved": False,
    }
