import threading
import uuid
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from api import publishing_service
from api.models import (
    EvidenceSubmission,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OrganizationMembership,
    VerificationAssignment,
)
from api.publication_snapshot_schema import (
    EDITORIAL_REVISION_SCHEMA_VERSION,
    FIRST_PUBLICATION_SCHEMA_VERSION,
    PublicationSnapshotSchemaError,
    validate_publication_snapshot,
)
from api.publishing_service import (
    InvalidFactCheckContent,
    PublishingAuthorizationError,
    PublishingConflict,
    create_editorial_revision_draft,
    create_fact_check_draft,
    publish_editorial_revision,
    publish_fact_check,
    submit_fact_check_for_review,
)
from api.tests.adjudication.test_adjudication_transaction_contract import (
    AdjudicationContractFixtures,
)
from api.verification_assignment_service import ensure_verification_assignment


class EditorialReplacementFixtures(AdjudicationContractFixtures):
    def make_published_context(self, *, suffix="initial"):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        context["decision"] = self.issue(context)["decision"]
        draft = create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            headline=f"Published headline {suffix}",
            summary=f"Published summary {suffix}.",
            article_body=f"Published analysis {suffix}.",
            source_urls=[f"https://example.com/editorial-{suffix}"],
        )
        submitted = submit_fact_check_for_review(
            fact_check=draft,
            actor=self.lead,
        )
        context["published"] = publish_fact_check(
            fact_check=submitted,
            actor=self.lead,
        )["fact_check"]
        context["seal"] = context["published"].publication_snapshot
        return context

    def make_submitted_revision(self, context, *, reason="Clarify the article."):
        revision = create_editorial_revision_draft(
            predecessor_id=context["published"].id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=context["published"].version,
            expected_decision_revision=context["decision"].revision_number,
            revision_reason=reason,
            headline=f"Revised headline {context['published'].version + 1}",
            summary="Revised summary with clearer context.",
            article_body="Revised analysis preserving the adjudicated conclusion.",
        )
        return submit_fact_check_for_review(
            fact_check=revision,
            actor=self.lead,
        )

    def replace(self, context, revision, **overrides):
        values = {
            "revision_id": revision.id,
            "predecessor_id": context["published"].id,
            "actor": self.lead,
            "organization_id": self.organization.id,
            "expected_predecessor_version": context["published"].version,
            "expected_revision_version": revision.version,
            "expected_decision_revision": context["decision"].revision_number,
        }
        values.update(overrides)
        return publish_editorial_revision(**values)


