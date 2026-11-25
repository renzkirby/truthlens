import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from api.management.commands.compare_cloudflare_assessment_chunk_sizes import (
    _causal_summary,
    _compare_arms,
    _experimental_chunk_plan,
)
from api.models import Claim, VerificationEvidence
from api.verification.evidence_assessment import EvidenceAssessment


def _assessment(stance, relevance=0.9, directness=0.8):
    return EvidenceAssessment(
        stance=stance,
        relevance_score=relevance,
        directness_score=directness,
    )


def _item(content="Frozen evidence passage."):
    return SimpleNamespace(
        evidence_link_id=uuid4(),
        stance=VerificationEvidence.Stance.UNKNOWN,
        relevance_score=None,
        directness_score=None,
        content=content,
    )


def _groups(item_counts=(2, 2, 2, 2, 2)):
    groups = []
    for count in item_counts:
        members = [_item() for _ in range(count)]
        groups.append((uuid4(), members))
    return groups


def _arm(assessments, *, chunks, duration_ms):
    return {
        "success": True,
        "duration_ms": duration_ms,
        "error_code": "",
        "chunks_attempted": chunks,
        "metadata": {},
        "assessments": assessments,
    }


class CloudflareChunkPlanTests(SimpleTestCase):
    def test_ten_items_plan_as_five_plus_five_without_dropping_keys(self):
        rows = [
            {
                "key": f"item_{index}",
                "evidence_content": f"Evidence passage {index}.",
            }
            for index in range(10)
        ]
        prompt = "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps({
            "claim_text": "A test claim.",
            "evidence_items": rows,
        })

        chunks, keys = _experimental_chunk_plan(
            "System instructions.",
            prompt,
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(keys, [f"item_{index}" for index in range(10)])
        parsed_sizes = [
            len(json.loads(chunk.split("\n", 1)[1])["evidence_items"])
            for chunk in chunks
        ]
        self.assertEqual(parsed_sizes, [5, 5])

    def test_char_limit_can_force_more_than_two_chunks_without_trimming(self):
        rows = [
            {
                "key": f"item_{index}",
                "evidence_content": "x" * 100,
            }
            for index in range(9)
        ]
        prompt = "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps({
            "claim_text": "A test claim.",
            "evidence_items": rows,
        })

        chunks, keys = _experimental_chunk_plan(
            "system",
            prompt,
            max_input_chars=500,
        )

        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual(keys, [f"item_{index}" for index in range(9)])


