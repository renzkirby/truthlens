"""Batch 7 paired evaluation planning and saved-response import: OFFLINE ONLY."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from api.verification.semantic_benchmark import BenchmarkInputError, compare, read_predictions, read_reference
from api.verification.semantic_eval_runner import (
    _balanced_ids, _decode_baseline, _source_baseline_prompt,
    collect, plan, write_collected, write_plan,
)

BASELINE = '''BATCH ISOLATION RULE: each item independently.
SUPPORTS REFUTES CONTEXT UNKNOWN. Return "assessments" with relevance_score and directness_score.'''


def _case(case_id, stance):
    return {
        "case_id": case_id, "axis": "sample", "assertion": "The bridge opened in 2024.",
        "evidence": "Official records confirm the bridge opened in 2024.",
        "reference_stance": stance, "rationale": "User-approved proposed classification.",
        "review_status": "USER_APPROVED_AI_PROPOSED", "reviewer_id": "USER_APPROVAL",
        "reviewed_on": "2026-10-24", "source_kind": "SYNTHETIC", "source_url": None,
    }


class OfflinePairedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.gold = self.root / "gold.jsonl"
        self.source = self.root / "evidence_assessment.py"
        self.jobs = self.root / "jobs.jsonl"
        self.manifest = self.root / "manifest.json"
        self.subset_gold = self.root / "pilot_gold.jsonl"
        self.responses = self.root / "responses.jsonl"
        self.baseline_out = self.root / "baseline.jsonl"
        self.candidate_out = self.root / "candidate.jsonl"
        self.errors_out = self.root / "errors.jsonl"
        self.summary_out = self.root / "summary.json"
        self.rows = {
            "s1": _case("s1", "SUPPORTS"),
            "r1": _case("r1", "REFUTES"),
            "c1": _case("c1", "CONTEXT"),
            "u1": _case("u1", "UNKNOWN"),
        }
        self.gold.write_text("".join(json.dumps(row) + "\n" for row in self.rows.values()), encoding="utf-8")
        self.source.write_text("_SYSTEM_INSTRUCTIONS = " + repr(BASELINE) + "\n", encoding="utf-8")

    def _plan(self, **options):
        return write_plan(gold_path=self.gold, baseline_source=self.source,
                          jobs_path=self.jobs, manifest_path=self.manifest,
                          subset_gold_path=self.subset_gold, cases=4, **options)

    def _save_responses(self, *, tamper=False, missing=None, invalid=None):
        jobs = [json.loads(line) for line in self.jobs.read_text(encoding="utf-8").splitlines()]
        output = []
        for job in jobs:
            if job["job_id"] == missing:
                continue
            if job["arm"] == "baseline":
                raw = json.dumps({"assessments": [{"key": "item_0", "stance": "SUPPORTS",
                              "relevance_score": 0.9, "directness_score": 1.0}]})
            else:
                quote = "Official records confirm the bridge opened in 2024."
                raw = json.dumps({"assertion_id": job["case_id"],
                                  "evidence_link_id": f'bench.{job["case_id"]}',
                                  "stance": "SUPPORTS", "quote": quote,
                                  "basis_kind": "DIRECT_AFFIRMATION"})
            if job["job_id"] == invalid:
                raw = '{"not valid": true}'
            output.append({"job_id": job["job_id"], "raw_response": raw,
                           "latency_ms": 12.5, "input_tokens": 500, "output_tokens": 30,
                           "provider": "TEST", "model_id": "model-v1", "temperature": 0.1})
        if tamper:
            output.append({"job_id": "unknown.s1", "raw_response": "{}",
                           "provider": "TEST", "model_id": "model-v1", "temperature": 0.1})
        self.responses.write_text("".join(json.dumps(x) + "\n" for x in output), encoding="utf-8")

    def test_plans_exact_paired_requests_with_label_blind_inputs(self):
        manifest = self._plan()
        jobs = [json.loads(line) for line in self.jobs.read_text().splitlines()]
        self.assertEqual(len(jobs), 8)
        self.assertEqual(manifest["paired_jobs"], 8)
        self.assertEqual(manifest["reserved_max_output_tokens"], 2048)
        self.assertFalse(manifest["provider_execution_supported"])
        self.assertEqual({x["case_id"] for x in jobs}, set(self.rows))
        self.assertEqual({x["arm"] for x in jobs}, {"baseline", "candidate"})
        self.assertEqual({x["case_id"] for x in jobs if x["arm"] == "baseline"},
                         {x["case_id"] for x in jobs if x["arm"] == "candidate"})
        for job in jobs:
            self.assertNotIn("reference_stance", str(job))
            self.assertNotIn("reviewer_id", str(job))
            self.assertNotIn("rationale", str(job))
            self.assertEqual(job["max_output_tokens"], 256)
            self.assertIn("Official records confirm", job["user_prompt"])
        self.assertEqual(manifest["selected_cases"], 4)
        self.assertEqual(len(read_reference(self.subset_gold)), 4)

    def test_reference_subset_does_not_leave_missing_nonpilot_cases(self):
        for i in range(12):
            self.rows[f"extra_{i}"] = _case(f"extra_{i}", "SUPPORTS")
        self.gold.write_text("".join(json.dumps(r) + "\n" for r in self.rows.values()), encoding="utf-8")
        self._plan()
        selected = read_reference(self.subset_gold)
        self.assertEqual(len(selected), 4)
        self.assertEqual(len(read_reference(self.gold)), 16)
        self.assertEqual({r["reference_stance"] for r in selected.values()}, set(
            ["SUPPORTS", "REFUTES", "CONTEXT", "UNKNOWN"
        ]))
        self.assertNotIn("reference_stance", self.jobs.read_text())

    def test_default_budget_prevents_silent_full_run(self):
        with self.assertRaisesRegex(BenchmarkInputError, "request limit"):
            plan(self.rows, BASELINE, cases=4, max_requests=7)
        with self.assertRaisesRegex(BenchmarkInputError, "Output-token"):
            plan(self.rows, BASELINE, cases=4, max_requests=8, max_total_output_tokens=2047)
        with self.assertRaisesRegex(BenchmarkInputError, "input"):
            plan(self.rows, BASELINE, cases=4, max_requests=8,
                 max_total_input_chars=100)
        with self.assertRaises(BenchmarkInputError):
            plan(self.rows, BASELINE, cases=True)

    def test_balanced_subset_is_deterministic(self):
        rows = dict(self.rows)
        for i in range(8):
            rows[f"extra{i}"] = _case(f"extra{i}", "SUPPORTS")
        self.assertEqual(_balanced_ids(rows, 4), ["extra0", "r1", "c1", "u1"])
        self.assertEqual(_balanced_ids(rows, 4), _balanced_ids(rows, 4))

    def test_eight_case_pilot_spans_distinct_regression_axes(self):
        """The approved 48-case fixture must not produce a two-axis pilot."""
        fixture = (Path(__file__).resolve().parents[5] / "docs" /
                   "verification_benchmarks" / "phase3_semantic_gold_v1.jsonl")
        references = read_reference(fixture)
        selected = _balanced_ids(references, 8)
        from collections import Counter
        self.assertEqual(selected, [
            "dart_01", "negation_02", "date_03", "actor_swap_04",
            "intent_02", "conflict_01", "taglish_03", "prompt_injection_04",
        ])
        self.assertEqual(Counter(references[case]["reference_stance"] for case in selected),
                         {stance: 2 for stance in ("SUPPORTS", "REFUTES", "CONTEXT", "UNKNOWN")})
        self.assertEqual(len({references[case]["axis"] for case in selected}), 8)

    def test_axis_diversification_is_independent_of_reference_row_order(self):
        samples = {}
        for axis in ("dart", "date", "negation", "other"):
            for stance, ending in (("SUPPORTS", "s"), ("REFUTES", "r"),
                                   ("CONTEXT", "c"), ("UNKNOWN", "u")):
                case_id = f"{axis}_{ending}"
                samples[case_id] = {**_case(case_id, stance), "axis": axis}
        original = _balanced_ids(samples, 4)
        shuffled = _balanced_ids(dict(reversed(list(samples.items()))), 4)
        self.assertEqual(original, shuffled)
        self.assertEqual(len({samples[c]["axis"] for c in original}), 4)
        self.assertEqual(len({samples[c]["reference_stance"] for c in original}), 4)

    def test_single_axis_fixture_still_balances_stances(self):
        self.assertEqual(_balanced_ids(self.rows, 4), ["s1", "r1", "c1", "u1"])
        manifest = self._plan()
        self.assertEqual(manifest["sampling_method"], "stance_balanced_axis_diversified_v2")
        self.assertEqual(manifest["selected_axis_counts"], {"sample": 4})

    def test_read_baseline_prompt_without_importing_source(self):
        self.source.write_text(
            "raise RuntimeError('WOULD EXECUTE IF IMPORTED')\n"
            + "_SYSTEM_INSTRUCTIONS = " + repr(BASELINE) + "\n",
            encoding="utf-8")
        self.assertEqual(_source_baseline_prompt(self.source), BASELINE)

    def test_nonliteral_baseline_fails_closed(self):
        self.source.write_text("_SYSTEM_INSTRUCTIONS = make_prompt()\n", encoding="utf-8")
        with self.assertRaises(BenchmarkInputError):
            _source_baseline_prompt(self.source)

    def test_unexpected_baseline_contract_rejected(self):
        self.source.write_text("_SYSTEM_INSTRUCTIONS = 'test'\n", encoding="utf-8")
        with self.assertRaises(BenchmarkInputError):
            _source_baseline_prompt(self.source)

    def test_files_cannot_overwrite(self):
        self._plan()
        with self.assertRaisesRegex(BenchmarkInputError, "Refusing to overwrite"):
            self._plan()

    def test_gold_change_detected_before_collection(self):
        self._plan()
        self._save_responses()
        self.gold.write_text(self.gold.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "Reference fixture differs"):
            collect(gold_path=self.gold, jobs_path=self.jobs, manifest_path=self.manifest,
                    responses_path=self.responses)

    def test_jobs_change_detected_before_collection(self):
        self._plan()
        self._save_responses()
        self.jobs.write_text(self.jobs.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "Job plan differs"):
            collect(gold_path=self.gold, jobs_path=self.jobs, manifest_path=self.manifest,
                    responses_path=self.responses)

    def test_rejects_duplicate_and_unexpected_response_ids(self):
        self._plan()
        self._save_responses(tamper=True)
        with self.assertRaisesRegex(BenchmarkInputError, "Unexpected or duplicate"):
            collect(gold_path=self.gold, jobs_path=self.jobs, manifest_path=self.manifest,
                    responses_path=self.responses)
        self._save_responses()
        with self.responses.open("a", encoding="utf-8") as stream:
            stream.write(self.responses.read_text(encoding="utf-8").splitlines()[0] + "\n")
        with self.assertRaisesRegex(BenchmarkInputError, "Unexpected or duplicate"):
            collect(gold_path=self.gold, jobs_path=self.jobs, manifest_path=self.manifest,
                    responses_path=self.responses)

    def test_imports_saved_responses_into_existing_scorer_contract(self):
        self._plan()
        self._save_responses()
        summary = write_collected(
            gold_path=self.gold, jobs_path=self.jobs, manifest_path=self.manifest,
            responses_path=self.responses, baseline_out=self.baseline_out,
            candidate_out=self.candidate_out, errors_out=self.errors_out,
            summary_out=self.summary_out,
        )
        refs = read_reference(self.gold)
        base = read_predictions(self.baseline_out, set(refs))
        candidate = read_predictions(self.candidate_out, set(refs))
        comparison = compare(refs, base, candidate)
        self.assertEqual(len(base), 4)
        self.assertEqual(len(candidate), 4)
        self.assertEqual(summary["rejected_or_missing_jobs"], 0)
        self.assertEqual(summary["input_tokens_reported_total"], 4000)
        self.assertEqual(summary["output_tokens_reported_total"], 240)
        self.assertEqual(comparison["paired_evaluated_cases"], 4)
        self.assertEqual(comparison["baseline"]["all_case_accuracy"], 0.25)
        self.assertEqual(comparison["candidate"]["all_case_accuracy"], 0.25)

    def test_invalid_candidate_does_not_turn_into_unknown(self):
        self._plan()
        self._save_responses(invalid="candidate.s1")
        preds, errors, summary = collect(gold_path=self.gold, jobs_path=self.jobs,
                                         manifest_path=self.manifest, responses_path=self.responses)
        self.assertEqual(len(preds["baseline"]), 4)
        self.assertEqual(len(preds["candidate"]), 3)
        self.assertIn("candidate.s1", [item["job_id"] for item in errors])
        self.assertEqual(summary["rejected_or_missing_jobs"], 1)
        self.assertNotIn("s1", [x["case_id"] for x in preds["candidate"]])

    def test_missing_job_does_not_turn_into_unknown(self):
        self._plan()
        self._save_responses(missing="baseline.s1")
        _, errors, summary = collect(gold_path=self.gold, jobs_path=self.jobs,
                                     manifest_path=self.manifest, responses_path=self.responses)
        self.assertEqual(summary["responses_present"], 7)
        self.assertEqual(errors[0], {"job_id": "baseline.s1", "reason": "NO_RESPONSE"})

    def test_invalid_baseline_schema_cannot_count_as_unknown(self):
        self.assertEqual(_decode_baseline('{"assessments": [{"key": "item_0", "stance": "SUPPORTS", "relevance_score": true, "directness_score": 0.7}]}')[0], None)
        self.assertEqual(_decode_baseline('{"assessments": []}')[0], None)
        self.assertEqual(_decode_baseline('{"assessments": [{"key": "item_0", "stance": "UNKNOWN", "relevance_score": 0.4, "directness_score": 0.2}]}')[0], "UNKNOWN")

    def test_invalid_metrics_rejected(self):
        self._plan()
        self._save_responses()
        raw = self.responses.read_text().splitlines()
        entry = json.loads(raw[0]); entry["output_tokens"] = True
        raw[0] = json.dumps(entry)
        self.responses.write_text("\n".join(raw) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "measurement"):
            collect(gold_path=self.gold, jobs_path=self.jobs,
                    manifest_path=self.manifest, responses_path=self.responses)

    def test_reject_overwrite_of_outputs(self):
        self._plan()
        self._save_responses()
        self.candidate_out.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "overwrite"):
            write_collected(gold_path=self.gold, jobs_path=self.jobs,
                            manifest_path=self.manifest, responses_path=self.responses,
                            baseline_out=self.baseline_out, candidate_out=self.candidate_out,
                            errors_out=self.errors_out, summary_out=self.summary_out)
        self.assertFalse(self.baseline_out.exists())

    def test_mixed_provider_metadata_rejected(self):
        self._plan()
        self._save_responses()
        raw = self.responses.read_text().splitlines()
        entry = json.loads(raw[-1]); entry["model_id"] = "other-v1"
        raw[-1] = json.dumps(entry)
        self.responses.write_text("\n".join(raw) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "differ across arms"):
            collect(gold_path=self.gold, jobs_path=self.jobs,
                    manifest_path=self.manifest, responses_path=self.responses)

    def test_over_budget_output_usage_rejected(self):
        self._plan()
        self._save_responses()
        raw = self.responses.read_text().splitlines()
        entry = json.loads(raw[0]); entry["output_tokens"] = 257
        raw[0] = json.dumps(entry)
        self.responses.write_text("\n".join(raw) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "per-request cap"):
            collect(gold_path=self.gold, jobs_path=self.jobs,
                    manifest_path=self.manifest, responses_path=self.responses)

    def test_missing_model_metadata_rejected(self):
        self._plan()
        self._save_responses()
        raw = self.responses.read_text().splitlines()
        entry = json.loads(raw[0]); del entry["provider"]
        raw[0] = json.dumps(entry)
        self.responses.write_text("\n".join(raw) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(BenchmarkInputError, "fields invalid"):
            collect(gold_path=self.gold, jobs_path=self.jobs,
                    manifest_path=self.manifest, responses_path=self.responses)

    def test_no_external_provider_is_imported(self):
        # Modules used by runner contain only Python stdlib and Batch 3-5 helpers.
        self.assertNotIn("import requests", Path(__import__(
            "api.verification.semantic_eval_runner", fromlist=["_"]).__file__).read_text())
        self.assertNotIn("call_llm_with_fallback", Path(__import__(
            "api.verification.semantic_eval_runner", fromlist=["_"]).__file__).read_text())


if __name__ == "__main__":
    unittest.main()
