import os
import json
import warnings
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from google.genai import errors, types

from api.services import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    LLMProviderUnavailableError,
    call_llm_with_fallback,
    llm_provider_scope,
)


class LLMProviderReliabilityTests(SimpleTestCase):
    def _capture_groq_failure(self, error):
        self.gemini_client.models.generate_content.reset_mock()
        self.groq_client.chat.completions.create.reset_mock()
        self.gemini_client.models.generate_content.side_effect = RuntimeError("Gemini unavailable")
        self.groq_client.chat.completions.create.side_effect = error
        with self.assertLogs("api.services", level="INFO") as logs:
            with self.assertRaises(LLMProviderUnavailableError) as raised:
                self._call(operation="evidence_assessment")
        self.assertIs(raised.exception.__cause__, error)
        self.gemini_client.models.generate_content.assert_called_once()
        self.groq_client.chat.completions.create.assert_called_once()
        output = "\n".join(logs.output)
        diagnostic = next(line for line in logs.output if "LLM_GROQ_FAILURE_METADATA" in line)
        return output, diagnostic

    def test_groq_failure_diagnostics_log_allowlisted_status_type_and_param(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                error = RuntimeError("Not logged")
                error.status_code = 400
                fields = {"type": "invalid_request_error", "param": "response_format"}
                error.body = {"error": fields} if nested else fields
                _, diagnostic = self._capture_groq_failure(error)
                for expected in ("operation=evidence_assessment", "status_code=400",
                                 "error_type=invalid_request_error", "param=response_format"):
                    self.assertIn(expected, diagnostic)
                self.assertNotIn("has_failed_generation=", diagnostic)

    def test_groq_failed_generation_is_logged_only_as_a_boolean(self):
        for value, expected in (("PRIVATE-GENERATION-CONTENT", "true"), (None, "false")):
            with self.subTest(expected=expected):
                error = RuntimeError("Not logged")
                error.body = {"failed_generation": value}
                output, diagnostic = self._capture_groq_failure(error)
                self.assertIn(f"has_failed_generation={expected}", diagnostic)
                self.assertNotIn("PRIVATE-GENERATION-CONTENT", output)

    def test_groq_error_code_is_allowlisted_for_nested_flat_and_attribute_metadata(self):
        for source in ("nested", "flat", "attribute"):
            for code, expected in (
                ("json_validate_failed", "json_validate_failed"),
                ("PRIVATE-ERROR-CODE", "unknown"),
                (None, "unknown"), (42, "unknown"), ([], "unknown"),
                ({"secret": "PRIVATE-ERROR-CODE"}, "unknown"),
            ):
                with self.subTest(source=source, expected=expected, code_type=type(code)):
                    error = RuntimeError("PRIVATE-ERROR-CODE")
                    if source == "attribute":
                        error.code = code
                    else:
                        fields = {"code": code}
                        error.body = {"error": fields} if source == "nested" else fields
                    output, diagnostic = self._capture_groq_failure(error)
                    self.assertIn(f"error_code={expected}", diagnostic)
                    self.assertNotIn("PRIVATE-ERROR-CODE", output)

    def test_groq_raising_code_accessor_is_harmless_and_missing_code_is_unknown(self):
        class UnreadableCodeError(RuntimeError):
            @property
            def code(self):
                raise RuntimeError("PRIVATE-CODE-ACCESS")

        for error in (UnreadableCodeError("PRIVATE-CODE-ACCESS"), RuntimeError("PRIVATE-CODE-ACCESS")):
            output, diagnostic = self._capture_groq_failure(error)
            self.assertIn("error_code=unknown", diagnostic)
            self.assertNotIn("PRIVATE-CODE-ACCESS", output)

    def test_groq_failure_diagnostics_exclude_all_arbitrary_provider_details(self):
        secret = "PRIVATE-CLAIM-EVIDENCE-URL-KEY-SECRET"
        error = RuntimeError(secret)
        error.status_code = secret
        error.body = {"error": {
            "type": secret, "param": secret, "message": secret,
            "failed_generation": {"content": secret, "reason": secret, "output": secret},
        }, "arbitrary_body_metadata": secret}
        output, diagnostic = self._capture_groq_failure(error)
        self.assertNotIn(secret, output)
        self.assertIn("error_type=unknown", diagnostic)
        self.assertIn("has_failed_generation=true", diagnostic)
        self.assertNotIn("status_code=", diagnostic)
        self.assertNotIn("param=", diagnostic)

    def test_groq_failure_diagnostics_tolerate_missing_malformed_and_raising_metadata(self):
        class UnreadableError(RuntimeError):
            @property
            def body(self):
                raise RuntimeError("PRIVATE-METADATA-ERROR")

            @property
            def status_code(self):
                raise RuntimeError("PRIVATE-METADATA-ERROR")

            @property
            def type(self):
                raise RuntimeError("PRIVATE-METADATA-ERROR")

            @property
            def param(self):
                raise RuntimeError("PRIVATE-METADATA-ERROR")

        errors_to_check = [RuntimeError("PRIVATE-METADATA-ERROR"),
                           UnreadableError("PRIVATE-METADATA-ERROR")]
        for body in (None, "PRIVATE-METADATA-ERROR", ["PRIVATE-METADATA-ERROR"],
                     {"error": {"type": [], "param": {}, "failed_generation": object()}}):
            error = RuntimeError("PRIVATE-METADATA-ERROR")
            error.body = body
            error.status_code = True
            errors_to_check.append(error)
        for error in errors_to_check:
            output, diagnostic = self._capture_groq_failure(error)
            self.assertNotIn("PRIVATE-METADATA-ERROR", output)
            self.assertIn("error_type=unknown", diagnostic)
            self.assertNotIn("status_code=", diagnostic)
            self.assertNotIn("param=", diagnostic)

    def test_bounded_gemini_operations_have_separate_thinking_and_json_capacity(self):
        for operation, visible, thoughts in (("evidence_assessment", 1056, 1536),
                                              ("persisted_evidence_evaluation", 1536, 2048)):
            with self.subTest(operation=operation), patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-flash"}):
                response = json.dumps(dict(reasoning="Evidence", verdict="UNVERIFIED",
                    summary="Insufficient", confidence_score=0, score_context="Context"))
                self.gemini_client.models.generate_content.return_value = SimpleNamespace(text=response)
                self._call(operation=operation, max_output_tokens=visible)
                config = self.gemini_client.models.generate_content.call_args.kwargs["config"]
                self.assertEqual(config.thinking_config.thinking_budget, thoughts)
                self.assertEqual(config.max_output_tokens, visible + thoughts)

    def test_unsupported_models_and_unrelated_operations_do_not_get_thinking_settings(self):
        for model, operation in (("gemini-2.5-pro", "evidence_assessment"),
                                 ("custom-gemini", "evidence_assessment"),
                                 ("gemini-2.5-flash", "claim_equivalence")):
            with self.subTest(model=model, operation=operation), patch.dict(os.environ, {"GEMINI_MODEL": model}):
                self._call(operation=operation, max_output_tokens=800)
                config = self.gemini_client.models.generate_content.call_args.kwargs["config"]
                self.assertIsNone(config.thinking_config)
                self.assertEqual(config.max_output_tokens, 800)

    def test_gemini_max_tokens_rejects_even_valid_json_and_falls_back_once(self):
        self.gemini_client.models.generate_content.return_value = SimpleNamespace(
            text='{"valid": true}', candidates=[SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)],
        )
        with self.assertLogs("api.services", level="INFO") as logs, llm_provider_scope():
            self.assertEqual(self._call(operation="evidence_assessment", max_output_tokens=1056),
                             '{"provider": "groq"}')
            # Successful takeover retains existing job-local degradation.
            self._call(operation="evidence_assessment", max_output_tokens=1056)
        self.gemini_client.models.generate_content.assert_called_once()
        self.assertEqual(self.groq_client.chat.completions.create.call_count, 2)
        args = self.groq_client.chat.completions.create.call_args.kwargs
        self.assertEqual(args["max_completion_tokens"], 1056)
        self.assertEqual(args["response_format"], {"type": "json_object"})
        self.assertNotIn("reasoning_effort", args)
        self.assertIn("finish_reason=MAX_TOKENS", "\n".join(logs.output))
        self.assertIn("outcome=failed", "\n".join(logs.output))

    def test_gemini_truncation_and_groq_failure_preserve_original_cause(self):
        self.gemini_client.models.generate_content.return_value = SimpleNamespace(
            text='{"partial":', candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
        )
        error = RuntimeError("private provider failure")
        self.groq_client.chat.completions.create.side_effect = error
        with self.assertRaises(LLMProviderUnavailableError) as raised:
            self._call(operation="evidence_assessment", max_output_tokens=800)
        self.assertIs(raised.exception.__cause__, error)
        self.gemini_client.models.generate_content.assert_called_once()
        self.groq_client.chat.completions.create.assert_called_once()

    def test_final_invalid_gemini_response_uses_existing_groq_fallback(self):
        self.gemini_client.models.generate_content.return_value = SimpleNamespace(text='{"partial":')
        valid = json.dumps(dict(reasoning="Evidence", verdict="UNVERIFIED", summary="Insufficient",
                                confidence_score=0, score_context="Context"))
        self.groq_client.chat.completions.create.return_value.choices[0].message.content = valid
        self.assertEqual(self._call(operation="persisted_evidence_evaluation", max_output_tokens=1536), valid)
        self.assertEqual(self.groq_client.chat.completions.create.call_args.kwargs["max_completion_tokens"], 1536)

    def test_final_max_tokens_rejects_valid_decision_and_returns_groq_decision(self):
        valid = dict(reasoning="Evidence", verdict="UNVERIFIED", summary="Insufficient",
                     confidence_score=0, score_context="Context")
        self.gemini_client.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps({**valid, "verdict": "FACT"}),
            candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
        )
        expected = json.dumps(valid)
        self.groq_client.chat.completions.create.return_value.choices[0].message.content = expected
        self.assertEqual(self._call(operation="persisted_evidence_evaluation", max_output_tokens=1536), expected)
        self.gemini_client.models.generate_content.assert_called_once()
        self.groq_client.chat.completions.create.assert_called_once()

    def test_sdk_unknown_finish_warning_is_scoped_and_unrelated_warnings_survive(self):
        secret = "PRIVATE-SDK-FINISH-VALUE"
        def response(**kwargs):
            warnings.warn_explicit(secret + " is not a valid FinishReason", UserWarning,
                                   filename="sdk.py", lineno=1, module="google.genai._common")
            warnings.warn("unrelated application warning", RuntimeWarning)
            return SimpleNamespace(text="{}")
        self.gemini_client.models.generate_content.side_effect = response
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            self.assertEqual(self._call(), "{}")
        self.assertEqual([str(w.message) for w in captured], ["unrelated application warning"])
        # The request-local SDK filter must not survive the call.
        with warnings.catch_warnings(record=True) as restored:
            warnings.simplefilter("always")
            warnings.warn_explicit(secret + " is not a valid FinishReason", UserWarning,
                                   filename="sdk.py", lineno=1, module="google.genai._common")
        self.assertEqual(len(restored), 1)
        self.assertIn(secret, str(restored[0].message))

    def test_truncated_assessment_with_failed_fallback_remains_unknown_without_scores(self):
        from api.verification.evidence_assessment import assess_reasoning_evidence_batch_against_claim
        self.gemini_client.models.generate_content.return_value = SimpleNamespace(
            text='{"partial":', candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
        )
        self.groq_client.chat.completions.create.side_effect = RuntimeError("simulated fallback failure")
        result = assess_reasoning_evidence_batch_against_claim("Claim", [SimpleNamespace(content="Evidence")])[0]
        self.assertEqual((result.stance, result.relevance_score, result.directness_score),
                         ("UNKNOWN", None, None))

    def test_invalid_final_responses_from_both_providers_raise_typed_failure(self):
        from api.services import LLMInvalidFinalResponseError
        self.gemini_client.models.generate_content.return_value = SimpleNamespace(text='{"partial":')
        self.groq_client.chat.completions.create.return_value.choices[0].message.content = '{"partial":'
        with self.assertRaises(LLMInvalidFinalResponseError):
            self._call(operation="persisted_evidence_evaluation", max_output_tokens=1536)
        self.gemini_client.models.generate_content.assert_called_once()
        self.groq_client.chat.completions.create.assert_called_once()

    def setUp(self):
        self.gemini_client = Mock()
        self.groq_client = Mock()
        self.gemini_client.models.generate_content.return_value = (
            SimpleNamespace(text='{"provider": "gemini"}')
        )
        self.groq_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"provider": "groq"}')
            )]
        )
        self.enterContext(patch(
            "api.services.gemini_client", self.gemini_client,
        ))
        self.enterContext(patch(
            "api.services.groq_client", self.groq_client,
        ))

    def _call(self, **kwargs):
        return call_llm_with_fallback(
            "System instructions",
            "User prompt",
            **kwargs,
        )

    def test_default_call_has_no_gemini_timeout(self):
        self.assertEqual(self._call(), '{"provider": "gemini"}')

        config = self.gemini_client.models.generate_content.call_args.kwargs[
            "config"
        ]
        self.assertIsNone(config.http_options)
        self.assertEqual(config.system_instruction, "System instructions")
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.temperature, 0.1)

    def test_gemini_diagnostics_tolerate_absent_or_none_metadata(self):
        for fields in ({}, {"candidates": None, "usage_metadata": None},
                       {"candidates": [], "usage_metadata": SimpleNamespace()},
                       {"candidates": [None], "usage_metadata": None}):
            with self.subTest(fields=fields):
                self.gemini_client.models.generate_content.return_value = SimpleNamespace(
                    text='{"provider": "gemini"}', **fields,
                )
                self.assertEqual(self._call(), '{"provider": "gemini"}')
        self.groq_client.chat.completions.create.assert_not_called()

    def test_gemini_diagnostics_log_recognized_finish_reason_and_token_counts(self):
        for reason in (types.FinishReason.MAX_TOKENS, "MAX_TOKENS", "FinishReason.MAX_TOKENS"):
            with self.subTest(reason=reason):
                self.gemini_client.models.generate_content.return_value = SimpleNamespace(
                    text='{"provider": "gemini"}',
                    candidates=[SimpleNamespace(finish_reason=reason)],
                    usage_metadata=SimpleNamespace(
                        prompt_token_count=1200, candidates_token_count=80,
                        thoughts_token_count=400, total_token_count=1680,
                    ),
                )
                with self.assertLogs("api.services", level="INFO") as logs:
                    self.assertEqual(self._call(operation="evidence_assessment"),
                                     '{"provider": "groq"}')
                diagnostic = next(line for line in logs.output
                                  if "LLM_GEMINI_RESPONSE_METADATA" in line)
                for expected in ("operation=evidence_assessment", "finish_reason=MAX_TOKENS",
                                 "prompt_token_count=1200", "candidates_token_count=80",
                                 "thoughts_token_count=400", "total_token_count=1680"):
                    self.assertIn(expected, diagnostic)

    def test_gemini_diagnostics_exclude_prompts_response_content_and_unsafe_metadata(self):
        secret = "PRIVATE-CLAIM-EVIDENCE-URL-SECRET"
        self.gemini_client.models.generate_content.return_value = SimpleNamespace(
            text=secret, candidates=[SimpleNamespace(finish_reason=secret, content=secret)],
            usage_metadata=SimpleNamespace(
                prompt_token_count=secret, candidates_token_count=None,
                thoughts_token_count=True, total_token_count=-1,
            ),
        )
        with self.assertLogs("api.services", level="INFO") as logs:
            self.assertEqual(call_llm_with_fallback(secret, secret, operation="evidence_assessment"), secret)
        output = "\n".join(logs.output)
        self.assertNotIn(secret, output)
        diagnostic = next(line for line in logs.output if "LLM_GEMINI_RESPONSE_METADATA" in line)
        self.assertNotIn("finish_reason=", diagnostic)
        self.assertNotIn("token_count=", diagnostic)

    def test_gemini_diagnostics_omit_unrecognized_enum_and_object_finish_reasons(self):
        secret = "PRIVATE-CLAIM-EVIDENCE-URL-SECRET"

        class InvalidReason:
            @property
            def value(self):
                raise RuntimeError(secret)

            def __str__(self):
                raise AssertionError("Unrecognized finish reason must not be stringified")

        # The SDK warning itself contains the raw value: capture and assert it
        # explicitly instead of leaking the synthetic secret to the test console.
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            unknown_reason = types.FinishReason(secret)
        self.assertEqual(len(captured), 1)
        self.assertIs(captured[0].category, UserWarning)
        self.assertIn("is not a valid FinishReason", str(captured[0].message))
        self.assertIn(secret, str(captured[0].message))
        for reason in (unknown_reason, SimpleNamespace(value=secret), InvalidReason()):
            self.gemini_client.models.generate_content.return_value = SimpleNamespace(
                text="{}", candidates=[SimpleNamespace(finish_reason=reason)],
            )
            with self.assertLogs("api.services", level="INFO") as logs:
                self.assertEqual(self._call(operation="evidence_assessment"), "{}")
            output = "\n".join(logs.output)
            self.assertNotIn(secret, output)
            diagnostic = next(line for line in logs.output if "LLM_GEMINI_RESPONSE_METADATA" in line)
            self.assertNotIn("finish_reason=", diagnostic)
        self.groq_client.chat.completions.create.assert_not_called()

    def test_gemini_diagnostic_metadata_access_errors_do_not_affect_success(self):
        class Response:
            text = '{"provider": "gemini"}'

            @property
            def candidates(self):
                raise RuntimeError("private metadata access error")

            @property
            def usage_metadata(self):
                raise RuntimeError("private metadata access error")

        self.gemini_client.models.generate_content.return_value = Response()
        with self.assertLogs("api.services", level="INFO") as logs:
            self.assertEqual(self._call(), Response.text)
        self.assertNotIn("private metadata access error", "\n".join(logs.output))
        self.groq_client.chat.completions.create.assert_not_called()

    def test_positive_timeout_uses_supported_request_http_options(self):
        result = self._call(
            operation="evidence_assessment",
            gemini_timeout_ms=1250,
        )

        self.assertEqual(result, '{"provider": "gemini"}')
        config = self.gemini_client.models.generate_content.call_args.kwargs[
            "config"
        ]
        self.assertIsInstance(config.http_options, types.HttpOptions)
        self.assertEqual(config.http_options.timeout, 1250)
        self.groq_client.chat.completions.create.assert_not_called()

    def test_timeout_failure_falls_back_without_passing_timeout_to_groq(self):
        self.gemini_client.models.generate_content.side_effect = TimeoutError(
            "Gemini timed out"
        )

        result = self._call(
            operation="evidence_assessment",
            gemini_timeout_ms=1250,
        )

        self.assertEqual(result, '{"provider": "groq"}')
        groq_kwargs = self.groq_client.chat.completions.create.call_args.kwargs
        self.assertNotIn("timeout", groq_kwargs)
        self.assertNotIn("http_options", groq_kwargs)

    def test_timeout_fallback_preserves_scope_degradation_and_scope_reset(self):
        self.gemini_client.models.generate_content.side_effect = [
            TimeoutError("Gemini timed out"),
            SimpleNamespace(text='{"provider": "gemini"}'),
        ]

        with llm_provider_scope():
            self.assertEqual(
                self._call(gemini_timeout_ms=1250),
                '{"provider": "groq"}',
            )
            self.assertEqual(
                self._call(gemini_timeout_ms=1250),
                '{"provider": "groq"}',
            )
        with llm_provider_scope():
            self.assertEqual(
                self._call(gemini_timeout_ms=1250),
                '{"provider": "gemini"}',
            )

        self.assertEqual(self.gemini_client.models.generate_content.call_count, 2)
        self.assertEqual(self.groq_client.chat.completions.create.call_count, 2)

    def test_successful_gemini_telemetry_is_structured_and_timed(self):
        with (
            patch("api.services.time.perf_counter", side_effect=[10.0, 10.25]),
            self.assertLogs("api.services", level="INFO") as logs,
        ):
            self._call(operation="evidence_assessment")

        provider_logs = [
            line for line in logs.output if "LLM_PROVIDER_CALL" in line
        ]
        self.assertEqual(len(provider_logs), 1)
        self.assertIn("operation=evidence_assessment", provider_logs[0])
        self.assertIn("provider=gemini", provider_logs[0])
        self.assertIn("duration_ms=250", provider_logs[0])
        self.assertIn("outcome=success", provider_logs[0])
        self.assertNotIn("provider=groq", "\n".join(provider_logs))

    def test_failure_telemetry_is_sanitized_and_logs_only_called_providers(self):
        secret = "provider-secret"
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            f"Gemini request contained {secret}"
        )
        with (
            patch(
                "api.services.time.perf_counter",
                side_effect=[1.0, 1.5, 2.0, 2.25],
            ),
            self.assertLogs("api.services", level="INFO") as logs,
        ):
            self._call(operation="evidence_assessment")

        output = "\n".join(logs.output)
        self.assertIn(
            "operation=evidence_assessment provider=gemini "
            "duration_ms=500 outcome=failed error=RuntimeError",
            output,
        )
        self.assertIn(
            "operation=evidence_assessment provider=groq "
            "duration_ms=250 outcome=success",
            output,
        )
        self.assertNotIn(secret, output)

    def test_degraded_scope_logs_only_the_actual_groq_request(self):
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            "Gemini unavailable"
        )

        with llm_provider_scope():
            self._call(operation="evidence_assessment")
            with (
                patch(
                    "api.services.time.perf_counter",
                    side_effect=[3.0, 3.125],
                ),
                self.assertLogs("api.services", level="INFO") as logs,
            ):
                self._call(operation="evidence_assessment")

        provider_logs = [
            line for line in logs.output if "LLM_PROVIDER_CALL" in line
        ]
        self.assertEqual(len(provider_logs), 1)
        self.assertIn("provider=groq", provider_logs[0])
        self.assertIn("duration_ms=125", provider_logs[0])
        self.assertNotIn("provider=gemini", provider_logs[0])

    def test_gemini_success_uses_configured_model_without_groq(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": " custom-gemini "}):
            result = self._call()

        self.assertEqual(result, '{"provider": "gemini"}')
        self.assertEqual(
            self.gemini_client.models.generate_content.call_args.kwargs["model"],
            "custom-gemini",
        )
        self.groq_client.chat.completions.create.assert_not_called()

    def test_missing_or_blank_model_variables_use_defaults(self):
        with patch.dict(
            os.environ,
            {"GEMINI_MODEL": "  ", "GROQ_MODEL": "\t"},
            clear=False,
        ):
            self.gemini_client.models.generate_content.side_effect = RuntimeError(
                "Gemini unavailable"
            )
            result = self._call()

        self.assertEqual(result, '{"provider": "groq"}')
        self.assertEqual(
            self.gemini_client.models.generate_content.call_args.kwargs["model"],
            DEFAULT_GEMINI_MODEL,
        )
        groq_kwargs = self.groq_client.chat.completions.create.call_args.kwargs
        self.assertEqual(groq_kwargs["model"], DEFAULT_GROQ_MODEL)
        self.assertEqual(groq_kwargs["response_format"], {"type": "json_object"})

    def test_missing_model_variables_use_defaults(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_MODEL", None)
            os.environ.pop("GROQ_MODEL", None)
            self.gemini_client.models.generate_content.side_effect = RuntimeError(
                "Gemini unavailable"
            )
            self._call()

        self.assertEqual(
            self.gemini_client.models.generate_content.call_args.kwargs["model"],
            "gemini-2.5-flash",
        )
        self.assertEqual(
            self.groq_client.chat.completions.create.call_args.kwargs["model"],
            "openai/gpt-oss-120b",
        )

    def test_explicit_groq_model_is_respected_after_gemini_failure(self):
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            "Gemini unavailable"
        )
        with patch.dict(os.environ, {"GROQ_MODEL": " custom-groq "}):
            result = self._call()

        self.assertEqual(result, '{"provider": "groq"}')
        self.assertEqual(
            self.groq_client.chat.completions.create.call_args.kwargs["model"],
            "custom-groq",
        )

    def test_gemini_structured_429_failure_uses_groq_once(self):
        self.gemini_client.models.generate_content.side_effect = errors.ClientError(
            429, {"error": {"status": "RESOURCE_EXHAUSTED"}},
        )

        self.assertEqual(self._call(), '{"provider": "groq"}')
        self.groq_client.chat.completions.create.assert_called_once()

    def test_gemini_structured_503_failure_uses_groq_once(self):
        self.gemini_client.models.generate_content.side_effect = errors.ServerError(
            503, {"error": {"status": "UNAVAILABLE"}},
        )

        self.assertEqual(self._call(), '{"provider": "groq"}')
        self.groq_client.chat.completions.create.assert_called_once()

    def test_both_provider_failures_raise_dedicated_exception(self):
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            "Gemini unavailable"
        )
        self.groq_client.chat.completions.create.side_effect = RuntimeError(
            "Groq unavailable"
        )

        with self.assertRaises(LLMProviderUnavailableError) as raised:
            self._call()

        self.assertNotIn("UNVERIFIED", str(raised.exception))
        self.groq_client.chat.completions.create.assert_called_once()

    def test_failure_logs_do_not_expose_exception_secrets(self):
        secret = "obvious-secret-token"
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            f"https://provider.example/request?key={secret}&token={secret}"
        )
        self.groq_client.chat.completions.create.side_effect = RuntimeError(
            f"Authorization: Bearer {secret}"
        )

        with self.assertLogs("api.services", level="WARNING") as logs:
            with self.assertRaises(LLMProviderUnavailableError):
                self._call()

        self.assertNotIn(secret, "\n".join(logs.output))

    def test_same_scope_uses_groq_after_successful_takeover(self):
        self.gemini_client.models.generate_content.side_effect = errors.ClientError(
            429, {"error": {"status": "RESOURCE_EXHAUSTED"}},
        )
        with llm_provider_scope():
            self.assertEqual(self._call(), '{"provider": "groq"}')
            self.assertEqual(self._call(), '{"provider": "groq"}')

        self.gemini_client.models.generate_content.assert_called_once()
        self.assertEqual(self.groq_client.chat.completions.create.call_count, 2)

    def test_new_scope_restores_gemini_first_after_broad_provider_failure(self):
        self.gemini_client.models.generate_content.side_effect = [
            RuntimeError("Gemini unavailable"),
            SimpleNamespace(text='{"provider": "gemini"}'),
        ]
        with llm_provider_scope():
            self.assertEqual(self._call(), '{"provider": "groq"}')
        with llm_provider_scope():
            self.assertEqual(self._call(), '{"provider": "gemini"}')

        self.assertEqual(self.gemini_client.models.generate_content.call_count, 2)
        self.groq_client.chat.completions.create.assert_called_once()

    def test_scope_resets_after_exception(self):
        self.gemini_client.models.generate_content.side_effect = [
            RuntimeError("Gemini unavailable"),
            SimpleNamespace(text='{"provider": "gemini"}'),
        ]
        error = RuntimeError("Pipeline interrupted")
        with self.assertRaises(RuntimeError) as raised:
            with llm_provider_scope():
                self.assertEqual(self._call(), '{"provider": "groq"}')
                raise error

        self.assertIs(raised.exception, error)
        # An unscoped call also proves the previous context was cleared.
        self.assertEqual(self._call(), '{"provider": "gemini"}')
        self.groq_client.chat.completions.create.assert_called_once()

    def test_failed_takeover_does_not_degrade_scope(self):
        self.gemini_client.models.generate_content.side_effect = [
            RuntimeError("Gemini unavailable"),
            SimpleNamespace(text='{"provider": "gemini"}'),
        ]
        self.groq_client.chat.completions.create.side_effect = RuntimeError(
            "Groq unavailable"
        )
        with llm_provider_scope():
            with self.assertRaises(LLMProviderUnavailableError):
                self._call()
            self.assertEqual(self._call(), '{"provider": "gemini"}')

        self.assertEqual(self.gemini_client.models.generate_content.call_count, 2)

    def test_groq_failure_after_takeover_raises_without_retrying_gemini(self):
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            "Gemini unavailable"
        )
        groq_error = RuntimeError("Groq unavailable")
        self.groq_client.chat.completions.create.side_effect = [
            self.groq_client.chat.completions.create.return_value,
            groq_error,
        ]
        with llm_provider_scope():
            self.assertEqual(self._call(), '{"provider": "groq"}')
            with self.assertRaises(LLMProviderUnavailableError) as raised:
                self._call()

        self.assertIs(raised.exception.__cause__, groq_error)
        self.gemini_client.models.generate_content.assert_called_once()

    def test_unscoped_calls_remain_independent(self):
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            "Gemini unavailable"
        )
        self._call()
        self._call()
        self.assertEqual(self.gemini_client.models.generate_content.call_count, 2)

    def test_nested_scope_starts_fresh_and_restores_outer_degradation(self):
        self.gemini_client.models.generate_content.side_effect = [
            RuntimeError("Gemini unavailable"),
            SimpleNamespace(text='{"provider": "gemini"}'),
        ]
        with llm_provider_scope():
            self.assertEqual(self._call(), '{"provider": "groq"}')
            with llm_provider_scope():
                self.assertEqual(self._call(), '{"provider": "gemini"}')
            self.assertEqual(self._call(), '{"provider": "groq"}')

        self.assertEqual(self.gemini_client.models.generate_content.call_count, 2)
        self.assertEqual(self.groq_client.chat.completions.create.call_count, 2)

    def test_degraded_scope_respects_groq_model_and_json_format(self):
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            "Gemini unavailable"
        )
        with patch.dict(os.environ, {"GROQ_MODEL": " scoped-groq "}):
            with llm_provider_scope():
                self._call()
                self._call()

        for provider_call in self.groq_client.chat.completions.create.call_args_list:
            self.assertEqual(provider_call.kwargs["model"], "scoped-groq")
            self.assertEqual(
                provider_call.kwargs["response_format"], {"type": "json_object"},
            )

    def test_structured_failure_logs_exclude_provider_details(self):
        secret = "obvious-secret-token"
        self.gemini_client.models.generate_content.side_effect = errors.ClientError(
            429, {"error": {"message": secret, "status": secret}},
        )
        with self.assertLogs("api.services", level="WARNING") as logs:
            with llm_provider_scope():
                self._call()
                self.groq_client.chat.completions.create.side_effect = RuntimeError(
                    f"Authorization: Bearer {secret}"
                )
                with self.assertRaises(LLMProviderUnavailableError):
                    self._call()

        output = "\n".join(logs.output)
        self.assertIn("ClientError code=429", output)
        self.assertNotIn(secret, output)
