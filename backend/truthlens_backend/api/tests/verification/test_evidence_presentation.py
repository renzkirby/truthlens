"""URL report source cards must be linked to the persisted evaluator evidence."""
from django.test import TestCase

from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification.evidence_presentation import (
    persisted_evidence_source_previews,
)


class PersistedEvidenceSourcePresentationTests(TestCase):
    def setUp(self):
        self.run = VerificationRun.objects.create(
            claim=Claim.objects.create(context_text="Public source claim."),
        )

    def _link(self, url, *, role=VerificationEvidence.EvidenceRole.SECONDARY,
              stance=VerificationEvidence.Stance.UNKNOWN, content="Source text.",
              title="Recorded evidence", canonical_url=None):
        source = EvidenceSource.objects.create(
            provider="TAVILY", url=url, canonical_url=canonical_url,
            content=content, title=title,
        )
        return VerificationEvidence.objects.create(
            verification_run=self.run, evidence_source=source,
            evidence_role=role, stance=stance,
        )

    def test_only_persisted_role_links_appear_not_retrieval_predictions(self):
        self._link("https://example.org/first", stance="SUPPORTS")
        self._link("https://example.org/second", stance="REFUTES")
        self._link("https://example.org/official", role="FACT_CHECK")
        sources = persisted_evidence_source_previews(
            self.run, VerificationEvidence.EvidenceRole.SECONDARY,
        )
        self.assertEqual({s["url"] for s in sources}, {
            "https://example.org/first", "https://example.org/second",
        })
        self.assertTrue(all(
            s["provenance"] == "PERSISTED_EVIDENCE" for s in sources
        ))
        self.assertEqual(VerificationEvidence.objects.count(), 3)

    def test_repeated_url_collapses_for_display_but_not_evidence(self):
        self._link("https://example.org/story", stance="SUPPORTS")
        self._link("https://example.org/story", stance="REFUTES")
        sources = persisted_evidence_source_previews(
            self.run, VerificationEvidence.EvidenceRole.SECONDARY,
        )
        self.assertEqual(len(sources), 1)
        self.assertEqual(VerificationEvidence.objects.count(), 2)

    def test_unsafe_urls_not_presented_and_canonical_url_fallback(self):
        self._link("javascript:alert(1)", canonical_url="https://example.org/safe")
        self._link("https://username:password@example.org/private")
        self._link("file:///etc/passwd")
        urls = [s["url"] for s in persisted_evidence_source_previews(
            self.run, VerificationEvidence.EvidenceRole.SECONDARY,
        )]
        self.assertEqual(urls, ["https://example.org/safe"])

    def test_missing_public_urls_do_not_fabricate_sources(self):
        self._link(None, content="Unlinked internal evidence.")
        self.assertEqual(
            persisted_evidence_source_previews(
                self.run, VerificationEvidence.EvidenceRole.SECONDARY,
            ), [],
        )