class CloudflareChunkComparisonTests(SimpleTestCase):
    def test_aa_control_stable_and_candidate_stable_passes(self):
        summary = _causal_summary(
            {"quality_gate": "PASS"},
            {"quality_gate": "PASS"},
        )
        self.assertEqual(summary["quality_gate"], "PASS")
        self.assertEqual(
            summary["causal_interpretation"],
            "NO_SEMANTIC_DRIFT_DETECTED",
        )

    def test_aa_control_drift_makes_candidate_result_inconclusive(self):
        summary = _causal_summary(
            {"quality_gate": "REVIEW"},
            {"quality_gate": "REVIEW"},
        )
        self.assertEqual(summary["quality_gate"], "INCONCLUSIVE")
        self.assertEqual(
            summary["causal_interpretation"],
            "MODEL_NONDETERMINISM_PRESENT",
        )

    def test_stable_aa_with_candidate_drift_flags_chunk_size_effect(self):
        summary = _causal_summary(
            {"quality_gate": "PASS"},
            {"quality_gate": "REVIEW"},
        )
        self.assertEqual(summary["quality_gate"], "REVIEW")
        self.assertEqual(
            summary["causal_interpretation"],
            "CHUNK_SIZE_EFFECT_PLAUSIBLE",
        )

    def test_aa_control_uses_three_chunk_expectation(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]

        result = _compare_arms(
            groups,
            items,
            _arm(values, chunks=3, duration_ms=2000),
            _arm(values, chunks=3, duration_ms=2100),
            expected_candidate_chunks=3,
            candidate_label="CONTROL",
        )

        self.assertEqual(result["quality_gate"], "PASS")
        self.assertNotIn("CONTROL_NOT_3_CHUNKS", result["review_reasons"])

    def test_lossless_stable_assessments_pass(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        baseline_values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]
        candidate_values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS, 0.95, 0.9)
            for _ in items
        ]

        result = _compare_arms(
            groups,
            items,
            _arm(baseline_values, chunks=3, duration_ms=2000),
            _arm(candidate_values, chunks=2, duration_ms=1300),
        )

        self.assertEqual(result["quality_gate"], "PASS")
        self.assertEqual(result["review_reasons"], [])
        self.assertTrue(result["all_items_assessed"])
        self.assertTrue(result["all_item_stances_match"])
        self.assertTrue(result["decisive_identity_topology_match"])
        self.assertEqual(result["latency_delta_ms"], -700)

    def test_selected_stance_drift_requires_review(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        baseline_values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]
        candidate_values = list(baseline_values)
        candidate_values[0] = _assessment(
            VerificationEvidence.Stance.CONTEXT
        )

        result = _compare_arms(
            groups,
            items,
            _arm(baseline_values, chunks=3, duration_ms=2000),
            _arm(candidate_values, chunks=2, duration_ms=1300),
        )

        self.assertEqual(result["quality_gate"], "REVIEW")
        self.assertIn("ITEM_STANCE_CHANGED", result["review_reasons"])
        # The first identity still has another SUPPORTS item, so item-level
        # drift must not be mislabeled as decisive identity-topology loss.
        self.assertNotIn(
            "DECISIVE_IDENTITY_TOPOLOGY_CHANGED",
            result["review_reasons"],
        )

    def test_losing_identity_only_decisive_stance_requires_review(self):
        groups = _groups(item_counts=(1, 2, 2, 2, 2))
        items = [item for _identity_id, members in groups for item in members]
        baseline_values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]
        candidate_values = list(baseline_values)
        candidate_values[0] = _assessment(
            VerificationEvidence.Stance.CONTEXT
        )

        result = _compare_arms(
            groups,
            items,
            _arm(baseline_values, chunks=3, duration_ms=2000),
            _arm(candidate_values, chunks=2, duration_ms=1300),
        )

        self.assertEqual(result["quality_gate"], "REVIEW")
        self.assertIn("ITEM_STANCE_CHANGED", result["review_reasons"])
        self.assertIn(
            "DECISIVE_IDENTITY_TOPOLOGY_CHANGED",
            result["review_reasons"],
        )

    def test_large_score_shift_requires_review_even_when_stance_matches(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        baseline_values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS, 0.9, 0.9)
            for _ in items
        ]
        candidate_values = list(baseline_values)
        candidate_values[0] = _assessment(
            VerificationEvidence.Stance.SUPPORTS,
            0.6,
            0.6,
        )

        result = _compare_arms(
            groups,
            items,
            _arm(baseline_values, chunks=3, duration_ms=2000),
            _arm(candidate_values, chunks=2, duration_ms=1300),
        )

        self.assertEqual(result["quality_gate"], "REVIEW")
        self.assertIn(
            "ITEM_SCORE_SHIFT_GT_0_20",
            result["review_reasons"],
        )

    def test_wrong_chunk_counts_are_invalid(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]

        result = _compare_arms(
            groups,
            items,
            _arm(values, chunks=2, duration_ms=1000),
            _arm(values, chunks=2, duration_ms=900),
        )

        self.assertEqual(result["quality_gate"], "INVALID")
        self.assertIn(
            "BASELINE_NOT_THREE_CHUNKS",
            result["review_reasons"],
        )


