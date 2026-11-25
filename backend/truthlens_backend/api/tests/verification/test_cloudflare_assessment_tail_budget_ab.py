import io
import json
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from api.models import Claim, VerificationRun, VerificationTelemetryEvent
from api.management.commands.compare_cloudflare_assessment_tail_budget import (
    _compare_arms,
    _forced_cloudflare_assessment,
)


def _arm(**overrides):
    values = {
        "status": VerificationRun.Status.COMPLETED,
        "verdict": "FACT",
        "confidence": 90,
        "summary": "Equivalent factual summary.",
        "score_context": "",
        "duration_ms": 1000,
        "exception_type": "",
        "evidence_total": 10,
        "evidence_assessed": 10,
        "source_identity_count": 5,
        "stance_counts": {"SUPPORTS": 10},
        "evidence_role_counts": {"SECONDARY": 10},
        "secondary_identity_stance_counts": {
            "ASSESSED": 5,
            "SUPPORTS": 5,
        },
        "assessment_stages": [],
        "assessment_provider_calls": [
            {
                "provider": "gemini",
                "outcome": "failed",
                "error_label": "_AssessmentGeminiQuotaError",
                "metadata": {},
            },
            {
                "provider": "cloudflare",
                "outcome": "success",
                "error_label": "",
                "metadata": {},
            },
        ],
        "database_isolated": True,
        "upstream_replay_complete": True,
    }
    values.update(overrides)
    return values


class CloudflareAssessmentTailBudgetABComparisonTests(SimpleTestCase):
    def test_equivalent_arms_pass_when_budget_applied(self):
        baseline = _arm()
        budgeted = _arm(
            evidence_assessed=8,
            duration_ms=700,
            assessment_provider_calls=[
                {
                    "provider": "gemini",
                    "outcome": "failed",
                    "error_label": "_AssessmentGeminiQuotaError",
                    "metadata": {},
                },
                {
                    "provider": "cloudflare",
                    "outcome": "success",
                    "error_label": "",
                    "metadata": {
                        "assessment_tail_budget_applied": True,
                        "assessment_items_original": 10,
                        "assessment_items_selected": 8,
                        "assessment_chunks_attempted": 2,
                    },
                },
            ],
        )

        result = _compare_arms(baseline, budgeted)

        self.assertEqual(result["automated_gate"], "PASS")
        self.assertEqual(result["review_reasons"], [])
        self.assertEqual(result["confidence_delta"], 0.0)
        self.assertEqual(result["latency_delta_ms"], -300)
        self.assertEqual(
            result["tail_budget"],
            {
                "applied": True,
                "original_items": 10,
                "selected_items": 8,
                "chunks": 2,
            },
        )

    def test_identity_topology_change_requires_review(self):
        baseline = _arm()
        budgeted = _arm(
            secondary_identity_stance_counts={
                "ASSESSED": 4,
                "SUPPORTS": 4,
                "UNKNOWN_ONLY": 1,
            },
            assessment_provider_calls=[
                {
                    "provider": "gemini",
                    "outcome": "failed",
                    "error_label": "_AssessmentGeminiQuotaError",
                    "metadata": {},
                },
                {
                    "provider": "cloudflare",
                    "outcome": "success",
                    "error_label": "",
                    "metadata": {
                        "assessment_tail_budget_applied": True,
                        "assessment_items_original": 10,
                        "assessment_items_selected": 8,
                        "assessment_chunks_attempted": 2,
                    },
                },
            ],
        )

        result = _compare_arms(baseline, budgeted)

        self.assertEqual(result["automated_gate"], "REVIEW")
        self.assertIn(
            "IDENTITY_STANCE_TOPOLOGY_CHANGED",
            result["review_reasons"],
        )

    def test_missing_budget_activation_requires_review(self):
        result = _compare_arms(_arm(), _arm())

        self.assertEqual(result["automated_gate"], "REVIEW")
        self.assertIn("TAIL_BUDGET_NOT_APPLIED", result["review_reasons"])

    def test_changed_summary_requires_manual_review(self):
        baseline = _arm(summary="Baseline factual explanation.")
        budgeted = _arm(
            summary="Different factual explanation.",
            assessment_provider_calls=[
                {
                    "provider": "gemini",
                    "outcome": "failed",
                    "error_label": "_AssessmentGeminiQuotaError",
                    "metadata": {},
                },
                {
                    "provider": "cloudflare",
                    "outcome": "success",
                    "error_label": "",
                    "metadata": {
                        "assessment_tail_budget_applied": True,
                        "assessment_items_original": 10,
                        "assessment_items_selected": 8,
                        "assessment_chunks_attempted": 2,
                    },
                },
            ],
        )

        result = _compare_arms(baseline, budgeted)

        self.assertEqual(result["automated_gate"], "REVIEW")
        self.assertIn(
            "SUMMARY_CHANGED_MANUAL_REVIEW",
            result["review_reasons"],
        )

    def test_contextual_verdict_always_requires_manual_review(self):
        baseline = _arm(verdict="MISLEADING")
        budgeted = _arm(
            verdict="MISLEADING",
            assessment_provider_calls=[
                {
                    "provider": "gemini",
                    "outcome": "failed",
                    "error_label": "_AssessmentGeminiQuotaError",
                    "metadata": {},
                },
                {
                    "provider": "cloudflare",
                    "outcome": "success",
                    "error_label": "",
                    "metadata": {
                        "assessment_tail_budget_applied": True,
                        "assessment_items_original": 10,
                        "assessment_items_selected": 8,
                        "assessment_chunks_attempted": 2,
                    },
                },
            ],
        )

        result = _compare_arms(baseline, budgeted)

        self.assertEqual(result["automated_gate"], "REVIEW")
        self.assertIn(
            "CONTEXTUAL_VERDICT_MANUAL_REVIEW",
            result["review_reasons"],
        )


