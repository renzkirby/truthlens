"""Offline-only tests for draft semantic stance benchmark; no Django DB."""

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from api.verification.semantic_benchmark import (
    BenchmarkInputError, STANCES, _cli, compare, read_predictions,
    read_reference, score,
)


GOLD = (Path(__file__).resolve().parents[5] / "docs" /
        "verification_benchmarks" / "phase3_semantic_gold_v1.jsonl")


class SemanticBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = read_reference(GOLD)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)

    def _write(self, name, rows):
        path = self.tmp / name
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def _predictions(self, stance_fn=None):
        return {k: {"case_id": k, "stance": (
            stance_fn(k, v) if stance_fn else v["reference_stance"]
        )} for k, v in self.reference.items()}

    def test_gold_set_has_48_balanced_draft_cases(self):
        self.assertEqual(len(self.reference), 48)
        self.assertEqual({x["review_status"] for x in self.reference.values()},
                         {"DRAFT_UNREVIEWED"})
        self.assertEqual({s: sum(v["reference_stance"] == s for v in
                             self.reference.values()) for s in STANCES},
                         {s: 12 for s in STANCES})
        self.assertIn("dart_01", self.reference)
        self.assertIn("filipino_01", self.reference)
        self.assertIn("prompt_injection_04", self.reference)

    def test_perfect_predictions_score_100_percent(self):
        result = score(self.reference, self._predictions())
        self.assertEqual(result["all_case_accuracy"], 1)
        self.assertEqual(result["macro_f1_missing_counted_as_errors"], 1)
        self.assertEqual(result["false_support_count"], 0)
        self.assertEqual(result["false_refute_count"], 0)
        self.assertEqual(result["missing_cases"], 0)

    def test_missing_predictions_count_as_error_not_unverified(self):
        preds = self._predictions()
        del preds["dart_01"]
        result = score(self.reference, preds)
        self.assertEqual(result["missing_cases"], 1)
        self.assertEqual(result["confusion"]["SUPPORTS"]["MISSING"], 1)
        self.assertAlmostEqual(result["all_case_accuracy"], 47/48, places=6)
        self.assertEqual(result["observed_accuracy"], 1)

    def test_false_support_and_false_refute_are_separate(self):
        preds = self._predictions()
        preds["dart_03"]["stance"] = "SUPPORTS"  # Partial coverage misread
        preds["date_01"]["stance"] = "REFUTES"  # True fact misread
        result = score(self.reference, preds)
        self.assertEqual(result["false_support_count"], 1)
        self.assertEqual(result["false_refute_count"], 1)
        self.assertAlmostEqual(result["all_case_accuracy"], 46/48, places=6)

    def test_excessive_unknown_is_measured(self):
        preds = self._predictions(lambda _k, _v: "UNKNOWN")
        result = score(self.reference, preds)
        self.assertEqual(result["over_abstain_count"], 36)
        self.assertEqual(result["predicted_unknown_count"], 48)
        self.assertEqual(result["all_case_accuracy"], 0.25)

    def test_by_axis_accuracy_is_reported(self):
        preds = self._predictions()
        preds["dart_02"]["stance"] = "UNKNOWN"
        result = score(self.reference, preds)
        self.assertEqual(result["by_axis"]["dart"]["accuracy"], 0.75)
        self.assertEqual(result["by_axis"]["filipino"]["accuracy"], 1)

    def test_missing_one_arm_does_not_masquerade_as_paired_fix(self):
        base = self._predictions()
        candidate = self._predictions()
        base["date_02"]["stance"] = "CONTEXT"
        del candidate["date_02"]
        result = compare(self.reference, base, candidate)
        self.assertEqual(result["paired_evaluated_cases"], 47)
        self.assertNotIn("date_02", result["candidate_fixes"])
        self.assertEqual(result["candidate"]["missing_cases"], 1)

    def test_regression_and_fix_reported_by_id(self):
        base = self._predictions()
        candidate = self._predictions()
        base["dart_03"]["stance"] = "SUPPORTS"
        candidate["date_01"]["stance"] = "UNKNOWN"
        result = compare(self.reference, base, candidate)
        self.assertEqual(result["candidate_fixes"], ["dart_03"])
        self.assertEqual(result["candidate_regressions"], ["date_01"])
        self.assertEqual(result["review_status"],
                         "PROVISIONAL_DRAFT_REFERENCES_NOT_HUMAN_VERIFIED")
        self.assertEqual(result["delta_all_case_accuracy"], 0)

    def test_duplicate_reference_ids_rejected(self):
        row = next(iter(self.reference.values()))
        file = self._write("duplicate.jsonl", [row, row])
        with self.assertRaisesRegex(BenchmarkInputError, "Duplicate case_id"):
            read_reference(file)

    def test_duplicate_prediction_ids_rejected(self):
        case_id = "dart_01"
        file = self._write("duplicate.jsonl", [
            {"case_id": case_id, "stance": "SUPPORTS"},
            {"case_id": case_id, "stance": "UNKNOWN"},
        ])
        with self.assertRaisesRegex(BenchmarkInputError, "Duplicate prediction"):
            read_predictions(file, self.reference)

    def test_duplicate_json_keys_rejected(self):
        path = self.tmp / "dupe-keys.jsonl"
        path.write_text('{"case_id":"dart_01","stance":"SUPPORTS","stance":"REFUTES"}\n',encoding="utf-8")
        with self.assertRaises(BenchmarkInputError):
            read_predictions(path, self.reference)

    def test_prediction_unknown_case_rejected(self):
        file = self._write("unknown.jsonl", [{"case_id":"invented","stance":"SUPPORTS"}])
        with self.assertRaises(BenchmarkInputError):
            read_predictions(file, self.reference)

    def test_predicted_invalid_label_rejected(self):
        file = self._write("invalid.jsonl", [{"case_id":"dart_01","stance":"FACT"}])
        with self.assertRaises(BenchmarkInputError):
            read_predictions(file, self.reference)

    def test_invalid_metric_bool_and_nan_rejected(self):
        for value in (True, float("nan"), -1):
            with self.subTest(value=value):
                file = self._write("invalid.jsonl", [{
                    "case_id":"dart_01","stance":"SUPPORTS","latency_ms":value}])
                with self.assertRaises(BenchmarkInputError):
                    read_predictions(file, self.reference)

    def test_invalid_output_tokens_rejected(self):
        file=self._write("bad.jsonl",[{"case_id":"dart_01","stance":"SUPPORTS","output_tokens":True}])
        with self.assertRaises(BenchmarkInputError):
            read_predictions(file,self.reference)

    def test_gold_fields_must_match_contract(self):
        bad = deepcopy(self.reference["dart_01"])
        bad["hidden_gold"] = "SUPPORTS"
        file=self._write("bad.jsonl",[bad])
        with self.assertRaises(BenchmarkInputError):
            read_reference(file)

    def test_unreviewed_case_cannot_claim_reviewer(self):
        bad=deepcopy(self.reference["dart_01"])
        bad["reviewer_id"]="reviewer01"
        file=self._write("bad.jsonl",[bad])
        with self.assertRaises(BenchmarkInputError):
            read_reference(file)

    def test_adjudicated_case_requires_review_metadata(self):
        bad=deepcopy(self.reference["dart_01"])
        bad["review_status"]="INDEPENDENTLY_ADJUDICATED"
        file=self._write("bad.jsonl",[bad])
        with self.assertRaises(BenchmarkInputError):
            read_reference(file)

    def test_source_derived_case_requires_url(self):
        bad=deepcopy(self.reference["dart_01"])
        bad["source_kind"]="SOURCE_DERIVED"
        bad["source_url"]=None
        file=self._write("bad.jsonl",[bad])
        with self.assertRaises(BenchmarkInputError):
            read_reference(file)

    def test_reports_optional_metrics_without_inventing_others(self):
        preds=self._predictions()
        preds["dart_01"]["latency_ms"]=30
        preds["dart_01"]["output_tokens"]=40
        result=score(self.reference,preds)
        self.assertEqual(result["latency_observed_cases"],1)
        self.assertEqual(result["mean_latency_ms_reported"],30)
        self.assertEqual(result["tokens_observed_cases"],1)
        self.assertEqual(result["mean_output_tokens_reported"],40)

    def test_validate_cli_provisional(self):
        buf=StringIO()
        with redirect_stdout(buf):
            status=_cli(["validate","--gold",str(GOLD)])
        self.assertEqual(status,0)
        self.assertTrue(json.loads(buf.getvalue())["not_ready_for_accuracy_claims"])

    def test_compare_cli_report_not_overwritten(self):
        predictions=list(self._predictions().values())
        base=self._write("base.jsonl",predictions)
        cand=self._write("cand.jsonl",predictions)
        output=self.tmp/"report.json"
        with redirect_stdout(StringIO()):
            status=_cli(["compare","--gold",str(GOLD),"--baseline",str(base),
                         "--candidate",str(cand),"--report",str(output)])
        self.assertEqual(status,0)
        data=json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(data["baseline"]["all_case_accuracy"],1)
        with redirect_stderr(StringIO()):
            status=_cli(["compare","--gold",str(GOLD),"--baseline",str(base),
                         "--candidate",str(cand),"--report",str(output)])
        self.assertEqual(status,2)

    def test_no_actual_provider_or_database_called(self):
        import api.verification.semantic_benchmark as module
        self.assertFalse(hasattr(module,"call_llm_with_fallback"))
        self.assertFalse(hasattr(module,"VerificationEvidence"))
        self.assertFalse(hasattr(module,"requests"))


if __name__ == "__main__":
    unittest.main()
