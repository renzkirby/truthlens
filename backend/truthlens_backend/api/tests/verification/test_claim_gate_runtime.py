import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api.services import (
    ClaimGateError,
    _is_known_satire_source_url,
    _normalize_claim_gate_stance,
    clean_ocr_text,
    extract_search_query,
)


class ClaimGateSatireRegressionTests(SimpleTestCase):
    def test_known_satire_source_accepts_exact_domains_and_subdomains(self):
        cases = (
            "https://theonion.com/article",
            "https://www.theonion.com/article",
            "https://news.theonion.com/article",
            "https://babylonbee.com/story",
            "https://sub.babylonbee.com/story",
            "https://BABYLONBEE.COM/story",
        )

        for url in cases:
            with self.subTest(url=url):
                self.assertTrue(
                    _is_known_satire_source_url(url)
                )

    def test_known_satire_source_rejects_lookalikes_and_invalid_urls(self):
        cases = (
            "https://eviltheonion.com/article",
            "https://theonion.com.evil.com/article",
            "https://evil.com/theonion.com/article",
            "https://theonion.com@evil.com/article",
            "https://example.com/article",
            "",
            None,
            "http://[",
        )

        for url in cases:
            with self.subTest(url=url):
                self.assertFalse(
                    _is_known_satire_source_url(url)
                )

    def test_normalize_stance_preserves_supported_non_satire_values(self):
        cases = (
            ("DEBUNKING", "DEBUNKING"),
            ("REPORTING", "REPORTING"),
            ("NEUTRAL", "NEUTRAL"),
            ("reporting", "REPORTING"),
        )

        for supplied, expected in cases:
            with self.subTest(supplied=supplied):
                result = _normalize_claim_gate_stance(
                    {
                        "cleaned_claim": "Example claim.",
                        "search_query": "example claim",
                        "article_stance": supplied,
                    },
                    has_known_satire_provenance=False,
                )

                self.assertEqual(
                    result["article_stance"],
                    expected,
                )

    def test_normalize_stance_downgrades_unsupported_satire_to_neutral(self):
        for supplied in ("SATIRE", " satire ", "UNKNOWN", None):
            with self.subTest(supplied=supplied):
                payload = {
                    "cleaned_claim": "Example claim.",
                    "search_query": "example claim",
                    "article_stance": supplied,
                }

                result = _normalize_claim_gate_stance(
                    payload,
                    has_known_satire_provenance=False,
                )

                self.assertEqual(
                    result["article_stance"],
                    "NEUTRAL",
                )
                self.assertEqual(
                    result["cleaned_claim"],
                    payload["cleaned_claim"],
                )
                self.assertEqual(
                    result["search_query"],
                    payload["search_query"],
                )

    def test_known_satire_provenance_forces_satire_stance(self):
        result = _normalize_claim_gate_stance(
            {
                "cleaned_claim": "Example claim.",
                "search_query": "example claim",
                "article_stance": "NEUTRAL",
            },
            has_known_satire_provenance=True,
        )

        self.assertEqual(
            result["article_stance"],
            "SATIRE",
        )

    @patch("api.services.call_llm_with_fallback")
    def test_text_model_satire_is_normalized_to_neutral(self, mock_llm):
        mock_llm.return_value = json.dumps(
            {
                "cleaned_claim":
                    "The government introduced an absurd new tax.",
                "search_query":
                    "government absurd new tax claim",
                "article_stance": "SATIRE",
            }
        )

        result = clean_ocr_text(
            "Absurd-looking government tax claim"
        )

        self.assertEqual(
            result["article_stance"],
            "NEUTRAL",
        )
        self.assertEqual(
            result["cleaned_claim"],
            "The government introduced an absurd new tax.",
        )

    @patch("api.services.call_llm_with_fallback")
    def test_normal_url_model_satire_is_normalized_to_neutral(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps(
            {
                "cleaned_claim": "Example claim.",
                "search_query": "example claim verification",
                "article_stance": "SATIRE",
            }
        )

        result = extract_search_query(
            "Example claim.",
            "https://example.com/article",
        )

        self.assertEqual(
            result["article_stance"],
            "NEUTRAL",
        )

    @patch("api.services.call_llm_with_fallback")
    def test_known_satire_url_forces_satire_stance(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps(
            {
                "cleaned_claim": "Example claim.",
                "search_query": "example claim verification",
                "article_stance": "NEUTRAL",
            }
        )

        result = extract_search_query(
            "Example claim.",
            "https://www.theonion.com/article",
        )

        self.assertEqual(
            result["article_stance"],
            "SATIRE",
        )

    @patch("api.services.call_llm_with_fallback")
    def test_lookalike_satire_url_does_not_gain_provenance(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps(
            {
                "cleaned_claim": "Example claim.",
                "search_query": "example claim verification",
                "article_stance": "SATIRE",
            }
        )

        result = extract_search_query(
            "Example claim.",
            "https://theonion.com.evil.example/article",
        )

        self.assertEqual(
            result["article_stance"],
            "NEUTRAL",
        )


class ClaimGateFailureRegressionTests(SimpleTestCase):
    @patch(
        "api.services.call_llm_with_fallback",
        return_value="not valid json",
    )
    def test_clean_ocr_text_invalid_json_raises_claim_gate_error(
        self,
        _mock_llm,
    ):
        with self.assertRaises(ClaimGateError) as context:
            clean_ocr_text("Example claim")

        self.assertIsInstance(
            context.exception.__cause__,
            json.JSONDecodeError,
        )

    @patch(
        "api.services.call_llm_with_fallback",
        return_value=json.dumps(
            {
                "search_query": "example claim",
                "article_stance": "NEUTRAL",
            }
        ),
    )
    def test_missing_cleaned_claim_raises_claim_gate_error(
        self,
        _mock_llm,
    ):
        with self.assertRaises(ClaimGateError):
            clean_ocr_text("Example claim")

    @patch("api.services.call_llm_with_fallback")
    def test_out_of_scope_is_preserved_while_satire_stance_is_neutralized(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps(
            {
                "cleaned_claim": "OUT_OF_SCOPE",
                "search_query": "none",
                "article_stance": "SATIRE",
            }
        )

        result = clean_ocr_text("Hello good morning")

        self.assertEqual(
            result["cleaned_claim"],
            "OUT_OF_SCOPE",
        )
        self.assertEqual(
            result["article_stance"],
            "NEUTRAL",
        )

    @patch(
        "api.services.call_llm_with_fallback",
        return_value="not valid json",
    )
    def test_extract_search_query_invalid_json_raises_claim_gate_error(
        self,
        _mock_llm,
    ):
        with self.assertRaises(ClaimGateError) as context:
            extract_search_query(
                "Example claim",
                "https://example.com/article",
            )

        self.assertIsInstance(
            context.exception.__cause__,
            json.JSONDecodeError,
        )
