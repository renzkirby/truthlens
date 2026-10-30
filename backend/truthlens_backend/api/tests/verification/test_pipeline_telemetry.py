from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from api import services
from api.models import Claim, VerificationRun, VerificationTelemetryEvent
from api.services import call_llm_with_fallback, llm_provider_scope
from api.verification.telemetry import (
    bind_verification_run,
    get_current_collector,
    record_llm_provider_call,
    record_pipeline_stage,
    verification_telemetry_scope,
)


class PipelineTelemetryCollectorTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Private claim text",
        )
        self.run = VerificationRun.objects.create(
            claim=self.claim,
            status=VerificationRun.Status.RUNNING,
        )

    def test_scope_buffers_without_writes_then_flushes_once_in_sequence(self):
        observed = {}

        @verification_telemetry_scope()
        def execute(claim_id):
            record_pipeline_stage("pre_run_stage", 12, text_length=42)
            observed["before_bind"] = VerificationTelemetryEvent.objects.count()
            bind_verification_run(self.run)
            record_llm_provider_call(
                "claim_gate",
                "gemini",
                self.run.id,
                34,
                "success",
            )
            observed["before_exit"] = VerificationTelemetryEvent.objects.count()

        with patch.object(
            VerificationTelemetryEvent.objects,
            "bulk_create",
            wraps=VerificationTelemetryEvent.objects.bulk_create,
        ) as bulk_create:
            execute(self.claim.id)

        self.assertEqual(observed, {"before_bind": 0, "before_exit": 0})
        bulk_create.assert_called_once()
        events = list(self.run.telemetry_events.order_by("sequence"))
        self.assertEqual([event.sequence for event in events], [1, 2])
        self.assertEqual(events[0].name, "pre_run_stage")
        self.assertEqual(events[1].name, "claim_gate")

    def test_nested_scope_reuses_collector_and_flushes_only_at_outer_exit(self):
        collector_ids = []

        @verification_telemetry_scope()
        def inner(claim_id):
            collector_ids.append(id(get_current_collector()))
            record_pipeline_stage("inner", 2)

        @verification_telemetry_scope()
        def outer(claim_id):
            collector_ids.append(id(get_current_collector()))
            record_pipeline_stage("outer_before", 1)
            inner(claim_id)
            bind_verification_run(self.run)
            record_pipeline_stage("outer_after", 3)
            self.assertFalse(self.run.telemetry_events.exists())

        outer(self.claim.id)

        self.assertEqual(len(set(collector_ids)), 1)
        self.assertEqual(
            list(self.run.telemetry_events.values_list("name", flat=True)),
            ["outer_before", "inner", "outer_after"],
        )

    def test_unbound_scope_discards_events(self):
        @verification_telemetry_scope()
        def execute(claim_id):
            record_pipeline_stage("orphaned", 10)

        execute(self.claim.id)
        self.assertFalse(VerificationTelemetryEvent.objects.exists())

    def test_metadata_allowlist_and_failed_outcome_are_privacy_safe(self):
        @verification_telemetry_scope()
        def execute(claim_id):
            bind_verification_run(self.run)
            record_pipeline_stage(
                "tavily_failed",
                11,
                status_code=503,
                has_results=False,
                bytes=99,
                ai_probability=0.25,
                persisted=True,
                error="secret exception text",
                claim_text="private claim",
                url="https://private.example/token",
                email="private@example.com",
                token="secret-token",
                prompt="private prompt",
                response="private response",
                arbitrary="private payload",
            )

        execute(self.claim.id)
        event = self.run.telemetry_events.get()
        self.assertEqual(event.outcome, "failed")
        self.assertEqual(
            event.metadata,
            {
                "status_code": 503,
                "has_results": False,
                "bytes": 99,
                "ai_probability": 0.25,
                "persisted": True,
            },
        )
        serialized = repr(event.metadata)
        for unsafe in (
            "secret exception",
            "private claim",
            "private.example",
            "private@example.com",
            "secret-token",
            "private prompt",
            "private response",
            "private payload",
        ):
            self.assertNotIn(unsafe, serialized)

    def test_gemini_model_metadata_is_allowlisted_without_private_fields(self):
        @verification_telemetry_scope()
        def execute(claim_id):
            bind_verification_run(self.run)
            record_llm_provider_call(
                "claim_gate",
                "gemini",
                self.run.id,
                9,
                "success",
                metadata={
                    "model_id": "gemini-3.5-flash-lite",
                    "prompt": "PRIVATE PROMPT",
                    "api_key": "PRIVATE KEY",
                },
            )

        execute(self.claim.id)
        event = self.run.telemetry_events.get()
        self.assertEqual(
            event.metadata,
            {"model_id": "gemini-3.5-flash-lite"},
        )
        self.assertNotIn("PRIVATE", repr(event.metadata))

    def test_flush_failure_never_propagates_or_logs_exception_secret(self):
        @verification_telemetry_scope()
        def execute(claim_id):
            bind_verification_run(self.run)
            record_pipeline_stage("complete", 1)
            return "verification-result"

        secret = "SECRET DATABASE FAILURE TOKEN=abc123"
        with self.assertLogs("api.verification.telemetry", level="ERROR") as captured:
            with patch.object(
                VerificationTelemetryEvent.objects,
                "bulk_create",
                side_effect=RuntimeError(secret),
            ):
                self.assertEqual(execute(self.claim.id), "verification-result")

        logged = "\n".join(captured.output)
        self.assertIn("Verification telemetry persistence failed", logged)
        self.assertIn(f"run_id={self.run.id}", logged)
        self.assertIn("event_count=1", logged)
        self.assertNotIn(secret, logged)
        self.assertFalse(self.run.telemetry_events.exists())

    def test_provider_attempts_share_call_id_and_degraded_call_gets_new_id(self):
        gemini = Mock()
        groq = Mock()
        gemini.models.generate_content.side_effect = RuntimeError(
            "provider secret must not persist"
        )
        groq.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        )

        @verification_telemetry_scope()
        def execute(claim_id):
            bind_verification_run(self.run)
            with llm_provider_scope():
                call_llm_with_fallback("System", "Prompt", operation="claim_gate")
                call_llm_with_fallback("System", "Prompt", operation="claim_gate")

        with patch("api.services.gemini_client", gemini), patch(
            "api.services.groq_client", groq
        ):
            execute(self.claim.id)

        events = list(self.run.telemetry_events.order_by("sequence"))
        self.assertEqual([event.provider for event in events], ["gemini", "groq", "groq"])
        self.assertEqual(events[0].provider_call_id, events[1].provider_call_id)
        self.assertIsNotNone(events[2].provider_call_id)
        self.assertNotEqual(events[1].provider_call_id, events[2].provider_call_id)
        self.assertEqual(events[0].error_label, "RuntimeError")
        self.assertNotIn("provider secret", repr(events))


