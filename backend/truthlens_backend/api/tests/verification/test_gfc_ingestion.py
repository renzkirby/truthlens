from unittest.mock import Mock

import requests

from django.test import TestCase

from api.models import EvidenceSource
from api.verification.contracts import RawEvidence
from api.verification.ingestion import (
    ingest_provider_evidence,
    ingest_raw_evidence,
)
from api.verification.providers.google_fact_check import (
    GoogleFactCheckProvider,
)


class GoogleFactCheckIngestionTests(TestCase):

    def _build_provider(
        self,
        payload,
    ):
        response = Mock()
        response.json.return_value = payload

        http_client = Mock()
        http_client.get.return_value = response

        provider = GoogleFactCheckProvider(
            api_key="test-api-key",
            http_client=http_client,
        )

        return (
            provider,
            http_client,
            response,
        )

    def test_gfc_evidence_is_normalized_and_persisted(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": ("Example public claim."),
                    "claimReview": [
                        {
                            "publisher": {
                                "name": ("Example Checker"),
                            },
                            "url": (
                                "HTTPS://Example.com:443/"
                                "fact-check"
                                "?utm_source=social"
                                "&id=42"
                                "#results"
                            ),
                            "title": ("Example Fact Check"),
                            "reviewDate": ("2026-08-21T12:30:00Z"),
                            "textualRating": ("False"),
                        }
                    ],
                }
            ]
        }

        provider, _, _ = self._build_provider(payload)

        sources = ingest_provider_evidence(
            provider,
            "example claim",
        )

        self.assertEqual(
            len(sources),
            1,
        )

        source = sources[0]

        self.assertEqual(
            EvidenceSource.objects.count(),
            1,
        )

        self.assertEqual(
            source.provider,
            "GOOGLE_FACT_CHECK",
        )

        self.assertEqual(
            source.source_type,
            "FACT_CHECK",
        )

        self.assertEqual(
            source.publisher,
            "Example Checker",
        )

        self.assertEqual(
            source.canonical_url,
            ("https://example.com/" "fact-check?id=42"),
        )

        self.assertIsNotNone(source.content_hash)

        self.assertIn(
            "Rating: False",
            source.content,
        )

    def test_equivalent_gfc_url_reuses_existing_source(
        self,
    ):
        first_payload = {
            "claims": [
                {
                    "text": "Example claim.",
                    "claimReview": [
                        {
                            "publisher": {
                                "name": "Checker",
                            },
                            "url": (
                                "https://Example.com/"
                                "fact-check"
                                "?utm_source=social"
                                "&id=42"
                            ),
                            "title": "Original Review",
                            "textualRating": "False",
                        }
                    ],
                }
            ]
        }

        second_payload = {
            "claims": [
                {
                    "text": "Example claim.",
                    "claimReview": [
                        {
                            "publisher": {
                                "name": "Checker",
                            },
                            "url": (
                                "https://example.com/" "fact-check" "?id=42" "#results"
                            ),
                            "title": "Updated Review",
                            "textualRating": "False",
                        }
                    ],
                }
            ]
        }

        first_provider, _, _ = self._build_provider(first_payload)

        second_provider, _, _ = self._build_provider(second_payload)

        first_sources = ingest_provider_evidence(
            first_provider,
            "example claim",
        )

        second_sources = ingest_provider_evidence(
            second_provider,
            "example claim",
        )

        self.assertEqual(
            EvidenceSource.objects.count(),
            1,
        )

        self.assertEqual(
            first_sources[0].pk,
            second_sources[0].pk,
        )

        self.assertEqual(
            second_sources[0].title,
            "Original Review",
        )

    def test_multiple_gfc_reviews_create_multiple_sources(
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
                            "url": ("https://a.example/" "review"),
                            "textualRating": "False",
                        },
                        {
                            "publisher": {
                                "name": "Checker B",
                            },
                            "url": ("https://b.example/" "review"),
                            "textualRating": ("Misleading"),
                        },
                    ],
                }
            ]
        }

        provider, _, _ = self._build_provider(payload)

        sources = ingest_provider_evidence(
            provider,
            "example claim",
        )

        self.assertEqual(
            len(sources),
            2,
        )

        self.assertEqual(
            EvidenceSource.objects.count(),
            2,
        )

        self.assertEqual(
            {source.publisher for source in sources},
            {
                "Checker A",
                "Checker B",
            },
        )

    def test_provider_error_is_not_silently_swallowed(
        self,
    ):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError(
            "Google provider unavailable"
        )

        http_client = Mock()
        http_client.get.return_value = response

        provider = GoogleFactCheckProvider(
            api_key="test-api-key",
            http_client=http_client,
        )

        with self.assertRaises(requests.HTTPError):
            ingest_provider_evidence(
                provider,
                "example claim",
            )

        self.assertEqual(
            EvidenceSource.objects.count(),
            0,
        )

    def test_ingestion_respects_provider_limit(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": "Example claim.",
                    "claimReview": [
                        {
                            "publisher": {
                                "name": "Checker 1",
                            },
                            "url": ("https://example.com/1"),
                            "textualRating": "False",
                        },
                        {
                            "publisher": {
                                "name": "Checker 2",
                            },
                            "url": ("https://example.com/2"),
                            "textualRating": "True",
                        },
                        {
                            "publisher": {
                                "name": "Checker 3",
                            },
                            "url": ("https://example.com/3"),
                            "textualRating": "Misleading",
                        },
                    ],
                }
            ]
        }

        provider, _, _ = self._build_provider(payload)

        sources = ingest_provider_evidence(
            provider,
            "example claim",
            limit=2,
        )

        self.assertEqual(
            len(sources),
            2,
        )

        self.assertEqual(
            EvidenceSource.objects.count(),
            2,
        )
        self.assertEqual(
            {source.publisher for source in sources},
            {
                "Checker 1",
                "Checker 2",
            },
        )

    def test_raw_evidence_can_be_ingested_without_provider_search(
        self,
    ):
        raw_evidence = RawEvidence(
            provider="GOOGLE_FACT_CHECK",
            url=("HTTPS://Example.com:443/" "fact-check?utm_source=test&id=42"),
            title="Example Review",
            publisher="Example Checker",
            content=("Claim reviewed: Example claim.\n" "Rating: False"),
            source_type="FACT_CHECK",
        )

        sources = ingest_raw_evidence([raw_evidence])

        self.assertEqual(
            len(sources),
            1,
        )

        source = sources[0]

        self.assertEqual(
            EvidenceSource.objects.count(),
            1,
        )

        self.assertEqual(
            source.provider,
            "GOOGLE_FACT_CHECK",
        )

        self.assertEqual(
            source.canonical_url,
            "https://example.com/fact-check?id=42",
        )

        self.assertIsNotNone(source.content_hash)

    def test_raw_evidence_ingestion_reuses_existing_source(
        self,
    ):
        first = RawEvidence(
            provider="GOOGLE_FACT_CHECK",
            url=("https://example.com/fact-check" "?utm_source=test&id=42"),
            title="Original Review",
            publisher="Example Checker",
            content="Rating: False",
            source_type="FACT_CHECK",
        )

        second = RawEvidence(
            provider="GOOGLE_FACT_CHECK",
            url=("https://example.com/fact-check" "?id=42#results"),
            title="Updated Review",
            publisher="Example Checker",
            content="Rating: False",
            source_type="FACT_CHECK",
        )

        first_sources = ingest_raw_evidence([first])

        second_sources = ingest_raw_evidence([second])

        self.assertEqual(
            EvidenceSource.objects.count(),
            1,
        )

        self.assertEqual(
            first_sources[0].pk,
            second_sources[0].pk,
        )

        self.assertEqual(
            second_sources[0].title,
            "Original Review",
        )
