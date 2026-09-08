import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

import requests
from tavily.errors import (
    InvalidAPIKeyError,
    TimeoutError as TavilyTimeoutError,
    UsageLimitExceededError,
)

from api.verification.contracts import RawEvidence
from api.verification.providers.tavily import (
    TavilyProvider,
    parse_tavily_response,
)


class TavilyResponseParserTests(TestCase):
    def test_one_result_maps_exactly(self):
        content = "Full evidence content.\n" * 40
        evidence = parse_tavily_response({
            "results": [{
                "url": " https://example.com/article ",
                "title": " Example Article ",
                "publisher": " Example Publisher ",
                "content": content,
                "published_date": "2026-08-21T12:30:00Z",
                "score": 0.99,
            }],
        })
        self.assertEqual(evidence, [RawEvidence(
            provider="TAVILY",
            url="https://example.com/article",
            title="Example Article",
            publisher="Example Publisher",
            content=content.strip(),
            source_type="WEB_SEARCH",
            published_at=datetime(2026, 8, 21, 12, 30, tzinfo=timezone.utc),
            raw_reference={"tavily_result_index": 0},
        )])

    def test_multiple_results_preserve_order_and_original_indexes(self):
        evidence = parse_tavily_response({
            "results": [
                None,
                {"url": "https://example.com/first"},
                {"title": "No identity"},
                {"content": "Content without a URL"},
                {"url": "https://example.com/last"},
            ],
        })
        self.assertEqual(
            [item.url for item in evidence],
            ["https://example.com/first", None, "https://example.com/last"],
        )
        self.assertEqual(
            [item.raw_reference for item in evidence],
            [{"tavily_result_index": index} for index in (1, 3, 4)],
        )

    def test_limit_applies_to_accepted_items(self):
        payload = {"results": [
            None, {}, {"url": "https://example.com/1"},
            {"content": "Second source"}, {"url": "https://example.com/3"},
        ]}
        before = deepcopy(payload)
        evidence = parse_tavily_response(payload, limit=2)
        self.assertEqual(
            [item.raw_reference for item in evidence],
            [{"tavily_result_index": 2}, {"tavily_result_index": 3}],
        )
        self.assertEqual(payload, before)

    def test_nonpositive_parser_limit_returns_no_evidence(self):
        for limit in (0, -1):
            with self.subTest(limit=limit):
                self.assertEqual(parse_tavily_response(
                    {"results": [{"url": "https://example.com"}]}, limit=limit
                ), [])

    def test_missing_or_non_list_results_return_no_evidence(self):
        for payload in ({}, {"results": None}, {"results": {}},
                        {"results": "invalid"}, {"results": ()}):
            with self.subTest(payload=payload):
                before = deepcopy(payload)
                self.assertEqual(parse_tavily_response(payload), [])
                self.assertEqual(payload, before)

    def test_malformed_and_identityless_results_are_skipped(self):
        payload = {"results": [
            None, [], "invalid", 42, {}, {"title": "Only a title"},
            {"publisher": "Only a publisher"}, {"score": 0.99},
            {"url": " ", "content": "\t"}, {"url": 42, "content": {}},
            {"url": "https://example.com"},
        ]}
        evidence = parse_tavily_response(payload)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].raw_reference, {"tavily_result_index": 10})

    def test_optional_malformed_fields_are_absent(self):
        for value in (None, "", " \t", 42, [], {}):
            with self.subTest(value=value):
                evidence = parse_tavily_response({"results": [{
                    "url": "https://example.com",
                    "title": value, "publisher": value,
                    "content": value, "published_date": value,
                }]})[0]
                self.assertIsNone(evidence.title)
                self.assertIsNone(evidence.publisher)
                self.assertIsNone(evidence.content)
                self.assertIsNone(evidence.published_at)
                content_only = parse_tavily_response({"results": [{
                    "url": value, "content": "Usable source content",
                }]})[0]
                self.assertIsNone(content_only.url)

    def test_publisher_is_not_inferred(self):
        evidence = parse_tavily_response({"results": [{
            "url": "https://reuters.com/article",
            "title": "Reuters article",
            "content": "Reported by Reuters",
        }]})[0]
        self.assertIsNone(evidence.publisher)

    def test_publication_dates_are_parsed_without_inference(self):
        cases = [
            ("2026-08-21T12:30:00Z",
             datetime(2026, 8, 21, 12, 30, tzinfo=timezone.utc)),
            ("2026-08-21T12:30:00+08:00",
             datetime(2026, 8, 21, 12, 30,
                      tzinfo=timezone(timedelta(hours=8)))),
            ("2026-08-21T12:30:00",
             datetime(2026, 8, 21, 12, 30, tzinfo=timezone.utc)),
            ("not-a-date", None), ("2026-02-30T12:00:00Z", None),
            (None, None),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                evidence = parse_tavily_response({"results": [{
                    "url": "https://example.com/2026/08/21",
                    "published_date": value,
                }]})[0]
                self.assertEqual(evidence.published_at, expected)
        missing = parse_tavily_response({"results": [{
            "url": "https://example.com/2026/08/21",
            "date": "2026-08-21T12:30:00Z",
        }]})[0]
        self.assertIsNone(missing.published_at)

    def test_answer_and_score_do_not_become_evidence_or_verdicts(self):
        self.assertEqual(parse_tavily_response({
            "answer": "This is true", "score": 1.0,
            "results": [{"score": 1.0, "title": "True"}],
        }), [])
        evidence = parse_tavily_response({
            "answer": "This is true",
            "results": [{
                "url": "https://example.com",
                "score": 0.99, "verdict": "FACT", "authority_score": 99,
                "raw_content": "Do not substitute this for content",
                "raw_reference": {"unexpected": "metadata"},
            }],
        })[0]
        self.assertEqual(evidence, RawEvidence(
            provider="TAVILY", url="https://example.com",
            source_type="WEB_SEARCH",
            raw_reference={"tavily_result_index": 0},
        ))


class TavilyProviderTests(TestCase):
    def setUp(self):
        self.client = Mock()
        self.payload = {"results": [{"url": "https://example.com"}]}
        self.client.search.return_value = self.payload
        self.provider = TavilyProvider(client=self.client)

    def test_blank_query_performs_no_client_work(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "api.verification.providers.tavily.TavilyClient"
        ) as constructor:
            provider = TavilyProvider()
            self.assertEqual(provider.search(" \n\t "), [])
            self.assertEqual(provider.search_with_payload(" "), ({}, []))
            self.assertEqual(self.provider.search(" "), [])
        constructor.assert_not_called()
        self.client.search.assert_not_called()

    def test_nonpositive_limit_performs_no_client_work(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "api.verification.providers.tavily.TavilyClient"
        ) as constructor:
            provider = TavilyProvider()
            for limit in (0, -1):
                with self.subTest(limit=limit):
                    self.assertEqual(provider.search("claim", limit=limit), [])
                    self.assertEqual(
                        provider.search_with_payload("claim", limit=limit),
                        ({}, []),
                    )
                    self.assertEqual(self.provider.search("claim", limit=limit), [])
        constructor.assert_not_called()
        self.client.search.assert_not_called()

    def test_missing_api_key_raises_provider_value_error(self):
        for environment in ({}, {"TAVILY_API_KEY": ""},
                            {"TAVILY_API_KEY": " \t"}):
            with self.subTest(environment=environment), patch.dict(
                os.environ, environment, clear=True
            ), patch("api.verification.providers.tavily.TavilyClient") as constructor:
                provider = TavilyProvider()
                with self.assertRaises(ValueError) as caught:
                    provider.search("claim")
                self.assertEqual(
                    str(caught.exception),
                    "TAVILY_API_KEY is required for Tavily search.",
                )
                constructor.assert_not_called()

    def test_explicit_api_key_overrides_environment(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "environment-key"}), patch(
            "api.verification.providers.tavily.TavilyClient",
            return_value=self.client,
        ) as constructor:
            TavilyProvider(api_key="explicit-key").search("claim")
        constructor.assert_called_once_with(api_key="explicit-key")

    def test_explicit_blank_key_does_not_fall_back_to_environment(self):
        for key in ("", " \t"):
            with self.subTest(key=key), patch.dict(
                os.environ, {"TAVILY_API_KEY": "environment-key"}
            ), patch("api.verification.providers.tavily.TavilyClient") as constructor:
                with self.assertRaisesRegex(
                    ValueError, "^TAVILY_API_KEY is required for Tavily search\\.$"
                ):
                    TavilyProvider(api_key=key).search("claim")
                constructor.assert_not_called()

    def test_environment_key_constructs_client_lazily_and_reuses_it(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "environment-key"}), patch(
            "api.verification.providers.tavily.TavilyClient",
            return_value=self.client,
        ) as constructor:
            provider = TavilyProvider()
            constructor.assert_not_called()
            provider.search("first")
            provider.search("second")
        constructor.assert_called_once_with(api_key="environment-key")
        self.assertEqual(self.client.search.call_count, 2)

    def test_injected_client_requires_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "api.verification.providers.tavily.TavilyClient"
        ) as constructor:
            evidence = TavilyProvider(client=self.client).search("claim")
        constructor.assert_not_called()
        self.client.search.assert_called_once()
        self.assertEqual(evidence[0].provider, "TAVILY")
        self.assertEqual(TavilyProvider.provider_name, "TAVILY")

    def test_search_uses_exact_preset_and_actual_sdk_timeout(self):
        TavilyProvider(client=self.client, timeout=7.5).search("claim", limit=2)
        self.client.search.assert_called_once_with(
            query="claim", search_depth="advanced", topic="general",
            include_answer=True,
            include_domains=[
                "gmanetwork.com", "rappler.com", "philstar.com", "inquirer.net",
                "news.abs-cbn.com", "manilabulletin.com", "bworldonline.com",
                "pna.gov.ph", "verafiles.org", "reuters.com", "apnews.com",
                "bbc.com", "cnn.com", "aljazeera.com", "nytimes.com",
                "theguardian.com", "snopes.com", "politifact.com",
                "factcheck.org", "afp.com",
            ],
            timeout=7.5,
        )
        self.assertNotIn("request_timeout", self.client.search.call_args.kwargs)
        self.assertNotIn("max_results", self.client.search.call_args.kwargs)

    def test_query_is_stripped_without_truncation(self):
        query = "claim " * 100
        self.provider.search(" \n" + query + "\t ")
        self.assertEqual(
            self.client.search.call_args.kwargs["query"], query.strip()
        )
        self.assertEqual(self.client.search.call_args.kwargs["timeout"], 12.0)

    def test_client_exceptions_propagate_unchanged(self):
        errors = [
            TavilyTimeoutError(7.5), InvalidAPIKeyError("invalid key"),
            UsageLimitExceededError("quota exhausted"),
            requests.ConnectionError("connection failed"),
            ValueError("invalid response JSON"),
        ]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.client.search.reset_mock()
                self.client.search.side_effect = error
                with self.assertRaises(type(error)) as caught:
                    self.provider.search("claim")
                self.assertIs(caught.exception, error)
                self.client.search.assert_called_once()

    def test_non_dictionary_response_raises_type_error(self):
        for payload in (None, [], "invalid", 42):
            with self.subTest(payload=payload):
                self.client.search.return_value = payload
                with self.assertRaises(TypeError):
                    self.provider.search_with_payload("claim")

    def test_search_with_payload_preserves_original_object_and_contents(self):
        payload = {
            "answer": "Provider answer", "score": 0.8, "extra": {"nested": [1]},
            "results": [
                None, {"url": "https://example.com/1", "score": 0.99},
                {"url": "https://example.com/2", "content": "Second source"},
            ],
        }
        before = deepcopy(payload)
        self.client.search.return_value = payload
        returned, evidence = self.provider.search_with_payload("claim", limit=1)
        self.assertIs(returned, payload)
        self.assertEqual(payload, before)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].raw_reference, {"tavily_result_index": 1})
        self.client.search.assert_called_once()

    def test_missing_or_malformed_results_payload_is_not_rewritten(self):
        for payload in ({}, {"results": None}, {"results": "invalid"}):
            with self.subTest(payload=payload):
                before = deepcopy(payload)
                self.client.search.return_value = payload
                returned, evidence = self.provider.search_with_payload("claim")
                self.assertIs(returned, payload)
                self.assertEqual(returned, before)
                self.assertEqual(evidence, [])

    def test_search_delegates_with_one_client_request(self):
        with patch.object(
            self.provider, "search_with_payload",
            wraps=self.provider.search_with_payload,
        ) as bridge:
            evidence = self.provider.search("claim", limit=2)
        bridge.assert_called_once_with("claim", limit=2)
        self.client.search.assert_called_once()
        self.assertEqual(evidence, [RawEvidence(
            provider="TAVILY", url="https://example.com",
            source_type="WEB_SEARCH", raw_reference={"tavily_result_index": 0},
        )])
