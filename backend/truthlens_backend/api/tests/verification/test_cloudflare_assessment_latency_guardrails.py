"""No-network, evidence-preserving Cloudflare assessment latency guardrail tests."""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.test import SimpleTestCase, override_settings

from api.services import call_llm_with_fallback, llm_provider_scope
from api.verification.cloudflare_evaluation import (
    CloudflareEvaluationError,
    generate_evaluation_json,
    sanitized_cloudflare_error_code,
)
from api.verification.cloudflare_pilot import (
    ASSESSMENT_HTTP_TIMEOUT,
    ASSESSMENT_MAX_ITEMS,
    ASSESSMENT_OPERATION,
    PILOT_COMPLETION_TOKENS,
    PILOT_OPERATION,
    call_validated_cloudflare_pilot,
    cloudflare_assessment_bypass_reason,
    cloudflare_assessment_reject_if_busy_enabled,
)
from api.verification.telemetry import (
    get_current_collector,
    verification_telemetry_scope,
)

_VALID_VERDICT = json.dumps({
    "reasoning": "A public source explicitly documents the return.",
    "verdict": "FACT",
    "summary": "The claim is supported.",
    "confidence_score": 92,
    "score_context": "One relevant direct source is documented.",
})


def _batch_prompt(count, length=24):
    return "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps({
        "claim_text": "The mission returned in 2023.",
        "evidence_items": [
            {
                "key": f"item_{index}",
                "evidence_content": f"Evidence {index}: " + ("x" * length),
            }
            for index in range(count)
        ],
    })


