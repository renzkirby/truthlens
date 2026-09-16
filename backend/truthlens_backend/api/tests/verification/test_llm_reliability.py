import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from api.services import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    LLMProviderUnavailableError,
    call_llm_with_fallback,
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

    def test_gemini_429_like_failure_uses_groq_once(self):
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            "429 quota exhausted"
        )

        self.assertEqual(self._call(), '{"provider": "groq"}')
        self.groq_client.chat.completions.create.assert_called_once()

    def test_gemini_503_like_failure_uses_groq_once(self):
        self.gemini_client.models.generate_content.side_effect = RuntimeError(
            "503 service unavailable"
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
