from datetime import datetime, timezone
from unittest import TestCase

from .verification.contracts import (
    NormalizedEvidence,
    RawEvidence,
)
from .verification.normalizers import (
    canonicalize_url,
    compute_content_hash,
    normalize_evidence,
    normalize_text,
)


class EvidenceContractTests(TestCase):

    def test_raw_evidence_can_represent_provider_result(self):
        published_at = datetime(
            2026,
            8,
            31,
            tzinfo=timezone.utc,
        )

        evidence = RawEvidence(
            provider="GOOGLE_FACT_CHECK",
            url="https://example.com/fact-check",
            title="Example Fact Check",
            publisher="Example Publisher",
            content="Example evidence content.",
            source_type="FACT_CHECK",
            published_at=published_at,
            raw_reference={
                "claim_review_index": 0,
            },
        )

        self.assertEqual(
            evidence.provider,
            "GOOGLE_FACT_CHECK",
        )

        self.assertEqual(
            evidence.publisher,
            "Example Publisher",
        )

        self.assertEqual(
            evidence.published_at,
            published_at,
        )

    def test_raw_evidence_allows_optional_provider_fields(self):
        evidence = RawEvidence(
            provider="TAVILY",
        )

        self.assertIsNone(evidence.url)
        self.assertIsNone(evidence.content)
        self.assertEqual(
            evidence.raw_reference,
            {},
        )

    def test_normalized_evidence_contains_internal_fields(self):
        evidence = NormalizedEvidence(
            provider="TAVILY",
            url="https://example.com/article",
            canonical_url="https://example.com/article",
            title="Example Article",
            publisher="Example News",
            source_type="NEWS",
            content="Normalized article content.",
            content_hash="a" * 64,
        )

        self.assertEqual(
            evidence.canonical_url,
            "https://example.com/article",
        )

        self.assertEqual(
            evidence.content_hash,
            "a" * 64,
        )

class EvidenceNormalizerTests(TestCase):

    def test_normalize_text_collapses_whitespace(self):
        result = normalize_text(
            "  Example   evidence\ncontent.  "
        )

        self.assertEqual(
            result,
            "Example evidence content.",
        )

    def test_normalize_text_returns_none_for_empty_text(self):
        self.assertIsNone(
            normalize_text("   ")
        )

    def test_canonicalize_url_removes_tracking_and_fragment(self):
        result = canonicalize_url(
            "HTTPS://Example.COM/article"
            "?utm_source=test&id=42"
            "#section"
        )

        self.assertEqual(
            result,
            "https://example.com/article?id=42",
        )

    def test_canonicalize_url_removes_default_https_port(self):
        result = canonicalize_url(
            "https://example.com:443/article"
        )

        self.assertEqual(
            result,
            "https://example.com/article",
        )

    def test_content_hash_is_stable_after_whitespace_normalization(self):
        first = compute_content_hash(
            "Example   evidence"
        )

        second = compute_content_hash(
            " Example evidence "
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            len(first),
            64,
        )

    def test_normalize_evidence_builds_internal_representation(self):
        raw = RawEvidence(
            provider="tavily",
            url=(
                "https://Example.com/article"
                "?utm_source=test"
            ),
            title="  Example   Article ",
            publisher=" Example News ",
            source_type="news",
            content=(
                "Example   evidence\ncontent."
            ),
            raw_reference={
                "result_index": 2,
            },
        )

        normalized = normalize_evidence(
            raw
        )

        self.assertEqual(
            normalized.provider,
            "TAVILY",
        )

        self.assertEqual(
            normalized.canonical_url,
            "https://example.com/article",
        )

        self.assertEqual(
            normalized.title,
            "Example Article",
        )

        self.assertEqual(
            normalized.publisher,
            "Example News",
        )

        self.assertEqual(
            normalized.source_type,
            "NEWS",
        )

        self.assertEqual(
            normalized.content,
            "Example evidence content.",
        )

        self.assertEqual(
            len(normalized.content_hash),
            64,
        )

        self.assertEqual(
            normalized.raw_reference,
            {
                "result_index": 2,
            },
        )
