"""Offline integration tests for bounded dev classification latency and fallback.

Each mocked Cloudflare request goes through the real JSON adapter and strict
classification contract. No external inference, Celery tasks, or database I/O.
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from api.services import LLMProviderUnavailableError, call_llm_with_fallback
from api.investigation_classifier import _query_classifier, classification_system_prompt
from api.verification.classification_contract import CLASSIFICATION_OPERATION
from api.verification.cloudflare_evaluation import DEFAULT_MODEL
from api.verification.cloudflare_pilot import (
    cloudflare_classification_http_timeout,
    cloudflare_classification_completion_budget,
    cloudflare_classification_reject_if_busy_enabled,
)

CLAIM = (
    "On October 14, 2024, NASA launched the Europa Clipper spacecraft "
    "aboard a SpaceX Falcon Heavy rocket from Kennedy Space Center in Florida."
)
VALID = json.dumps({
    "decision": "CLASSIFY",
    "primary_subject": "SCIENCE",
    "domains": [
        {"code": "SCIENCE", "evidence": "NASA launched the Europa Clipper"},
        {"code": "TECHNOLOGY", "evidence": "SpaceX Falcon Heavy rocket"},
    ],
})
ABSTAIN = json.dumps({
    "decision": "ABSTAIN",
    "primary_subject": None,
    "domains": [],
})


class GeminiBillingError(RuntimeError):
    code = 402


class GroqRateLimited(RuntimeError):
    status_code = 429


@override_settings(APP_ENV="development", DEBUG=True)
class ClassificationLatencyPolicyTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "1",
            "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY": "1",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "30",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "offline-placeholder-token",
        }))
        gemini = Mock()
        gemini.models.generate_content.side_effect = GeminiBillingError(402)
        self.gemini = self.enterContext(patch("api.services.gemini_client", gemini))
        groq = Mock()
        self.groq = self.enterContext(patch("api.services.groq_client", groq))
        self.groq_call = groq.with_options.return_value.chat.completions.create
        self.groq_call.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=VALID)),
        ])
        self.http = self.enterContext(patch(
            "api.verification.cloudflare_evaluation.requests.post",
        ))
        self._response(VALID)

    def _response(self, content):
        self.http.return_value.status_code = 200
        self.http.return_value.json.return_value = {
            "choices": [{
                "message": {"content": content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 188,
                "completion_tokens": 867,
                "total_tokens": 1055,
            },
        }

    def _classify(self):
        return call_llm_with_fallback(
            "Return strict subject classification JSON with claim quotations.",
            CLAIM,
            operation=CLASSIFICATION_OPERATION,
        )

    def test_30s_candidate_uses_exactly_one_validated_cloudflare_request(self):
        self.assertEqual(cloudflare_classification_http_timeout(), (3, 30))
        self.assertTrue(cloudflare_classification_reject_if_busy_enabled())
        self.assertEqual(self._classify(), VALID)
        self.gemini.models.generate_content.assert_called_once()
        self.http.assert_called_once()
        self.groq.with_options.assert_not_called()
        kwargs = self.http.call_args.kwargs
        self.assertEqual(kwargs["timeout"], (3, 30))
        self.assertEqual(kwargs["json"]["model"], DEFAULT_MODEL)
        self.assertEqual(kwargs["json"]["max_tokens"], 1024)
        self.assertIs(kwargs["json"]["stream"], False)
        self.assertEqual(kwargs["json"]["options"], {"rejectIfBusy": True})
        self.assertEqual(kwargs["json"]["messages"][1]["content"], CLAIM)
        self.assertNotIn("retry", kwargs["json"])

    def test_default_classification_budget_stays_1024(self):
        self.assertEqual(cloudflare_classification_completion_budget(), 1024)
        self.assertEqual(cloudflare_classification_http_timeout(), (3, 30))
        self.assertEqual(self._classify(), VALID)
        self.assertEqual(self.http.call_args.kwargs["json"]["max_tokens"], 1024)
        self.http.assert_called_once()

    def test_final_dev_profile_4096_with_exact_production_prompt(self):
        # Only this test's explicit dev flags can enlarge classification.
        # Use the actual _query_classifier entry point; no DB/Celery/HTTP.
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_CLASSIFICATION_MAX_TOKENS": "4096",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "45",
        }):
            self.assertEqual(cloudflare_classification_completion_budget(), 4096)
            self.assertEqual(cloudflare_classification_http_timeout(), (3, 45))
            self.assertEqual(_query_classifier(CLAIM), json.loads(VALID))
        self.http.assert_called_once()
        self.gemini.models.generate_content.assert_called_once()
        self.groq.with_options.assert_not_called()
        request = self.http.call_args.kwargs
        self.assertEqual(request["timeout"], (3, 45))
        self.assertEqual(request["json"]["max_tokens"], 4096)
        self.assertEqual(request["json"]["model"], DEFAULT_MODEL)
        self.assertEqual(request["json"]["messages"][0]["content"],
                         classification_system_prompt())
        self.assertEqual(request["json"]["messages"][1]["content"], CLAIM)
        self.assertFalse(request["json"]["stream"])
        self.assertEqual(request["json"]["options"], {"rejectIfBusy": True})
        self.assertNotIn("retry", request["json"])

    def test_4096_profile_empty_reasoning_response_falls_back_to_groq(self):
        # The Cloudflare-02 style failure remains fail-closed, never a
        # fabricated subject verdict, and always uses no retry.
        self.http.return_value.json.return_value = {
            "choices": [{
                "message": {
                    "content": "",
                    "reasoning_content": "mock reasoning never logged",
                },
                "finish_reason": "length",
            }],
            "usage": {
                "prompt_tokens": 177,
                "completion_tokens": 4096,
                "total_tokens": 4273,
            },
        }
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_CLASSIFICATION_MAX_TOKENS": "4096",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "45",
        }), patch("api.services.record_llm_provider_call") as telemetry:
            self.assertEqual(_query_classifier(CLAIM), json.loads(VALID))
        self.http.assert_called_once()
        self.groq.with_options.assert_called_once_with(max_retries=0)
        self.groq_call.assert_called_once()
        statuses = [(c.args[1], c.args[4]) for c in telemetry.call_args_list]
        self.assertEqual(statuses, [
            ("gemini", "failed"), ("cloudflare", "failed"), ("groq", "success"),
        ])
        cf_call = telemetry.call_args_list[1]
        self.assertEqual(
            cf_call.args[5],
            "CloudflareEvaluationError code=EMPTY_PROVIDER_RESPONSE",
        )
        self.assertNotIn("mock reasoning never logged", str(telemetry.call_args_list))

    def test_invalid_4096_budget_and_45s_timeout_fail_closed(self):
        for invalid in ("4095", "8192", "true", "", " 4096"):
            with self.subTest(value=invalid), patch.dict(os.environ, {
                "CLOUDFLARE_PILOT_CLASSIFICATION_MAX_TOKENS": invalid,
                "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "45",
            }):
                self.assertEqual(cloudflare_classification_completion_budget(), 1024)
                self.assertEqual(cloudflare_classification_http_timeout(), (3, 15))
        self.http.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_4096_flags_cannot_activate_in_production(self):
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_CLASSIFICATION_MAX_TOKENS": "4096",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "45",
        }):
            self.assertEqual(cloudflare_classification_completion_budget(), 1024)
            self.assertEqual(cloudflare_classification_http_timeout(), (3, 15))
            self.gemini.models.generate_content.side_effect = None
            self.gemini.models.generate_content.return_value = SimpleNamespace(
                text=VALID,
            )
            self.assertEqual(_query_classifier(CLAIM), json.loads(VALID))
        self.http.assert_not_called()

    def test_candidate_accepts_strict_abstention_without_forced_groq(self):
        self._response(ABSTAIN)
        self.assertEqual(self._classify(), ABSTAIN)
        self.http.assert_called_once()
        self.groq.with_options.assert_not_called()

    def test_30s_read_timeout_falls_through_once_to_groq(self):
        self.http.side_effect = requests.exceptions.ReadTimeout(
            "offline simulated timeout, no network",
        )
        with patch("api.services.record_llm_provider_call") as telemetry:
            self.assertEqual(self._classify(), VALID)
        self.http.assert_called_once()
        self.groq.with_options.assert_called_once_with(max_retries=0)
        self.groq_call.assert_called_once()
        self.assertEqual(
            [(c.args[1], c.args[4]) for c in telemetry.call_args_list],
            [("gemini", "failed"), ("cloudflare", "failed"), ("groq", "success")],
        )
        self.assertEqual(
            telemetry.call_args_list[1].args[5],
            "CloudflareEvaluationError code=TRANSPORT_ReadTimeout",
        )

    def test_capacity_reject_3040_falls_through_once_to_groq(self):
        self.http.return_value.status_code = 429
        self.http.return_value.json.return_value = {
            "errors": [{"code": 3040, "message": "never show raw vendor text"}],
        }
        with patch("api.services.record_llm_provider_call") as telemetry:
            self.assertEqual(self._classify(), VALID)
        self.http.assert_called_once()
        self.groq_call.assert_called_once()
        self.assertEqual(
            telemetry.call_args_list[1].args[5],
            "CloudflareEvaluationError code=HTTP_429_CAPACITY",
        )
        self.assertNotIn(
            "never show raw vendor text", str(telemetry.call_args_list),
        )

    def test_invalid_cloudflare_contract_also_uses_validated_groq(self):
        self._response('{"decision":"CLASSIFY","primary_subject":"SCIENCE","domains":[]}')
        self.assertEqual(self._classify(), VALID)
        self.http.assert_called_once()
        self.groq_call.assert_called_once()

    def test_complete_provider_exhaustion_fails_not_classifies(self):
        self.http.side_effect = requests.exceptions.ReadTimeout()
        self.groq_call.side_effect = GroqRateLimited("offline synthetic 429")
        with self.assertRaises(LLMProviderUnavailableError):
            self._classify()
        self.http.assert_called_once()
        self.groq.with_options.assert_called_once_with(max_retries=0)
        self.groq_call.assert_called_once()

    def test_invalid_opt_in_retains_15s_not_30s(self):
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "60",
            "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY": "true",
        }):
            self.assertEqual(cloudflare_classification_http_timeout(), (3, 15))
            self.assertFalse(cloudflare_classification_reject_if_busy_enabled())
            self.assertEqual(self._classify(), VALID)
        kwargs = self.http.call_args.kwargs
        self.assertEqual(kwargs["timeout"], (3, 15))
        self.assertNotIn("options", kwargs["json"])

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_prod_never_reaches_cloudflare_even_when_flags_set(self):
        self.gemini.models.generate_content.side_effect = None
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=VALID,
        )
        self.assertEqual(self._classify(), VALID)
        self.http.assert_not_called()
        self.groq.with_options.assert_not_called()
