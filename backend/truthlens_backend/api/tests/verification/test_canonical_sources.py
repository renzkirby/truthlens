from django.test import TestCase

from api.models import CanonicalSource, EvidenceSource
from api.verification.canonical_sources import (
    AmbiguousCanonicalSourceHostError,
    CanonicalSourceHostCollisionError,
    assign_canonical_source,
    canonical_source_id_for_host,
)


class CanonicalSourceHostIdentityTests(TestCase):
    def _source(self, **fields):
        return EvidenceSource.objects.create(provider="TAVILY", **fields)

    def test_canonical_url_hostname_is_preferred(self):
        source = self._source(
            canonical_url="https://canonical.example/article",
            url="https://fallback.example/article",
        )

        assigned = assign_canonical_source(source)

        self.assertEqual(assigned.canonical_source.domain, "canonical.example")
        self.assertFalse(CanonicalSource.objects.filter(
            domain="fallback.example"
        ).exists())

    def test_url_is_fallback_when_canonical_url_has_no_usable_hostname(self):
        source = self._source(
            canonical_url="not-a-url",
            url="https://fallback.example/article",
        )

        assigned = assign_canonical_source(source)

        self.assertEqual(assigned.canonical_source.domain, "fallback.example")

    def test_hostname_is_lowercased_and_one_leading_www_is_removed(self):
        source = self._source(
            canonical_url="https://WWW.Reuters.com/article",
        )

        assigned = assign_canonical_source(source)

        canonical_source = assigned.canonical_source
        self.assertEqual(canonical_source.pk, canonical_source_id_for_host("reuters.com"))
        self.assertEqual(canonical_source.name, "reuters.com")
        self.assertEqual(canonical_source.domain, "reuters.com")
        self.assertIsNone(canonical_source.source_type)
        self.assertIsNone(canonical_source.canonical_url)

    def test_repeated_assignment_is_idempotent(self):
        source = self._source(canonical_url="https://example.com/article")

        first = assign_canonical_source(source)
        second = assign_canonical_source(source)

        self.assertEqual(first.canonical_source_id, second.canonical_source_id)
        self.assertEqual(CanonicalSource.objects.count(), 1)

    def test_exact_existing_host_is_reused_case_insensitively(self):
        existing = CanonicalSource.objects.create(
            name="Existing Source",
            domain="Example.COM",
            source_type="CURATED",
            canonical_url="https://example.com",
        )
        before = CanonicalSource.objects.values().get(pk=existing.pk)
        source = self._source(canonical_url="https://example.com/article")

        assigned = assign_canonical_source(source)

        self.assertEqual(assigned.canonical_source_id, existing.pk)
        self.assertEqual(CanonicalSource.objects.count(), 1)
        self.assertEqual(CanonicalSource.objects.values().get(pk=existing.pk), before)

    def test_existing_leading_www_domain_is_reused_unchanged(self):
        existing = CanonicalSource.objects.create(
            name="Existing Source",
            domain="WWW.Example.com",
            source_type="CURATED",
            canonical_url="https://www.example.com",
        )
        before = CanonicalSource.objects.values().get(pk=existing.pk)
        source = self._source(canonical_url="https://www.example.com/article")

        assigned = assign_canonical_source(source)

        self.assertEqual(assigned.canonical_source_id, existing.pk)
        self.assertEqual(CanonicalSource.objects.count(), 1)
        self.assertEqual(CanonicalSource.objects.values().get(pk=existing.pk), before)

    def test_preassigned_source_is_preserved_without_creating_another_family(self):
        existing = CanonicalSource.objects.create(
            name="Curated Family",
            domain="curated.example",
        )
        source = self._source(
            canonical_source=existing,
            canonical_url="https://different.example/article",
        )

        assigned = assign_canonical_source(source)

        self.assertEqual(assigned.canonical_source_id, existing.pk)
        self.assertEqual(CanonicalSource.objects.count(), 1)

    def test_subdomains_remain_distinct(self):
        root = assign_canonical_source(self._source(
            canonical_url="https://reuters.com/article",
        ))
        news = assign_canonical_source(self._source(
            canonical_url="https://news.reuters.com/article",
        ))

        self.assertNotEqual(root.canonical_source_id, news.canonical_source_id)
        self.assertEqual(
            {source.domain for source in CanonicalSource.objects.all()},
            {"reuters.com", "news.reuters.com"},
        )

    def test_unusable_urls_and_publisher_metadata_do_not_create_host_identity(self):
        source = self._source(
            canonical_url="not-a-url",
            url=None,
            publisher="Reuters",
            title="Reuters report",
            content="Reuters attributed copy.",
        )

        assigned = assign_canonical_source(source)

        self.assertIsNone(assigned.canonical_source_id)
        self.assertEqual(CanonicalSource.objects.count(), 0)

    def test_duplicate_case_insensitive_domains_raise_explicit_ambiguity(self):
        CanonicalSource.objects.create(name="First", domain="example.com")
        CanonicalSource.objects.create(name="Second", domain="EXAMPLE.COM")
        source = self._source(canonical_url="https://example.com/article")

        with self.assertRaisesRegex(
            AmbiguousCanonicalSourceHostError,
            "Multiple CanonicalSource rows match host example.com",
        ):
            assign_canonical_source(source)

        source.refresh_from_db()
        self.assertIsNone(source.canonical_source_id)

    def test_duplicate_leading_www_domains_raise_explicit_ambiguity(self):
        CanonicalSource.objects.create(name="First", domain="example.com")
        CanonicalSource.objects.create(name="Second", domain="WWW.EXAMPLE.COM")
        source = self._source(canonical_url="https://www.example.com/article")

        with self.assertRaisesRegex(
            AmbiguousCanonicalSourceHostError,
            "Multiple CanonicalSource rows match host example.com",
        ):
            assign_canonical_source(source)

        source.refresh_from_db()
        self.assertIsNone(source.canonical_source_id)

    def test_deterministic_uuid_collision_with_other_domain_raises(self):
        CanonicalSource.objects.create(
            id=canonical_source_id_for_host("example.com"),
            name="Other host",
            domain="other.example",
        )
        source = self._source(canonical_url="https://example.com/article")

        with self.assertRaisesRegex(
            CanonicalSourceHostCollisionError,
            "incompatible host for example.com",
        ):
            assign_canonical_source(source)

        source.refresh_from_db()
        self.assertIsNone(source.canonical_source_id)

    def test_unsaved_evidence_source_is_rejected_using_model_state(self):
        source = EvidenceSource(
            provider="TAVILY",
            canonical_url="https://example.com/article",
        )

        with self.assertRaisesRegex(ValueError, "must already be persisted"):
            assign_canonical_source(source)

        self.assertEqual(CanonicalSource.objects.count(), 0)
