from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import Mock, patch

from django.test import TestCase
from tavily.errors import TimeoutError as TavilyTimeoutError

from api.models import (
    CanonicalSource,
    EvidenceSource,
    VerificationEvidence,
    VerificationRun,
)
from api.verification.contracts import RawEvidence
from api.verification.ingestion import ingest_provider_evidence, ingest_raw_evidence
from api.verification.persistence import persist_evidence_source
from api.verification.providers.tavily import TavilyProvider


class TavilyIngestionTests(TestCase):
    def _build_provider(self, results, **payload_fields):
        payload = {"results": results, **payload_fields}
        client = Mock()
        client.search.return_value = payload
        return TavilyProvider(client=client), client, payload

    def test_evidence_is_normalized_and_persisted(self):
        provider, client, _ = self._build_provider([{
            "url": " https://example.com/article ",
            "title": " Example   Article ",
            "publisher": " Example   Publisher ",
            "content": " Full evidence.\n More   detail. ",
            "published_date": "2026-08-21T12:30:00Z",
            "score": 0.99,
        }])
        sources = ingest_provider_evidence(provider, "claim")
        self.assertEqual(len(sources), 1)
        self.assertEqual(EvidenceSource.objects.count(), 1)
        source = EvidenceSource.objects.get(pk=sources[0].pk)
        self.assertEqual(source.provider, "TAVILY")
        self.assertEqual(source.source_type, "WEB_SEARCH")
        self.assertEqual(source.url, "https://example.com/article")
        self.assertEqual(source.title, "Example Article")
        self.assertEqual(source.publisher, "Example Publisher")
        self.assertEqual(source.content, "Full evidence. More detail.")
        self.assertEqual(
            source.content_hash,
            sha256(b"Full evidence. More detail.").hexdigest(),
        )
        self.assertEqual(
            source.published_at,
            datetime(2026, 8, 21, 12, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(source.raw_reference, {"tavily_result_index": 0})
        client.search.assert_called_once()

    def test_canonical_url_normalization_preserves_meaningful_parameters(self):
        provider, _, _ = self._build_provider([{
            "url": "HTTPS://Example.com:443/article?utm_source=social&id=42#results",
        }])
        source = ingest_provider_evidence(provider, "claim")[0]
        self.assertEqual(source.canonical_url, "https://example.com/article?id=42")

    def test_equivalent_urls_reuse_existing_source_without_overwrite(self):
        first, _, _ = self._build_provider([{
            "url": "https://Example.com/article?utm_source=social&id=42",
            "title": "Original title", "content": "Original content",
            "publisher": "Original publisher",
            "published_date": "2026-08-21T12:30:00Z",
        }])
        original = ingest_provider_evidence(first, "claim")[0]
        before = EvidenceSource.objects.filter(pk=original.pk).values().get()
        second, _, _ = self._build_provider([
            None,
            {
                "url": "https://example.com/article?id=42#results",
                "title": "Updated title", "content": "Updated content",
                "publisher": "Updated publisher",
                "published_date": "2026-09-01T12:30:00Z",
            },
        ])
        reused = ingest_provider_evidence(second, "claim")[0]
        self.assertEqual(reused.pk, original.pk)
        self.assertEqual(EvidenceSource.objects.count(), 1)
        self.assertEqual(
            EvidenceSource.objects.filter(pk=original.pk).values().get(), before
        )

    def test_content_hash_reuses_source_across_different_urls(self):
        first, _, _ = self._build_provider([{
            "url": "https://example.com/first", "content": "Same   content",
        }])
        second, _, _ = self._build_provider([{
            "url": "https://example.com/second", "content": "Same\ncontent",
        }])
        original = ingest_provider_evidence(first, "claim")[0]
        reused = ingest_provider_evidence(second, "claim")[0]
        self.assertEqual(reused.pk, original.pk)
        self.assertEqual(reused.url, "https://example.com/first")
        self.assertEqual(EvidenceSource.objects.count(), 1)

    def test_multiple_distinct_results_create_sources_in_order(self):
        provider, _, _ = self._build_provider([
            {"url": "https://example.com/1", "content": "First content"},
            {"url": "https://example.com/2", "content": "Second content"},
            {"content": "Content-only evidence"},
        ])
        sources = ingest_provider_evidence(provider, "claim")
        self.assertEqual(EvidenceSource.objects.count(), 3)
        self.assertEqual(
            [source.url for source in sources],
            ["https://example.com/1", "https://example.com/2", None],
        )
        self.assertEqual(
            [source.raw_reference for source in sources],
            [{"tavily_result_index": index} for index in range(3)],
        )

    def test_duplicate_results_return_one_persisted_source(self):
        provider, _, _ = self._build_provider([
            {"url": "https://example.com/article?utm_source=social"},
            {"url": "https://example.com/article#results"},
        ])
        sources = ingest_provider_evidence(provider, "claim")
        self.assertEqual(len(sources), 1)
        self.assertEqual(EvidenceSource.objects.count(), 1)
        self.assertEqual(sources[0].raw_reference, {"tavily_result_index": 0})

    def test_same_evidence_remains_provider_scoped(self):
        gfc = ingest_raw_evidence([RawEvidence(
            provider="GOOGLE_FACT_CHECK",
            url="https://example.com/article", content="Shared content",
            source_type="FACT_CHECK",
        )])[0]
        provider, _, _ = self._build_provider([{
            "url": "https://example.com/article", "content": "Shared content",
        }])
        tavily = ingest_provider_evidence(provider, "claim")[0]
        self.assertNotEqual(tavily.pk, gfc.pk)
        self.assertEqual(tavily.provider, "TAVILY")
        self.assertEqual(tavily.content_hash, gfc.content_hash)
        self.assertEqual(tavily.canonical_url, gfc.canonical_url)
        self.assertEqual(EvidenceSource.objects.count(), 2)

    def test_provider_exception_propagates_without_writes(self):
        provider, client, _ = self._build_provider([])
        error = TavilyTimeoutError(12.0)
        client.search.side_effect = error
        with patch("api.verification.ingestion.persist_evidence_source") as persist:
            with self.assertRaises(TavilyTimeoutError) as caught:
                ingest_provider_evidence(provider, "claim")
        self.assertIs(caught.exception, error)
        persist.assert_not_called()
        self.assertEqual(EvidenceSource.objects.count(), 0)

    def test_limit_bounds_persisted_output(self):
        provider, _, _ = self._build_provider([
            None,
            {"url": "https://example.com/1"},
            {"url": "https://example.com/2"},
            {"url": "https://example.com/3"},
        ])
        sources = ingest_provider_evidence(provider, "claim", limit=2)
        self.assertEqual(len(sources), 2)
        self.assertEqual(EvidenceSource.objects.count(), 2)
        self.assertEqual(
            [source.url for source in sources],
            ["https://example.com/1", "https://example.com/2"],
        )

    def test_empty_evidence_produces_no_writes(self):
        provider, _, _ = self._build_provider([])
        with patch("api.verification.ingestion.persist_evidence_source") as persist:
            self.assertEqual(ingest_provider_evidence(provider, "claim"), [])
        persist.assert_not_called()
        self.assertEqual(EvidenceSource.objects.count(), 0)

    def test_payload_bridge_ingests_without_second_search_or_mutation(self):
        provider, client, payload = self._build_provider(
            [
                None,
                {"url": "https://example.com/1", "content": " Full  content ",
                 "score": 0.99},
                {"url": "https://example.com/2", "content": "Second content"},
            ],
            answer="Provider answer", score=0.8, extra={"nested": [1, 2]},
        )
        before = deepcopy(payload)
        returned, evidence = provider.search_with_payload("claim", limit=1)
        sources = ingest_raw_evidence(evidence)
        client.search.assert_called_once()
        self.assertIs(returned, payload)
        self.assertEqual(payload, before)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].content, "Full content")
        self.assertEqual(sources[0].raw_reference, {"tavily_result_index": 1})

    def test_batch_persistence_failure_rolls_back_new_sources(self):
        provider, _, _ = self._build_provider([
            {"url": "https://example.com/1"},
            {"url": "https://example.com/2"},
        ])
        existing = ingest_raw_evidence([RawEvidence(
            provider="TAVILY", url="https://example.com/existing",
        )])[0]
        calls = []

        def persist_then_fail(evidence):
            calls.append(evidence)
            if len(calls) == 2:
                self.assertTrue(EvidenceSource.objects.filter(
                    canonical_url="https://example.com/1"
                ).exists())
                raise RuntimeError("Simulated batch persistence failure")
            return persist_evidence_source(evidence)

        with patch(
            "api.verification.ingestion.persist_evidence_source",
            side_effect=persist_then_fail,
        ):
            with self.assertRaisesRegex(RuntimeError, "Simulated batch persistence"):
                ingest_provider_evidence(provider, "claim")
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            list(EvidenceSource.objects.values_list("pk", flat=True)), [existing.pk]
        )

    def test_ingestion_leaves_scoring_canonical_source_and_lifecycle_untouched(self):
        before = {
            model: model.objects.count()
            for model in (CanonicalSource, VerificationRun, VerificationEvidence)
        }
        provider, _, _ = self._build_provider([{
            "url": "https://reuters.com/article", "content": "Source content",
            "score": 0.99, "authority_score": 99, "relevance_score": 0.99,
            "directness_score": 0.99, "recency_score": 0.99,
            "stance": "SUPPORTS", "verdict": "FACT",
            "canonical_source": "Reuters",
        }])
        source = ingest_provider_evidence(provider, "claim")[0]
        source.refresh_from_db()
        self.assertIsNone(source.canonical_source_id)
        self.assertIsNone(source.authority_score)
        self.assertIsNone(source.publisher)
        self.assertEqual(source.raw_reference, {"tavily_result_index": 0})
        for model, count in before.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(model.objects.count(), count)