class CloudflareChunkSizeCommandTests(TestCase):
    @override_settings(APP_ENV="production", DEBUG=False)
    def test_command_is_development_only(self):
        with self.assertRaises(CommandError):
            call_command(
                "compare_cloudflare_assessment_chunk_sizes",
                claims=["A test claim."],
            )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_retrieval_runs_once_and_database_is_rolled_back(self):
        dossier_groups = [
            SimpleNamespace(
                identity_id=uuid4(),
                evidence=tuple(_item() for _ in range(2)),
            )
            for _ in range(5)
        ]
        all_items = [
            item for group in dossier_groups for item in group.evidence
        ]
        baseline_values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in all_items
        ]
        control_values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in all_items
        ]
        candidate_values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in all_items
        ]
        seen_ids = []

        def baseline_arm(system, prompt, claim_text, evidence_items):
            seen_ids.append(tuple(
                item.evidence_link_id for item in evidence_items
            ))
            return _arm(
                baseline_values,
                chunks=3,
                duration_ms=2000,
            )

        def control_arm(system, prompt, claim_text, evidence_items):
            seen_ids.append(tuple(
                item.evidence_link_id for item in evidence_items
            ))
            return _arm(
                control_values,
                chunks=3,
                duration_ms=2100,
            )

        def candidate_arm(system, prompt, claim_text, evidence_items):
            seen_ids.append(tuple(
                item.evidence_link_id for item in evidence_items
            ))
            return _arm(
                candidate_values,
                chunks=2,
                duration_ms=1300,
            )

        before_claims = Claim.objects.count()
        output = io.StringIO()

        with (
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "tasks._retrieve_and_ingest_tavily_queries",
                return_value={"results": []},
            ) as retrieval,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "load_reasoning_evidence_dossier_for_run",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "filter_reasoning_evidence_dossier_by_role",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_baseline_arm",
                side_effect=baseline_arm,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_control_arm",
                side_effect=control_arm,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_candidate_arm",
                side_effect=candidate_arm,
            ),
        ):
            call_command(
                "compare_cloudflare_assessment_chunk_sizes",
                claims=["A test claim."],
                json=True,
                stdout=output,
            )

        report = json.loads(output.getvalue())[0]
        retrieval.assert_called_once()
        self.assertEqual(len(seen_ids), 3)
        self.assertEqual(seen_ids[0], seen_ids[1])
        self.assertEqual(seen_ids[0], seen_ids[2])
        self.assertEqual(Claim.objects.count(), before_claims)
        self.assertTrue(report["database_isolated"])
        self.assertEqual(report["frozen_evidence"]["item_count"], 10)
        self.assertEqual(
            report["frozen_evidence"]["baseline_planned_chunks"],
            3,
        )
        self.assertEqual(
            report["frozen_evidence"]["candidate_planned_chunks"],
            2,
        )
        self.assertEqual(report["quality_gate"], "PASS")
        self.assertEqual(
            report["causal_interpretation"],
            "NO_SEMANTIC_DRIFT_DETECTED",
        )
        self.assertEqual(
            report["control_comparison"]["quality_gate"],
            "PASS",
        )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_eleven_item_batch_is_skipped_before_provider_arms(self):
        dossier_groups = [
            SimpleNamespace(
                identity_id=uuid4(),
                evidence=tuple(_item() for _ in range(count)),
            )
            for count in (3, 2, 2, 2, 2)
        ]

        output = io.StringIO()
        with (
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "tasks._retrieve_and_ingest_tavily_queries",
                return_value={"results": []},
            ) as retrieval,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "load_reasoning_evidence_dossier_for_run",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "filter_reasoning_evidence_dossier_by_role",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_baseline_arm",
            ) as baseline,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_control_arm",
            ) as control,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_candidate_arm",
            ) as candidate,
        ):
            call_command(
                "compare_cloudflare_assessment_chunk_sizes",
                claims=["A test claim."],
                json=True,
                stdout=output,
            )

        report = json.loads(output.getvalue())[0]
        self.assertEqual(report["quality_gate"], "SKIPPED")
        self.assertEqual(
            report["eligibility"],
            "NOT_NINE_TO_TEN_ITEM_ELIGIBLE",
        )
        self.assertEqual(report["frozen_evidence"]["item_count"], 11)
        retrieval.assert_called_once()
        baseline.assert_not_called()
        control.assert_not_called()
        candidate.assert_not_called()

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_command_stops_after_baseline_429(self):
        dossier_groups = [
            SimpleNamespace(
                identity_id=uuid4(),
                evidence=tuple(_item() for _ in range(2)),
            )
            for _ in range(5)
        ]
        calls = []

        def baseline_arm(system, prompt, claim_text, evidence_items):
            calls.append(claim_text)
            return {
                "success": False,
                "duration_ms": 500,
                "error_code": "HTTP_429",
                "chunks_attempted": 1,
                "metadata": {},
                "assessments": [],
            }

        output = io.StringIO()
        with (
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "tasks._retrieve_and_ingest_tavily_queries",
                return_value={"results": []},
            ) as retrieval,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "load_reasoning_evidence_dossier_for_run",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "filter_reasoning_evidence_dossier_by_role",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_baseline_arm",
                side_effect=baseline_arm,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_control_arm",
            ) as control,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_candidate_arm",
            ) as candidate,
        ):
            call_command(
                "compare_cloudflare_assessment_chunk_sizes",
                claims=["A test claim.", "A second claim."],
                json=True,
                stdout=output,
            )

        report = json.loads(output.getvalue())
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["quality_gate"], "BLOCKED")
        self.assertEqual(
            report[0]["blocked_reason"],
            "CLOUDFLARE_HTTP_429",
        )
        self.assertEqual(calls, ["A test claim."])
        retrieval.assert_called_once()
        control.assert_not_called()
        candidate.assert_not_called()

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_command_stops_after_control_429(self):
        dossier_groups = [
            SimpleNamespace(
                identity_id=uuid4(),
                evidence=tuple(_item() for _ in range(2)),
            )
            for _ in range(5)
        ]
        values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for group in dossier_groups
            for _item_value in group.evidence
        ]

        output = io.StringIO()
        with (
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "tasks._retrieve_and_ingest_tavily_queries",
                return_value={"results": []},
            ) as retrieval,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "load_reasoning_evidence_dossier_for_run",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "filter_reasoning_evidence_dossier_by_role",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_baseline_arm",
                return_value=_arm(values, chunks=3, duration_ms=1000),
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_control_arm",
                return_value={
                    "success": False,
                    "duration_ms": 400,
                    "error_code": "HTTP_429",
                    "chunks_attempted": 1,
                    "metadata": {},
                    "assessments": [],
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_sizes."
                "_run_candidate_arm",
            ) as candidate,
        ):
            call_command(
                "compare_cloudflare_assessment_chunk_sizes",
                claims=["A test claim.", "A second claim."],
                json=True,
                stdout=output,
            )

        report = json.loads(output.getvalue())
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["quality_gate"], "BLOCKED")
        self.assertEqual(
            report[0]["blocked_reason"],
            "CLOUDFLARE_HTTP_429",
        )
        retrieval.assert_called_once()
        candidate.assert_not_called()

