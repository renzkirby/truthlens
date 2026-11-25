import io
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from api.management.commands.compare_cloudflare_assessment_chunk_concurrency import (
    _causal_summary,
    _compare_arms,
    _full_prompt,
    _material_scope_system_instructions,
    _run_candidate_arm,
)
from api.models import Claim, VerificationEvidence
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.cloudflare_pilot import _assessment_chunk_plan
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
    return [
        (uuid4(), [_item() for _ in range(count)])
        for count in item_counts
    ]


def _arm(assessments, *, chunks=3, duration_ms=1000):
    return {
        "success": True,
        "duration_ms": duration_ms,
        "error_code": "",
        "chunks_attempted": chunks,
        "metadata": {},
        "assessments": assessments,
    }


def _raw_assessments_for_prompt(prompt):
    payload = json.loads(prompt.split("\n", 1)[1])
    return json.dumps({
        "assessments": [
            {
                "key": row["key"],
                "stance": VerificationEvidence.Stance.SUPPORTS,
                "relevance_score": 0.9,
                "directness_score": 0.8,
            }
            for row in payload["evidence_items"]
        ]
    })


class CloudflareConcurrencyCandidateTests(SimpleTestCase):
    def test_candidate_uses_exact_production_chunks_with_max_two_in_flight(self):
        evidence_items = [_item(f"Evidence {index}") for index in range(10)]
        system = _material_scope_system_instructions()
        prompt = _full_prompt("A test claim.", evidence_items)
        expected_prompts, _ = _assessment_chunk_plan(system, prompt)

        lock = threading.Lock()
        active = 0
        max_active = 0
        seen_prompts = []

        def fake_call(system_instructions, user_prompt, **kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                seen_prompts.append(user_prompt)
            time.sleep(0.03)
            try:
                return _raw_assessments_for_prompt(user_prompt)
            finally:
                with lock:
                    active -= 1

        with patch(
            "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
            "call_validated_cloudflare_pilot",
            side_effect=fake_call,
        ):
            result = _run_candidate_arm(
                system,
                prompt,
                "A test claim.",
                evidence_items,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["chunks_attempted"], 3)
        self.assertEqual(result["metadata"]["max_concurrency"], 2)
        self.assertEqual(result["metadata"]["waves_attempted"], 2)
        self.assertEqual(max_active, 2)
        self.assertCountEqual(seen_prompts, expected_prompts)
        self.assertEqual(len(result["assessments"]), 10)

    def test_candidate_does_not_start_third_chunk_after_first_wave_429(self):
        evidence_items = [_item(f"Evidence {index}") for index in range(10)]
        system = _material_scope_system_instructions()
        prompt = _full_prompt("A test claim.", evidence_items)
        expected_prompts, _ = _assessment_chunk_plan(system, prompt)
        seen_prompts = []
        lock = threading.Lock()

        def fake_call(system_instructions, user_prompt, **kwargs):
            with lock:
                seen_prompts.append(user_prompt)
            if user_prompt == expected_prompts[0]:
                raise CloudflareEvaluationError("HTTP_429")
            time.sleep(0.02)
            return _raw_assessments_for_prompt(user_prompt)

        with patch(
            "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
            "call_validated_cloudflare_pilot",
            side_effect=fake_call,
        ):
            result = _run_candidate_arm(
                system,
                prompt,
                "A test claim.",
                evidence_items,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "HTTP_429")
        self.assertEqual(result["chunks_attempted"], 2)
        self.assertEqual(result["metadata"]["waves_attempted"], 1)
        self.assertCountEqual(seen_prompts, expected_prompts[:2])
        self.assertNotIn(expected_prompts[2], seen_prompts)


class CloudflareConcurrencyComparisonTests(SimpleTestCase):
    def test_stable_control_and_candidate_pass(self):
        groups = _groups()
        items = [item for _identity, members in groups for item in members]
        values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]

        control = _compare_arms(
            groups,
            items,
            _arm(values, duration_ms=2000),
            _arm(values, duration_ms=2100),
            candidate_label="CONTROL",
        )
        candidate = _compare_arms(
            groups,
            items,
            _arm(values, duration_ms=2000),
            _arm(values, duration_ms=1300),
        )
        causal = _causal_summary(control, candidate)

        self.assertEqual(control["quality_gate"], "PASS")
        self.assertEqual(candidate["quality_gate"], "PASS")
        self.assertEqual(causal["quality_gate"], "PASS")
        self.assertEqual(
            causal["causal_interpretation"],
            "NO_SEMANTIC_DRIFT_DETECTED",
        )

    def test_stable_control_with_candidate_stance_drift_flags_concurrency(self):
        groups = _groups(item_counts=(1, 2, 2, 2, 2))
        items = [item for _identity, members in groups for item in members]
        baseline_values = [
            _assessment(VerificationEvidence.Stance.REFUTES)
            for _ in items
        ]
        candidate_values = list(baseline_values)
        candidate_values[0] = _assessment(
            VerificationEvidence.Stance.CONTEXT,
            relevance=0.7,
            directness=0.2,
        )

        control = _compare_arms(
            groups,
            items,
            _arm(baseline_values),
            _arm(baseline_values),
            candidate_label="CONTROL",
        )
        candidate = _compare_arms(
            groups,
            items,
            _arm(baseline_values),
            _arm(candidate_values),
        )
        causal = _causal_summary(control, candidate)

        self.assertEqual(control["quality_gate"], "PASS")
        self.assertEqual(candidate["quality_gate"], "REVIEW")
        self.assertIn("ITEM_STANCE_CHANGED", candidate["review_reasons"])
        self.assertIn(
            "DECISIVE_IDENTITY_TOPOLOGY_CHANGED",
            candidate["review_reasons"],
        )
        self.assertEqual(causal["quality_gate"], "REVIEW")
        self.assertEqual(
            causal["causal_interpretation"],
            "CONCURRENCY_EFFECT_PLAUSIBLE",
        )

    def test_control_drift_makes_result_inconclusive(self):
        causal = _causal_summary(
            {"quality_gate": "REVIEW"},
            {"quality_gate": "PASS"},
        )

        self.assertEqual(causal["quality_gate"], "INCONCLUSIVE")
        self.assertEqual(
            causal["causal_interpretation"],
            "MODEL_NONDETERMINISM_PRESENT",
        )


