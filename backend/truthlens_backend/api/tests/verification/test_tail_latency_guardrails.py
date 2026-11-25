import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from api import tasks
from api.services import (
    GROQ_RELIABILITY_HTTP_TIMEOUT_SECONDS,
    call_llm_with_fallback,
    llm_provider_scope,
)


@override_settings(APP_ENV="development", DEBUG=True)
class GroqTailLatencyGuardrailTests(SimpleTestCase):
    def _run_fallback(self, *, hardening):
        gemini = Mock()
        gemini.models.generate_content.side_effect = RuntimeError(
            "synthetic provider failure"
        )
        groq = Mock()
        groq.with_options.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"provider":"groq"}')
                    )
                ]
            )
        )

        with (
            patch.dict(
                os.environ,
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
                    "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
                    "ENABLE_PROVIDER_RELIABILITY_HARDENING": (
                        "1" if hardening else "0"
                    ),
                    "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "0",
                },
                clear=False,
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            llm_provider_scope(),
        ):
            result = call_llm_with_fallback(
                "System instructions",
                "User prompt",
            )

        self.assertEqual(result, '{"provider":"groq"}')
        groq.with_options.return_value.chat.completions.create.assert_called_once()
        return groq

    def test_hardening_bounds_each_groq_fallback_request(self):
        groq = self._run_fallback(hardening=True)

        groq.with_options.assert_called_once_with(
            max_retries=0,
            timeout=GROQ_RELIABILITY_HTTP_TIMEOUT_SECONDS,
        )
        self.assertEqual(GROQ_RELIABILITY_HTTP_TIMEOUT_SECONDS, 20.0)

    def test_hardening_off_preserves_existing_groq_client_options(self):
        groq = self._run_fallback(hardening=False)

        groq.with_options.assert_called_once_with(max_retries=0)


class OptionalRecoveryTailLatencyGuardrailTests(SimpleTestCase):
    def _kwargs(self, **overrides):
        values = {
            "initial_result": {
                "verdict": "UNVERIFIED",
                "summary": "Evidence remains insufficient.",
                "confidence_score": 35,
            },
            "cleaned_claim": "A verifiable public claim.",
            "claim_id": "claim-id",
            "run": SimpleNamespace(pk="run-id"),
            "article_stance": "NEUTRAL",
            "official_rating_policy": {"resolution": "NONE"},
            "gfc_evidence_assessed": False,
            "is_text_claim": True,
            "pipeline_started_at": 20.0,
        }
        values.update(overrides)
        return values

    def test_recovery_is_skipped_after_tail_latency_cutoff(self):
        initial = self._kwargs()["initial_result"]

        with (
            patch(
                "api.tasks.time.perf_counter",
                side_effect=[100.0, 100.0],
            ),
            patch(
                "api.tasks.load_reasoning_evidence_dossier_for_run",
            ) as load_dossier,
            patch("api.tasks.TavilyProvider") as provider,
            patch("api.tasks._log_stage") as log_stage,
        ):
            result = tasks._attempt_primary_source_recovery(
                **self._kwargs(initial_result=initial)
            )

        self.assertIs(result, initial)
        load_dossier.assert_not_called()
        provider.assert_not_called()
        log_stage.assert_called_once()
        self.assertEqual(
            log_stage.call_args.args[1],
            "primary_source_recovery",
        )
        self.assertEqual(
            log_stage.call_args.kwargs["outcome"],
            "skipped_tail_latency_budget",
        )

    def test_recovery_remains_available_before_tail_latency_cutoff(self):
        provider = Mock()
        provider.search_with_payload.return_value = ({}, [])

        with (
            patch(
                "api.tasks.time.perf_counter",
                side_effect=[60.0, 60.1],
            ),
            patch(
                "api.tasks.load_reasoning_evidence_dossier_for_run",
                return_value=[],
            ),
            patch(
                "api.tasks.TavilyProvider",
                return_value=provider,
            ) as provider_class,
            patch("api.tasks._log_stage"),
        ):
            result = tasks._attempt_primary_source_recovery(
                **self._kwargs(pipeline_started_at=20.0)
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        provider_class.assert_called_once_with(
            timeout=tasks.DEFAULT_HTTP_TIMEOUT_SEC,
        )
        provider.search_with_payload.assert_called_once_with(
            "A verifiable public claim.",
            limit=tasks.PRIMARY_SOURCE_RECOVERY_RESULT_LIMIT,
            primary_source_recovery=True,
        )
