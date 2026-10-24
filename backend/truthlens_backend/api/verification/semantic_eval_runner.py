"""Batch 7 *offline-only* paired evidence-stance evaluation preparation.

Creates immutable-ish, label-blind request plans; validates SAVED responses;
exports prediction JSONL files for semantic_benchmark.compare. No model or
provider clients, network, database, credentials, or execution adapters.
Nothing here authorizes live inference or runtime verdict changes.
"""

import argparse
import ast
from collections import Counter
import hashlib
import json
import math
import re
from pathlib import Path
import sys

from .semantic_benchmark import (
    BenchmarkInputError, STANCES, _no_duplicate_keys, read_reference,
)
from .semantic_review import (
    build_blind_semantic_review_prompt, validate_blind_semantic_review,
)

ARMS = ("baseline", "candidate")
BASELINE_REQUIRED_FIELDS = frozenset({"key", "stance", "relevance_score", "directness_score"})
RESPONSE_FIELDS = frozenset({"job_id", "raw_response", "latency_ms", "input_tokens", "output_tokens",
                             "provider", "model_id", "temperature"})
RESPONSE_REQUIRED = frozenset({"job_id", "raw_response", "provider", "model_id", "temperature"})
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:/-]{1,120}\Z")
MANIFEST_VERSION = "phase3-offline-paired-v1"
MAX_JOB_BYTES = 24000
MAX_RESPONSE_LINE = 24000

# Prioritize distinct regression dimensions in a small diagnostic pilot.
# This ordering is documented, deterministic, and is not a representative
# random sample of news claims. Fallback axes sort alphabetically.
PILOT_AXIS_PRIORITY = (
    "dart", "negation", "date", "actor_swap", "intent", "conflict",
    "taglish", "prompt_injection", "quantity", "attribution",
    "filipino", "chronology",
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _strict_json(text):
    return json.loads(text, object_pairs_hook=_no_duplicate_keys,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          BenchmarkInputError("Non-finite JSON number")))


def _read_lines(path, *, max_chars):
    rows = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            if len(line) > max_chars:
                raise BenchmarkInputError(f"Oversized record at line {number}")
            try:
                data = _strict_json(line)
            except (ValueError, TypeError, RecursionError) as exc:
                raise BenchmarkInputError(f"Invalid JSON at line {number}") from exc
            if type(data) is not dict:
                raise BenchmarkInputError(f"Non-object at line {number}")
            rows.append(data)
    if not rows:
        raise BenchmarkInputError("Empty JSONL")
    return rows


def _source_baseline_prompt(source_path):
    """Read, but NEVER import/execute, the actual production baseline prompt.

    Importing evidence_assessment imports Django models and provider services;
    AST extraction avoids those side effects and prevents prompt drift.
    """
    contents = Path(source_path).read_text(encoding="utf-8")
    tree = ast.parse(contents)
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_SYSTEM_INSTRUCTIONS"
            for target in node.targets
        ):
            if not isinstance(node.value, ast.Constant) or type(node.value.value) is not str:
                raise BenchmarkInputError("Baseline prompt is not a static literal")
            values.append(node.value.value)
    if len(values) != 1 or not values[0].strip():
        raise BenchmarkInputError("Cannot locate exactly one baseline system prompt")
    for required in ("BATCH ISOLATION RULE", "relevance_score", "directness_score",
                     '"assessments"', "SUPPORTS", "REFUTES", "CONTEXT", "UNKNOWN"):
        if required not in values[0]:
            raise BenchmarkInputError("Unexpected baseline prompt contract")
    return values[0]


