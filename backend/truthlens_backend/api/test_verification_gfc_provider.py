from datetime import timezone
from unittest import TestCase
from unittest.mock import Mock

from .verification.providers.google_fact_check import (
    GOOGLE_FACT_CHECK_ENDPOINT,
    GoogleFactCheckProvider,
    parse_google_fact_check_response,
)


class GoogleFactCheckResponseParserTests(
    TestCase
):

    def test_parses_fact_check_review_into_raw_evidence(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": (
                        "Example public claim."
                    ),
                    "claimant": "Example Person",
                    "claimDate": (
                        "2026-08-20T10:00:00Z"
                    ),
                    "claimReview": [
                        {
                            "publisher": {
                                "name": (
                                    "Example "
                                    "Fact Checker"
                                ),
                            },
                            "url": (
                                "https://example.com/"
                                "fact-check"
                            ),
                            "title": (
                                "Example Fact Check"
                            ),
                            "reviewDate": (
                                "2026-08-21T12:30:00Z"
                            ),
                            "textualRating": (
                                "False"
                            ),
                            "languageCode": "en",
                        }
                    ],
                }
            ]
        }

        results = (
            parse_google_fact_check_response(
                payload
            )
        )

        self.assertEqual(
            len(results),
            1,
        )

        evidence = results[0]

        self.assertEqual(
            evidence.provider,
            "GOOGLE_FACT_CHECK",
        )

        self.assertEqual(
            evidence.url,
            (
                "https://example.com/"
                "fact-check"
            ),
        )

        self.assertEqual(
            evidence.title,
            "Example Fact Check",
        )

        self.assertEqual(
            evidence.publisher,
            "Example Fact Checker",
        )

        self.assertEqual(
            evidence.source_type,
            "FACT_CHECK",
        )

        self.assertIn(
            "Claim reviewed: "
            "Example public claim.",
            evidence.content,
        )

        self.assertIn(
            "Rating: False",
            evidence.content,
        )

        self.assertEqual(
            evidence.published_at.tzinfo,
            timezone.utc,
        )

        self.assertEqual(
            evidence.raw_reference,
            {
                "gfc_claim_index": 0,
                "gfc_review_index": 0,
            },
        )

    def test_each_claim_review_becomes_separate_evidence(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": "Example claim.",
                    "claimReview": [
                        {
                            "publisher": {
                                "name": "Checker A",
                            },
                            "url": (
                                "https://a.example/"
                                "review"
                            ),
                            "textualRating": (
                                "False"
                            ),
                        },
                        {
                            "publisher": {
                                "name": "Checker B",
                            },
                            "url": (
                                "https://b.example/"
                                "review"
                            ),
                            "textualRating": (
                                "Misleading"
                            ),
                        },
                    ],
                }
            ]
        }

        results = (
            parse_google_fact_check_response(
                payload
            )
        )

        self.assertEqual(
            len(results),
            2,
        )

        self.assertEqual(
            results[0].publisher,
            "Checker A",
        )

        self.assertEqual(
            results[1].publisher,
            "Checker B",
        )

    def test_limit_is_applied_across_reviews(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": "Example claim.",
                    "claimReview": [
                        {
                            "url": (
                                "https://example.com/1"
                            ),
                        },
                        {
                            "url": (
                                "https://example.com/2"
                            ),
                        },
                        {
                            "url": (
                                "https://example.com/3"
                            ),
                        },
                    ],
                }
            ]
        }

        results = (
            parse_google_fact_check_response(
                payload,
                limit=2,
            )
        )

        self.assertEqual(
            len(results),
            2,
        )

    def test_missing_or_invalid_claims_return_empty_list(
        self,
    ):
        self.assertEqual(
            parse_google_fact_check_response(
                {}
            ),
            [],
        )

        self.assertEqual(
            parse_google_fact_check_response(
                {
                    "claims": "invalid",
                }
            ),
            [],
        )

    def test_invalid_review_date_returns_no_publication_date(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": "Example claim.",
                    "claimDate": (
                        "2026-08-20T10:00:00Z"
                    ),
                    "claimReview": [
                        {
                            "url": (
                                "https://example.com/"
                                "review"
                            ),
                            "reviewDate": "not-a-date",
                        }
                    ],
                }
            ]
        }

        evidence = (
            parse_google_fact_check_response(
                payload
            )[0]
        )

        self.assertIsNone(
            evidence.published_at
        )

    def test_empty_claim_review_is_skipped(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": "Example claim.",
                    "claimReview": [
                        {},
                    ],
                }
            ]
        }

        results = (
            parse_google_fact_check_response(
                payload
            )
        )

        self.assertEqual(
            results,
            [],
        )


class GoogleFactCheckProviderTests(
    TestCase
):

    def test_search_calls_google_and_returns_evidence(
        self,
    ):
        response = Mock()

        response.json.return_value = {
            "claims": [
                {
                    "text": "Example claim.",
                    "claimReview": [
                        {
                            "publisher": {
                                "name": (
                                    "Example Checker"
                                ),
                            },
                            "url": (
                                "https://example.com/"
                                "review"
                            ),
                            "textualRating": (
                                "False"
                            ),
                        }
                    ],
                }
            ]
        }

        http_client = Mock()
        http_client.get.return_value = (
            response
        )

        provider = GoogleFactCheckProvider(
            api_key="test-api-key",
            timeout=7.5,
            http_client=http_client,
        )

        results = provider.search(
            "  example claim  ",
            limit=3,
        )

        http_client.get.assert_called_once_with(
            GOOGLE_FACT_CHECK_ENDPOINT,
            params={
                "query": "example claim",
                "key": "test-api-key",
            },
            timeout=7.5,
        )

        response.raise_for_status.assert_called_once_with()

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            results[0].provider,
            "GOOGLE_FACT_CHECK",
        )

    def test_blank_query_does_not_make_http_request(
        self,
    ):
        http_client = Mock()

        provider = GoogleFactCheckProvider(
            api_key="test-api-key",
            http_client=http_client,
        )

        results = provider.search("   ")

        self.assertEqual(
            results,
            [],
        )

        http_client.get.assert_not_called()

    def test_missing_api_key_is_rejected(
        self,
    ):
        provider = GoogleFactCheckProvider(
            api_key="",
            http_client=Mock(),
        )

        with self.assertRaises(ValueError):
            provider.search(
                "example claim"
            )
