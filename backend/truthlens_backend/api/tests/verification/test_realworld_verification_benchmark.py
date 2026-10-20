"""Offline assurance for the real-world benchmark review and scoring gates."""
import copy
import io
import json
from collections import Counter
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.realworld_benchmark import load_corpus, reviewed_gold_verdict


class RealWorldCorpusReviewTests(SimpleTestCase):
    def test_curated_source_linked_corpus_is_unapproved(self):
        cases = load_corpus()
        self.assertEqual(len(cases), 30)
        self.assertEqual(
            Counter(c["proposed_verdict"] for c in cases),
            Counter({"FACT": 14, "FAKE": 12, "MISLEADING": 2, "UNVERIFIED": 2}),
        )
        self.assertEqual(len({c["domain"] for c in cases}), 12)
        self.assertGreaterEqual(
            sum(c["language"] == "fil" for c in cases), 5
        )
        self.assertTrue(all(c["review"]["status"] == "PENDING" for c in cases))
        self.assertTrue(all(reviewed_gold_verdict(c) is None for c in cases))
        self.assertTrue(all(
            src["url"].startswith("https://")
            for c in cases for src in c["sources"]
        ))

    def test_approval_needs_independent_reviewer_and_confirmed_provenance(self):
        case = copy.deepcopy(load_corpus()[0])
        case["review"] = {"status": "APPROVED"}
        with self.assertRaises(ValidationError):
            reviewed_gold_verdict(case)
        case["review"] = {
            "status": "APPROVED",
            "reviewer": "independent-reviewer",
            "reviewed_at": "2026-10-20",
            "approved_verdict": "FACT",
            "rationale": "Checked the constitutional provision independently.",
            "source_checked": True,
        }
        self.assertEqual(reviewed_gold_verdict(case), "FACT")
        case["review"]["source_checked"] = False
        with self.assertRaises(ValidationError):
            reviewed_gold_verdict(case)


