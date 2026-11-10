import os
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services


class GroqVisionExplanationTests(SimpleTestCase):
    def _response(self, content="Vision explanation"):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                )
            ]
        )

    def test_uses_supported_default_vision_model(self):
        with (
            patch.dict(os.environ, {"GROQ_VISION_MODEL": ""}, clear=False),
            patch.object(
                services.groq_client.chat.completions,
                "create",
                return_value=self._response(),
            ) as create,
        ):
            result = services.generate_deepfake_explanation(
                "ZmFrZS1pbWFnZQ==",
                "Face-Swap / Deepfake Manipulation",
            )

        self.assertEqual(result, "Vision explanation")
        self.assertEqual(
            create.call_args.kwargs["model"],
            services.DEFAULT_GROQ_VISION_MODEL,
        )
        self.assertEqual(
            services.DEFAULT_GROQ_VISION_MODEL,
            "qwen/qwen3.8-27b",
        )

    def test_environment_can_override_vision_model(self):
        with (
            patch.dict(
                os.environ,
                {"GROQ_VISION_MODEL": "custom/vision-model"},
                clear=False,
            ),
            patch.object(
                services.groq_client.chat.completions,
                "create",
                return_value=self._response(),
            ) as create,
        ):
            services.generate_deepfake_explanation(
                "ZmFrZS1pbWFnZQ==",
                "Diffusion Generative AI",
            )

        self.assertEqual(
            create.call_args.kwargs["model"],
            "custom/vision-model",
        )

    def test_provider_failure_returns_existing_safe_fallback(self):
        category = "Face-Swap / Deepfake Manipulation"
        with patch.object(
            services.groq_client.chat.completions,
            "create",
            side_effect=RuntimeError("provider unavailable"),
        ):
            result = services.generate_deepfake_explanation(
                "ZmFrZS1pbWFnZQ==",
                category,
            )

        self.assertEqual(
            result,
            (
                f"Forensic analysis indicates this is a {category}. "
                "However, a detailed visual summary could not be generated "
                "at this time."
            ),
        )
