"""No-network acceptance tests for the paired 1024/4096 budget design."""
import copy
import hashlib
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from api.management.commands.audit_investigation_classification import DEFAULT_CORPUS
from api.verification.classification_capture_plan import build_capture_plan
from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
)
from api.verification.cloudflare_budget_benchmark import (
    BUDGETS, CASE_IDS, EXPECTED_APPROVED_CORPUS_SHA256, MANIFEST_NAME,
    OBSERVATIONS_NAME, PLANNED_TRIALS, PROFILE, build_budget_benchmark,
    export_private_benchmark, safe_benchmark_summary,
    score_budget_benchmark, validate_benchmark_files,
)


CROSS_VALID = json.dumps({
    "decision": "CLASSIFY",
    "domains": [
        {"code": "SCIENCE", "evidence": "scientists would analyze data"},
        {"code": "TECHNOLOGY", "evidence": "Falcon Heavy rocket launch"},
    ],
})
SCHOLARSHIP_WRONG = json.dumps({
    "decision": "CLASSIFY",
    "domains": [{"code": "SPORTS", "evidence": "sports scholarship"}],
})
ABSTAIN = json.dumps({"decision": "ABSTAIN", "domains": []})


class PairedCloudflareBudgetBenchmarkTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.cases = copy.deepcopy(load_classification_corpus(DEFAULT_CORPUS))
        for c in self.cases:
            c["review"] = {
                "status": "APPROVED",
                "reviewer": "Temporary mocked-test reviewer only",
                "notes": "Synthetic approval for unit-test fixtures, not real signoff.",
            }
        self.path = self.root / "reference.json"
        self.path.write_text(json.dumps({
            "schema_version": 1, "cases": self.cases,
        }), encoding="utf-8")
        fake_hash = build_capture_plan(
            self.cases, provider="cloudflare", model_id="test",
            limit=4, case_ids=list(CASE_IDS),
        )["corpus_sha256"]
        self.enterContext(patch(
            "api.verification.cloudflare_budget_benchmark.EXPECTED_APPROVED_CORPUS_SHA256",
            fake_hash,
        ))
        self.manifest = build_budget_benchmark(self.cases)
        self.folder = export_private_benchmark(
            self.manifest, self.root / "new-private-benchmark",
        )
        self.post = self.enterContext(patch(
            "api.verification.cloudflare_evaluation.requests.post",
        ))
        self.fallback = self.enterContext(patch(
            "api.services.call_llm_with_fallback",
        ))

    def _obs(self, trial_id, *, status="CAPTURED", raw=CROSS_VALID,
             code=None, duration=8500, completion=829):
        return {
            "trial_id": trial_id,
            "status": status,
            "raw_response": raw if status == "CAPTURED" else None,
            "error_code": code,
            "duration_ms": duration,
            "usage": {
                "finish_reason": "stop" if status == "CAPTURED" else "length",
                "prompt_tokens": 177,
                "completion_tokens": completion,
                "total_tokens": None,
                "reasoning_tokens": None,
                "reasoning_present": True,
            },
        }

    def _write_observations(self, records):
        content = {
            "schema_version": 1, "profile": PROFILE,
            "manifest_sha256": self.manifest["manifest_sha256"],
            "observations": records,
        }
        (self.folder / OBSERVATIONS_NAME).write_text(
            json.dumps(content), encoding="utf-8",
        )

    def test_fixed_balanced_plan_contains_16_unique_trial_ids(self):
        self.assertEqual(PLANNED_TRIALS, 16)
        self.assertEqual(self.manifest["planned_trials"], 16)
        self.assertEqual(self.manifest["model_id"], "@cf/google/gemma-4-26b-a4b-it")
        trials = self.manifest["trials"]
        self.assertEqual(len(set(t["trial_id"] for t in trials)), 16)
        self.assertEqual(sorted(set(t["max_completion_tokens"] for t in trials)),
                         [1024, 4096])
        for case_id in CASE_IDS:
            subset = [t for t in trials if t["case_id"] == case_id]
            self.assertEqual(len(subset), 4)
            self.assertEqual(
                [(t["repeat"], t["max_completion_tokens"]) for t in subset],
                [(1, 1024), (1, 4096), (2, 4096), (2, 1024)]
                if case_id in (CASE_IDS[0], CASE_IDS[2])
                else [(1, 4096), (1, 1024), (2, 1024), (2, 4096)]
            )
        self.post.assert_not_called()
        self.fallback.assert_not_called()

    def test_plan_is_deterministic_and_explicitly_not_a_live_executor(self):
        again = build_budget_benchmark(self.cases)
        self.assertEqual(again, self.manifest)
        summary = safe_benchmark_summary(again)
        self.assertEqual(summary["provider_calls"], 0)
        self.assertFalse(summary["live_execution_implemented"])
        self.assertFalse(summary["enforcement_approved"])
        self.assertEqual(summary["per_budget_planned"], 8)
        self.assertEqual(summary["repetitions_per_case_per_budget"], 2)

    def test_private_export_contains_no_reference_labels_or_predictions(self):
        source = (self.folder / MANIFEST_NAME).read_text()
        self.assertNotIn("draft_expected", source)
        self.assertNotIn("review", source)
        self.assertEqual(json.loads(
            (self.folder / OBSERVATIONS_NAME).read_text()
        )["observations"], [])
        with self.assertRaises(ClassificationAuditError):
            export_private_benchmark(self.manifest, self.folder)

    def test_pending_reference_is_refused(self):
        with self.assertRaises(ClassificationAuditError):
            build_budget_benchmark(load_classification_corpus(DEFAULT_CORPUS))

    def test_different_approval_fingerprint_is_refused(self):
        changed = copy.deepcopy(self.cases)
        changed[0]["review"]["notes"] = "Changed simulated signoff"
        with self.assertRaises(ClassificationAuditError):
            build_budget_benchmark(changed)

    def test_malformed_manifest_or_observations_block_scoring(self):
        manifest_path = self.folder / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text())
        manifest["trials"][0]["max_completion_tokens"] = 8192
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ClassificationAuditError):
            validate_benchmark_files(self.cases, self.folder)
        manifest_path.write_text(json.dumps(self.manifest))
        self._write_observations([])
        packet = json.loads((self.folder / OBSERVATIONS_NAME).read_text())
        packet["manifest_sha256"] = "0" * 64
        (self.folder / OBSERVATIONS_NAME).write_text(json.dumps(packet))
        with self.assertRaises(ClassificationAuditError):
            validate_benchmark_files(self.cases, self.folder)

    def test_initial_empty_benchmark_has_no_fake_accuracy(self):
        manifest, observations = validate_benchmark_files(self.cases, self.folder)
        score = score_budget_benchmark(self.cases, manifest, observations)
        self.assertEqual(score["planned_trials"], 16)
        self.assertEqual(score["observed_trials"], 0)
        self.assertEqual(score["unobserved_trials"], 16)
        self.assertFalse(score["all_trials_observed"])
        self.assertFalse(score["enforcement_approved"])
        self.assertFalse(score["statistically_generalizable"])
        for budget in BUDGETS:
            arm = score["per_budget"][str(budget)]
            self.assertEqual(arm["observed"], 0)
            self.assertEqual(arm["missing"], 8)
            self.assertIsNone(arm["observed_exact_match_rate"])
            self.assertIsNone(arm["median_observed_duration_ms"])

    def test_success_failure_and_invalid_are_not_collapsed(self):
        self._write_observations([
            self._obs("cross_spacecraft__r1__t1024"),
            self._obs(
                "cross_spacecraft__r1__t4096",
                status="PROVIDER_FAILED", raw=None,
                code="EMPTY_PROVIDER_RESPONSE", completion=4096,
            ),
            self._obs("cross_spacecraft__r2__t4096", raw="bad json"),
        ])
        manifest, items = validate_benchmark_files(self.cases, self.folder)
        score = score_budget_benchmark(self.cases, manifest, items)
        self.assertEqual(score["observed_trials"], 3)
        self.assertEqual(score["unobserved_trials"], 13)
        self.assertEqual(score["per_budget"]["1024"]["exact_matches"], 1)
        self.assertEqual(score["per_budget"]["1024"]["missing"], 7)
        self.assertEqual(score["per_budget"]["4096"]["provider_failed"], 1)
        self.assertEqual(score["per_budget"]["4096"]["invalid_contract"], 1)
        self.assertEqual(score["per_budget"]["4096"]["exact_matches"], 0)
        self.assertEqual(score["per_budget"]["4096"]["observed_exact_match_rate"], 0)
        self.assertFalse(score["all_trials_observed"])

    def test_wrong_domains_trigger_scope_leak_diagnostic(self):
        self._write_observations([
            self._obs(
                "cross_school_sport__r1__t4096",
                raw=SCHOLARSHIP_WRONG,
            ),
            self._obs(
                "ambiguous_plan__r1__t1024",
                raw=ABSTAIN,
            ),
        ])
        manifest, rows = validate_benchmark_files(self.cases, self.folder)
        score = score_budget_benchmark(self.cases, manifest, rows)
        self.assertEqual(score["per_budget"]["4096"]["wrong_domains"], 1)
        self.assertEqual(score["per_budget"]["4096"]["potential_scope_leaks"], 1)
        self.assertEqual(score["per_budget"]["1024"]["exact_matches"], 1)
        self.assertEqual(score["per_case"]["ambiguous_plan"]["exact_matches"], 1)
        self.assertFalse(score["enforcement_approved"])

    def test_duplicate_unknown_or_fabricated_failure_rejected(self):
        single = self._obs("cross_spacecraft__r1__t1024")
        for broken in (
            [single, single],
            [self._obs("invented__r1__t1024")],
            [self._obs(
                "cross_spacecraft__r1__t4096",
                status="PROVIDER_FAILED", raw=None,
                code="api key secret abc",
            )],
            [self._obs(
                "cross_spacecraft__r1__t4096",
                status="PROVIDER_FAILED", raw=None,
                code=None,
            )],
        ):
            with self.subTest(broken=broken):
                with self.assertRaises(ClassificationAuditError):
                    score_budget_benchmark(self.cases, self.manifest, broken)

    def test_unknown_usage_and_bogus_status_fail_closed(self):
        record = self._obs("cross_spacecraft__r1__t1024")
        bads = []
        for fn in (
            lambda x: x["usage"].update(completion_tokens=-1),
            lambda x: x["usage"].update(reasoning_present="yes"),
            lambda x: x.update(status="NOT_ATTEMPTED"),
            lambda x: x.update(duration_ms=-1),
            lambda x: x.update(error_code="INTERNAL_INFO"),
            lambda x: x.update(raw_response=None),
        ):
            instance = copy.deepcopy(record)
            fn(instance)
            bads.append(instance)
        for bad in bads:
            with self.subTest(status=bad):
                with self.assertRaises(ClassificationAuditError):
                    score_budget_benchmark(self.cases, self.manifest, [bad])

    def test_read_only_score_cli_is_sanitized_and_network_free(self):
        out = StringIO()
        call_command(
            "score_cloudflare_budget_benchmark",
            "--corpus", str(self.path),
            "--campaign-dir", str(self.folder),
            "--json-summary", stdout=out,
        )
        score = json.loads(out.getvalue())
        self.assertEqual(score["unobserved_trials"], 16)
        self.assertNotIn("NASA announced", out.getvalue())
        self.assertNotIn("raw_response", out.getvalue())
        self.post.assert_not_called()
        self.fallback.assert_not_called()

    def test_prepare_cli_read_only_or_private_export_only(self):
        out = StringIO()
        call_command(
            "prepare_cloudflare_budget_benchmark",
            "--corpus", str(self.path), "--json-summary", stdout=out,
        )
        summary = json.loads(out.getvalue())
        self.assertEqual(summary["planned_trials"], 16)
        self.assertFalse(summary.get("private_package_created", False))
        self.post.assert_not_called()
        new_folder = self.root / "private-two"
        call_command(
            "prepare_cloudflare_budget_benchmark",
            "--corpus", str(self.path),
            "--export-dir", str(new_folder),
            "--json-summary", stdout=StringIO(),
        )
        self.assertTrue((new_folder / MANIFEST_NAME).exists())
        self.post.assert_not_called()

    def test_denies_directory_inside_repository(self):
        target = Path(__file__).resolve().parents[4] / "SHOULD_NOT_CREATE_BENCHMARK"
        with self.assertRaises(ClassificationAuditError):
            export_private_benchmark(self.manifest, target)
        self.assertFalse(target.exists())

    def test_error_printing_never_exposes_observation_claim_text(self):
        with self.assertRaises(CommandError) as caught:
            call_command(
                "score_cloudflare_budget_benchmark",
                "--corpus", str(self.path),
                "--campaign-dir", str(self.root / "missing"),
                stdout=StringIO(),
            )
        self.assertNotIn("NASA", str(caught.exception))
        self.post.assert_not_called()