class RealWorldBenchmarkCommandTests(SimpleTestCase):
    def _approved_case(self, idx=0):
        case = copy.deepcopy(load_corpus()[idx])
        case["review"] = {
            "status": "APPROVED",
            "reviewer": "test-reviewer",
            "reviewed_at": "2026-10-20",
            "approved_verdict": case["proposed_verdict"],
            "rationale": "Primary source has been independently inspected.",
            "source_checked": True,
        }
        return case

    def test_dry_run_reports_candidate_counts_without_calling_any_provider(self):
        out = io.StringIO()
        with patch(
            "api.management.commands.evaluate_realworld_verification_providers.generate_evaluation_json"
        ) as cloudflare:
            call_command("evaluate_realworld_verification_providers", stdout=out)
        self.assertIn("30 candidates", out.getvalue())
        self.assertIn("approved=0", out.getvalue())
        self.assertIn("pending=30", out.getvalue())
        self.assertIn("DRY RUN ONLY", out.getvalue())
        cloudflare.assert_not_called()

    @override_settings(DEBUG=True)
    def test_live_refuses_provisional_labels_without_calls(self):
        with patch.dict("os.environ", {"ENABLE_CLOUDFLARE_EVALUATION": "1"}):
            with patch(
                "api.management.commands.evaluate_realworld_verification_providers.generate_evaluation_json"
            ) as cloudflare, self.assertRaisesRegex(CommandError, "No independently APPROVED"):
                call_command("evaluate_realworld_verification_providers", live=True)
        cloudflare.assert_not_called()

    @override_settings(DEBUG=False)
    def test_live_rejects_non_development_environment(self):
        with self.assertRaisesRegex(CommandError, "DEBUG=True"):
            call_command("evaluate_realworld_verification_providers", live=True)

    @override_settings(DEBUG=True)
    def test_scoring_uses_original_evidence_prompt_and_reviewed_label(self):
        case = self._approved_case()
        # Review label is independent of provisional label.
        case["review"]["approved_verdict"] = "FACT"
        valid = json.dumps({
            "reasoning": "The evidence explicitly supports the claim.",
            "verdict": "FACT",
            "summary": "Supported by the supplied evidence.",
            "confidence_score": 90,
            "score_context": "Direct documentary support in the dossier.",
        })
        out = io.StringIO()
        with (
            patch.dict("os.environ", {
                "ENABLE_CLOUDFLARE_EVALUATION": "1",
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                "CLOUDFLARE_API_TOKEN": "test-token-secret",
            }),
            patch(
                "api.management.commands.evaluate_realworld_verification_providers.load_corpus",
                return_value=[case],
            ),
            patch(
                "api.management.commands.evaluate_realworld_verification_providers.generate_evaluation_json",
                return_value=valid,
            ) as llm,
        ):
            call_command(
                "evaluate_realworld_verification_providers",
                live=True, case=[case["id"]], limit=1, stdout=out,
            )
        self.assertEqual(llm.call_count, 1)
        system, user = llm.call_args.args
        self.assertIn("SOURCE IDENTITY GROUP", system)
        self.assertIn(case["claim"], user)
        self.assertIn(case["evidence_snapshot"], user)
        self.assertNotIn(case["label_reason"], user)
        self.assertEqual(llm.call_args.kwargs["max_completion_tokens"], 2048)
        self.assertIn("matched=1/1", out.getvalue())
        self.assertIn("CONFUSION provider=cloudflare expected=FACT actual=FACT", out.getvalue())
        self.assertNotIn("test-token-secret", out.getvalue())

    @override_settings(DEBUG=True)
    def test_quota_error_stops_additional_provider_calls(self):
        cases = [self._approved_case(0), self._approved_case(1)]
        out = io.StringIO()
        with (
            patch.dict("os.environ", {
                "ENABLE_CLOUDFLARE_EVALUATION": "1",
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                "CLOUDFLARE_API_TOKEN": "test-token-secret",
            }),
            patch(
                "api.management.commands.evaluate_realworld_verification_providers.load_corpus",
                return_value=cases,
            ),
            patch(
                "api.management.commands.evaluate_realworld_verification_providers.generate_evaluation_json",
                side_effect=CloudflareEvaluationError("HTTP_429"),
            ) as llm,
        ):
            call_command(
                "evaluate_realworld_verification_providers",
                live=True, limit=2, stdout=out,
            )
        llm.assert_called_once()
        self.assertIn("error=HTTP_429", out.getvalue())
        self.assertIn("no further requests to that provider", out.getvalue())
        self.assertIn("matched=0/1 valid=0 errors=1", out.getvalue())
        self.assertNotIn("verdict=UNVERIFIED", out.getvalue())

    @override_settings(DEBUG=True)
    def test_missing_json_contract_does_not_count_as_correct_unverified(self):
        case = self._approved_case(29)
        out = io.StringIO()
        with (
            patch.dict("os.environ", {
                "ENABLE_CLOUDFLARE_EVALUATION": "1",
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                "CLOUDFLARE_API_TOKEN": "test-token-secret",
            }),
            patch(
                "api.management.commands.evaluate_realworld_verification_providers.load_corpus",
                return_value=[case],
            ),
            patch(
                "api.management.commands.evaluate_realworld_verification_providers.generate_evaluation_json",
                return_value="{}",
            ),
        ):
            call_command(
                "evaluate_realworld_verification_providers",
                live=True, case=[case["id"]], stdout=out,
            )
        self.assertIn("contract_ok=False", out.getvalue())
        self.assertIn("matched=0/1 valid=0 errors=0", out.getvalue())

    def test_unknown_case_and_invalid_budget_rejected_without_network(self):
        for kwargs in (
            {"case": ["unrecognized-id"]},
            {"max_completion_tokens": 4097},
            {"limit": 31},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(CommandError):
                call_command("evaluate_realworld_verification_providers", **kwargs)
