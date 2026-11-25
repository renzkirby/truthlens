import io
import json
import os
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from api.models import Claim, VerificationRun, VerificationTelemetryEvent
from api.management.commands.compare_evidence_assessment_budget import (
    _UpstreamReplayTape,
    _compare_arms,
)


def _arm(**overrides):
    result = {
        "adaptive": False,
        "status": VerificationRun.Status.COMPLETED,
        "verdict": "FACT",
        "confidence": 90,
        "summary": "Summary.",
        "score_context": "Context.",
        "duration_ms": 1000,
        "exception_type": "",
        "evidence_total": 6,
        "evidence_assessed": 6,
        "source_identity_count": 6,
        "stance_counts": {"SUPPORTS": 6},
        "assessment_stages": [],
        "assessment_provider_calls": [],
        "run_id": None,
    }
    result.update(overrides)
    return result


class AdaptiveEvidenceAssessmentABComparisonTests(TestCase):
    def test_matching_noncontextual_result_passes_automated_gate(self):
        baseline = _arm()
        adaptive = _arm(adaptive=True, duration_ms=700)

        result = _compare_arms(baseline, adaptive)

        self.assertEqual(result["automated_gate"], "PASS")
        self.assertTrue(result["verdict_match"])
        self.assertEqual(result["latency_delta_ms"], -300)
        self.assertEqual(result["latency_change_pct"], -30.0)

    def test_more_decisive_adaptive_result_requires_review(self):
        baseline = _arm(verdict="UNVERIFIED", confidence=20)
        adaptive = _arm(adaptive=True, verdict="FACT", confidence=90)

        result = _compare_arms(baseline, adaptive)

        self.assertEqual(result["automated_gate"], "REVIEW")
        self.assertIn("VERDICT_CHANGED", result["review_reasons"])
        self.assertIn("ADAPTIVE_MORE_DECISIVE", result["review_reasons"])
        self.assertIn("CONFIDENCE_SHIFT_GT_15", result["review_reasons"])

    def test_contextual_verdict_always_requires_manual_review(self):
        baseline = _arm(verdict="MISLEADING", confidence=80)
        adaptive = _arm(adaptive=True, verdict="MISLEADING", confidence=80)

        result = _compare_arms(baseline, adaptive)

        self.assertEqual(result["automated_gate"], "REVIEW")
        self.assertIn(
            "CONTEXTUAL_VERDICT_MANUAL_REVIEW",
            result["review_reasons"],
        )




class AdaptiveEvidenceAssessmentReplayTapeTests(TestCase):
    def test_replay_returns_recorded_result_without_recalling_provider(self):
        tape = _UpstreamReplayTape()
        calls = []

        def provider(value, *, limit=5):
            calls.append((value, limit))
            return {"value": value, "limit": limit}

        with patch(
            "api.management.commands.compare_evidence_assessment_budget.time.sleep"
        ) as sleep:
            baseline = tape.call_function(
                "claim_gate",
                provider,
                False,
                "claim",
                limit=4,
            )
            tape.begin_replay()
            adaptive = tape.call_function(
                "claim_gate",
                provider,
                True,
                "claim",
                limit=4,
            )

        self.assertEqual(baseline, adaptive)
        self.assertEqual(calls, [("claim", 4)])
        self.assertTrue(tape.replay_complete())
        self.assertLessEqual(sleep.call_count, 1)

    def test_replay_input_change_is_rejected(self):
        tape = _UpstreamReplayTape()
        tape.call_function("claim_gate", lambda value: value, False, "claim")
        tape.begin_replay()

        with self.assertRaises(RuntimeError):
            tape.call_function(
                "claim_gate",
                lambda value: value,
                True,
                "different claim",
            )


class AdaptiveEvidenceAssessmentABCommandTests(TestCase):
    @override_settings(APP_ENV="production", DEBUG=False)
    def test_command_is_restricted_to_local_development(self):
        with self.assertRaises(CommandError):
            call_command(
                "compare_evidence_assessment_budget",
                claims=["A test claim."],
            )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_live_harness_switches_flag_bypasses_reuse_and_cleans_temp_claims(self):
        seen_flags = []
        seen_claim_ids = []

        def fake_pipeline(claim_text, claim_id, triggered_by_id=None):
            from api import claim_matching, tasks

            self.assertEqual(
                claim_matching.find_matching_claim(
                    "fingerprint",
                    Claim.ClaimType.TEXT,
                ),
                None,
            )
            self.assertIsNone(tasks.search_official_vault(claim_text))
            self.assertFalse(tasks._resolve_exact_published_claim(None, claim_text))
            self.assertFalse(
                tasks._resolve_equivalent_published_claim(
                    None,
                    claim_text,
                    None,
                )
            )

            seen_flags.append(
                os.getenv(tasks.EVIDENCE_ASSESSMENT_BUDGET_FLAG)
            )
            seen_claim_ids.append(str(claim_id))

            claim = Claim.objects.get(pk=claim_id)
            claim.ai_verdict = "FACT"
            claim.consensus_score = 90
            claim.ai_summary = "Synthetic harness result."
            claim.score_context = "Synthetic harness score."
            claim.save(
                update_fields=[
                    "ai_verdict",
                    "consensus_score",
                    "ai_summary",
                    "score_context",
                    "last_updated",
                ]
            )

            now = timezone.now()
            run = VerificationRun.objects.create(
                claim=claim,
                status=VerificationRun.Status.COMPLETED,
                pipeline_version="test",
                started_at=now,
                completed_at=now + timedelta(milliseconds=100),
            )
            VerificationTelemetryEvent.objects.create(
                verification_run=run,
                sequence=1,
                event_type=VerificationTelemetryEvent.EventType.PIPELINE_STAGE,
                name="tavily_evidence_assessment_batch",
                duration_ms=50,
                outcome="",
                metadata={
                    "eligible_items": 6,
                    "selected_items": 4 if seen_flags[-1] == "1" else 6,
                    "deferred_items": 2 if seen_flags[-1] == "1" else 0,
                    "assessment_waves": 1,
                    "adaptive_budget": seen_flags[-1] == "1",
                    "early_stopped": seen_flags[-1] == "1",
                },
                occurred_at=now,
            )

        before_claims = Claim.objects.count()
        output = io.StringIO()

        with patch(
            "api.tasks.execute_core_text_pipeline",
            side_effect=fake_pipeline,
        ):
            call_command(
                "compare_evidence_assessment_budget",
                claims=["A test claim."],
                json=True,
                stdout=output,
            )

        report = json.loads(output.getvalue())
        self.assertEqual(seen_flags, ["0", "1"])
        self.assertEqual(len(set(seen_claim_ids)), 2)
        self.assertEqual(Claim.objects.count(), before_claims)
        self.assertEqual(report[0]["baseline"]["verdict"], "FACT")
        self.assertEqual(report[0]["adaptive"]["verdict"], "FACT")
        self.assertEqual(
            report[0]["comparison"]["automated_gate"],
            "PASS",
        )
        self.assertEqual(
            report[0]["adaptive"]["assessment_stages"][0]["metadata"][
                "selected_items"
            ],
            4,
        )
