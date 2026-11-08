import json
from unittest.mock import patch

from django.test import SimpleTestCase

from api.verification.cloudflare_pilot import validate_pilot_response

from api.services import (
    ClaimGateError,
    _is_known_satire_source_url,
    _normalize_claim_gate_stance,
    clean_ocr_text,
    extract_search_query,
    extract_source_bounded_noneditable_claim,
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


class NoneditableClaimFallbackTests(SimpleTestCase):
    @patch("api.services.call_llm_with_fallback")
    def test_fallback_keeps_ambiguous_identifier_and_bounds_query_to_source(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps({
            "cleaned_claim": "PBBM built a subway train underground.",
            "search_query": "PBBM subway Ferdinand Marcos underground",
            "search_queries": ["PBBM subway Ferdinand Marcos underground"],
            "article_stance": "NEUTRAL",
        })

        result = extract_source_bounded_noneditable_claim(
            "TOP PROJECT PBBM built a subway train underground",
            source_kind="IMAGE",
        )

        self.assertEqual(
            result["cleaned_claim"],
            "PBBM built a subway train underground.",
        )
        self.assertEqual(
            result["search_query"],
            "pbbm subway underground",
        )
        self.assertEqual(
            result["search_queries"],
            ["pbbm subway underground"],
        )
        self.assertEqual(result["_material_anchor_tokens"], ["pbbm"])
        self.assertTrue(result["_assertion_complete"])
        self.assertNotIn("ferdinand", result["search_query"])
        self.assertNotIn("marcos", result["search_query"])

    @patch("api.services.call_llm_with_fallback")
    def test_fallback_rejects_invented_material_identifier_in_claim(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps({
            "cleaned_claim": "Ferdinand Marcos Jr built a subway.",
            "search_query": "PBBM subway",
            "search_queries": ["PBBM subway"],
            "article_stance": "NEUTRAL",
        })

        result = extract_source_bounded_noneditable_claim(
            "PBBM built a subway",
            source_kind="IMAGE",
        )

        self.assertEqual(result["cleaned_claim"], "INSUFFICIENT_CONTEXT")
        self.assertEqual(result["search_query"], "")
        self.assertEqual(result["search_queries"], [])

    @patch("api.services.call_llm_with_fallback")
    def test_fallback_amount_only_claim_has_no_identity_anchor(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps({
            "cleaned_claim": "stole P58 million",
            "search_query": "stole P58 million",
            "search_queries": ["stole P58 million"],
            "article_stance": "NEUTRAL",
        })

        result = extract_source_bounded_noneditable_claim(
            "stole P58 million",
            source_kind="IMAGE",
        )

        self.assertEqual(result["cleaned_claim"], "stole P58 million")
        self.assertEqual(result["_material_anchor_tokens"], [])
        self.assertTrue(result["_assertion_complete"])

    @patch("api.services.call_llm_with_fallback")
    def test_topic_fragment_cannot_be_marked_complete_without_predicate(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps({
            "cleaned_claim": "PBBM subway underground",
            "search_query": "PBBM subway underground",
            "search_queries": ["PBBM subway underground"],
            "article_stance": "NEUTRAL",
        })

        result = extract_source_bounded_noneditable_claim(
            "PBBM subway underground",
            source_kind="IMAGE",
        )

        self.assertEqual(result["cleaned_claim"], "PBBM subway underground")
        self.assertEqual(result["_material_anchor_tokens"], ["pbbm"])
        self.assertFalse(result["_assertion_complete"])

    @patch("api.services.call_llm_with_fallback")
    def test_source_bounded_filipino_predicate_can_be_complete(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps({
            "cleaned_claim": "PBBM gumawa subway tren",
            "search_query": "PBBM gumawa subway tren",
            "search_queries": ["PBBM gumawa subway tren"],
            "article_stance": "NEUTRAL",
        })

        result = extract_source_bounded_noneditable_claim(
            "PBBM gumawa subway tren",
            source_kind="IMAGE",
        )

        self.assertEqual(result["_material_anchor_tokens"], ["pbbm"])
        self.assertTrue(result["_assertion_complete"])
        self.assertEqual(result["search_query"], "pbbm gumawa subway tren")

    @patch("api.services.call_llm_with_fallback")
    def test_fallback_rejects_translated_or_invented_predicate(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps({
            "cleaned_claim": "PBBM built subway",
            "search_query": "PBBM subway",
            "search_queries": ["PBBM subway"],
            "article_stance": "NEUTRAL",
        })

        result = extract_source_bounded_noneditable_claim(
            "PBBM gumawa subway",
            source_kind="IMAGE",
        )

        self.assertEqual(result["cleaned_claim"], "INSUFFICIENT_CONTEXT")
        self.assertEqual(result["search_queries"], [])

    def test_fallback_rejects_unsupported_source_kind(self):
        with self.assertRaises(ValueError):
            extract_source_bounded_noneditable_claim(
                "Example claim",
                source_kind="TEXT",
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

    @patch("api.services.call_llm_with_fallback")
    def test_insufficient_context_is_preserved_without_retrieval_queries(
        self,
        mock_llm,
    ):
        mock_llm.return_value = json.dumps(
            {
                "cleaned_claim": "INSUFFICIENT_CONTEXT",
                "search_query": "joel 800 million pesos",
                "search_queries": ["joel 800 million pesos"],
                "article_stance": "NEUTRAL",
            }
        )

        result = clean_ocr_text("Joel stole 800 million pesos")

        self.assertEqual(result["cleaned_claim"], "INSUFFICIENT_CONTEXT")
        self.assertEqual(result["search_query"], "")
        self.assertEqual(result["search_queries"], [])

    def test_strict_claim_gate_contract_accepts_only_empty_queries_for_insufficient_context(
        self,
    ):
        valid = {
            "cleaned_claim": "INSUFFICIENT_CONTEXT",
            "search_query": "",
            "search_queries": [],
            "article_stance": "NEUTRAL",
        }
        invalid = {
            **valid,
            "search_query": "joel 800 million pesos",
            "search_queries": ["joel 800 million pesos"],
        }

        self.assertTrue(
            validate_pilot_response("claim_gate", json.dumps(valid), "Text: ...")
        )
        self.assertFalse(
            validate_pilot_response("claim_gate", json.dumps(invalid), "Text: ...")
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