class ProductionOperationLabelTests(TestCase):
    def test_production_helpers_pass_stable_operation_labels(self):
        claim_gate = '{"cleaned_claim":"A claim","search_query":"query","search_queries":["query"],"article_stance":"NEUTRAL"}'
        equivalence = '{"equivalent":true,"reasoning":"Same proposition","material_differences":[]}'
        relevance = '{"reasoning":"Same event","is_relevant":true}'
        verdict = '{"reasoning":"Evidence bound","verdict":"FACT","summary":"Supported","confidence_score":95,"score_context":"Strong evidence supports this claim"}'
        gfc = {
            "claims": [
                {
                    "text": "A claim",
                    "claimReview": [
                        {
                            "textualRating": "True",
                            "publisher": {"name": "Fact checker"},
                        }
                    ],
                }
            ]
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[
                claim_gate,
                claim_gate,
                equivalence,
                relevance,
                verdict,
                verdict,
                verdict,
                verdict,
                verdict,
            ],
        ) as provider_call:
            self.assertEqual(services.clean_ocr_text("raw")["cleaned_claim"], "A claim")
            self.assertEqual(
                services.extract_search_query("raw", "https://example.com")["cleaned_claim"],
                "A claim",
            )
            self.assertTrue(services.assess_claim_equivalence("A", "A")["equivalent"])
            self.assertTrue(services.is_fact_check_relevant("A", "A"))
            services.evaluate_image_claim_with_gfc("A", gfc)
            services.evaluate_url_claim_with_gfc("A", gfc)
            services.evaluate_image_claim_with_tavily("A", "Evidence")
            services.evaluate_url_claim_with_tavily("A", "Evidence")
            services.evaluate_claim_with_persisted_evidence("A", "Evidence")

        self.assertEqual(
            [call.kwargs["operation"] for call in provider_call.call_args_list],
            [
                "claim_gate",
                "claim_gate",
                "claim_equivalence",
                "fact_check_relevance",
                "gfc_evaluation",
                "gfc_evaluation",
                "tavily_evaluation",
                "tavily_evaluation",
                "persisted_evidence_evaluation",
            ],
        )