def _batch_response(count):
    return json.dumps({"assessments": [
        {
            "key": f"item_{i}",
            "stance": "SUPPORTS" if i % 2 == 0 else "REFUTES",
            "relevance_score": 0.9,
            "directness_score": 0.8,
        }
        for i in range(count)
    ]})


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflareAssessmentLatencyRoutingTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "1",
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0",
        }))
        self.cloud = self.enterContext(patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json",
        ))
        gemini = Mock()
        gemini.models.generate_content.return_value = SimpleNamespace(
            text=_batch_response(9),
        )
        self.gemini = self.enterContext(
            patch("api.services.gemini_client", gemini),
        )
        groq = Mock()
        groq.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=_batch_response(9)),
            )],
        )
        self.groq = self.enterContext(
            patch("api.services.groq_client", groq),
        )

    def _assessment(self, count=9, *, length=24):
        return call_llm_with_fallback(
            "Assess each original source independently.",
            _batch_prompt(count, length=length),
            operation=ASSESSMENT_OPERATION,
        )

    def _verdict(self):
        return call_llm_with_fallback(
            "Judge from the complete evidence dossier.",
            "=== SOURCE IDENTITY GROUP 1 ===\nArticle confirms the event.",
            operation=PILOT_OPERATION,
        )

    def test_nine_item_batch_bypasses_cloudflare_without_dropping_evidence(self):
        with patch("api.services.record_llm_provider_call") as record:
            result = self._assessment(9)
        self.assertEqual(result, _batch_response(9))
        self.cloud.assert_not_called()
        self.gemini.models.generate_content.assert_called_once()
        self.assertEqual(
            self.gemini.models.generate_content.call_args.kwargs["contents"],
            _batch_prompt(9),
        )
        event = record.call_args_list[0]
        self.assertEqual(event.args[1], "cloudflare")
        self.assertEqual(event.args[4], "skipped")
        self.assertEqual(
            event.args[5], "CloudflareEvaluationError code=ASSESSMENT_BATCH_TOO_LARGE",
        )

    def test_bypass_keeps_final_verdict_cloudflare_eligible_same_job(self):
        self.cloud.return_value = _VALID_VERDICT
        with llm_provider_scope():
            self.assertEqual(self._assessment(9), _batch_response(9))
            self.assertEqual(self._verdict(), _VALID_VERDICT)
        self.cloud.assert_called_once()
        self.assertEqual(
            self.cloud.call_args.kwargs["max_completion_tokens"],
            PILOT_COMPLETION_TOKENS,
        )
        self.assertNotIn("http_timeout", self.cloud.call_args.kwargs)

    def test_large_batch_with_gemini_unavailable_still_allows_final_cloudflare(self):
        self.gemini.models.generate_content.side_effect = RuntimeError(
            "Provider payment unavailable",
        )
        self.cloud.return_value = _VALID_VERDICT
        with llm_provider_scope():
            self.assertEqual(self._assessment(9), _batch_response(9))
            self.assertEqual(self._verdict(), _VALID_VERDICT)
        self.cloud.assert_called_once()
        self.groq.chat.completions.create.assert_called_once()
        self.assertEqual(
            self.groq.chat.completions.create.call_args.kwargs["messages"][1]["content"],
            _batch_prompt(9),
        )

    def test_four_item_batch_uses_cloudflare_and_full_2048_budget(self):
        self.cloud.return_value = _batch_response(4)
        with patch("api.services.record_llm_provider_call") as record:
            result = self._assessment(4)
        self.assertEqual(result, _batch_response(4))
        self.gemini.models.generate_content.assert_not_called()
        self.cloud.assert_called_once()
        self.assertEqual(
            self.cloud.call_args.kwargs["http_timeout"], ASSESSMENT_HTTP_TIMEOUT,
        )
        self.assertEqual(
            self.cloud.call_args.kwargs["max_completion_tokens"], 2048,
        )
        self.assertEqual(record.call_args.args[4], "success")

    def test_successful_small_assessment_then_verdict_in_same_job(self):
        self.cloud.side_effect = [_batch_response(2), _VALID_VERDICT]
        with llm_provider_scope():
            self.assertEqual(self._assessment(2), _batch_response(2))
            self.assertEqual(self._verdict(), _VALID_VERDICT)
        self.assertEqual(self.cloud.call_count, 2)

    def test_actual_cloudflare_transport_failure_still_trips_shared_breaker(self):
        self.cloud.side_effect = [
            CloudflareEvaluationError("TRANSPORT_ReadTimeout"),
            _VALID_VERDICT,
        ]
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=_batch_response(2),
        )
        with llm_provider_scope():
            self.assertEqual(self._assessment(2), _batch_response(2))
            # The final evaluator should not incur another Cloudflare call
            # after a genuine Cloudflare outage in this one job.
            self.gemini.models.generate_content.return_value = SimpleNamespace(
                text=_VALID_VERDICT,
            )
            self.assertEqual(self._verdict(), _VALID_VERDICT)
        self.cloud.assert_called_once()
        with llm_provider_scope():
            self.assertEqual(self._verdict(), _VALID_VERDICT)
        self.assertEqual(self.cloud.call_count, 2)

    def test_oversized_prompt_bypasses_without_truncation(self):
        system = "Independent assessment."
        prompt = _batch_prompt(2, length=16000)
        self.assertEqual(
            cloudflare_assessment_bypass_reason(system, prompt),
            "PROMPT_TOO_LONG",
        )
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=_batch_response(2),
        )
        with patch("api.services.record_llm_provider_call") as record:
            self.assertEqual(call_llm_with_fallback(
                system, prompt, operation=ASSESSMENT_OPERATION,
            ), _batch_response(2))
        self.cloud.assert_not_called()
        self.assertEqual(
            self.gemini.models.generate_content.call_args.kwargs["contents"],
            prompt,
        )
        self.assertIn("PROMPT_TOO_LONG", record.call_args_list[0].args[5])

    def test_exact_threshold_and_invalid_envelopes(self):
        self.assertEqual(ASSESSMENT_MAX_ITEMS, 4)
        self.assertIsNone(cloudflare_assessment_bypass_reason(
            "System", _batch_prompt(4),
        ))
        self.assertEqual(
            cloudflare_assessment_bypass_reason("System", _batch_prompt(5)),
            "ASSESSMENT_BATCH_TOO_LARGE",
        )
        for invalid in ("not json", "UNTRUSTED ASSESSMENT DATA:\n{}"):
            self.assertEqual(
                cloudflare_assessment_bypass_reason("System", invalid),
                "INVALID_ASSESSMENT_INPUT",
            )

    def test_local_bypass_event_never_leaks_claims_or_evidence(self):
        @verification_telemetry_scope()
        def run(claim_id):
            self._assessment(9)
            event = get_current_collector().events[0]
            return event["outcome"], event["error_label"], event["metadata"]

        status, error, metadata = run(str(uuid4()))
        self.assertEqual(status, "skipped")
        self.assertEqual(error, "CloudflareEvaluationError code=ASSESSMENT_BATCH_TOO_LARGE")
        self.assertEqual(metadata, {})
        self.assertNotIn("mission", str((status, error, metadata)))

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_prod_never_even_performs_cloudflare_preflight(self):
        with patch(
            "api.services.cloudflare_assessment_bypass_reason",
            side_effect=AssertionError("should not preflight in production"),
        ):
            self.assertEqual(self._assessment(9), _batch_response(9))
        self.cloud.assert_not_called()

    def test_disabled_assessment_flag_preserves_existing_routing(self):
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "0",
        }), patch(
            "api.services.cloudflare_assessment_bypass_reason",
            side_effect=AssertionError("should not preflight when off"),
        ):
            self.assertEqual(self._assessment(9), _batch_response(9))
        self.cloud.assert_not_called()


class CloudflareAssessmentTransportTimeoutTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "test-secret",
        }))

    def _mock_post(self, content):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": content}}],
        }
        return Mock(return_value=response)

    def test_assessment_uses_shorter_timeout_not_final_verdict(self):
        post = self._mock_post(_batch_response(2))
        with patch(
            "api.verification.cloudflare_evaluation.requests.post", post,
        ):
            result = call_validated_cloudflare_pilot(
                "System", _batch_prompt(2),
                operation=ASSESSMENT_OPERATION,
            )
        self.assertEqual(result, _batch_response(2))
        self.assertEqual(post.call_args.kwargs["timeout"], (3, 15))
        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 2048)
        self.assertEqual(len(post.call_args.kwargs["json"]["messages"]), 2)

        post_final = self._mock_post(_VALID_VERDICT)
        with patch(
            "api.verification.cloudflare_evaluation.requests.post", post_final,
        ):
            self.assertEqual(
                call_validated_cloudflare_pilot("System", "Dossier"),
                _VALID_VERDICT,
            )
        self.assertEqual(post_final.call_args.kwargs["timeout"], (5, 45))
        self.assertEqual(post_final.call_args.kwargs["json"]["max_tokens"], 2048)

    def test_invalid_timeouts_rejected_before_network(self):
        post = Mock()
        for invalid in (0, 15, (0, 15), (3, 0), (3, 46), (6, 15),
                        (True, 15), (3.0, 15), ("3", 15), [3, 15]):
            with self.subTest(value=invalid), self.assertRaisesRegex(
                CloudflareEvaluationError, "INVALID_HTTP_TIMEOUT",
            ):
                generate_evaluation_json(
                    "System", "Dossier", http_timeout=invalid,
                    http_post=post,
                )
        post.assert_not_called()

    def test_timeout_has_sanitized_label_and_no_retry(self):
        post = Mock(side_effect=requests.exceptions.ReadTimeout("private body"))
        with self.assertRaisesRegex(
            CloudflareEvaluationError, "^TRANSPORT_ReadTimeout$",
        ):
            generate_evaluation_json(
                "System", "Dossier", http_timeout=(3, 15),
                http_post=post,
            )
        post.assert_called_once()
        self.assertEqual(
            sanitized_cloudflare_error_code(
                CloudflareEvaluationError("ASSESSMENT_BATCH_TOO_LARGE")
            ),
            "ASSESSMENT_BATCH_TOO_LARGE",
        )


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflareAssessmentCapacityFastFailTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "secret-never-output",
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "1",
            "CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY": "1",
        }))

    def _post(self, raw):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": raw}}],
            "usage": {
                "prompt_tokens": 900,
                "completion_tokens": 350,
                "completion_tokens_details": {"reasoning_tokens": 125},
            },
        }
        return Mock(return_value=response)

    def test_explicit_dev_opt_in_passes_flag_to_assessment_only(self):
        self.assertTrue(cloudflare_assessment_reject_if_busy_enabled())
        prompt = _batch_prompt(1)
        original_response = _batch_response(1)
        assessment_post = self._post(original_response)
        audit = {}
        with patch(
            "api.verification.cloudflare_evaluation.requests.post",
            assessment_post,
        ):
            result = call_validated_cloudflare_pilot(
                "Instructions", prompt,
                operation=ASSESSMENT_OPERATION, audit_metadata=audit,
            )
        self.assertEqual(result, original_response)
        sent = assessment_post.call_args.kwargs
        self.assertEqual(sent["json"]["options"], {"rejectIfBusy": True})
        self.assertEqual(sent["json"]["messages"][1]["content"], prompt)
        self.assertEqual(sent["json"]["max_tokens"], 2048)
        self.assertEqual(sent["timeout"], (3, 15))
        self.assertEqual(audit["prompt_tokens"], 900)
        self.assertEqual(audit["reasoning_tokens"], 125)

        final_post = self._post(_VALID_VERDICT)
        with patch(
            "api.verification.cloudflare_evaluation.requests.post",
            final_post,
        ):
            self.assertEqual(
                call_validated_cloudflare_pilot("Instructions", "full dossier"),
                _VALID_VERDICT,
            )
        final_json = final_post.call_args.kwargs["json"]
        self.assertNotIn("options", final_json)
        self.assertEqual(final_json["max_tokens"], 2048)
        self.assertEqual(final_post.call_args.kwargs["timeout"], (5, 45))

    def test_all_flags_required_and_production_blocked(self):
        for flag in (
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT",
            "CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY",
        ):
            with self.subTest(flag=flag), patch.dict(os.environ, {flag: "0"}):
                self.assertFalse(cloudflare_assessment_reject_if_busy_enabled())

        with override_settings(APP_ENV="staging"):
            self.assertFalse(cloudflare_assessment_reject_if_busy_enabled())
        with override_settings(DEBUG=False):
            self.assertFalse(cloudflare_assessment_reject_if_busy_enabled())
        with override_settings(APP_ENV="production", DEBUG=False):
            self.assertFalse(cloudflare_assessment_reject_if_busy_enabled())

    def test_invalid_or_non_exact_opt_in_does_not_inject_options(self):
        for value in ("", "false", "true", "True", "2", " 1"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY": value},
            ):
                self.assertFalse(cloudflare_assessment_reject_if_busy_enabled())
                post = self._post(_batch_response(1))
                with patch(
                    "api.verification.cloudflare_evaluation.requests.post", post,
                ):
                    self.assertEqual(
                        call_validated_cloudflare_pilot(
                            "Instructions", _batch_prompt(1),
                            operation=ASSESSMENT_OPERATION,
                        ),
                        _batch_response(1),
                    )
                self.assertNotIn("options", post.call_args.kwargs["json"])

    def test_reasoning_content_never_enters_returned_assessment_text(self):
        raw = _batch_response(1)
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": raw,
                    "reasoning_content": "PRIVATE THINKING DO NOT STORE",
                },
            }],
        }
        post = Mock(return_value=response)
        metadata = {}
        with patch("api.verification.cloudflare_evaluation.requests.post", post):
            result = call_validated_cloudflare_pilot(
                "Instructions", _batch_prompt(1),
                operation=ASSESSMENT_OPERATION, audit_metadata=metadata,
            )
        self.assertEqual(result, raw)
        self.assertNotIn("PRIVATE THINKING", str(metadata))
        self.assertTrue(metadata["reasoning_present"])
