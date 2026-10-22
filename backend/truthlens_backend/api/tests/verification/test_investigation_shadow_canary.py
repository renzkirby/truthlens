import json
import os
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from api import services
from api.management.commands.run_investigation_classification_shadow_canary import (
    CANARY_SOURCE,
    CONFIRMATION,
)
from api.models import (
    Claim,
    ClaimInvestigationClassification,
    InvestigationClassificationAssessment,
)
from api.tasks import classify_investigation_claim_task
from api.verification.cloudflare_evaluation import CloudflareEvaluationError


SCIENCE = json.dumps({
    "decision": "CLASSIFY",
    "domains": [{"code": "SCIENCE", "evidence": "science experiment"}],
})
CROSS = json.dumps({
    "decision": "CLASSIFY",
    "domains": [
        {"code": "HEALTH", "evidence": "hospital"},
        {"code": "ECONOMY", "evidence": "central bank raised interest rates"},
    ],
})
ABSTAIN = '{"decision":"ABSTAIN","domains":[]}'


@override_settings(
    APP_ENV="development",
    DEBUG=True,
    INVESTIGATION_CLASSIFICATION_MODE="shadow",
)
class InvestigationShadowCanaryCommandTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "1",
            "GEMINI_API_KEY": "test-gemini",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "test-cloudflare",
            "GROQ_API_KEY": "test-groq",
        }))
        gemini = Mock()
        self.gemini = self.enterContext(patch(
            "api.services.gemini_client", gemini,
        ))
        self.cloudflare = self.enterContext(patch(
            "api.services.call_validated_cloudflare_pilot",
            return_value=SCIENCE,
        ))
        groq = Mock()
        self.groq = self.enterContext(patch("api.services.groq_client", groq))
        self.groq_request = (
            groq.with_options.return_value.chat.completions.create
        )
        self.groq_request.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=SCIENCE)),
        ])

    def _run_live(self):
        out = StringIO()
        call_command(
            "run_investigation_classification_shadow_canary",
            "--execute-live",
            "--confirm-live", CONFIRMATION,
            "--json-summary",
            stdout=out,
        )
        return json.loads(out.getvalue())

    def test_default_is_read_only_dry_run(self):
        out = StringIO()
        call_command(
            "run_investigation_classification_shadow_canary",
            "--json-summary",
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["status"], "SHADOW_CANARY_DRY_RUN_NO_PROVIDER_CALLS"
        )
        self.assertEqual(payload["planned_claims"], 3)
        self.assertEqual(payload["max_provider_stage_attempts"], 9)
        self.assertEqual(payload["provider_calls"], 0)
        self.assertEqual(payload["db_writes"], 0)
        self.assertFalse(Claim.objects.filter(source_type=CANARY_SOURCE).exists())
        self.gemini.models.generate_content.assert_not_called()
        self.cloudflare.assert_not_called()
        self.groq_request.assert_not_called()

    def test_three_live_gemini_results_persist_shadow_only(self):
        self.gemini.models.generate_content.side_effect = [
            SimpleNamespace(text=SCIENCE),
            SimpleNamespace(text=CROSS),
            SimpleNamespace(text=ABSTAIN),
        ]
        payload = self._run_live()
        self.assertEqual(payload["status"], "SHADOW_CANARY_FINISHED")
        self.assertEqual(payload["claims_created"], 3)
        self.assertFalse(payload["stopped_early"])
        self.assertEqual(payload["provider_stage_attempts"], 3)
        self.assertEqual(payload["exact_matches"], 3)
        self.assertTrue(payload["all_exact"])
        self.assertEqual(payload["authoritative_rows"], 0)
        self.assertEqual(payload["factual_verdicts_changed"], 0)
        self.assertEqual(
            [r["task_outcome"] for r in payload["results"]],
            ["SUGGESTED", "SUGGESTED", "ABSTAINED"],
        )
        self.assertEqual(
            [r["assessment"]["candidate_domains"] for r in payload["results"]],
            [["SCIENCE"], ["ECONOMY", "HEALTH"], []],
        )
        self.assertEqual(
            [r["assessment"]["reason_code"] for r in payload["results"]],
            ["", "", "MODEL_ABSTAINED"],
        )
        self.assertEqual(
            [[e["provider"] for e in r["provider_trace"]]
             for r in payload["results"]],
            [["gemini"], ["gemini"], ["gemini"]],
        )
        self.assertEqual(
            Claim.objects.filter(source_type=CANARY_SOURCE).count(), 3
        )
        self.assertEqual(
            InvestigationClassificationAssessment.objects.filter(
                claim__source_type=CANARY_SOURCE
            ).count(), 3
        )
        self.assertFalse(
            ClaimInvestigationClassification.objects.filter(
                claim__source_type=CANARY_SOURCE
            ).exists()
        )

    def test_complete_provider_exhaustion_stops_after_first_claim(self):
        self.gemini.models.generate_content.side_effect = RuntimeError(
            "synthetic Gemini failure"
        )
        self.cloudflare.side_effect = CloudflareEvaluationError(
            "TRANSPORT_ReadTimeout"
        )
        self.groq_request.side_effect = RuntimeError("synthetic Groq failure")
        payload = self._run_live()
        self.assertEqual(payload["claims_created"], 1)
        self.assertTrue(payload["stopped_early"])
        self.assertEqual(payload["provider_stage_attempts"], 3)
        self.assertFalse(payload["all_exact"])
        self.assertEqual(payload["results"][0]["task_outcome"], "FAILED")
        self.assertEqual(
            payload["results"][0]["assessment"]["reason_code"],
            "PROVIDER_UNAVAILABLE",
        )
        self.assertEqual(
            [e["provider"] for e in payload["results"][0]["provider_trace"]],
            ["gemini", "cloudflare", "groq"],
        )
        self.assertFalse(ClaimInvestigationClassification.objects.exists())

    def test_live_rejects_wrong_confirmation_without_provider_call(self):
        with self.assertRaises(CommandError):
            call_command(
                "run_investigation_classification_shadow_canary",
                "--execute-live",
                "--confirm-live", "WRONG",
                stdout=StringIO(),
            )
        self.gemini.models.generate_content.assert_not_called()
        self.assertFalse(Claim.objects.filter(source_type=CANARY_SOURCE).exists())

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_live_rejects_production(self):
        with self.assertRaises(CommandError):
            self._run_live()
        self.gemini.models.generate_content.assert_not_called()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    def test_live_requires_shadow_mode(self):
        with self.assertRaises(CommandError):
            self._run_live()
        self.gemini.models.generate_content.assert_not_called()

    def test_live_requires_full_shared_hierarchy_flags(self):
        with patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0",
        }):
            with self.assertRaises(CommandError):
                self._run_live()
        self.gemini.models.generate_content.assert_not_called()

    def test_live_refuses_replay_when_canary_rows_exist(self):
        Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Existing synthetic shadow canary row.",
            source_type=CANARY_SOURCE,
            is_ai_generated=True,
        )
        with self.assertRaises(CommandError):
            self._run_live()
        self.gemini.models.generate_content.assert_not_called()

    def test_classification_task_initializes_and_restores_provider_job_scope(self):
        observed = []

        def inspect_scope(_claim_id):
            observed.append((
                services._gemini_degraded.get(),
                services._cloudflare_pilot_degraded.get(),
            ))
            return "DISABLED"

        self.assertIsNone(services._gemini_degraded.get())
        self.assertIsNone(services._cloudflare_pilot_degraded.get())
        with patch(
            "api.investigation_classifier.classify_investigation_claim",
            side_effect=inspect_scope,
        ):
            self.assertEqual(
                classify_investigation_claim_task.run("synthetic-claim-id"),
                "DISABLED",
            )
        self.assertEqual(observed, [(False, False)])
        self.assertIsNone(services._gemini_degraded.get())
        self.assertIsNone(services._cloudflare_pilot_degraded.get())
