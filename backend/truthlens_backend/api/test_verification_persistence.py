from django.test import TestCase

from .models import EvidenceSource
from .verification.contracts import NormalizedEvidence
from .verification.persistence import (
    persist_evidence_source,
)


class EvidenceSourcePersistenceTests(TestCase):

    def test_persists_normalized_evidence(self):
        evidence = NormalizedEvidence(
            provider="TAVILY",
            url="https://example.com/article?utm_source=test",
            canonical_url="https://example.com/article",
            title="Example Article",
            publisher="Example News",
            source_type="NEWS",
            content="Example evidence content.",
            content_hash="a" * 64,
            raw_reference={
                "result_index": 0,
            },
        )

        source, created = persist_evidence_source(
            evidence
        )

        self.assertTrue(created)

        self.assertEqual(
            EvidenceSource.objects.count(),
            1,
        )

        self.assertEqual(
            source.provider,
            "TAVILY",
        )

        self.assertEqual(
            source.canonical_url,
            "https://example.com/article",
        )

        self.assertEqual(
            source.content_hash,
            "a" * 64,
        )

        self.assertEqual(
            source.raw_reference,
            {
                "result_index": 0,
            },
        )

    def test_reuses_same_provider_and_canonical_url(self):
        first = NormalizedEvidence(
            provider="TAVILY",
            canonical_url="https://example.com/article",
            title="Original Title",
            content_hash="a" * 64,
        )

        first_source, first_created = (
            persist_evidence_source(first)
        )

        second = NormalizedEvidence(
            provider="TAVILY",
            canonical_url="https://example.com/article",
            title="Different Title",
            content_hash="b" * 64,
        )

        second_source, second_created = (
            persist_evidence_source(second)
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)

        self.assertEqual(
            first_source.id,
            second_source.id,
        )

        self.assertEqual(
            EvidenceSource.objects.count(),
            1,
        )

        # Existing persisted evidence is not overwritten.
        self.assertEqual(
            second_source.title,
            "Original Title",
        )

    def test_reuses_same_provider_and_content_hash(self):
        first = NormalizedEvidence(
            provider="TAVILY",
            canonical_url="https://example.com/article-one",
            content="Same evidence content.",
            content_hash="c" * 64,
        )

        first_source, _ = persist_evidence_source(
            first
        )

        second = NormalizedEvidence(
            provider="TAVILY",
            canonical_url="https://example.com/article-two",
            content="Same evidence content.",
            content_hash="c" * 64,
        )

        second_source, created = (
            persist_evidence_source(second)
        )

        self.assertFalse(created)

        self.assertEqual(
            first_source.id,
            second_source.id,
        )

        self.assertEqual(
            EvidenceSource.objects.count(),
            1,
        )

    def test_different_providers_remain_separate(self):
        tavily = NormalizedEvidence(
            provider="TAVILY",
            canonical_url="https://example.com/article",
            content_hash="d" * 64,
        )

        gfc = NormalizedEvidence(
            provider="GOOGLE_FACT_CHECK",
            canonical_url="https://example.com/article",
            content_hash="d" * 64,
        )

        tavily_source, _ = persist_evidence_source(
            tavily
        )

        gfc_source, gfc_created = (
            persist_evidence_source(gfc)
        )

        self.assertTrue(gfc_created)

        self.assertNotEqual(
            tavily_source.id,
            gfc_source.id,
        )

        self.assertEqual(
            EvidenceSource.objects.count(),
            2,
        )

    def test_identityless_evidence_is_not_deduplicated(self):
        evidence = NormalizedEvidence(
            provider="TAVILY",
            title="Evidence without stable identity",
        )

        first_source, first_created = (
            persist_evidence_source(evidence)
        )

        second_source, second_created = (
            persist_evidence_source(evidence)
        )

        self.assertTrue(first_created)
        self.assertTrue(second_created)

        self.assertNotEqual(
            first_source.id,
            second_source.id,
        )

        self.assertEqual(
            EvidenceSource.objects.count(),
            2,
        )

    def test_blank_provider_is_rejected(self):
        evidence = NormalizedEvidence(
            provider="   ",
            canonical_url="https://example.com/article",
        )

        with self.assertRaises(ValueError):
            persist_evidence_source(evidence)

        self.assertEqual(
            EvidenceSource.objects.count(),
            0,
        )