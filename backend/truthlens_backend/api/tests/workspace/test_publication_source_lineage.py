from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    EvidenceSubmission,
    OfficialFactCheck,
    OfficialFactCheckSource,
    OfficialFactCheckSourceEvidenceLink,
    VerificationAssignment,
)
from api.publishing_service import (
    PublishingConflict,
    create_fact_check_draft,
    publish_fact_check,
    submit_fact_check_for_review,
    update_fact_check_draft,
)
from api.tests.adjudication.test_adjudication_transaction_contract import (
    AdjudicationContractFixtures,
)


class PublicationSourceLineageTests(
    AdjudicationContractFixtures,
    TestCase,
):
    def make_decided_context(self, evidence_statuses=None):
        statuses = evidence_statuses or [
            EvidenceSubmission.EvidenceStatus.VERIFIED
        ]
        context = self.make_context(evidence_statuses=statuses)
        context["decision"] = self.issue(context)["decision"]
        context["snapshot"] = context["decision"].evidence_snapshot
        return context

    def make_draft(self, context, *, source_urls=None, suffix="lineage"):
        return create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            headline=f"Snapshot-backed fact check {suffix}",
            summary="A professional summary of the adjudicated claim.",
            article_body="The article explains the reviewed evidence.",
            source_urls=source_urls,
        )

    def test_draft_sources_use_the_decision_snapshot(self):
        context = self.make_decided_context()
        evidence = context["evidence"][0]

        draft = self.make_draft(context)

        source = OfficialFactCheckSource.objects.get(
            fact_check=draft,
            url=evidence.evidence_url,
        )
        link = source.evidence_links.get()
        self.assertEqual(
            source.source_type,
            OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE,
        )
        self.assertFalse(source.is_editorially_selected)
        self.assertIsNone(source.evidence_submission_id)
        self.assertEqual(link.snapshot_id, context["snapshot"].id)
        self.assertEqual(link.captured_evidence_id, evidence.id)
        draft.refresh_from_db()
        self.assertEqual(draft.sources, [evidence.evidence_url])

    def test_duplicate_verified_urls_share_one_source_and_keep_all_lineage(self):
        context = self.make_context(
            evidence_statuses=[
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
            ]
        )
        shared_url = "https://example.com/shared-evidence"
        now = timezone.now()
        first, second, rejected = context["evidence"]
        EvidenceSubmission.objects.filter(pk=first.pk).update(
            evidence_url=shared_url,
            evidence_caption="Earlier captured title",
            submitted_at=now - timedelta(hours=1),
        )
        EvidenceSubmission.objects.filter(pk=second.pk).update(
            evidence_url=shared_url,
            evidence_caption="Later captured title",
            submitted_at=now,
        )
        EvidenceSubmission.objects.filter(pk=rejected.pk).update(
            evidence_url=shared_url,
            submitted_at=now + timedelta(hours=1),
        )
        context["decision"] = self.issue(context)["decision"]
        context["snapshot"] = context["decision"].evidence_snapshot

        draft = self.make_draft(context, suffix="duplicate")

        source = OfficialFactCheckSource.objects.get(
            fact_check=draft,
            url=shared_url,
        )
        self.assertEqual(source.title, "Earlier captured title")
        self.assertSetEqual(
            set(
                source.evidence_links.values_list(
                    "captured_evidence_id", flat=True
                )
            ),
            {first.id, second.id},
        )
        self.assertFalse(
            source.evidence_links.filter(captured_evidence_id=rejected.id).exists()
        )

    def test_snapshot_null_and_invalid_urls_are_not_automatic_sources(self):
        context = self.make_context(
            evidence_statuses=[
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.VERIFIED,
            ]
        )
        invalid_urls = [None, "", "javascript:alert(1)"]
        for evidence, invalid_url in zip(context["evidence"], invalid_urls):
            EvidenceSubmission.objects.filter(pk=evidence.pk).update(
                evidence_url=invalid_url
            )
        context["decision"] = self.issue(context)["decision"]
        context["snapshot"] = context["decision"].evidence_snapshot

        draft = self.make_draft(context, suffix="invalid-urls")

        self.assertFalse(draft.source_items.exists())
        draft.refresh_from_db()
        self.assertEqual(draft.sources, [])

    def test_later_live_evidence_changes_do_not_change_source_lineage(self):
        context = self.make_decided_context()
        evidence = context["evidence"][0]
        captured_url = evidence.evidence_url
        EvidenceSubmission.objects.filter(pk=evidence.pk).update(
            evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
            evidence_url="https://example.com/later-live-url",
            evidence_caption="Later live title",
        )

        draft = self.make_draft(context, suffix="live-change")

        source = draft.source_items.get()
        self.assertEqual(source.url, captured_url)
        self.assertEqual(
            source.evidence_links.get().captured_evidence_id,
            evidence.id,
        )
        self.assertFalse(
            draft.source_items.filter(
                url="https://example.com/later-live-url"
            ).exists()
        )

    def test_later_live_verification_does_not_create_a_snapshot_source(self):
        context = self.make_decided_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.REJECTED]
        )
        evidence = context["evidence"][0]
        EvidenceSubmission.objects.filter(pk=evidence.pk).update(
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            evidence_url="https://example.com/later-verified-source",
        )

        draft = self.make_draft(context, suffix="no-live-fallback")

        self.assertFalse(draft.source_items.exists())
        draft.refresh_from_db()
        self.assertEqual(draft.sources, [])

    def test_missing_or_unsupported_snapshot_fails_without_live_fallback(self):
        missing = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        missing["decision"] = AdjudicationDecision.objects.create(
            claim=missing["claim"],
            moderation_case=missing["case"],
            verdict=AdjudicationDecision.Verdict.FAKE,
            canonical_claim="Legacy decision without captured evidence.",
            rationale="Historical provenance is unavailable.",
            decided_by=self.lead,
            organization=self.organization,
            decision_source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
            revision_number=1,
            is_current=True,
        )
        with self.assertRaises(PublishingConflict):
            self.make_draft(missing, suffix="missing-snapshot")

        unsupported = self.make_decided_context()
        AdjudicationDecisionEvidenceSnapshot.objects.filter(
            pk=unsupported["snapshot"].pk
        ).update(schema_version=99)
        with self.assertRaises(PublishingConflict):
            self.make_draft(unsupported, suffix="unsupported-snapshot")

        self.assertFalse(
            OfficialFactCheck.objects.filter(
                claim__in=[missing["claim"], unsupported["claim"]]
            ).exists()
        )

    def test_lineage_rejects_cross_claim_and_rejected_associations(self):
        first = self.make_decided_context()
        second = self.make_decided_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.REJECTED]
        )
        draft = self.make_draft(first, suffix="identity")
        source = draft.source_items.get()

        with self.assertRaises(ValidationError):
            OfficialFactCheckSourceEvidenceLink.objects.create(
                source=source,
                snapshot=second["snapshot"],
                captured_evidence_id=second["evidence"][0].id,
            )

        rejected_draft = self.make_draft(
            second,
            source_urls=[second["evidence"][0].evidence_url],
            suffix="rejected-association",
        )
        rejected_source = rejected_draft.source_items.get(
            url=second["evidence"][0].evidence_url
        )
        with self.assertRaises(ValidationError):
            OfficialFactCheckSourceEvidenceLink.objects.create(
                source=rejected_source,
                snapshot=second["snapshot"],
                captured_evidence_id=second["evidence"][0].id,
            )

    def test_repeated_synchronization_is_idempotent(self):
        context = self.make_decided_context()
        draft = self.make_draft(context, suffix="idempotent")

        update_fact_check_draft(
            fact_check=draft,
            actor=self.lead,
            headline="Updated without changing lineage",
        )
        update_fact_check_draft(
            fact_check=draft,
            actor=self.lead,
            summary="Updated again without changing lineage.",
        )

        self.assertEqual(draft.source_items.count(), 1)
        self.assertEqual(
            OfficialFactCheckSourceEvidenceLink.objects.filter(
                source__fact_check=draft
            ).count(),
            1,
        )

    def test_editorial_selection_can_share_and_release_snapshot_source(self):
        context = self.make_decided_context()
        captured_url = context["evidence"][0].evidence_url
        first_manual = "https://example.com/editorial-one"
        second_manual = "https://example.com/editorial-two"
        draft = self.make_draft(
            context,
            suffix="dual-origin",
            source_urls=[captured_url, first_manual],
        )

        shared_source = draft.source_items.get(url=captured_url)
        self.assertTrue(shared_source.is_editorially_selected)
        self.assertEqual(
            shared_source.source_type,
            OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE,
        )
        self.assertEqual(shared_source.evidence_links.count(), 1)

        updated = update_fact_check_draft(
            fact_check=draft,
            actor=self.lead,
            source_urls=[second_manual],
        )

        shared_source.refresh_from_db()
        self.assertFalse(shared_source.is_editorially_selected)
        self.assertEqual(shared_source.evidence_links.count(), 1)
        self.assertFalse(updated.source_items.filter(url=first_manual).exists())
        self.assertTrue(
            updated.source_items.filter(
                url=second_manual,
                is_editorially_selected=True,
            ).exists()
        )
        updated.refresh_from_db()
        self.assertEqual(
            updated.sources,
            list(
                updated.source_items.order_by("created_at", "id").values_list(
                    "url", flat=True
                )
            ),
        )

    def test_existing_editorial_source_gains_lineage_without_reclassification(self):
        context = self.make_decided_context()
        captured_url = context["evidence"][0].evidence_url
        draft = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Pre-lineage editorial draft",
            summary="A draft created before normalized lineage was available.",
            article_body="The article contains a documented analysis.",
            publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            version=1,
            drafted_by=self.lead,
        )
        editorial_source = OfficialFactCheckSource.objects.create(
            fact_check=draft,
            url=captured_url,
            title="Editorial title must remain",
            evidence_submission=context["evidence"][0],
            added_by=self.moderator,
            source_type=OfficialFactCheckSource.SourceType.MODERATOR_ADDED,
            is_editorially_selected=True,
        )

        update_fact_check_draft(
            fact_check=draft,
            actor=self.lead,
            headline="Updated pre-lineage editorial draft",
        )

        editorial_source.refresh_from_db()
        self.assertEqual(
            editorial_source.source_type,
            OfficialFactCheckSource.SourceType.MODERATOR_ADDED,
        )
        self.assertTrue(editorial_source.is_editorially_selected)
        self.assertEqual(editorial_source.title, "Editorial title must remain")
        self.assertEqual(
            editorial_source.evidence_submission,
            context["evidence"][0],
        )
        self.assertEqual(editorial_source.added_by, self.moderator)
        self.assertEqual(
            editorial_source.evidence_links.get().captured_evidence_id,
            context["evidence"][0].id,
        )

    def test_legacy_unknown_source_is_preserved_during_editorial_replacement(self):
        context = self.make_decided_context()
        draft = self.make_draft(
            context,
            suffix="legacy",
            source_urls=["https://example.com/removable-editorial"],
        )
        legacy = OfficialFactCheckSource.objects.create(
            fact_check=draft,
            url="https://example.com/legacy-unknown",
            title="Preserved historical source",
            source_type=OfficialFactCheckSource.SourceType.LEGACY_IMPORT,
            added_by=self.moderator,
        )

        update_fact_check_draft(
            fact_check=draft,
            actor=self.lead,
            source_urls=[],
        )

        legacy.refresh_from_db()
        self.assertIsNone(legacy.is_editorially_selected)
        self.assertEqual(
            legacy.source_type,
            OfficialFactCheckSource.SourceType.LEGACY_IMPORT,
        )
        self.assertEqual(legacy.title, "Preserved historical source")
        self.assertEqual(legacy.added_by, self.moderator)

    def test_lineage_failure_rolls_back_draft_and_sources(self):
        context = self.make_decided_context()

        with patch(
            "api.publishing_service."
            "OfficialFactCheckSourceEvidenceLink.objects.get_or_create",
            side_effect=RuntimeError("lineage persistence unavailable"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "lineage persistence unavailable",
            ):
                self.make_draft(context, suffix="rollback")

        self.assertFalse(
            OfficialFactCheck.objects.filter(claim=context["claim"]).exists()
        )
        self.assertFalse(
            OfficialFactCheckSource.objects.filter(
                fact_check__claim=context["claim"]
            ).exists()
        )

    def test_lineage_links_reject_ordinary_edits_and_direct_deletion(self):
        context = self.make_decided_context()
        draft = self.make_draft(context, suffix="immutable")
        link = OfficialFactCheckSourceEvidenceLink.objects.get(
            source__fact_check=draft
        )

        with self.assertRaises(ValidationError):
            link.save()
        with self.assertRaises(ValidationError):
            link.delete()

        self.assertTrue(
            OfficialFactCheckSourceEvidenceLink.objects.filter(
                pk=link.pk
            ).exists()
        )

    def test_first_publication_keeps_lineage_and_completes_assignment(self):
        context = self.make_decided_context()
        draft = self.make_draft(context, suffix="publication")
        submitted = submit_fact_check_for_review(
            fact_check=draft,
            actor=self.lead,
        )

        result = publish_fact_check(
            fact_check=submitted,
            actor=self.lead,
        )

        context["assignment"].refresh_from_db()
        self.assertEqual(
            result["fact_check"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertTrue(
            OfficialFactCheckSourceEvidenceLink.objects.filter(
                source__fact_check=result["fact_check"],
                snapshot=context["snapshot"],
            ).exists()
        )