def _balanced_ids(references, count):
    """Prefer stance balance AND varied axes in a deterministic pilot.

    Gold labels are used *only* to select/score cases, never inserted into
    model job payloads. When axes or stances are scarce, repeat them only as
    necessary rather than silently dropping requested cases.
    """
    priority = {axis: i for i, axis in enumerate(PILOT_AXIS_PRIORITY)}
    label_order = {stance: i for i, stance in enumerate(STANCES)}
    candidates = dict(references)
    label_counts = Counter()
    axis_counts = Counter()
    selected = []
    while candidates and len(selected) < count:
        case_id = min(candidates, key=lambda key: (
            label_counts[candidates[key]["reference_stance"]],
            axis_counts[candidates[key]["axis"]],
            priority.get(candidates[key]["axis"], len(priority)),
            candidates[key]["axis"],
            label_order[candidates[key]["reference_stance"]],
            key,
        ))
        row = candidates.pop(case_id)
        selected.append(case_id)
        label_counts[row["reference_stance"]] += 1
        axis_counts[row["axis"]] += 1
    return selected


def plan(references, baseline_prompt, *, cases=8, max_requests=16,
         output_token_cap=256, max_total_output_tokens=4096,
         max_total_input_chars=120000):
    """Prepare paired jobs, not requests to be executed. Budget is PLAN ONLY."""
    ints = (cases, max_requests, output_token_cap, max_total_output_tokens,
            max_total_input_chars)
    if any(type(x) is not int or x < 1 for x in ints):
        raise BenchmarkInputError("Budget fields must be positive integers")
    if cases > len(references) or 2 * cases > max_requests:
        raise BenchmarkInputError("Case selection exceeds explicit request limit")
    if 2 * cases * output_token_cap > max_total_output_tokens:
        raise BenchmarkInputError("Output-token reservation exceeds explicit total cap")
    if not isinstance(baseline_prompt, str) or not baseline_prompt.strip():
        raise BenchmarkInputError("Invalid baseline prompt")
    jobs = []
    for case_id in _balanced_ids(references, cases):
        row = references[case_id]
        # Same assertion/evidence for both arms, no reference label or rationale.
        baseline_data = {
            "claim_text": row["assertion"],
            "evidence_items": [{"key": "item_0", "evidence_content": row["evidence"]}],
        }
        system_candidate, user_candidate = build_blind_semantic_review_prompt(
            assertion_id=case_id, assertion_text=row["assertion"],
            evidence_link_id=f"bench.{case_id}", evidence_content=row["evidence"],
        )
        for arm, system, user in (
            ("baseline", baseline_prompt,
             "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps(baseline_data, ensure_ascii=False)),
            ("candidate", system_candidate, user_candidate),
        ):
            job = {
                "job_id": f"{arm}.{case_id}", "case_id": case_id,
                "arm": arm, "system_prompt": system, "user_prompt": user,
                "max_output_tokens": output_token_cap,
            }
            if len(_json(job).encode("utf-8")) > MAX_JOB_BYTES:
                raise BenchmarkInputError("Prompt job exceeds record limit")
            jobs.append(job)
    total_input_chars = sum(len(job["system_prompt"]) + len(job["user_prompt"])
                            for job in jobs)
    if total_input_chars > max_total_input_chars:
        raise BenchmarkInputError("Planned input exceeds explicit character cap")
    return jobs, {
        "schema_version": MANIFEST_VERSION,
        "status": "OFFLINE_PLAN_ONLY_NOT_APPROVED_FOR_INFERENCE",
        "models_or_providers_selected": False,
        "provider_execution_supported": False,
        "reference_review_counts": dict(sorted(Counter(
            r["review_status"] for r in references.values()).items())),
        "case_ids": _balanced_ids(references, cases),
        "sampling_method": "stance_balanced_axis_diversified_v2",
        "selected_axis_counts": dict(sorted(Counter(
            references[k]["axis"] for k in _balanced_ids(references, cases)
        ).items())),
        "selected_cases": cases, "paired_jobs": len(jobs),
        "max_requests": max_requests,
        "output_token_cap_per_request": output_token_cap,
        "reserved_max_output_tokens": len(jobs) * output_token_cap,
        "max_total_output_tokens": max_total_output_tokens,
        "planned_input_characters": total_input_chars,
        "max_total_input_characters": max_total_input_chars,
        "baseline_system_prompt_sha256": _hash(baseline_prompt.encode("utf-8")),
        "model_settings_required_before_execution": {
            "identical_model_and_provider": True, "identical_temperature": True,
            "temperature": None, "model_id": None, "provider": None,
            "max_output_tokens": output_token_cap,
        },
        "warning": "Synthetic user-approved AI-proposed labels; not independently adjudicated. "
                   "A request plan does not enforce real provider spending limits.",
    }


def _job_bytes(jobs):
    return ("".join(_json(job) + "\n" for job in jobs)).encode("utf-8")


def write_plan(*, gold_path, baseline_source, jobs_path, manifest_path, subset_gold_path=None, cases=8,
               max_requests=16, output_token_cap=256, max_total_output_tokens=4096,
               max_total_input_chars=120000):
    references = read_reference(gold_path)
    baseline = _source_baseline_prompt(baseline_source)
    jobs, manifest = plan(references, baseline, cases=cases,
                          max_requests=max_requests, output_token_cap=output_token_cap,
                          max_total_output_tokens=max_total_output_tokens,
                          max_total_input_chars=max_total_input_chars)
    manifest["gold_sha256"] = _hash(Path(gold_path).read_bytes())
    job_bytes = _job_bytes(jobs)
    manifest["jobs_sha256"] = _hash(job_bytes)
    subset_bytes = ("".join(_json(references[k]) + "\n" for k in manifest["case_ids"])).encode("utf-8")
    manifest["subset_gold_sha256"] = _hash(subset_bytes)
    output_paths = [Path(jobs_path), Path(manifest_path)]
    if subset_gold_path is not None:
        output_paths.append(Path(subset_gold_path))
    if len({path.resolve() for path in output_paths}) != len(output_paths):
        raise BenchmarkInputError("Plan output paths must differ")
    for path in output_paths:
        if Path(path).exists():
            raise BenchmarkInputError(f"Refusing to overwrite {path}")
    with Path(jobs_path).open("xb") as out:
        out.write(job_bytes)
    with Path(manifest_path).open("x", encoding="utf-8") as out:
        json.dump(manifest, out, indent=2, sort_keys=True)
        out.write("\n")
    if subset_gold_path is not None:
        with Path(subset_gold_path).open("xb") as out:
            out.write(subset_bytes)
    return manifest


def _decode_baseline(raw):
    """Production single-evidence JSON envelope, scored only if complete."""
    try:
        parsed = _strict_json(raw)
    except (ValueError, TypeError, RecursionError):
        return None, "INVALID_JSON"
    if type(parsed) is not dict or set(parsed) != {"assessments"}:
        return None, "INVALID_BASELINE_ENVELOPE"
    items = parsed["assessments"]
    if type(items) is not list or len(items) != 1 or type(items[0]) is not dict:
        return None, "INVALID_BASELINE_ITEM_COUNT"
    entry = items[0]
    if set(entry) != BASELINE_REQUIRED_FIELDS or entry["key"] != "item_0":
        return None, "INVALID_BASELINE_SCHEMA"
    if type(entry["stance"]) is not str or entry["stance"] not in STANCES:
        return None, "INVALID_BASELINE_STANCE"
    for key in ("relevance_score", "directness_score"):
        value = entry[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            return None, "INVALID_BASELINE_SCORE"
    return entry["stance"], None


def _decode_candidate(raw, job, references):
    case_id = job["case_id"]
    row = references[case_id]
    result = validate_blind_semantic_review(
        raw, assertion_id=case_id, assertion_text=row["assertion"],
        evidence_link_id=f"bench.{case_id}", evidence_content=row["evidence"],
    )
    if result.accepted and not result.semantic_verified and not result.verdict_eligible:
        return result.proposed_stance, None
    return None, result.reason_code


def collect(*, gold_path, jobs_path, manifest_path, responses_path):
    """Read SAVED provider outputs only; never send requests or infer truth."""
    references = read_reference(gold_path)
    manifest = _strict_json(Path(manifest_path).read_text(encoding="utf-8"))
    if type(manifest) is not dict or manifest.get("schema_version") != MANIFEST_VERSION:
        raise BenchmarkInputError("Unexpected plan manifest")
    if manifest.get("gold_sha256") != _hash(Path(gold_path).read_bytes()):
        raise BenchmarkInputError("Reference fixture differs from plan")
    job_bytes = Path(jobs_path).read_bytes()
    if manifest.get("jobs_sha256") != _hash(job_bytes):
        raise BenchmarkInputError("Job plan differs from recorded manifest")
    jobs = _read_lines(jobs_path, max_chars=MAX_JOB_BYTES)
    if manifest.get("paired_jobs") != len(jobs):
        raise BenchmarkInputError("Job count mismatch")
    allowed_ids = {job.get("job_id") for job in jobs}
    if len(allowed_ids) != len(jobs) or any(
        type(job.get("case_id")) is not str
        or job["case_id"] not in references
        or job.get("arm") not in ARMS
        or job["job_id"] != f'{job["arm"]}.{job["case_id"]}'
        for job in jobs
    ):
        raise BenchmarkInputError("Invalid job identifiers")
    jobs_by_id = {job["job_id"]: job for job in jobs}
    predictions = {arm: [] for arm in ARMS}
    errors = []
    seen = set()
    expected_model_settings = None
    input_tokens_recorded = []
    output_tokens_recorded = []
    for output in _read_lines(responses_path, max_chars=MAX_RESPONSE_LINE):
        if set(output) - RESPONSE_FIELDS or not RESPONSE_REQUIRED.issubset(output):
            raise BenchmarkInputError("Response record fields invalid")
        job_id, raw = output["job_id"], output["raw_response"]
        if type(job_id) is not str or job_id not in jobs_by_id or job_id in seen:
            raise BenchmarkInputError("Unexpected or duplicate response job_id")
        if type(raw) is not str or not raw.strip() or len(raw) > 20000:
            raise BenchmarkInputError("Invalid saved raw response")
        provider, model_id, temperature = (output["provider"], output["model_id"],
                                           output["temperature"])
        if (type(provider) is not str or not IDENTIFIER.fullmatch(provider)
                or type(model_id) is not str or not IDENTIFIER.fullmatch(model_id)
                or type(temperature) not in (int, float)
                or not math.isfinite(temperature) or not 0 <= temperature <= 2):
            raise BenchmarkInputError("Invalid provider/model/settings metadata")
        settings = (provider, model_id, float(temperature))
        if expected_model_settings is None:
            expected_model_settings = settings
        elif settings != expected_model_settings:
            raise BenchmarkInputError("Provider/model/temperature differ across arms")
        seen.add(job_id)
        for key, max_value in (("latency_ms", 3600000), ("input_tokens", 1000000),
                               ("output_tokens", 1000000)):
            if key in output and (type(output[key]) not in (int, float) or
                                  not math.isfinite(output[key]) or not 0 <= output[key] <= max_value or
                                  (key in ("input_tokens", "output_tokens")
                                   and type(output[key]) is not int)):
                raise BenchmarkInputError("Invalid supplied measurement")
        if "output_tokens" in output and output["output_tokens"] > manifest["output_token_cap_per_request"]:
            raise BenchmarkInputError("Reported output tokens exceed planned per-request cap")
        if "input_tokens" in output:
            input_tokens_recorded.append(output["input_tokens"])
        if "output_tokens" in output:
            output_tokens_recorded.append(output["output_tokens"])
        if sum(output_tokens_recorded) > manifest["max_total_output_tokens"]:
            raise BenchmarkInputError("Recorded output tokens exceed planned total cap")
        job = jobs_by_id[job_id]
        if job["arm"] == "baseline":
            stance, reason = _decode_baseline(raw)
        else:
            stance, reason = _decode_candidate(raw, job, references)
        if reason:
            errors.append({"job_id": job_id, "reason": reason})
            continue
        pred = {"case_id": job["case_id"], "stance": stance}
        for key in ("latency_ms", "output_tokens"):
            if key in output:
                pred[key] = output[key]
        predictions[job["arm"]].append(pred)
    for job_id in sorted(allowed_ids - seen):
        errors.append({"job_id": job_id, "reason": "NO_RESPONSE"})
    return predictions, errors, {
        "plan_job_count": len(jobs), "responses_present": len(seen),
        "validated_predictions_by_arm": {arm: len(predictions[arm]) for arm in ARMS},
        "rejected_or_missing_jobs": len(errors),
        "provider_model_temperature_reported": {
            "provider": expected_model_settings[0],
            "model_id": expected_model_settings[1],
            "temperature": expected_model_settings[2],
        } if expected_model_settings else None,
        "input_tokens_observed_jobs": len(input_tokens_recorded),
        "input_tokens_reported_total": sum(input_tokens_recorded),
        "output_tokens_observed_jobs": len(output_tokens_recorded),
        "output_tokens_reported_total": sum(output_tokens_recorded),
        "warning": "Model proposals only; not semantic proof or human-adjudicated accuracy.",
    }


def write_collected(*, gold_path, jobs_path, manifest_path, responses_path,
                    baseline_out, candidate_out, errors_out, summary_out):
    predictions, errors, summary = collect(
        gold_path=gold_path, jobs_path=jobs_path,
        manifest_path=manifest_path, responses_path=responses_path,
    )
    if not all(predictions.values()):
        raise BenchmarkInputError("Each arm needs at least one valid saved response")
    destinations = tuple(map(Path, (baseline_out, candidate_out, errors_out, summary_out)))
    if len({p.resolve() for p in destinations}) != len(destinations):
        raise BenchmarkInputError("Output paths must be distinct")
    if any(path.exists() for path in destinations):
        raise BenchmarkInputError("Refusing to overwrite an existing report")
    data = (
        "".join(_json(p) + "\n" for p in predictions["baseline"]),
        "".join(_json(p) + "\n" for p in predictions["candidate"]),
        "".join(_json(e) + "\n" for e in errors),
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    for target, content in zip(destinations, data):
        with target.open("x", encoding="utf-8") as out:
            out.write(content)
    return summary


def _cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    maker = commands.add_parser("plan", help="Build label-blind OFFLINE request plan")
    maker.add_argument("--gold", type=Path, required=True)
    maker.add_argument("--baseline-source", type=Path, default=Path(__file__).with_name("evidence_assessment.py"))
    maker.add_argument("--jobs", type=Path, required=True)
    maker.add_argument("--manifest", type=Path, required=True)
    maker.add_argument("--subset-gold", type=Path, required=True,
                       help="Scoring-only reference subset; NEVER send to a model")
    maker.add_argument("--cases", type=int, default=8)
    maker.add_argument("--max-requests", type=int, default=16)
    maker.add_argument("--output-token-cap", type=int, default=256)
    maker.add_argument("--max-total-output-tokens", type=int, default=4096)
    maker.add_argument("--max-total-input-chars", type=int, default=120000)
    importer = commands.add_parser("collect", help="Validate saved responses; no providers")
    for flag in ("gold", "jobs", "manifest", "responses", "baseline-out", "candidate-out", "errors-out", "summary-out"):
        importer.add_argument("--" + flag, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = write_plan(gold_path=args.gold, baseline_source=args.baseline_source,
                                jobs_path=args.jobs, manifest_path=args.manifest,
                                subset_gold_path=args.subset_gold,
                                cases=args.cases, max_requests=args.max_requests,
                                output_token_cap=args.output_token_cap,
                                max_total_output_tokens=args.max_total_output_tokens,
                                max_total_input_chars=args.max_total_input_chars)
        else:
            result = write_collected(
                gold_path=args.gold, jobs_path=args.jobs, manifest_path=args.manifest,
                responses_path=args.responses, baseline_out=args.baseline_out,
                candidate_out=args.candidate_out, errors_out=args.errors_out,
                summary_out=args.summary_out,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"Offline evaluation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
