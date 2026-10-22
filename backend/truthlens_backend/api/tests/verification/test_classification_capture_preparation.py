"""No-network, no-ORM guardrails for approved-reference capture preparation."""
import copy
import hashlib
import json
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from api.management.commands.audit_investigation_classification import DEFAULT_CORPUS
from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
)
from api.verification.classification_capture_plan import (
    build_capture_plan, summarize_capture_plan, write_private_capture_package,
)


class ClassificationCapturePreparationTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.pending = load_classification_corpus(DEFAULT_CORPUS)
        self.approved = copy.deepcopy(self.pending)
        for case in self.approved:
            case["review"] = {
                "status": "APPROVED",
                "reviewer": "Fictional reviewer for offline unit test",
                "notes": "Synthetic approval metadata for fixture-only test.",
            }
        self.path = self.root / "test_approved.json"
        self.path.write_text(json.dumps({
            "schema_version": 1, "cases": self.approved,
        }), encoding="utf-8")

    def test_fail_closed_on_default_pending_reference_corpus(self):
        with self.assertRaises(ClassificationAuditError):
            build_capture_plan(self.pending, provider="gemini")
        target = self.root / "not_written"
        with self.assertRaises(CommandError):
            call_command(
                "prepare_investigation_classification_evaluation",
                "--corpus", str(DEFAULT_CORPUS),
                "--provider", "gemini",
                "--export-dir", str(target),
                stdout=StringIO(),
            )
        self.assertFalse(target.exists())

    def test_default_canary_is_four_explicit_safety_cases(self):
        plan = build_capture_plan(self.approved, provider="cloudflare")
        summary = summarize_capture_plan(plan)
        self.assertEqual(summary["case_ids"], [
            "cross_spacecraft", "cross_school_sport",
            "ambiguous_plan", "injection_civic",
        ])
        self.assertEqual(summary["planned_requests"], 4)
        self.assertEqual(summary["approved_references_in_source"], 32)
        self.assertEqual(summary["provider_calls"], 0)
        self.assertEqual(summary["db_writes"], 0)
        self.assertIs(summary["enforcement_approved"], False)
        self.assertEqual(summary["cost"]["status"], "UNKNOWN")
        self.assertEqual(plan["max_output_tokens"], 1024)

    def test_full_limit_is_bounded_and_unique(self):
        plan = build_capture_plan(self.approved, provider="gemini", limit=32)
        self.assertEqual(len(plan["requests"]), 32)
        self.assertEqual(
            len(set(item["case_id"] for item in plan["requests"])), 32
        )
        self.assertEqual(len(plan["corpus_sha256"]), 64)

    def test_explicit_case_selection_cannot_escape_limit_or_corpus(self):
        for selections, limit in (
            (["science_telescope", "science_telescope"], 2),
            (["not_a_real_claim"], 4),
            (["science_telescope", "health_vaccine"], 1),
        ):
            with self.subTest(selections=selections):
                with self.assertRaises(ClassificationAuditError):
                    build_capture_plan(
                        self.approved, provider="groq",
                        limit=limit, case_ids=selections,
                    )
        with self.assertRaises(ClassificationAuditError):
            build_capture_plan(self.approved, provider="groq", limit=33)
        with self.assertRaises(ClassificationAuditError):
            build_capture_plan(self.approved, provider="unknown")
        one = build_capture_plan(
            self.approved, provider="groq", limit=1,
            case_ids=["science_telescope"],
        )
        self.assertEqual(one["requests"][0]["case_id"], "science_telescope")

    def test_illustrative_prices_require_complete_explicit_assumptions(self):
        with self.assertRaises(ClassificationAuditError):
            build_capture_plan(
                self.approved, provider="gemini",
                input_price_per_million=Decimal("2"),
            )
        with self.assertRaises(ClassificationAuditError):
            build_capture_plan(
                self.approved, provider="gemini",
                input_price_per_million=Decimal("NaN"),
                output_price_per_million=Decimal("4"),
                assumed_input_tokens=1000,
                assumed_output_tokens=500,
            )
        cost = build_capture_plan(
            self.approved, provider="gemini",
            input_price_per_million=Decimal("2"),
            output_price_per_million=Decimal("4"),
            assumed_input_tokens=1000,
            assumed_output_tokens=500,
        )["cost"]
        self.assertEqual(cost["status"], "ILLUSTRATIVE_ONLY")
        self.assertEqual(cost["estimated_usd"], "0.016000")
        self.assertIn("NOT a spend cap", cost["warning"])

    def test_private_export_contains_inputs_but_no_reference_labels_or_results(self):
        plan = build_capture_plan(self.approved, provider="cloudflare", limit=4)
        target = self.root / "new-private-capture"
        folder = write_private_capture_package(plan, target)
        self.assertTrue(folder.is_dir())
        manifest = json.loads((folder / "capture_inputs.json").read_text(encoding="utf-8"))
        predictions = json.loads((folder / "predictions.json").read_text(encoding="utf-8"))
        self.assertEqual(predictions, {"schema_version": 1, "predictions": []})
        self.assertEqual(manifest["provider"], "cloudflare")
        self.assertNotIn("draft_expected", (folder / "capture_inputs.json").read_text())
        self.assertNotIn("review", (folder / "capture_inputs.json").read_text())
        for request in manifest["requests"]:
            self.assertEqual(request["claim_sha256"], hashlib.sha256(
                request["claim_text"].encode("utf-8")
            ).hexdigest())
        with self.assertRaises(ClassificationAuditError):
            write_private_capture_package(plan, target)

    def test_refuses_export_inside_checkout(self):
        plan = build_capture_plan(self.approved, provider="groq")
        application = Path(__file__).resolve().parents[3]
        forbidden = application / "DO_NOT_CREATE_CLASSIFICATION_PACKAGE"
        with self.assertRaises(ClassificationAuditError):
            write_private_capture_package(plan, forbidden)
        self.assertFalse(forbidden.exists())

    def test_cli_sanitizes_printed_claims_and_never_scores_models(self):
        output = StringIO()
        call_command(
            "prepare_investigation_classification_evaluation",
            "--corpus", str(self.path), "--provider", "gemini",
            "--json-summary", stdout=output,
        )
        result = json.loads(output.getvalue())
        self.assertEqual(result["case_ids"][:2], [
            "cross_spacecraft", "cross_school_sport",
        ])
        self.assertEqual(result["provider_calls"], 0)
        self.assertIs(result["enforcement_approved"], False)
        self.assertNotIn("Europa Clipper spacecraft", output.getvalue())
        self.assertNotIn("draft_expected", output.getvalue())
        self.assertNotIn("raw_response", output.getvalue())

    def test_cli_export_is_explicit_and_never_populates_predictions(self):
        output = StringIO()
        target = self.root / "cli-export"
        call_command(
            "prepare_investigation_classification_evaluation",
            "--corpus", str(self.path), "--provider", "groq",
            "--limit", "1", "--case-ids", "ambiguous_plan",
            "--export-dir", str(target), stdout=output,
        )
        self.assertIn("NO PROVIDER CALLS", output.getvalue())
        self.assertEqual(json.loads(
            (target / "predictions.json").read_text(encoding="utf-8")
        )["predictions"], [])
        self.assertEqual(len(json.loads(
            (target / "capture_inputs.json").read_text(encoding="utf-8")
        )["requests"]), 1)