class CloudflareConcurrencyCommandTests(TestCase):
    @override_settings(APP_ENV="production", DEBUG=False)
    def test_command_is_development_only(self):
        with self.assertRaises(CommandError):
            call_command(
                "compare_cloudflare_assessment_chunk_concurrency",
                claims=["A test claim."],
            )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_retrieval_runs_once_all_arms_share_frozen_items_and_rollback(self):
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
        values = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in all_items
        ]
        seen_ids = []

        def arm(duration_ms):
            def runner(system, prompt, claim_text, evidence_items):
                seen_ids.append(tuple(
                    item.evidence_link_id for item in evidence_items
                ))
                return _arm(values, duration_ms=duration_ms)
            return runner

        before_claims = Claim.objects.count()
        output = io.StringIO()

        with (
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "tasks._retrieve_and_ingest_tavily_queries",
                return_value={"results": []},
            ) as retrieval,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "load_reasoning_evidence_dossier_for_run",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "filter_reasoning_evidence_dossier_by_role",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_baseline_arm",
                side_effect=arm(2000),
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_control_arm",
                side_effect=arm(2100),
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_candidate_arm",
                side_effect=arm(1300),
            ),
        ):
            call_command(
                "compare_cloudflare_assessment_chunk_concurrency",
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
            3,
        )
        self.assertEqual(report["quality_gate"], "PASS")
        self.assertEqual(
            report["causal_interpretation"],
            "NO_SEMANTIC_DRIFT_DETECTED",
        )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_non_three_chunk_batch_is_skipped_before_provider_arms(self):
        dossier_groups = [
            SimpleNamespace(
                identity_id=uuid4(),
                evidence=tuple(_item() for _ in range(2)),
            )
            for _ in range(4)
        ]
        output = io.StringIO()

        with (
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "tasks._retrieve_and_ingest_tavily_queries",
                return_value={"results": []},
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "load_reasoning_evidence_dossier_for_run",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "filter_reasoning_evidence_dossier_by_role",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_baseline_arm",
            ) as baseline,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_control_arm",
            ) as control,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_candidate_arm",
            ) as candidate,
        ):
            call_command(
                "compare_cloudflare_assessment_chunk_concurrency",
                claims=["A test claim."],
                json=True,
                stdout=output,
            )

        report = json.loads(output.getvalue())[0]
        self.assertEqual(report["quality_gate"], "SKIPPED")
        self.assertEqual(
            report["eligibility"],
            "NOT_THREE_CHUNK_ELIGIBLE",
        )
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
        output = io.StringIO()

        with (
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "tasks._retrieve_and_ingest_tavily_queries",
                return_value={"results": []},
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "load_reasoning_evidence_dossier_for_run",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "filter_reasoning_evidence_dossier_by_role",
                return_value=dossier_groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_baseline_arm",
                return_value={
                    "success": False,
                    "duration_ms": 500,
                    "error_code": "HTTP_429",
                    "chunks_attempted": 1,
                    "metadata": {},
                    "assessments": [],
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_control_arm",
            ) as control,
            patch(
                "api.management.commands.compare_cloudflare_assessment_chunk_concurrency."
                "_run_candidate_arm",
            ) as candidate,
        ):
            call_command(
                "compare_cloudflare_assessment_chunk_concurrency",
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
        control.assert_not_called()
        candidate.assert_not_called()