class EditorialRevisionPublicationTests(EditorialReplacementFixtures, TestCase):
    def test_replacement_archives_exact_predecessor_and_creates_v2_seal_event(self):
        context = self.make_published_context(suffix="success")
        predecessor_payload = deepcopy(context["seal"].payload)
        predecessor_published_at = context["published"].published_at
        assignment_count = VerificationAssignment.objects.filter(
            claim=context["claim"]
        ).count()
        revision = self.make_submitted_revision(
            context,
            reason="Correct structure and improve source explanation.",
        )

        result = self.replace(context, revision)

        context["published"].refresh_from_db()
        revision.refresh_from_db()
        context["assignment"].refresh_from_db()
        successor_seal = revision.publication_snapshot
        event = ModerationEvent.objects.get(
            case=context["case"],
            event_type=ModerationEvent.EventType.ARTICLE_REVISED,
        )
        self.assertEqual(result["fact_check"].id, revision.id)
        self.assertEqual(result["archived_fact_check"].id, context["published"].id)
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.ARCHIVED,
        )
        self.assertEqual(
            revision.publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(context["published"].published_at, predecessor_published_at)
        self.assertEqual(context["seal"].payload, predecessor_payload)
        context["seal"].full_clean()
        self.assertEqual(
            successor_seal.schema_version,
            EDITORIAL_REVISION_SCHEMA_VERSION,
        )
        self.assertEqual(successor_seal.captured_at, revision.published_at)
        self.assertEqual(successor_seal.payload["fact_check_id"], str(revision.id))
        self.assertEqual(
            successor_seal.payload["revision"],
            {
                "revision_kind": "EDITORIAL_REVISION",
                "supersedes_fact_check_id": str(context["published"].id),
                "supersedes_publication_snapshot_id": str(context["seal"].id),
                "predecessor_article_version": context["published"].version,
                "predecessor_published_at": predecessor_published_at.isoformat(),
                "revision_reason": (
                    "Correct structure and improve source explanation."
                ),
                "revision_requested_by": {
                    "id": str(self.lead.id),
                    "username": self.lead.username,
                },
                "revision_requested_at": revision.revision_requested_at.isoformat(),
            },
        )
        self.assertEqual(event.actor, self.lead)
        self.assertEqual(event.notes, revision.revision_reason)
        self.assertEqual(
            event.metadata["old_fact_check_id"], str(context["published"].id)
        )
        self.assertEqual(event.metadata["new_fact_check_id"], str(revision.id))
        self.assertEqual(
            event.metadata["predecessor_publication_snapshot_id"],
            str(context["seal"].id),
        )
        self.assertEqual(
            event.metadata["successor_publication_snapshot_id"],
            str(successor_seal.id),
        )
        successor_seal.full_clean()
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertEqual(
            VerificationAssignment.objects.filter(claim=context["claim"]).count(),
            assignment_count,
        )
        with self.assertRaises(PublishingConflict):
            self.replace(context, revision)
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=context["case"],
                event_type=ModerationEvent.EventType.ARTICLE_REVISED,
            ).count(),
            1,
        )
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=revision
            ).count(),
            1,
        )

    def test_v1_first_publication_and_strict_v2_schema_dispatch_remain_distinct(self):
        context = self.make_published_context(suffix="schema")
        self.assertEqual(
            context["seal"].schema_version,
            FIRST_PUBLICATION_SCHEMA_VERSION,
        )
        self.assertNotIn("revision", context["seal"].payload)
        validate_publication_snapshot(
            schema_version=FIRST_PUBLICATION_SCHEMA_VERSION,
            payload=context["seal"].payload,
        )

        revision = self.make_submitted_revision(context)
        self.replace(context, revision)
        payload = deepcopy(revision.publication_snapshot.payload)
        validate_publication_snapshot(
            schema_version=EDITORIAL_REVISION_SCHEMA_VERSION,
            payload=payload,
        )

        malformed_payloads = []
        extra = deepcopy(payload)
        extra["revision"]["unexpected"] = True
        malformed_payloads.append(extra)
        invalid_actor = deepcopy(payload)
        invalid_actor["revision"]["revision_requested_by"] = {"id": "x"}
        malformed_payloads.append(invalid_actor)
        empty_reason = deepcopy(payload)
        empty_reason["revision"]["revision_reason"] = "   "
        malformed_payloads.append(empty_reason)
        oversized_reason = deepcopy(payload)
        oversized_reason["revision"]["revision_reason"] = "x" * 2001
        malformed_payloads.append(oversized_reason)
        invalid_kind = deepcopy(payload)
        invalid_kind["revision"]["revision_kind"] = "FACTUAL_CORRECTION"
        malformed_payloads.append(invalid_kind)
        invalid_timestamp = deepcopy(payload)
        invalid_timestamp["revision"]["revision_requested_at"] = "not-a-date"
        malformed_payloads.append(invalid_timestamp)
        invalid_id = deepcopy(payload)
        invalid_id["revision"]["supersedes_fact_check_id"] = "not-a-uuid"
        malformed_payloads.append(invalid_id)

        for malformed in malformed_payloads:
            with self.subTest(revision=malformed["revision"]):
                with self.assertRaises(PublicationSnapshotSchemaError):
                    validate_publication_snapshot(
                        schema_version=EDITORIAL_REVISION_SCHEMA_VERSION,
                        payload=malformed,
                    )
        with self.assertRaises(PublicationSnapshotSchemaError):
            validate_publication_snapshot(schema_version=99, payload=payload)

    def test_historical_null_initial_metadata_remains_publishable_without_history(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        context["decision"] = self.issue(context)["decision"]
        draft = create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            headline="Historical-null initial publication",
            summary="No prior publication history exists for this claim.",
            article_body="The initial metadata remains historically compatible.",
        )
        submitted = submit_fact_check_for_review(
            fact_check=draft,
            actor=self.lead,
        )
        OfficialFactCheck.objects.filter(pk=submitted.pk).update(revision_kind=None)
        submitted.refresh_from_db()

        published = publish_fact_check(fact_check=submitted, actor=self.lead)[
            "fact_check"
        ]

        self.assertIsNone(published.revision_kind)
        self.assertEqual(
            published.publication_snapshot.schema_version,
            FIRST_PUBLICATION_SCHEMA_VERSION,
        )
        self.assertNotIn("revision", published.publication_snapshot.payload)

    def test_successive_replacements_form_a_linear_sealed_chain(self):
        context = self.make_published_context(suffix="chain")
        first_revision = self.make_submitted_revision(context, reason="Revision one.")
        self.replace(context, first_revision)

        original = context["published"]
        context["published"] = first_revision
        context["seal"] = first_revision.publication_snapshot
        second_revision = self.make_submitted_revision(
            context,
            reason="Revision two.",
        )
        self.replace(context, second_revision)

        original.refresh_from_db()
        first_revision.refresh_from_db()
        second_revision.refresh_from_db()
        self.assertEqual(original.publication_status, "ARCHIVED")
        self.assertEqual(first_revision.publication_status, "ARCHIVED")
        self.assertEqual(second_revision.publication_status, "PUBLISHED")
        self.assertEqual(second_revision.supersedes_id, first_revision.id)
        self.assertEqual(
            second_revision.publication_snapshot.payload["revision"][
                "supersedes_publication_snapshot_id"
            ],
            str(first_revision.publication_snapshot.id),
        )

        with self.assertRaises(PublishingConflict):
            publish_editorial_revision(
                revision_id=second_revision.id,
                predecessor_id=original.id,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_predecessor_version=original.version,
                expected_revision_version=second_revision.version,
                expected_decision_revision=context["decision"].revision_number,
            )

    def test_historical_null_initial_root_can_publish_editorial_revision(self):
        context = self.make_published_context(suffix="historical-null-root")
        root_id = context["published"].id
        root_seal_id = context["seal"].id
        root_payload = deepcopy(context["seal"].payload)
        OfficialFactCheck.objects.filter(pk=root_id).update(revision_kind=None)
        context["published"].refresh_from_db()

        revision = self.make_submitted_revision(
            context,
            reason="Clarify wording from a historical initial publication.",
        )
        self.replace(context, revision)

        context["published"].refresh_from_db()
        revision.refresh_from_db()
        root_seal = OfficialFactCheckPublicationSnapshot.objects.get(pk=root_seal_id)
        self.assertIsNone(context["published"].revision_kind)
        self.assertEqual(root_seal.schema_version, FIRST_PUBLICATION_SCHEMA_VERSION)
        self.assertEqual(root_seal.payload, root_payload)
        self.assertEqual(context["published"].publication_status, "ARCHIVED")
        self.assertEqual(revision.publication_status, "PUBLISHED")
        self.assertEqual(revision.supersedes_id, root_id)

    def test_abandoned_never_published_draft_is_not_publication_history(self):
        context = self.make_published_context(suffix="abandoned-draft")
        OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Abandoned draft",
            summary="This draft was never published.",
            article_body="Abandoned draft content.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=context["published"].version + 1,
            drafted_by=self.lead,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        revision = self.make_submitted_revision(context)

        self.replace(context, revision)

        revision.refresh_from_db()
        self.assertEqual(revision.publication_status, "PUBLISHED")

    def test_disconnected_recorded_history_blocks_editorial_replacement(self):
        context = self.make_published_context(suffix="disconnected-history")
        revision = self.make_submitted_revision(context)
        recorded_at = timezone.now()
        disconnected = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Disconnected recorded publication",
            summary="Recorded publication without a connected seal.",
            article_body="Historical content is not reconstructed.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=revision.version + 1,
            drafted_by=self.lead,
            reviewed_by=self.lead,
            reviewed_at=recorded_at,
            published_by=self.lead,
            published_at=recorded_at,
            archived_at=recorded_at,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        disconnected_payload = deepcopy(context["seal"].payload)
        disconnected_payload.update(
            {
                "fact_check_id": str(disconnected.id),
                "article_version": disconnected.version,
                "published_at": recorded_at.isoformat(),
            }
        )
        OfficialFactCheckPublicationSnapshot.objects.bulk_create(
            [
                OfficialFactCheckPublicationSnapshot(
                    fact_check=disconnected,
                    decision_snapshot=context["decision"].evidence_snapshot,
                    schema_version=FIRST_PUBLICATION_SCHEMA_VERSION,
                    captured_at=recorded_at,
                    payload=disconnected_payload,
                )
            ]
        )

        with self.assertRaises(PublishingConflict):
            self.replace(context, revision)

        context["published"].refresh_from_db()
        revision.refresh_from_db()
        self.assertEqual(context["published"].publication_status, "PUBLISHED")
        self.assertEqual(revision.publication_status, "IN_REVIEW")

    def test_chain_validator_rejects_cyclic_or_branched_stored_history(self):
        published_at = timezone.now()
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()

        def history_item(item_id, *, supersedes_id, status="ARCHIVED"):
            return SimpleNamespace(
                id=item_id,
                publication_status=status,
                published_at=published_at,
                supersedes_id=supersedes_id,
            )

        def history_snapshot(item_id):
            return SimpleNamespace(
                id=uuid.uuid4(),
                fact_check_id=item_id,
                schema_version=EDITORIAL_REVISION_SCHEMA_VERSION,
                captured_at=published_at,
            )

        cyclic_items = [
            history_item(first_id, supersedes_id=second_id),
            history_item(
                second_id,
                supersedes_id=first_id,
                status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ),
        ]
        cyclic_snapshots = [
            history_snapshot(first_id),
            history_snapshot(second_id),
        ]
        with patch(
            "api.publishing_service._validate_predecessor_publication_snapshot",
            return_value={},
        ):
            with self.assertRaises(PublishingConflict):
                publishing_service._validate_complete_publication_history(
                    predecessor=cyclic_items[1],
                    fact_checks=cyclic_items,
                    publication_snapshots=cyclic_snapshots,
                    organization=SimpleNamespace(),
                )

        root_id = uuid.uuid4()
        left_id = uuid.uuid4()
        right_id = uuid.uuid4()
        branched_items = [
            history_item(root_id, supersedes_id=None),
            history_item(
                left_id,
                supersedes_id=root_id,
                status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ),
            history_item(right_id, supersedes_id=root_id),
        ]
        branched_snapshots = [
            history_snapshot(root_id),
            history_snapshot(left_id),
            history_snapshot(right_id),
        ]
        with patch(
            "api.publishing_service._validate_predecessor_publication_snapshot",
            return_value={},
        ):
            with self.assertRaises(PublishingConflict):
                publishing_service._validate_complete_publication_history(
                    predecessor=branched_items[1],
                    fact_checks=branched_items,
                    publication_snapshots=branched_snapshots,
                    organization=SimpleNamespace(),
                )

    def test_strict_inputs_stale_versions_and_authority_fail_closed(self):
        context = self.make_published_context(suffix="preconditions")
        revision = self.make_submitted_revision(context)

        for field, value in (
            ("revision_id", True),
            ("predecessor_id", "not-a-uuid"),
            ("organization_id", False),
            ("expected_predecessor_version", 0),
            ("expected_revision_version", True),
            ("expected_decision_revision", -1),
        ):
            with self.subTest(field=field):
                with self.assertRaises(InvalidFactCheckContent):
                    self.replace(context, revision, **{field: value})

        for field, value in (
            ("expected_predecessor_version", context["published"].version + 1),
            ("expected_revision_version", revision.version + 1),
            ("expected_decision_revision", context["decision"].revision_number + 1),
        ):
            with self.subTest(field=field):
                with self.assertRaises(PublishingConflict):
                    self.replace(context, revision, **{field: value})

        with self.assertRaises(PublishingAuthorizationError):
            self.replace(
                context,
                revision,
                organization_id=self.other_organization.id,
            )
        with self.assertRaises(PublishingAuthorizationError):
            self.replace(context, revision, actor=self.moderator)
        OrganizationMembership.objects.filter(
            organization=self.organization,
            user=self.lead,
        ).update(status=OrganizationMembership.Status.SUSPENDED)
        with self.assertRaises(PublishingAuthorizationError):
            self.replace(context, revision)

        context["published"].refresh_from_db()
        revision.refresh_from_db()
        self.assertEqual(context["published"].publication_status, "PUBLISHED")
        self.assertEqual(revision.publication_status, "IN_REVIEW")

    def test_missing_malformed_or_already_present_seal_blocks_replacement(self):
        missing = self.make_published_context(suffix="missing-seal")
        missing_revision = self.make_submitted_revision(missing)
        OfficialFactCheckPublicationSnapshot.objects.filter(
            pk=missing["seal"].pk
        ).delete()
        with self.assertRaises(PublishingConflict):
            self.replace(missing, missing_revision)

        malformed = self.make_published_context(suffix="malformed-seal")
        malformed_revision = self.make_submitted_revision(malformed)
        payload = deepcopy(malformed["seal"].payload)
        payload["claim_id"] = str(missing["claim"].id)
        OfficialFactCheckPublicationSnapshot.objects.filter(
            pk=malformed["seal"].pk
        ).update(payload=payload)
        with self.assertRaises(PublishingConflict):
            self.replace(malformed, malformed_revision)

        sealed = self.make_published_context(suffix="sealed-successor")
        sealed_revision = self.make_submitted_revision(sealed)
        OfficialFactCheckPublicationSnapshot.objects.bulk_create(
            [
                OfficialFactCheckPublicationSnapshot(
                    fact_check=sealed_revision,
                    decision_snapshot=sealed["decision"].evidence_snapshot,
                    captured_at=sealed["published"].published_at,
                    payload=sealed["seal"].payload,
                )
            ]
        )
        with self.assertRaises(PublishingConflict):
            self.replace(sealed, sealed_revision)

    def test_open_assignment_conflicts_and_completed_assignment_is_untouched(self):
        context = self.make_published_context(suffix="assignment")
        revision = self.make_submitted_revision(context)

        # Capture the persisted completion timestamp, not the stale
        # in-memory value left over from fixture creation.
        context["assignment"].refresh_from_db()
        completed_at = context["assignment"].completed_at

        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertIsNotNone(completed_at)

        VerificationAssignment.objects.create(
            claim=context["claim"],
            organization=self.organization,
            claimed_by=self.lead,
            status=VerificationAssignment.Status.ACTIVE,
        )

        with self.assertRaises(PublishingConflict):
            self.replace(context, revision)

        context["assignment"].refresh_from_db()

        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertEqual(
            context["assignment"].completed_at,
            completed_at,
        )

    def test_wrong_decision_or_missing_case_provenance_fails_closed(self):
        wrong_decision = self.make_published_context(suffix="wrong-decision")
        wrong_revision = self.make_submitted_revision(wrong_decision)
        other = self.make_published_context(suffix="other-decision")
        OfficialFactCheck.objects.filter(pk=wrong_revision.pk).update(
            adjudication_decision=other["decision"]
        )
        with self.assertRaises(PublishingConflict):
            self.replace(wrong_decision, wrong_revision)

        missing_case = self.make_published_context(suffix="missing-case")
        missing_case_revision = self.make_submitted_revision(missing_case)
        type(missing_case["decision"]).objects.filter(
            pk=missing_case["decision"].pk
        ).update(moderation_case=None)
        with self.assertRaises(PublishingConflict):
            self.replace(missing_case, missing_case_revision)

    def test_replacement_lineage_uses_snapshot_after_live_evidence_changes(self):
        context = self.make_published_context(suffix="snapshot-lineage")
        captured_url = context["decision"].evidence_snapshot.evidence_records[0][
            "evidence_url"
        ]
        revision = self.make_submitted_revision(context)
        EvidenceSubmission.objects.filter(pk=context["evidence"][0].pk).update(
            evidence_url="https://example.com/later-live-evidence"
        )

        self.replace(context, revision)

        captured_sources = revision.publication_snapshot.payload["sources"]
        captured_source = next(
            source for source in captured_sources if source["url"] == captured_url
        )
        self.assertEqual(
            captured_source["lineage"][0]["decision_evidence_snapshot_id"],
            str(context["decision"].evidence_snapshot.id),
        )

    def test_v2_seal_preserves_duplicate_url_lineage_and_editorial_origin(self):
        context = self.make_context(
            evidence_statuses=[
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.VERIFIED,
            ]
        )
        shared_url = "https://example.com/shared-revision-source"
        EvidenceSubmission.objects.filter(
            pk__in=[item.pk for item in context["evidence"]]
        ).update(evidence_url=shared_url)
        context["decision"] = self.issue(context)["decision"]
        draft = create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            headline="Shared-source predecessor",
            summary="Shared-source predecessor summary.",
            article_body="Shared-source predecessor analysis.",
            source_urls=[shared_url],
        )
        context["published"] = publish_fact_check(
            fact_check=submit_fact_check_for_review(
                fact_check=draft,
                actor=self.lead,
            ),
            actor=self.lead,
        )["fact_check"]
        context["seal"] = context["published"].publication_snapshot
        revision = self.make_submitted_revision(context)

        self.replace(context, revision)

        source = next(
            item
            for item in revision.publication_snapshot.payload["sources"]
            if item["url"] == shared_url
        )
        self.assertTrue(source["is_editorially_selected"])
        self.assertEqual(
            {item["captured_evidence_id"] for item in source["lineage"]},
            {str(item.id) for item in context["evidence"]},
        )

    def test_ordinary_publish_cannot_bypass_replacement_after_manual_archival(self):
        context = self.make_published_context(suffix="bypass")
        revision = self.make_submitted_revision(context)
        OfficialFactCheck.objects.filter(pk=context["published"].pk).update(
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED
        )

        with self.assertRaises(PublishingConflict):
            publish_fact_check(fact_check=revision, actor=self.lead)

        revision.refresh_from_db()
        self.assertEqual(revision.publication_status, "IN_REVIEW")
        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=revision
            ).exists()
        )

    def test_ordinary_initial_publish_cannot_bypass_archived_sealed_history(self):
        context = self.make_published_context(suffix="initial-history-bypass")
        OfficialFactCheck.objects.filter(pk=context["published"].pk).update(
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            archived_at=timezone.now(),
        )
        candidate = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Distinct initial candidate",
            summary="A separate candidate must not replace recorded history.",
            article_body="This is not an explicit editorial revision.",
            publication_status=OfficialFactCheck.PublicationStatus.IN_REVIEW,
            version=context["published"].version + 1,
            drafted_by=self.lead,
            submitted_for_review_at=timezone.now(),
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )

        with self.assertRaises(PublishingConflict):
            publish_fact_check(fact_check=candidate, actor=self.lead)

        candidate.refresh_from_db()
        context["published"].refresh_from_db()
        self.assertEqual(candidate.publication_status, "IN_REVIEW")
        self.assertEqual(context["published"].publication_status, "ARCHIVED")
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count(),
            1,
        )

    def test_seal_or_event_failure_rolls_back_all_replacement_effects(self):
        for target, error in (
            (
                "api.models.OfficialFactCheckPublicationSnapshot.save",
                RuntimeError("seal unavailable"),
            ),
            (
                "api.publishing_service._record_publication_event",
                RuntimeError("event unavailable"),
            ),
        ):
            context = self.make_published_context(suffix=target.rsplit(".", 1)[-1])
            revision = self.make_submitted_revision(context)
            revision.source_items.all().delete()
            source_count = revision.source_items.count()
            event_count = ModerationEvent.objects.filter(case=context["case"]).count()
            with self.subTest(target=target):
                with patch(target, side_effect=error):
                    with self.assertRaises(RuntimeError):
                        self.replace(context, revision)

                context["published"].refresh_from_db()
                revision.refresh_from_db()
                self.assertEqual(context["published"].publication_status, "PUBLISHED")
                self.assertEqual(revision.publication_status, "IN_REVIEW")
                self.assertFalse(
                    OfficialFactCheckPublicationSnapshot.objects.filter(
                        fact_check=revision
                    ).exists()
                )
                self.assertEqual(revision.source_items.count(), source_count)
                self.assertEqual(
                    ModerationEvent.objects.filter(case=context["case"]).count(),
                    event_count,
                )

    def test_post_commit_index_failure_does_not_undo_replacement(self):
        context = self.make_published_context(suffix="index-failure")
        revision = self.make_submitted_revision(context)
        with patch(
            "api.tasks.index_official_fact_check_task.delay",
            side_effect=RuntimeError("index dispatch unavailable"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                result = self.replace(context, revision)

        context["published"].refresh_from_db()
        revision.refresh_from_db()
        self.assertEqual(result["fact_check"].id, revision.id)
        self.assertEqual(context["published"].publication_status, "ARCHIVED")
        self.assertEqual(revision.publication_status, "PUBLISHED")
        self.assertTrue(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=revision
            ).exists()
        )


class EditorialRevisionPublicationPostgresTests(
    EditorialReplacementFixtures,
    TransactionTestCase,
):
    def test_competing_replacements_terminate_with_one_winner(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")

        context = self.make_published_context(suffix="concurrent")
        revision = self.make_submitted_revision(context)

        barrier = threading.Barrier(2)
        outcomes = {}
        errors = {}

        def replace(worker_name):
            outcome = None

            try:
                close_old_connections()
                actor = User.objects.get(pk=self.lead.pk)

                barrier.wait(timeout=10)

                publish_editorial_revision(
                    revision_id=revision.id,
                    predecessor_id=context["published"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_predecessor_version=context["published"].version,
                    expected_revision_version=revision.version,
                    expected_decision_revision=context["decision"].revision_number,
                )

            except PublishingConflict:
                outcome = "conflict"

            except Exception as error:
                outcome = f"error:{type(error).__name__}"
                errors[worker_name] = repr(error)

            else:
                outcome = "published"

            finally:
                try:
                    # Close only this worker's database connection.
                    connections["default"].close()
                except Exception as error:
                    outcome = f"error:{type(error).__name__}"
                    errors[worker_name] = repr(error)

                outcomes[worker_name] = outcome

        with patch("api.publishing_service._queue_fact_check_index"):
            workers = [
                threading.Thread(
                    target=replace,
                    args=(f"replacement-{index}",),
                    name=f"replacement-{index}",
                )
                for index in (1, 2)
            ]

            for worker in workers:
                worker.start()

            # One bounded deadline shared by both workers.
            deadline = time.monotonic() + 90.0

            for worker in workers:
                remaining = max(0.0, deadline - time.monotonic())
                worker.join(timeout=remaining)

            self.assertFalse(
                any(worker.is_alive() for worker in workers),
                "Replacement workers did not terminate within the "
                "shared 90-second deadline.",
            )

        self.assertFalse(errors, str(errors))
        self.assertCountEqual(
            list(outcomes.values()),
            ["published", "conflict"],
        )

        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ).count(),
            1,
        )
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=revision
            ).count(),
            1,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=context["case"],
                event_type=ModerationEvent.EventType.ARTICLE_REVISED,
            ).count(),
            1,
        )

    def test_assignment_ensure_waits_for_replacement_without_reopening_work(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")

        context = self.make_published_context(suffix="assignment-race")
        revision = self.make_submitted_revision(context)
        context["assignment"].refresh_from_db()
        completed_at = context["assignment"].completed_at
        assignment_count = VerificationAssignment.objects.filter(
            claim=context["claim"]
        ).count()
        replacement_holds_locks = threading.Event()
        allow_replacement = threading.Event()
        assignment_lock_attempted = threading.Event()
        assignment_finished = threading.Event()
        outcomes = []
        original_sync = publishing_service._sync_fact_check_sources

        def hold_source_sync(*args, **kwargs):
            replacement_holds_locks.set()
            allow_replacement.wait(timeout=10)
            return original_sync(*args, **kwargs)

        def replace():
            close_old_connections()
            actor = User.objects.get(pk=self.lead.pk)
            try:
                publish_editorial_revision(
                    revision_id=revision.id,
                    predecessor_id=context["published"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_predecessor_version=context["published"].version,
                    expected_revision_version=revision.version,
                    expected_decision_revision=context["decision"].revision_number,
                )
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"replacement-error:{type(error).__name__}")
            else:
                outcomes.append("replacement-published")
            finally:
                close_old_connections()

        def ensure_assignment():
            close_old_connections()
            claim = type(context["claim"]).objects.get(pk=context["claim"].pk)

            def observe_lock(execute, sql, params, many, execution_context):
                normalized_sql = sql.upper()
                if 'FROM "API_CLAIM"' in normalized_sql and (
                    "FOR UPDATE" in normalized_sql
                ):
                    assignment_lock_attempted.set()
                return execute(sql, params, many, execution_context)

            try:
                with connection.execute_wrapper(observe_lock):
                    assignment = ensure_verification_assignment(claim=claim)
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"assignment-error:{type(error).__name__}")
            else:
                outcomes.append(
                    "assignment-none" if assignment is None else "assignment-created"
                )
            finally:
                assignment_finished.set()
                close_old_connections()

        with patch(
            "api.publishing_service._sync_fact_check_sources",
            side_effect=hold_source_sync,
        ), patch("api.publishing_service._queue_fact_check_index"):
            replacement_worker = threading.Thread(target=replace)
            assignment_worker = threading.Thread(target=ensure_assignment)
            replacement_worker.start()
            self.assertTrue(replacement_holds_locks.wait(timeout=10))
            assignment_worker.start()
            self.assertTrue(assignment_lock_attempted.wait(timeout=10))
            self.assertFalse(assignment_finished.wait(timeout=0.25))
            allow_replacement.set()
            replacement_worker.join(timeout=10)
            assignment_worker.join(timeout=10)

        self.assertFalse(replacement_worker.is_alive())
        self.assertFalse(assignment_worker.is_alive())
        self.assertCountEqual(
            outcomes,
            ["replacement-published", "assignment-none"],
        )
        context["assignment"].refresh_from_db()
        context["published"].refresh_from_db()
        revision.refresh_from_db()
        self.assertEqual(context["published"].publication_status, "ARCHIVED")
        self.assertEqual(revision.publication_status, "PUBLISHED")
        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ).count(),
            1,
        )
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertEqual(context["assignment"].completed_at, completed_at)
        self.assertEqual(
            VerificationAssignment.objects.filter(claim=context["claim"]).count(),
            assignment_count,
        )
        self.assertFalse(
            VerificationAssignment.objects.filter(
                claim=context["claim"],
                status__in={
                    VerificationAssignment.Status.AVAILABLE,
                    VerificationAssignment.Status.ACTIVE,
                },
            ).exists()
        )