class CloudflareAssessmentForcedFallbackTests(SimpleTestCase):
    def test_only_assessment_wrapper_temporarily_replaces_gemini_client(self):
        from api import services
        original_client = services.gemini_client
        observed = {}

        def fake_call(*args, **kwargs):
            observed["inside"] = services.gemini_client
            return '{"assessments": []}'

        with patch(
            "api.management.commands.compare_cloudflare_assessment_tail_budget."
            "_ORIGINAL_ASSESSMENT_CALL_LLM",
            side_effect=fake_call,
        ):
            result = _forced_cloudflare_assessment(
                "instructions",
                "prompt",
                operation="evidence_assessment",
            )

        self.assertEqual(result, '{"assessments": []}')
        self.assertIsNot(observed["inside"], original_client)
        self.assertIs(services.gemini_client, original_client)


class CloudflareAssessmentTailBudgetABCommandTests(TestCase):
    @override_settings(APP_ENV="production", DEBUG=False)
    def test_command_is_rejected_outside_development(self):
        with self.assertRaises(CommandError):
            call_command(
                "compare_cloudflare_assessment_tail_budget",
                claims=["A test claim."],
            )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_command_switches_only_tail_flag_and_rolls_back_each_arm(self):
        seen_flags = []
        seen_claim_ids = []

        def fake_pipeline(claim_text, claim_id, triggered_by_id=None):
            seen_flags.append(
                os.getenv("ENABLE_CLOUDFLARE_ASSESSMENT_TAIL_BUDGET")
            )
            seen_claim_ids.append(str(claim_id))

            claim = Claim.objects.get(pk=claim_id)
            claim.ai_verdict = "FACT"
            claim.consensus_score = 90
            claim.ai_summary = "Synthetic quality A/B result."
            claim.score_context = "Synthetic score context."
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
            metadata = {}
            if seen_flags[-1] == "1":
                metadata = {
                    "assessment_tail_budget_applied": True,
                    "assessment_items_original": 10,
                    "assessment_items_selected": 8,
                    "assessment_chunks_attempted": 2,
                }

            VerificationTelemetryEvent.objects.create(
                verification_run=run,
                sequence=1,
                event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
                name="evidence_assessment",
                provider="gemini",
                duration_ms=1,
                outcome="failed",
                error_label="_AssessmentGeminiQuotaError",
                metadata={},
                occurred_at=now,
            )
            VerificationTelemetryEvent.objects.create(
                verification_run=run,
                sequence=2,
                event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
                name="evidence_assessment",
                provider="cloudflare",
                duration_ms=50,
                outcome="success",
                error_label="",
                metadata=metadata,
                occurred_at=now,
            )

        before_claims = Claim.objects.count()
        output = io.StringIO()

        with (
            patch(
                "api.tasks.execute_core_text_pipeline",
                side_effect=fake_pipeline,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_tail_budget."
                "_ORIGINAL_CLEAN_OCR_TEXT",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
        ):
            call_command(
                "compare_cloudflare_assessment_tail_budget",
                claims=["A test claim."],
                json=True,
                stdout=output,
            )

        report = json.loads(output.getvalue())
        self.assertEqual(seen_flags, ["0", "1"])
        self.assertEqual(len(set(seen_claim_ids)), 2)
        self.assertEqual(Claim.objects.count(), before_claims)
        self.assertEqual(len(report), 1)
        self.assertTrue(report[0]["baseline"]["database_isolated"])
        self.assertTrue(report[0]["budgeted"]["database_isolated"])
