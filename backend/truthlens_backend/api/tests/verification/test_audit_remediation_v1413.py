import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services
from api.verification.runs import CURRENT_VERIFICATION_PIPELINE_VERSION


class VerificationAuditRemediationV1413Tests(SimpleTestCase):
    def test_claim_gate_prompts_use_generic_nonfactual_examples(self):
        payload = {
            "cleaned_claim": "OUT_OF_SCOPE",
            "search_query": "",
            "search_queries": [],
            "article_stance": "NEUTRAL",
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(payload),
        ) as provider:
            services.clean_ocr_text("Public libraries should stay open later.")
            services.extract_search_query(
                "Public libraries should stay open later.",
                "https://example.com/article",
            )

        prompts = [call.args[0] for call in provider.call_args_list]
        self.assertEqual(len(prompts), 2)

        generic_examples = (
            "Public libraries should stay open later.",
            "I hope the meeting goes well tomorrow.",
            "Please forward this note to your classmates.",
            "That movie was really inspiring.",
            "Vanilla ice cream tastes better than chocolate.",
            "The health ministry said schools should serve healthier meals.",
        )
        frozen_examples = (
            "School cafeterias should offer healthier food.",
            "I hope our presentation goes well tomorrow.",
            "Please send this link to your classmates.",
            "That speech was really inspiring.",
            "Chocolate ice cream tastes better than every other flavor.",
            "WHO said schools should offer healthier food.",
        )

        for prompt in prompts:
            for value in generic_examples:
                with self.subTest(kind="generic", value=value):
                    self.assertIn(value, prompt)
            for value in frozen_examples:
                with self.subTest(kind="frozen", value=value):
                    self.assertNotIn(value, prompt)

    def test_prompt_generalization_remains_in_v1413_or_later(self):
        version = tuple(
            int(part) for part in CURRENT_VERIFICATION_PIPELINE_VERSION.split(".")
        )
        self.assertGreaterEqual(version, (1, 4, 13))
