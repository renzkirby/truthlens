"""No-network/no-database test coverage for reviewer-gated subject audit."""
import copy
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import SimpleTestCase

from api.verification.classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
    load_classification_predictions, score_classification_predictions,
    summarize_classification_corpus,
)
from api.management.commands.audit_investigation_classification import DEFAULT_CORPUS


def valid_response(*domains):
    return json.dumps({
        "decision": "CLASSIFY",
        "primary_subject": domains[0][0],
        "domains": [{"code": code, "evidence": quote} for code, quote in domains],
    })


def _approve(cases, *ids):
    approved = copy.deepcopy(cases)
    for case in approved:
        if case["id"] in ids:
            case["review"] = {
                "status": "APPROVED",
                "reviewer": "Synthetic test reviewer",
                "notes": "Test-only reviewer label, not a real-world accuracy judgment.",
            }
    return approved


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class SubjectCorpusQualityAuditTests(SimpleTestCase):
    def setUp(self):
        self.cases = load_classification_corpus(DEFAULT_CORPUS)
        self.temp = self.enterContext(TemporaryDirectory())
        self.root = Path(self.temp)

    def test_draft_corpus_spans_all_supported_subject_codes(self):
        summary = summarize_classification_corpus(self.cases)
        self.assertEqual(summary["cases"], 32)
        self.assertEqual(summary["approved"], 0)
        self.assertEqual(summary["pending"], 32)
        self.assertEqual(
            sum(n > 0 for n in summary["draft_domain_counts"].values()), 12,
        )
        self.assertEqual(
            {tag for tag, count in summary["tag_counts"].items() if count},
            {
                "single_domain", "cross_domain", "ambiguous",
                "location_only", "prompt_injection", "weak_evidence",
                "contradictory", "out_of_scope",
            },
        )

    def test_school_sports_scholarship_consensus_is_pending_education_only(self):
        """A multi-subject-looking claim must not gain a SPORTS requirement by keyword."""
        case = next(
            item for item in self.cases if item["id"] == "cross_school_sport"
        )
        self.assertEqual(
            case["draft_expected"],
            {"decision": "CLASSIFY", "domains": ["EDUCATION"]},
        )
        self.assertEqual(case["review"], {
            "status": "PENDING", "reviewer": "", "notes": "",
        })
        self.assertIn("cross_domain", case["tags"])

    def test_default_command_is_dry_read_and_does_not_claim_accuracy(self):
        buf = StringIO()
        call_command("audit_investigation_classification", stdout=buf)
        output = buf.getvalue()
        self.assertIn("CORPUS cases=32 approved=0 pending=32", output)
        self.assertIn("NOT SCORED", output)
        self.assertIn("NO PROVIDER CALLS", output)
        self.assertNotIn(self.cases[0]["claim_text"], output)

    def test_json_summary_never_prints_claim_text_or_model_output(self):
        buf = StringIO()
        call_command("audit_investigation_classification",
                     "--json-summary", stdout=buf)
        obj = json.loads(buf.getvalue())
        self.assertEqual(obj["status"], "NO_REVIEWED_REFERENCES")
        self.assertIsNone(obj["evaluation"])
        self.assertIs(obj["enforcement_approved"], False)
        self.assertNotIn(self.cases[0]["claim_text"], buf.getvalue())

    def test_review_approval_requires_reviewer_and_notes(self):
        cases = copy.deepcopy(self.cases)
        cases[0]["review"]["status"] = "APPROVED"
        path = _write(self.root / "bad.json", {
            "schema_version": 1, "cases": cases,
        })
        with self.assertRaises(ClassificationAuditError):
            load_classification_corpus(path)
        cases[0]["review"]["reviewer"] = "Reviewer A"
        cases[0]["review"]["notes"] = "Review example for unit test."
        _write(path, {"schema_version": 1, "cases": cases})
        self.assertEqual(
            summarize_classification_corpus(
                load_classification_corpus(path)
            )["approved"], 1,
        )

    def test_corpus_rejects_duplicate_ids_or_invalid_subjects(self):
        for mutate in (
            lambda cases: cases[1].update(id=cases[0]["id"]),
            lambda cases: cases[0]["draft_expected"].update(
                domains=["UNRECOGNIZED"],
            ),
            lambda cases: cases[0].update(tags=[{"bad": "tag"}]),
            lambda cases: cases[0].update(claim_text="Short"),
            lambda cases: cases[0]["draft_expected"].update(
                decision="ABSTAIN",
            ),
        ):
            with self.subTest(mutation=str(mutate)):
                cases = copy.deepcopy(self.cases)
                mutate(cases)
                path = _write(self.root / "bad.json", {
                    "schema_version": 1, "cases": cases,
                })
                with self.assertRaises(ClassificationAuditError):
                    load_classification_corpus(path)

    def test_prediction_input_rejects_unknown_and_duplicate_case_ids(self):
        known = {c["id"] for c in self.cases}
        for entries in (
            [{"case_id": "unknown_case", "raw_response": "{}"}],
            [{"case_id": "science_telescope", "raw_response": "{}"}] * 2,
            [{"case_id": "science_telescope", "raw_response": None}],
            [{"case_id": "science_telescope", "raw_response": "x" * 8001}],
        ):
            with self.subTest(entries_count=len(entries)):
                path = _write(self.root / "bad_predictions.json", {
                    "schema_version": 1, "predictions": entries,
                })
                with self.assertRaises(ClassificationAuditError):
                    load_classification_predictions(path, known)

    def test_valid_reviewed_predictions_are_descriptive_not_authorization(self):
        approved = _approve(
            self.cases, "science_telescope", "cross_spacecraft",
            "ambiguous_plan",
        )
        preds = {
            "science_telescope": valid_response((
                "SCIENCE", "Astronomers published telescope observations",
            )),
            "cross_spacecraft": valid_response(
                ("SCIENCE", "scientists would analyze data"),
                ("TECHNOLOGY", "Europa Clipper spacecraft"),
            ),
            "ambiguous_plan": json.dumps({
                "decision": "ABSTAIN", "primary_subject": None, "domains": [],
            }),
        }
        report = score_classification_predictions(approved, preds)
        self.assertEqual(report["approved"], 3)
        self.assertEqual(report["predicted"], 3)
        self.assertEqual(report["exact_matches"], 3)
        self.assertEqual(report["safe_abstentions"], 1)
        self.assertEqual(report["potential_scope_leaks"], 0)
        self.assertTrue(report["coverage_complete"])
        self.assertEqual(report["exact_match_rate"], 1.0)
        self.assertIs(report["eligible_for_automatic_enforcement"], False)

    def test_wrong_or_overconfident_domains_show_potential_scope_leaks(self):
        approved = _approve(
            self.cases, "science_telescope", "cross_spacecraft",
            "ambiguous_plan", "injection_civic", "technology_patch",
        )
        preds = {
            "science_telescope": json.dumps({
                "decision": "ABSTAIN", "primary_subject": None, "domains": [],
            }),
            "cross_spacecraft": valid_response((
                "SCIENCE", "scientists would analyze data",
            )),
            "ambiguous_plan": valid_response((
                "TECHNOLOGY", "the plan was changed yesterday",
            )),
            "injection_civic": valid_response((
                "HEALTH", "fabricated quotation not in the claim",
            )),
        }
        report = score_classification_predictions(approved, preds)
        self.assertEqual(report["approved"], 5)
        self.assertEqual(report["predicted"], 4)
        self.assertEqual(report["missing"], 1)
        self.assertEqual(report["invalid_json_or_quotes"], 1)
        self.assertEqual(report["missed_classifications"], 1)
        self.assertEqual(report["wrong_domains"], 1)
        self.assertEqual(report["overclassified_abstentions"], 1)
        self.assertEqual(report["potential_scope_leaks"], 2)
        self.assertEqual(report["potential_scope_exclusions"], 1)
        self.assertEqual(
            report["problems_by_case_id"]["potential_scope_leaks"],
            ["cross_spacecraft", "ambiguous_plan"],
        )
        self.assertFalse(report["coverage_complete"])
        self.assertIsNone(report["exact_match_rate"])
        self.assertIs(report["eligible_for_automatic_enforcement"], False)

    def test_extra_subject_or_abstention_could_exclude_qualified_partners(self):
        approved = _approve(self.cases, "science_telescope", "cross_spacecraft")
        predictions = {
            "science_telescope": valid_response(
                ("SCIENCE", "Astronomers published telescope observations"),
                ("TECHNOLOGY", "telescope observations"),
            ),
            "cross_spacecraft": json.dumps({
                "decision": "ABSTAIN", "primary_subject": None, "domains": [],
            }),
        }
        report = score_classification_predictions(approved, predictions)
        self.assertEqual(report["wrong_domains"], 1)
        self.assertEqual(report["missed_classifications"], 1)
        self.assertEqual(report["potential_scope_exclusions"], 2)
        self.assertEqual(report["potential_scope_leaks"], 0)
        self.assertEqual(
            report["problems_by_case_id"]["potential_scope_exclusions"],
            ["science_telescope", "cross_spacecraft"],
        )
        self.assertIs(report["eligible_for_automatic_enforcement"], False)

    def test_command_scores_only_human_approved_references(self):
        approved = _approve(self.cases, "science_telescope")
        corpus = _write(self.root / "approved.json", {
            "schema_version": 1, "cases": approved,
        })
        predictions = _write(self.root / "predictions.json", {
            "schema_version": 1,
            "predictions": [
                {"case_id": "science_telescope", "raw_response":
                    valid_response((
                        "SCIENCE", "Astronomers published telescope observations",
                    ))},
            ],
        })
        buf = StringIO()
        call_command("audit_investigation_classification",
                     "--corpus", str(corpus),
                     "--predictions", str(predictions),
                     "--json-summary", stdout=buf)
        output = json.loads(buf.getvalue())
        self.assertEqual(output["status"], "DESCRIPTIVE_AUDIT_ONLY")
        self.assertEqual(output["evaluation"]["exact_matches"], 1)
        self.assertEqual(output["evaluation"]["exact_match_rate"], 1.0)
        self.assertIs(output["enforcement_approved"], False)
        self.assertNotIn("Astronomers published", buf.getvalue())

    def test_command_with_unapproved_predictions_never_reports_accuracy(self):
        predictions = _write(self.root / "unreviewed.json", {
            "schema_version": 1,
            "predictions": [
                {"case_id": "science_telescope", "raw_response":
                    valid_response((
                        "SCIENCE", "Astronomers published telescope observations",
                    ))},
            ],
        })
        buf = StringIO()
        call_command("audit_investigation_classification",
                     "--predictions", str(predictions), stdout=buf)
        self.assertIn("NOT SCORED", buf.getvalue())
