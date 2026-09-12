from copy import deepcopy
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.db import IntegrityError, transaction
from django.utils import timezone

from api import publishing_service as publishing_module
from api.models import (
    EvidenceSubmission,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OrganizationMembership,
    VerificationAssignment,
)
from api.publishing_service import (
    InvalidFactCheckContent,
    PublishingAuthorizationError,
    PublishingConflict,
    create_editorial_revision_draft,
    create_fact_check_draft,
    publish_fact_check,
    submit_fact_check_for_review,
    update_fact_check_draft,
)
from api.tests.adjudication.test_adjudication_transaction_contract import (
    AdjudicationContractFixtures,
)


class EditorialRevisionDraftTests(AdjudicationContractFixtures, TestCase):
    def make_published_context(
        self,
        *,
        source_urls=None,
        evidence_statuses=None,
        suffix="predecessor",
    ):
        context = self.make_context(
            evidence_statuses=evidence_statuses
            or [EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        context["decision"] = self.issue(context)["decision"]
        draft = create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            headline=f"Published headline {suffix}",
            summary=f"Published summary {suffix}.",
            article_body=f"Published analysis {suffix}.",
            source_urls=source_urls,
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

    def create_revision(self, context, **overrides):
        values = {
            "predecessor_id": context["published"].id,
            "actor": self.lead,
            "organization_id": self.organization.id,
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
            "revision_reason": "Improve editorial clarity and source context.",
        }
        values.update(overrides)
        return create_editorial_revision_draft(**values)

    def test_revision_records_explicit_metadata_and_uses_sealed_content(self):
        context = self.make_published_context(suffix="sealed-content")
        sealed_payload = deepcopy(context["seal"].payload)
        self.assertEqual(
            context["published"].revision_kind,
            OfficialFactCheck.RevisionKind.INITIAL,
        )

        revision = self.create_revision(context)

        self.assertEqual(
            revision.revision_kind,
            OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
        )
        self.assertEqual(revision.supersedes_id, context["published"].id)
        self.assertEqual(
            revision.revision_reason,
            "Improve editorial clarity and source context.",
        )
        self.assertEqual(revision.revision_requested_by, self.lead)
        self.assertIsNotNone(revision.revision_requested_at)
        self.assertEqual(revision.headline, sealed_payload["headline"])
        self.assertEqual(revision.summary, sealed_payload["summary"])
        self.assertEqual(revision.article_body, sealed_payload["article_body"])
        self.assertEqual(revision.canonical_claim, context["decision"].canonical_claim)
        self.assertEqual(revision.verdict, context["decision"].verdict)
        self.assertEqual(revision.version, context["published"].version + 1)
        context["published"].refresh_from_db()
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(context["seal"].payload, sealed_payload)

    def test_reason_and_transport_preconditions_are_strict(self):
        for invalid_reason in (None, "", "   ", 7):
            context = self.make_published_context(suffix=str(invalid_reason))
            with self.subTest(reason=invalid_reason):
                with self.assertRaises(InvalidFactCheckContent):
                    self.create_revision(context, revision_reason=invalid_reason)

        context = self.make_published_context(suffix="identities")
        for field, invalid_value in (
            ("predecessor_id", True),
            ("predecessor_id", "not-a-uuid"),
            ("organization_id", False),
            ("expected_predecessor_version", True),
            ("expected_decision_revision", 0),
        ):
            with self.subTest(field=field):
                with self.assertRaises(InvalidFactCheckContent):
                    self.create_revision(context, **{field: invalid_value})

    def test_stale_versions_and_database_identities_fail_closed(self):
        predecessor_stale = self.make_published_context(suffix="stale-predecessor")
        with self.assertRaises(PublishingConflict):
            self.create_revision(
                predecessor_stale,
                expected_predecessor_version=(
                    predecessor_stale["published"].version + 1
                ),
            )

        decision_stale = self.make_published_context(suffix="stale-decision")
        with self.assertRaises(PublishingConflict):
            self.create_revision(
                decision_stale,
                expected_decision_revision=(
                    decision_stale["decision"].revision_number + 1
                ),
            )

        cross_claim = self.make_published_context(suffix="cross-claim")
        other = self.make_published_context(suffix="other-claim")
        OfficialFactCheck.objects.filter(pk=cross_claim["published"].pk).update(
            adjudication_decision=other["decision"]
        )
        with self.assertRaises(PublishingConflict):
            self.create_revision(cross_claim)
        self.assertFalse(
            OfficialFactCheck.objects.filter(
                supersedes=cross_claim["published"]
            ).exists()
        )

    def test_organization_scope_and_current_capability_are_rechecked(self):
        wrong_organization = self.make_published_context(suffix="wrong-org")
        with self.assertRaises(PublishingAuthorizationError):
            self.create_revision(
                wrong_organization,
                organization_id=self.other_organization.id,
            )
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        with self.assertRaises(PublishingConflict):
            self.create_revision(
                wrong_organization,
                organization_id=self.other_organization.id,
            )

        revoked = self.make_published_context(suffix="revoked")
        OrganizationMembership.objects.filter(
            organization=self.organization,
            user=self.lead,
        ).update(status=OrganizationMembership.Status.SUSPENDED)
        with self.assertRaises(PublishingAuthorizationError):
            self.create_revision(revoked)
        self.assertFalse(
            OfficialFactCheck.objects.filter(supersedes=revoked["published"]).exists()
        )

    def test_missing_historical_seal_fails_without_backfill(self):
        context = self.make_published_context(suffix="missing-seal")
        OfficialFactCheckPublicationSnapshot.objects.filter(
            pk=context["seal"].pk
        ).delete()

        with self.assertRaises(PublishingConflict):
            self.create_revision(context)

        self.assertFalse(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check=context["published"]
            ).exists()
        )
        self.assertFalse(
            OfficialFactCheck.objects.filter(supersedes=context["published"]).exists()
        )

    def test_completed_assignment_stays_complete_and_open_work_conflicts(self):
        completed = self.make_published_context(suffix="completed-assignment")
        revision = self.create_revision(completed)
        completed["assignment"].refresh_from_db()
        self.assertEqual(
            completed["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertEqual(
            VerificationAssignment.objects.filter(claim=completed["claim"]).count(),
            1,
        )
        self.assertEqual(revision.drafted_by, self.lead)

        open_work = self.make_published_context(suffix="open-assignment")
        VerificationAssignment.objects.create(
            claim=open_work["claim"],
            organization=self.organization,
            claimed_by=self.lead,
            status=VerificationAssignment.Status.ACTIVE,
        )
        with self.assertRaises(PublishingConflict):
            self.create_revision(open_work)

    def test_version_allocation_and_duplicate_active_successor_protection(self):
        context = self.make_published_context(suffix="versions")
        OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Abandoned historical draft",
            summary="Historical draft summary.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=7,
        )
        revision = self.create_revision(context)
        self.assertEqual(revision.version, 8)

        with self.assertRaises(PublishingConflict):
            self.create_revision(context)
        self.assertEqual(
            OfficialFactCheck.objects.filter(
                supersedes=context["published"],
                publication_status__in=(
                    OfficialFactCheck.PublicationStatus.DRAFT,
                    OfficialFactCheck.PublicationStatus.IN_REVIEW,
                ),
            ).count(),
            1,
        )

        revision.publication_status = OfficialFactCheck.PublicationStatus.ARCHIVED
        revision.save(update_fields=["publication_status", "updated_at"])
        later_attempt = self.create_revision(context)
        self.assertEqual(later_attempt.version, 9)

    def test_source_inheritance_uses_new_rows_and_lineage_identities(self):
        editorial_url = "https://example.com/editorially-selected"
        context = self.make_published_context(
            source_urls=[editorial_url],
            suffix="source-inheritance",
        )
        predecessor_source_ids = set(
            context["published"].source_items.values_list("id", flat=True)
        )
        predecessor_link_ids = set(
            context["published"].source_items.values_list(
                "evidence_links__id", flat=True
            )
        )
        predecessor_link_ids.discard(None)

        revision = self.create_revision(context)
        revision_sources = revision.source_items.order_by("created_at", "id")
        revision_link_ids = set(
            revision_sources.values_list("evidence_links__id", flat=True)
        )
        revision_link_ids.discard(None)
        self.assertTrue(
            revision_sources.filter(
                url=editorial_url,
                is_editorially_selected=True,
            ).exists()
        )
        self.assertTrue(
            predecessor_source_ids.isdisjoint(
                set(revision_sources.values_list("id", flat=True))
            )
        )
        self.assertTrue(predecessor_link_ids.isdisjoint(revision_link_ids))
        self.assertEqual(
            set(
                context["published"].source_items.values_list(
                    "evidence_links__captured_evidence_id", flat=True
                )
            ),
            set(
                revision_sources.values_list(
                    "evidence_links__captured_evidence_id", flat=True
                )
            ),
        )

    def test_unknown_editorial_origin_is_not_inherited(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.REJECTED]
        )
        context["decision"] = self.issue(context)["decision"]
        draft = create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            headline="Unknown-origin predecessor",
            summary="Unknown-origin summary.",
            article_body="Unknown-origin analysis.",
            source_urls=["https://example.com/legacy-unknown-selection"],
        )
        draft.source_items.update(is_editorially_selected=None)
        submitted = submit_fact_check_for_review(
            fact_check=draft,
            actor=self.lead,
        )
        context["published"] = publish_fact_check(
            fact_check=submitted,
            actor=self.lead,
        )["fact_check"]
        context["seal"] = context["published"].publication_snapshot

        revision = self.create_revision(context)

        self.assertFalse(revision.source_items.exists())

    def test_invalid_inherited_selection_fails_closed(self):
        context = self.make_published_context(
            source_urls=["https://example.com/inherited-source"],
            suffix="invalid-inheritance",
        )
        payload = deepcopy(context["seal"].payload)
        inherited = next(
            source
            for source in payload["sources"]
            if source["is_editorially_selected"] is True
        )
        inherited["url"] = "javascript:invalid"
        OfficialFactCheckPublicationSnapshot.objects.filter(
            pk=context["seal"].pk
        ).update(payload=payload)

        with self.assertRaises(PublishingConflict):
            self.create_revision(context)
        self.assertFalse(
            OfficialFactCheck.objects.filter(supersedes=context["published"]).exists()
        )

    def test_explicit_sources_override_inheritance_and_draft_can_progress(self):
        inherited_url = "https://example.com/inherited-editorial"
        replacement_url = "https://example.com/replacement-editorial"
        context = self.make_published_context(
            source_urls=[inherited_url],
            suffix="editable",
        )
        revision = self.create_revision(
            context,
            source_urls=[replacement_url],
            headline="Initial revised headline",
        )
        self.assertFalse(revision.source_items.filter(url=inherited_url).exists())
        self.assertTrue(revision.source_items.filter(url=replacement_url).exists())

        updated = update_fact_check_draft(
            fact_check=revision,
            actor=self.lead,
            headline="Edited revision headline",
        )
        submitted = submit_fact_check_for_review(
            fact_check=updated,
            actor=self.lead,
        )
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        self.assertEqual(
            submitted.revision_kind,
            OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
        )

        with self.assertRaises(PublishingConflict):
            publish_fact_check(fact_check=submitted, actor=self.lead)
        context["published"].refresh_from_db()
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )

    def test_ordinary_creation_cannot_bypass_explicit_revision_workflow(self):
        context = self.make_published_context(suffix="ordinary-bypass")
        with self.assertRaises(PublishingConflict):
            create_fact_check_draft(
                decision=context["decision"],
                actor=self.lead,
                headline="Improper ordinary draft",
                summary="This must use the revision workflow.",
            )

        context["published"].refresh_from_db()
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )

    def test_revision_metadata_is_immutable_and_correction_kind_is_reserved(self):
        context = self.make_published_context(suffix="immutable-metadata")
        revision = self.create_revision(context)
        revision.revision_reason = "A later rewritten reason."
        with self.assertRaises(ValidationError):
            revision.save(update_fields=["revision_reason", "updated_at"])

        with self.assertRaises(TypeError):
            create_editorial_revision_draft(
                predecessor_id=context["published"].id,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_predecessor_version=context["published"].version,
                expected_decision_revision=context["decision"].revision_number,
                revision_reason="Attempt correction through editorial service.",
                revision_kind=OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            )

    def test_model_rejects_incomplete_or_malformed_revision_metadata(self):
        context = self.make_published_context(suffix="model-validation")
        malformed = OfficialFactCheck(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Malformed revision",
            summary="Malformed revision summary.",
            publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            version=context["published"].version + 1,
            supersedes=context["published"],
            revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            revision_reason="",
            revision_requested_at=None,
        )
        with self.assertRaises(ValidationError):
            malformed.full_clean(
                validate_unique=False,
                validate_constraints=False,
            )

        initial = OfficialFactCheck(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Malformed initial",
            summary="Malformed initial summary.",
            publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            version=context["published"].version + 1,
            supersedes=context["published"],
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        with self.assertRaises(ValidationError):
            initial.full_clean(
                validate_unique=False,
                validate_constraints=False,
            )

    def test_source_initialization_failure_rolls_back_every_partial_row(self):
        context = self.make_published_context(suffix="rollback")
        event_count = ModerationEvent.objects.filter(case=context["case"]).count()
        fact_check_count = OfficialFactCheck.objects.filter(
            claim=context["claim"]
        ).count()

        original_sync = publishing_module._sync_fact_check_sources

        def fail_after_source_initialization(*args, **kwargs):
            original_sync(*args, **kwargs)
            raise RuntimeError("source initialization failed")

        with patch(
            "api.publishing_service._sync_fact_check_sources",
            side_effect=fail_after_source_initialization,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "source initialization failed",
            ):
                self.create_revision(context)

        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            fact_check_count,
        )
        self.assertFalse(
            OfficialFactCheck.objects.filter(supersedes=context["published"]).exists()
        )
        self.assertEqual(
            ModerationEvent.objects.filter(case=context["case"]).count(),
            event_count,
        )

    def test_historically_published_successor_cannot_branch_after_archival(self):
        context = self.make_published_context(suffix="historical-successor")
        revision = self.create_revision(context)

        # Simulate historical publication followed by archival.
        # This is test-only setup; B2 has not implemented replacement yet.
        OfficialFactCheck.objects.filter(pk=revision.pk).update(
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            published_at=timezone.now(),
        )
        revision.refresh_from_db()

        # The service must reject another successor from the same predecessor.
        with self.assertRaises(PublishingConflict):
            self.create_revision(context)

        # The database must independently reserve the historical relationship.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OfficialFactCheck.objects.create(
                    claim=context["claim"],
                    adjudication_decision=context["decision"],
                    organization=self.organization,
                    canonical_claim=context["decision"].canonical_claim,
                    verdict=context["decision"].verdict,
                    headline="Improper second successor",
                    summary="This must not create a second branch.",
                    article_body="Regression test.",
                    publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
                    version=revision.version + 1,
                    drafted_by=self.lead,
                    supersedes=context["published"],
                    revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
                    revision_reason="Attempt another historical branch.",
                    revision_requested_by=self.lead,
                    revision_requested_at=timezone.now(),
                )
