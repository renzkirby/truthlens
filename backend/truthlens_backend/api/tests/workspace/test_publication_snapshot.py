from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from api.knowledge_reuse_service import index_published_fact_check
from api.models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
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


class PublicationSnapshotTests(AdjudicationContractFixtures, TestCase):
    def make_decided_context(self, evidence_statuses=None):
        context = self.make_context(
            evidence_statuses=evidence_statuses
            or [EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        context["decision"] = self.issue(context)["decision"]
        context["decision_snapshot"] = context["decision"].evidence_snapshot
        return context

    def make_submitted_draft(self, context, *, source_urls=None, suffix="seal"):
        draft = create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            headline=f"Sealed publication {suffix}",
            summary="A professional summary of the adjudicated claim.",
            article_body="The article documents the reviewed source basis.",
            source_urls=source_urls,
        )
        return submit_fact_check_for_review(
            fact_check=draft,
            actor=self.lead,
        )

    def publish_context(self, context, *, source_urls=None, suffix="seal"):
        submitted = self.make_submitted_draft(
            context,
            source_urls=source_urls,
            suffix=suffix,
        )
        result = publish_fact_check(fact_check=submitted, actor=self.lead)
        return result["fact_check"], result

    def test_first_publication_creates_one_exact_sealed_record(self):
        context = self.make_decided_context()
        fact_check, result = self.publish_context(context, suffix="exact")

        snapshot = OfficialFactCheckPublicationSnapshot.objects.get(
            fact_check=fact_check
        )
        payload = snapshot.payload
        self.assertEqual(snapshot.captured_at, fact_check.published_at)
        self.assertEqual(snapshot.decision_snapshot, context["decision_snapshot"])
        self.assertEqual(payload["fact_check_id"], str(fact_check.id))
        self.assertEqual(payload["claim_id"], str(context["claim"].id))
        self.assertEqual(payload["decision_id"], str(context["decision"].id))
        self.assertEqual(
            payload["decision_evidence_snapshot_id"],
            str(context["decision_snapshot"].id),
        )
        self.assertEqual(payload["article_version"], fact_check.version)
        self.assertEqual(payload["published_at"], fact_check.published_at.isoformat())
        self.assertEqual(payload["canonical_claim"], fact_check.canonical_claim)
        self.assertEqual(payload["verdict"], fact_check.verdict)
        self.assertEqual(payload["headline"], fact_check.headline)
        self.assertEqual(payload["summary"], fact_check.summary)
        self.assertEqual(payload["article_body"], fact_check.article_body)
        self.assertEqual(payload["drafted_by"]["id"], str(self.lead.id))
        self.assertEqual(payload["reviewed_by"]["id"], str(self.lead.id))
        self.assertEqual(payload["published_by"]["id"], str(self.lead.id))
        self.assertEqual(payload["organization"]["id"], str(self.organization.id))
        self.assertEqual(payload["organization"]["name"], self.organization.name)
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=fact_check
            ).count(),
            1,
        )
        with self.assertRaises(ValidationError):
            OfficialFactCheckPublicationSnapshot.objects.create(
                fact_check=fact_check,
                decision_snapshot=context["decision_snapshot"],
                captured_at=fact_check.published_at,
                payload=deepcopy(payload),
            )
        self.assertIsNone(result["archived_fact_check"])
        context["assignment"].refresh_from_db()
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )

    def test_duplicate_url_and_dual_origin_capture_complete_lineage(self):
        context = self.make_context(
            evidence_statuses=[
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
            ]
        )
        shared_url = "https://example.com/sealed-shared-source"
        now = timezone.now()
        for index, evidence in enumerate(context["evidence"]):
            EvidenceSubmission.objects.filter(pk=evidence.pk).update(
                evidence_url=shared_url,
                submitted_at=now + timedelta(minutes=index),
            )
        context["decision"] = self.issue(context)["decision"]
        context["decision_snapshot"] = context["decision"].evidence_snapshot

        fact_check, _result = self.publish_context(
            context,
            source_urls=[shared_url],
            suffix="duplicate-lineage",
        )

        payload_source = fact_check.publication_snapshot.payload["sources"][0]
        self.assertEqual(payload_source["url"], shared_url)
        self.assertTrue(payload_source["is_editorially_selected"])
        self.assertEqual(
            {item["captured_evidence_id"] for item in payload_source["lineage"]},
            {str(context["evidence"][0].id), str(context["evidence"][1].id)},
        )
        self.assertNotIn(
            str(context["evidence"][2].id),
            {item["captured_evidence_id"] for item in payload_source["lineage"]},
        )
        for item in payload_source["lineage"]:
            self.assertEqual(
                item["decision_evidence_snapshot_id"],
                str(context["decision_snapshot"].id),
            )
        self.assertEqual(
            {item["id"] for item in payload_source["lineage"]},
            {
                str(link_id)
                for link_id in OfficialFactCheckSourceEvidenceLink.objects.filter(
                    source__fact_check=fact_check
                ).values_list("id", flat=True)
            },
        )

    def test_source_order_and_explicit_nulls_are_preserved(self):
        context = self.make_decided_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.REJECTED]
        )
        submitted = self.make_submitted_draft(
            context,
            source_urls=[
                "https://example.com/editorial-first",
                "https://example.com/editorial-second",
            ],
            suffix="ordered-null",
        )
        first_source = submitted.source_items.order_by("created_at", "id").first()
        OfficialFactCheckSource.objects.filter(pk=first_source.pk).update(
            title=None,
            added_by=None,
            is_editorially_selected=None,
        )

        fact_check = publish_fact_check(
            fact_check=submitted,
            actor=self.lead,
        )["fact_check"]
        expected_source_ids = [
            str(source_id)
            for source_id in fact_check.source_items.order_by(
                "created_at", "id"
            ).values_list("id", flat=True)
        ]
        payload_sources = fact_check.publication_snapshot.payload["sources"]

        self.assertEqual(
            [item["id"] for item in payload_sources],
            expected_source_ids,
        )
        captured_first = next(
            item for item in payload_sources if item["id"] == str(first_source.id)
        )
        self.assertIsNone(captured_first["title"])
        self.assertIsNone(captured_first["added_by"])
        self.assertIsNone(captured_first["is_editorially_selected"])
        self.assertIsNone(captured_first["legacy_evidence_submission_id"])
        self.assertEqual(captured_first["lineage"], [])

    def test_later_live_changes_do_not_change_sealed_payload(self):
        context = self.make_decided_context()
        fact_check, _result = self.publish_context(context, suffix="durable")
        snapshot = fact_check.publication_snapshot
        original_payload = deepcopy(snapshot.payload)
        source = fact_check.source_items.get()

        OfficialFactCheck.objects.filter(pk=fact_check.pk).update(
            headline="Later mutable headline"
        )
        OfficialFactCheckSource.objects.filter(pk=source.pk).update(
            title="Later mutable source title"
        )
        EvidenceSubmission.objects.filter(pk=context["evidence"][0].pk).update(
            evidence_url="https://example.com/later-evidence-url"
        )
        type(self.lead).objects.filter(pk=self.lead.pk).update(
            username="later-username"
        )
        type(self.organization).objects.filter(pk=self.organization.pk).update(
            name="Later organization name"
        )

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.payload, original_payload)

    def test_malformed_or_cross_decision_lineage_fails_closed(self):
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="bad-lineage")
        other = self.make_decided_context()
        link = OfficialFactCheckSourceEvidenceLink.objects.get(
            source__fact_check=submitted
        )
        OfficialFactCheckSourceEvidenceLink.objects.filter(pk=link.pk).update(
            snapshot=other["decision_snapshot"]
        )
        event_count = ModerationEvent.objects.filter(case=context["case"]).count()

        with self.assertRaises(PublishingConflict):
            publish_fact_check(fact_check=submitted, actor=self.lead)

        submitted.refresh_from_db()
        context["assignment"].refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )
        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=submitted
            ).exists()
        )
        self.assertEqual(
            ModerationEvent.objects.filter(case=context["case"]).count(),
            event_count,
        )

    def test_unknown_captured_evidence_lineage_fails_closed(self):
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="unknown-evidence")
        link = OfficialFactCheckSourceEvidenceLink.objects.get(
            source__fact_check=submitted
        )
        OfficialFactCheckSourceEvidenceLink.objects.filter(pk=link.pk).update(
            captured_evidence_id="00000000-0000-0000-0000-000000000001"
        )

        with self.assertRaises(PublishingConflict):
            publish_fact_check(fact_check=submitted, actor=self.lead)

        submitted.refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=submitted
            ).exists()
        )

    def test_sealed_record_failure_rolls_back_all_publication_effects(self):
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="rollback")
        submitted.source_items.all().delete()
        event_count = ModerationEvent.objects.filter(case=context["case"]).count()

        with patch(
            "api.models.OfficialFactCheckPublicationSnapshot.save",
            side_effect=RuntimeError("sealed record storage unavailable"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "sealed record storage unavailable",
            ):
                publish_fact_check(fact_check=submitted, actor=self.lead)

        submitted.refresh_from_db()
        context["assignment"].refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(case=context["case"]).count(),
            event_count,
        )
        self.assertFalse(submitted.source_items.exists())
        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=submitted
            ).exists()
        )

    def test_sealed_records_articles_and_sources_reject_ordinary_changes(self):
        context = self.make_decided_context()
        fact_check, _result = self.publish_context(context, suffix="protected")
        snapshot = fact_check.publication_snapshot
        source = fact_check.source_items.get()

        snapshot.payload = {**snapshot.payload, "headline": "Changed seal"}
        with self.assertRaises(ValidationError):
            snapshot.save()
        with self.assertRaises(ValidationError):
            snapshot.delete()
        with self.assertRaises(ProtectedError):
            fact_check.delete()

        fact_check.headline = "Changed published headline"
        with self.assertRaises(ValidationError):
            fact_check.save(update_fields=["headline", "updated_at"])
        fact_check.refresh_from_db()

        source.title = "Changed source title"
        with self.assertRaises(ValidationError):
            source.save(update_fields=["title"])
        with self.assertRaises(ValidationError):
            source.delete()
        with self.assertRaises(ValidationError):
            OfficialFactCheckSource.objects.create(
                fact_check=fact_check,
                url="https://example.com/late-source",
                source_type=OfficialFactCheckSource.SourceType.MODERATOR_ADDED,
                is_editorially_selected=True,
            )

        with self.assertRaises(ValidationError):
            OfficialFactCheckSourceEvidenceLink.objects.create(
                source=source,
                snapshot=context["decision_snapshot"],
                captured_evidence_id=context["evidence"][0].id,
            )

        fact_check.publication_status = OfficialFactCheck.PublicationStatus.ARCHIVED
        fact_check.archived_at = timezone.now()
        fact_check.save(
            update_fields=["publication_status", "archived_at", "updated_at"]
        )
        fact_check.refresh_from_db()
        self.assertEqual(
            fact_check.publication_status,
            OfficialFactCheck.PublicationStatus.ARCHIVED,
        )

    def test_draft_edits_and_sealed_index_maintenance_remain_allowed(self):
        draft_context = self.make_decided_context()
        draft = create_fact_check_draft(
            decision=draft_context["decision"],
            actor=self.lead,
            headline="Editable draft",
            summary="Draft summary.",
            article_body="Draft analysis.",
            source_urls=["https://example.com/editable-draft"],
        )
        update_fact_check_draft(
            fact_check=draft,
            actor=self.lead,
            headline="Still editable draft",
            source_urls=["https://example.com/replaced-draft-source"],
        )
        draft.refresh_from_db()
        self.assertEqual(draft.headline, "Still editable draft")

        sealed_context = self.make_decided_context()
        sealed, _result = self.publish_context(sealed_context, suffix="index")
        fake_embedding = [0.01] * 384
        with patch(
            "api.knowledge_reuse_service.generate_embedding",
            return_value=fake_embedding,
        ):
            self.assertTrue(index_published_fact_check(sealed))
        sealed.refresh_from_db()
        self.assertIsNotNone(sealed.embedding)

    def test_legacy_published_article_remains_snapshot_absent_and_mutable(self):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Legacy publication without a sealed record.",
        )
        legacy = OfficialFactCheck.objects.create(
            claim=claim,
            canonical_claim="Legacy canonical claim.",
            verdict=AdjudicationDecision.Verdict.UNVERIFIED,
            headline="Legacy published headline",
            summary="Legacy summary.",
            article_body="Legacy article body.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
            published_at=timezone.now(),
        )

        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=legacy
            ).exists()
        )
        legacy.headline = "Legacy behavior remains unchanged"
        legacy.save(update_fields=["headline", "updated_at"])
        legacy.refresh_from_db()
        self.assertEqual(legacy.headline, "Legacy behavior remains unchanged")

    def test_sealed_source_cannot_be_reparented_or_deleted_after_in_memory_change(self):
        sealed_context = self.make_decided_context()
        sealed, _result = self.publish_context(
            sealed_context,
            suffix="reparent-protection",
        )
        source = sealed.source_items.get()

        draft_context = self.make_decided_context()
        draft = create_fact_check_draft(
            decision=draft_context["decision"],
            actor=self.lead,
            headline="Unsealed destination",
            summary="Draft summary.",
            article_body="Draft analysis.",
        )

        source.fact_check = draft
        with self.assertRaises(ValidationError):
            source.save(update_fields=["fact_check_id"])

        source.refresh_from_db()
        self.assertEqual(source.fact_check_id, sealed.id)

        source.fact_check = draft
        with self.assertRaises(ValidationError):
            source.delete()

        self.assertTrue(
            OfficialFactCheckSource.objects.filter(
                pk=source.pk,
                fact_check=sealed,
            ).exists()
        )
