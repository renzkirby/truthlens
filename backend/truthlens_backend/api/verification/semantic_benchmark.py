"""Offline Phase 3 claim/evidence stance benchmark (NOT a verification gate).

Uses reference labels and pre-collected prediction JSONL files. It never imports
provider clients, makes network calls, touches the database, or certifies claims.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
import argparse
import json
import math
from pathlib import Path
import sys

STANCES = ("SUPPORTS", "REFUTES", "CONTEXT", "UNKNOWN")
REFERENCE_KEYS = frozenset({
    "case_id", "axis", "assertion", "evidence", "reference_stance",
    "rationale", "source_kind", "review_status", "reviewer_id",
    "reviewed_on", "source_url",
})
PREDICTION_REQUIRED = frozenset({"case_id", "stance"})
PREDICTION_OPTIONAL = frozenset({"latency_ms", "output_tokens"})
MAX_RECORD_LENGTH = 16000


class BenchmarkInputError(ValueError):
    """The benchmark cannot safely process the supplied inputs."""


def _no_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise BenchmarkInputError("Duplicate JSON object key")
        obj[key] = value
    return obj


def _read_jsonl(path):
    """Strict read: reject ambiguous, truncated, duplicate-key or oversized JSON."""
    output = []
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            if len(line) > MAX_RECORD_LENGTH:
                raise BenchmarkInputError(f"{path}:{line_number}: record too long")
            try:
                obj = json.loads(line, object_pairs_hook=_no_duplicate_keys,
                                 parse_constant=lambda x: (_ for _ in ()).throw(
                                     BenchmarkInputError("Non-finite JSON number")
                                 ))
            except (ValueError, TypeError, RecursionError) as exc:
                raise BenchmarkInputError(
                    f"{path}:{line_number}: invalid JSON ({exc})"
                ) from exc
            if not isinstance(obj, dict):
                raise BenchmarkInputError(f"{path}:{line_number}: expected object")
            output.append(obj)
    if not output:
        raise BenchmarkInputError(f"{path}: no records")
    return output


def _nonempty_short(value, *, limit=2400):
    return type(value) is str and 0 < len(value.strip()) <= limit


def read_reference(path):
    cases = {}
    for obj in _read_jsonl(path):
        if set(obj) != REFERENCE_KEYS:
            raise BenchmarkInputError("Reference fixture fields do not match contract")
        case_id = obj["case_id"]
        if not _nonempty_short(case_id, limit=80) or not all(
            char.isalnum() or char in "_-" for char in case_id
        ):
            raise BenchmarkInputError("Invalid case_id")
        if case_id in cases:
            raise BenchmarkInputError(f"Duplicate case_id: {case_id}")
        if not all(_nonempty_short(obj[field], limit=3000) for field in (
            "axis", "assertion", "evidence", "rationale", "source_kind"
        )):
            raise BenchmarkInputError(f"Invalid text in {case_id}")
        if obj["reference_stance"] not in STANCES:
            raise BenchmarkInputError(f"Invalid reference stance in {case_id}")
        if obj["source_kind"] not in {"SYNTHETIC", "SOURCE_DERIVED"}:
            raise BenchmarkInputError(f"Invalid source kind in {case_id}")
        if type(obj["source_url"]) not in (str, type(None)):
            raise BenchmarkInputError(f"Invalid source URL in {case_id}")
        if obj["source_kind"] == "SOURCE_DERIVED" and not (
            _nonempty_short(obj["source_url"], limit=1200)
            and obj["source_url"].startswith("https://")
        ):
            raise BenchmarkInputError(f"Source-derived case missing URL: {case_id}")
        status = obj["review_status"]
        if status == "DRAFT_UNREVIEWED":
            if obj["reviewer_id"] is not None or obj["reviewed_on"] is not None:
                raise BenchmarkInputError(f"Draft must not claim review: {case_id}")
        elif status == "INDEPENDENTLY_ADJUDICATED":
            if not (_nonempty_short(obj["reviewer_id"], limit=120)
                    and _nonempty_short(obj["reviewed_on"], limit=40)):
                raise BenchmarkInputError(f"Adjudication metadata missing: {case_id}")
        else:
            raise BenchmarkInputError(f"Invalid review status: {case_id}")
        cases[case_id] = obj
    return cases


def read_predictions(path, reference_ids):
    predictions = {}
    for obj in _read_jsonl(path):
        fields = set(obj)
        if not PREDICTION_REQUIRED.issubset(fields) or not fields.issubset(
            PREDICTION_REQUIRED | PREDICTION_OPTIONAL
        ):
            raise BenchmarkInputError("Invalid prediction fields")
        case_id = obj["case_id"]
        if type(case_id) is not str or case_id not in reference_ids:
            raise BenchmarkInputError(f"Prediction refers to unknown case: {case_id}")
        if case_id in predictions:
            raise BenchmarkInputError(f"Duplicate prediction case: {case_id}")
        if obj["stance"] not in STANCES:
            raise BenchmarkInputError(f"Invalid prediction stance: {case_id}")
        if "latency_ms" in obj and (
            type(obj["latency_ms"]) not in (float, int)
            or not math.isfinite(obj["latency_ms"])
            or not 0 <= obj["latency_ms"] <= 3600000
        ):
            raise BenchmarkInputError(f"Invalid latency: {case_id}")
        if "output_tokens" in obj and (
            type(obj["output_tokens"]) is not int
            or not 0 <= obj["output_tokens"] <= 1000000
        ):
            raise BenchmarkInputError(f"Invalid output_tokens: {case_id}")
        predictions[case_id] = obj
    return predictions


def _ratio(a, b):
    return round(a / b, 6) if b else None


def _mean(values):
    return round(sum(values) / len(values), 3) if values else None


def score(reference, predictions):
    """Count *missing* predictions as wrong for all-case accuracy.

    Scores are diagnostic only. An adjudicated reference set is necessary but
    not sufficient to claim factual or real-world verification accuracy.
    """
    gold_ids = set(reference)
    if any(k not in gold_ids for k in predictions):
        raise BenchmarkInputError("Predictions reference unknown cases")
    total = len(reference)
    observed = len(predictions)
    correct = sum(
        reference[case_id]["reference_stance"] == row["stance"]
        for case_id, row in predictions.items()
    )
    labels = list(STANCES) + ["MISSING"]
    confusion = {g: {p: 0 for p in labels} for g in STANCES}
    for case_id, obj in reference.items():
        gold = obj["reference_stance"]
        prediction = predictions.get(case_id)
        confusion[gold][prediction["stance"] if prediction else "MISSING"] += 1

    per_class = {}
    for stance in STANCES:
        tp = confusion[stance][stance]
        predicted = sum(confusion[g][stance] for g in STANCES)
        support = sum(confusion[stance].values())
        precision = _ratio(tp, predicted)
        recall = _ratio(tp, support)
        f1 = (round(2 * tp / (predicted + support), 6)
              if (predicted + support) else None)
        per_class[stance] = {
            "support": support, "predicted": predicted,
            "precision": precision, "recall": recall, "f1": f1,
        }
    macro_f1 = round(sum(row["f1"] for row in per_class.values()) / 4, 6)
    by_axis = {}
    for axis in sorted({c["axis"] for c in reference.values()}):
        ids = [k for k, c in reference.items() if c["axis"] == axis]
        axis_correct = sum(
            k in predictions
            and predictions[k]["stance"] == reference[k]["reference_stance"]
            for k in ids
        )
        by_axis[axis] = {"cases": len(ids), "correct": axis_correct,
                         "accuracy": _ratio(axis_correct, len(ids))}

    false_support = sum(confusion[g]["SUPPORTS"] for g in STANCES if g != "SUPPORTS")
    false_refute = sum(confusion[g]["REFUTES"] for g in STANCES if g != "REFUTES")
    over_abstain = sum(confusion[g]["UNKNOWN"] for g in STANCES if g != "UNKNOWN")
    latency = [obj["latency_ms"] for obj in predictions.values() if "latency_ms" in obj]
    tokens = [obj["output_tokens"] for obj in predictions.values() if "output_tokens" in obj]
    return {
        "total_cases": total, "prediction_coverage": _ratio(observed, total),
        "predicted_cases": observed, "missing_cases": total - observed,
        "all_case_accuracy": _ratio(correct, total),
        "observed_accuracy": _ratio(correct, observed),
        "macro_f1_missing_counted_as_errors": macro_f1,
        "false_support_count": false_support, "false_refute_count": false_refute,
        "over_abstain_count": over_abstain,
        "predicted_unknown_count": sum(confusion[g]["UNKNOWN"] for g in STANCES),
        "confusion": confusion, "per_class": per_class, "by_axis": by_axis,
        "mean_latency_ms_reported": _mean(latency),
        "latency_observed_cases": len(latency),
        "mean_output_tokens_reported": _mean(tokens),
        "tokens_observed_cases": len(tokens),
    }


def compare(reference, baseline, candidate):
    """Report diagnostic deltas, not a claim of independent human validation."""
    base = score(reference, baseline)
    new = score(reference, candidate)
    fixed, regressed = [], []
    for k, gold in reference.items():
        if k not in baseline or k not in candidate:
            continue
        original_right = baseline[k]["stance"] == gold["reference_stance"]
        candidate_right = candidate[k]["stance"] == gold["reference_stance"]
        if candidate_right and not original_right:
            fixed.append(k)
        if original_right and not candidate_right:
            regressed.append(k)
    counts = Counter(v["review_status"] for v in reference.values())
    return {
        "benchmark_kind": "OFFLINE_EVIDENCE_STANCE_COMPARISON",
        "review_status": (
            "INDEPENDENTLY_ADJUDICATED_REFERENCES" if not counts.get("DRAFT_UNREVIEWED")
            else "PROVISIONAL_DRAFT_REFERENCES_NOT_HUMAN_VERIFIED"
        ),
        "reference_review_counts": dict(sorted(counts.items())),
        "warning": (
            "Structural scoring does not certify semantic correctness, provenance, "
            "source reliability, claim-level verdicts, or production accuracy."
        ),
        "baseline": base, "candidate": new,
        "delta_all_case_accuracy": round(new["all_case_accuracy"] - base["all_case_accuracy"], 6),
        "delta_macro_f1": round(new["macro_f1_missing_counted_as_errors"] - base["macro_f1_missing_counted_as_errors"], 6),
        "candidate_fixes": sorted(fixed), "candidate_regressions": sorted(regressed),
        "paired_evaluated_cases": sum(k in baseline and k in candidate for k in reference),
    }


def _cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate draft/adjudicated reference JSONL")
    validate.add_argument("--gold", type=Path, required=True)
    run = commands.add_parser("compare", help="Score already collected predictions; no AI calls")
    run.add_argument("--gold", type=Path, required=True)
    run.add_argument("--baseline", type=Path, required=True)
    run.add_argument("--candidate", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        reference = read_reference(args.gold)
        counts = Counter(x["review_status"] for x in reference.values())
        if args.command == "validate":
            print(json.dumps({"cases": len(reference),
                              "review_counts": dict(sorted(counts.items())),
                              "not_ready_for_accuracy_claims": bool(counts.get("DRAFT_UNREVIEWED"))},
                             indent=2, sort_keys=True))
            return 0
        baseline = read_predictions(args.baseline, set(reference))
        candidate = read_predictions(args.candidate, set(reference))
        result = compare(reference, baseline, candidate)
        # Do not overwrite a report inadvertently; atomic/secure sinks are not needed
        # for these synthetic benchmark metrics but collision avoidance matters.
        with args.report.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, sort_keys=True)
            output.write("\n")
        print(json.dumps({"report": str(args.report), "cases": len(reference),
                          "review_status": result["review_status"],
                          "baseline_all_case_accuracy": result["baseline"]["all_case_accuracy"],
                          "candidate_all_case_accuracy": result["candidate"]["all_case_accuracy"]},
                         indent=2, sort_keys=True))
        return 0
    except (OSError, BenchmarkInputError) as exc:
        print(f"Benchmark input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
