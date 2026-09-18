import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from google.genai import errors

from api.services import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    LLMProviderUnavailableError,
    call_llm_with_fallback,
    llm_provider_scope,
)


class LLMProviderReliabilityTests(SimpleTestCase):
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

    def _call(self):
        return call_llm_with_fallback("System instructions", "User prompt")

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
