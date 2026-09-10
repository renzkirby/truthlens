import threading
import time
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from api import publishing_service
from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OfficialFactCheckSource,
    OfficialFactCheckSourceEvidenceLink,
    Organization,
    OrganizationMembership,
    VerificationAssignment,
    VerificationRun,
)
from api.publishing_service import (
    InvalidFactCheckContent,
    PublishingAuthorizationError,
    PublishingConflict,
    create_editorial_revision_draft,
    publish_editorial_revision,
    publish_factual_correction,
    submit_fact_check_for_review,
)
from api.publication_snapshot_schema import FACTUAL_CORRECTION_SCHEMA_VERSION
from api.tests.workspace.test_factual_correction_publication_history import (
    FactualCorrectionPublicationHistoryFixtures,
)
from api.verification_assignment_service import ensure_verification_assignment


class FactualCorrectionHandoffFixtures(FactualCorrectionPublicationHistoryFixtures):
    def setUp(self):
        super().setUp()
        self.publisher = User.objects.create_user(
            username="correction-handoff-publisher",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.publisher,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

    def handoff(self, context, **overrides):
        values = {
            "correction_request_id": context["correction_request"].id,
            "actor": self.publisher,
            "organization_id": self.organization.id,
            "expected_proposal_version": context["prepared_proposal"].version,
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
        }
        values.update(overrides)
        return publish_factual_correction(**values)

    def assert_handoff_rolled_back(self, context, before):
        context["claim"].refresh_from_db()
        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        context["correction_request"].refresh_from_db()
        context["correction_case"].refresh_from_db()
        self.assertEqual(context["claim"].final_verdict, before["verdict"])
        self.assertTrue(context["decision"].is_current)
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(
            context["correction_request"].status,
            FactualCorrectionRequest.Status.ACTIVE,
        )
        self.assertNotEqual(
            context["correction_case"].status,
            ModerationCase.Status.RESOLVED,
        )
        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            before["decisions"],
        )
        self.assertEqual(
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision__claim=context["claim"]
            ).count(),
            before["decision_snapshots"],
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            before["fact_checks"],
        )
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count(),
            before["publication_snapshots"],
        )
        self.assertFalse(
            ModerationEvent.objects.filter(
                case=context["correction_case"],
                event_type__in={
                    ModerationEvent.EventType.VERDICT_REVISED,
                    ModerationEvent.EventType.ARTICLE_REVISED,
                },
            ).exists()
        )

    def authority_counts(self, context):
        claim = type(context["claim"]).objects.get(pk=context["claim"].pk)

        return {
            "verdict": claim.final_verdict,
            "decisions": AdjudicationDecision.objects.filter(claim=claim).count(),
            "decision_snapshots": (
                AdjudicationDecisionEvidenceSnapshot.objects.filter(
                    decision__claim=claim
                ).count()
            ),
            "fact_checks": OfficialFactCheck.objects.filter(claim=claim).count(),
            "publication_snapshots": (
                OfficialFactCheckPublicationSnapshot.objects.filter(
                    fact_check__claim=claim
                ).count()
            ),
        }


class FactualCorrectionHandoffTests(FactualCorrectionHandoffFixtures, TestCase):
    def test_handoff_preserves_distinct_approval_publication_and_source_provenance(
        self,
    ):
        context = self.make_prepared_context(suffix="handoff-success")
        predecessor = context["published"]
        predecessor_decision = context["decision"]
        predecessor_snapshot = predecessor_decision.evidence_snapshot
        predecessor_seal = context["seal"]
        original_decision_records = deepcopy(predecessor_snapshot.evidence_records)
        original_seal_payload = deepcopy(predecessor_seal.payload)
        abandoned_version = predecessor.version + 4
        OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=predecessor_decision,
            organization=self.organization,
            canonical_claim=predecessor_decision.canonical_claim,
            verdict=predecessor_decision.verdict,
            headline="Abandoned draft",
            summary="This abandoned row consumed a claim-wide version.",
            article_body="It must not become the correction predecessor.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=abandoned_version,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )

        with patch("api.publishing_service._queue_fact_check_index") as queue_index:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                result = self.handoff(context)

        decision = result["decision"]
        decision_snapshot = result["decision_snapshot"]
        successor = result["fact_check"]
        seal = result["publication_snapshot"]
        self.assertEqual(len(callbacks), 1)
        queue_index.assert_called_once_with(successor.id)
        predecessor.refresh_from_db()
        predecessor_decision.refresh_from_db()
        context["claim"].refresh_from_db()
        context["thread"].refresh_from_db()
        context["correction_request"].refresh_from_db()
        context["correction_case"].refresh_from_db()

        self.assertNotEqual(self.lead.id, self.publisher.id)
        self.assertEqual(decision.decided_by_id, self.lead.id)
        self.assertEqual(decision.decided_at, context["prepared_proposal"].prepared_at)
        self.assertEqual(successor.reviewed_by_id, self.lead.id)
        self.assertEqual(successor.published_by_id, self.publisher.id)
        self.assertIsNone(successor.drafted_by_id)
        self.assertIsNone(successor.submitted_for_review_at)
        self.assertEqual(
            decision.decision_source, AdjudicationDecision.DecisionSource.HUMAN_REVIEW
        )
        self.assertEqual(decision.supersedes_id, predecessor_decision.id)
        self.assertEqual(
            decision.revision_number, predecessor_decision.revision_number + 1
        )
        self.assertEqual(successor.version, abandoned_version + 1)
        self.assertEqual(successor.supersedes_id, predecessor.id)
        self.assertEqual(
            successor.revision_kind, OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION
        )
        self.assertEqual(successor.published_at, predecessor.archived_at)
        self.assertEqual(seal.captured_at, successor.published_at)
        self.assertEqual(seal.schema_version, FACTUAL_CORRECTION_SCHEMA_VERSION)
        self.assertEqual(
            decision_snapshot.evidence_records,
            [
                item["record"]
                for item in context["prepared_proposal"].prepared_payload[
                    "evidence_basis"
                ]["items"]
            ],
        )
        self.assertEqual(
            predecessor_snapshot.evidence_records, original_decision_records
        )
        self.assertEqual(predecessor_seal.payload, original_seal_payload)
        self.assertFalse(predecessor_decision.is_current)
        self.assertTrue(decision.is_current)
        self.assertEqual(context["claim"].final_verdict, decision.verdict)
        self.assertEqual(context["thread"].moderator_verdict, decision.verdict)
        self.assertEqual(context["thread"].moderated_by_id, self.lead.id)
        self.assertEqual(
            context["correction_request"].status,
            FactualCorrectionRequest.Status.COMPLETED,
        )
        self.assertEqual(
            context["correction_case"].status, ModerationCase.Status.RESOLVED
        )

        sources = list(successor.source_items.order_by("created_at", "id"))
        self.assertEqual(
            [source.url for source in sources], context["prepared_proposal"].source_urls
        )
        self.assertTrue(all(source.is_editorially_selected for source in sources))
        self.assertTrue(all(source.added_by_id is None for source in sources))
        links = list(
            OfficialFactCheckSourceEvidenceLink.objects.filter(source__in=sources)
        )
        self.assertTrue(links)
        self.assertTrue(all(link.snapshot_id == decision_snapshot.id for link in links))
        self.assertTrue(
            all(link.snapshot_id != predecessor_snapshot.id for link in links)
        )
        self.assertEqual(
            {str(link.captured_evidence_id) for link in links},
            {
                lineage["evidence_id"]
                for source in context["prepared_proposal"].prepared_payload["sources"]
                for lineage in source["evidence"]
            },
        )
        self.assertEqual(
            self.validate_history({**context, "published": successor}),
            seal,
        )

        for event_type in (
            ModerationEvent.EventType.VERDICT_REVISED,
            ModerationEvent.EventType.ARTICLE_REVISED,
        ):
            event = ModerationEvent.objects.get(
                case=context["correction_case"],
                event_type=event_type,
            )
            self.assertEqual(event.actor_id, self.publisher.id)
            self.assertEqual(
                event.metadata["old_decision_id"], str(predecessor_decision.id)
            )
            self.assertEqual(event.metadata["new_decision_id"], str(decision.id))
            self.assertEqual(event.metadata["old_fact_check_id"], str(predecessor.id))
            self.assertEqual(event.metadata["new_fact_check_id"], str(successor.id))
            self.assertEqual(
                event.metadata["old_decision_evidence_snapshot_id"],
                str(predecessor_snapshot.id),
            )
            self.assertEqual(
                event.metadata["new_decision_evidence_snapshot_id"],
                str(decision_snapshot.id),
            )
            self.assertEqual(
                event.metadata["predecessor_publication_snapshot_id"],
                str(predecessor_seal.id),
            )
            self.assertEqual(
                event.metadata["successor_publication_snapshot_id"], str(seal.id)
            )
            self.assertEqual(
                event.metadata["approver_snapshot"]["id"], str(self.lead.id)
            )
            self.assertEqual(
                event.metadata["publisher_snapshot"]["id"], str(self.publisher.id)
            )
            self.assertEqual(
                event.metadata["trust_dispatch_status"],
                "NOT_SCHEDULED_POLICY_UNDEFINED",
            )

    def test_strict_inputs_capability_scope_versions_and_terminal_states_fail_closed(
        self,
    ):
        context = self.make_prepared_context(suffix="handoff-guards")
        for overrides in (
            {"correction_request_id": True},
            {"organization_id": True},
            {"expected_proposal_version": True},
            {"expected_predecessor_version": 0},
            {"expected_decision_revision": 0},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(
                InvalidFactCheckContent
            ):
                self.handoff(context, **overrides)

        for actor in (self.moderator, self.researcher):
            with self.subTest(actor=actor.username), self.assertRaises(
                PublishingAuthorizationError
            ):
                self.handoff(context, actor=actor)
        platform_moderator = User.objects.create_user(
            username="platform-moderator-without-partner-authority",
            password="test-password",
            is_staff=True,
        )
        with self.assertRaises(PublishingAuthorizationError):
            self.handoff(context, actor=platform_moderator)
        with self.assertRaises(PublishingConflict):
            self.handoff(context, organization_id=self.other_organization.id)
        for field in (
            "expected_proposal_version",
            "expected_predecessor_version",
            "expected_decision_revision",
        ):
            with self.subTest(field=field), self.assertRaises(PublishingConflict):
                current = {
                    "expected_proposal_version": context["prepared_proposal"].version,
                    "expected_predecessor_version": context["published"].version,
                    "expected_decision_revision": context["decision"].revision_number,
                }[field]
                self.handoff(context, **{field: current + 1})

        cancelled = self.make_prepared_context(suffix="cancelled-handoff")
        cancelled["correction_request"].status = (
            FactualCorrectionRequest.Status.CANCELLED
        )
        cancelled["correction_request"].save(update_fields=["status", "updated_at"])
        ModerationCase.objects.filter(pk=cancelled["correction_case"].id).update(
            status=ModerationCase.Status.CANCELLED
        )
        with self.assertRaises(PublishingConflict):
            self.handoff(cancelled)

        result = self.handoff(context)
        counts = self.authority_counts({**context, "claim": result["decision"].claim})
        with self.assertRaises(PublishingConflict):
            self.handoff(context)
        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            counts["decisions"],
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            counts["fact_checks"],
        )
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count(),
            counts["publication_snapshots"],
        )
        for event_type in (
            ModerationEvent.EventType.VERDICT_REVISED,
            ModerationEvent.EventType.ARTICLE_REVISED,
        ):
            self.assertEqual(
                ModerationEvent.objects.filter(
                    case=context["correction_case"],
                    event_type=event_type,
                ).count(),
                1,
            )

    def test_competing_assignment_draft_evidence_case_and_successor_are_rejected(self):
        blockers = ("assignment", "draft", "evidence-case", "successor")
        for blocker in blockers:
            with self.subTest(blocker=blocker):
                context = self.make_prepared_context(suffix=f"block-{blocker}")
                if blocker == "assignment":
                    VerificationAssignment.objects.create(
                        claim=context["claim"],
                        organization=self.organization,
                        claimed_by=self.publisher,
                        status=VerificationAssignment.Status.ACTIVE,
                    )
                elif blocker == "draft":
                    self.make_reserved_draft(context)
                elif blocker == "evidence-case":
                    ModerationCase.objects.create(
                        case_type=ModerationCase.CaseType.EVIDENCE,
                        evidence_submission=context["evidence"][0],
                        organization=self.organization,
                        source=ModerationCase.Source.EVIDENCE_SUBMISSION,
                        status=ModerationCase.Status.OPEN,
                    )
                else:
                    AdjudicationDecision.objects.create(
                        claim=context["claim"],
                        moderation_case=context["correction_case"],
                        verdict=context["prepared_proposal"].verdict,
                        canonical_claim=context["prepared_proposal"].canonical_claim,
                        rationale=context["prepared_proposal"].rationale,
                        decided_by=self.lead,
                        organization=self.organization,
                        revision_number=context["decision"].revision_number + 1,
                        supersedes=context["decision"],
                        is_current=False,
                    )
                with self.assertRaises(PublishingConflict):
                    self.handoff(context)

    def test_publisher_membership_and_partner_status_are_rechecked_under_lock(self):
        suspended = self.make_prepared_context(suffix="suspended-publisher")
        membership = OrganizationMembership.objects.get(
            organization=self.organization,
            user=self.publisher,
        )
        membership.status = OrganizationMembership.Status.SUSPENDED
        membership.save(update_fields=["status"])
        with self.assertRaises(PublishingAuthorizationError):
            self.handoff(suspended)

        membership.status = OrganizationMembership.Status.ACTIVE
        membership.save(update_fields=["status"])
        inactive_partner = self.make_prepared_context(suffix="inactive-partner")
        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED
        self.organization.save(update_fields=["partner_status", "updated_at"])
        with self.assertRaises(PublishingAuthorizationError):
            self.handoff(inactive_partner)

    def test_tampered_prepared_payload_or_changed_evidence_is_rejected(self):
        tampered = self.make_prepared_context(suffix="tampered-payload")
        payload = deepcopy(tampered["prepared_proposal"].prepared_payload)
        payload["article"]["summary"] = "A post-approval replacement summary."
        type(tampered["prepared_proposal"]).objects.filter(
            pk=tampered["prepared_proposal"].id
        ).update(prepared_payload=payload)
        with self.assertRaises(PublishingConflict):
            self.handoff(tampered)

        stale = self.make_prepared_context(suffix="stale-evidence")
        evidence = stale["evidence"][0]
        type(evidence).objects.filter(pk=evidence.id).update(
            moderator_notes="Evidence changed after approval."
        )
        with self.assertRaises(PublishingConflict):
            self.handoff(stale)

    def test_optional_completed_verification_run_is_preserved_exactly(self):
        context = self.make_proposal_context(suffix="handoff-verification-run")
        run = VerificationRun.objects.create(
            claim=context["claim"],
            triggered_by=self.author,
            status=VerificationRun.Status.COMPLETED,
            pipeline_version="correction-handoff-v1",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        proposal = self.save_proposal(context, verification_run_id=run.id)
        context["prepared_proposal"] = self.prepare_proposal(
            context,
            proposal,
        )["proposal"]

        result = self.handoff(context)

        self.assertEqual(result["decision"].verification_run_id, run.id)
        self.assertEqual(
            result["publication_snapshot"].payload["correction"][
                "prepared_proposal_id"
            ],
            str(proposal.id),
        )

    def test_deleted_approver_is_not_replaced_by_publisher_or_fabricated_author(self):
        context = self.make_prepared_context(suffix="deleted-approver")
        approver_snapshot = deepcopy(context["prepared_proposal"].prepared_by_snapshot)
        User.objects.filter(pk=self.lead.id).delete()
        context["prepared_proposal"].refresh_from_db()
        context["correction_request"].refresh_from_db()

        result = self.handoff(context)

        self.assertIsNone(result["decision"].decided_by_id)
        self.assertIsNone(result["fact_check"].reviewed_by_id)
        self.assertIsNone(result["fact_check"].drafted_by_id)
        self.assertIsNone(result["fact_check"].revision_requested_by_id)
        self.assertEqual(
            result["publication_snapshot"].payload["correction"]["approved_by"],
            approver_snapshot,
        )
        self.assertNotEqual(
            result["publication_snapshot"].payload["correction"]["approved_by"]["id"],
            str(self.publisher.id),
        )
        self.assertTrue(
            all(
                source.added_by_id is None
                for source in result["fact_check"].source_items.all()
            )
        )

    def test_expected_uniqueness_races_translate_but_unrelated_integrity_propagates(
        self,
    ):
        expected = self.make_prepared_context(suffix="expected-integrity")
        before = self.authority_counts(expected)
        with patch(
            "api.publishing_service.AdjudicationDecision.objects.create",
            side_effect=IntegrityError("uniq_adjudication_claim_revision"),
        ), self.assertRaises(PublishingConflict):
            self.handoff(expected)
        self.assert_handoff_rolled_back(expected, before)

        snapshot = self.make_prepared_context(suffix="snapshot-integrity")
        before = self.authority_counts(snapshot)
        with patch(
            "api.publishing_service.AdjudicationDecisionEvidenceSnapshot.objects.create",
            side_effect=IntegrityError(
                "api_adjudicationdecisionevidencesnapshot_decision_id_key"
            ),
        ), self.assertRaises(IntegrityError):
            self.handoff(snapshot)
        self.assert_handoff_rolled_back(snapshot, before)

        lineage = self.make_prepared_context(suffix="lineage-integrity")
        before = self.authority_counts(lineage)
        with patch(
            "api.publishing_service.OfficialFactCheckSourceEvidenceLink.objects.create",
            side_effect=IntegrityError("unique_source_captured_evidence"),
        ), self.assertRaises(IntegrityError):
            self.handoff(lineage)
        self.assert_handoff_rolled_back(lineage, before)

        unrelated = self.make_prepared_context(suffix="unrelated-integrity")
        before = self.authority_counts(unrelated)
        with patch(
            "api.publishing_service.AdjudicationDecision.objects.create",
            side_effect=IntegrityError("unrelated persistence failure"),
        ), self.assertRaises(IntegrityError):
            self.handoff(unrelated)
        self.assert_handoff_rolled_back(unrelated, before)

    def test_failures_at_every_handoff_stage_roll_back_public_authority(self):
        stages = (
            "decision",
            "snapshot",
            "article",
            "source",
            "cache",
            "seal",
            "event",
            "case-resolution",
            "request-completion",
        )
        for stage in stages:
            with self.subTest(stage=stage):
                context = self.make_prepared_context(suffix=f"rollback-{stage}")
                before = self.authority_counts(context)
                patches = []
                if stage == "decision":
                    patches.append(
                        patch(
                            "api.publishing_service.AdjudicationDecision.objects.create",
                            side_effect=RuntimeError(stage),
                        )
                    )
                elif stage == "snapshot":
                    patches.append(
                        patch(
                            "api.publishing_service.AdjudicationDecisionEvidenceSnapshot.objects.create",
                            side_effect=RuntimeError(stage),
                        )
                    )
                elif stage == "article":
                    original = OfficialFactCheck.save

                    def fail_new_article(instance, *args, **kwargs):
                        if instance._state.adding:
                            raise RuntimeError(stage)
                        return original(instance, *args, **kwargs)

                    patches.append(
                        patch(
                            "api.publishing_service.OfficialFactCheck.save",
                            new=fail_new_article,
                        )
                    )
                elif stage == "source":
                    patches.append(
                        patch(
                            "api.publishing_service.OfficialFactCheckSource.save",
                            side_effect=RuntimeError(stage),
                        )
                    )
                elif stage == "cache":
                    patches.append(
                        patch(
                            "api.publishing_service._sync_sources_cache",
                            side_effect=RuntimeError(stage),
                        )
                    )
                elif stage == "seal":
                    patches.append(
                        patch(
                            "api.publishing_service.OfficialFactCheckPublicationSnapshot.objects.create",
                            side_effect=RuntimeError(stage),
                        )
                    )
                elif stage == "event":
                    original = ModerationEvent.objects.create

                    def fail_article_event(**kwargs):
                        if (
                            kwargs.get("event_type")
                            == ModerationEvent.EventType.ARTICLE_REVISED
                        ):
                            raise RuntimeError(stage)
                        return original(**kwargs)

                    patches.append(
                        patch(
                            "api.publishing_service.ModerationEvent.objects.create",
                            side_effect=fail_article_event,
                        )
                    )
                elif stage == "case-resolution":
                    patches.append(
                        patch(
                            "api.publishing_service._resolve_factual_correction_case",
                            side_effect=RuntimeError(stage),
                        )
                    )
                else:
                    original = FactualCorrectionRequest.save

                    def fail_completion(instance, *args, **kwargs):
                        if instance.status == FactualCorrectionRequest.Status.COMPLETED:
                            raise RuntimeError(stage)
                        return original(instance, *args, **kwargs)

                    patches.append(
                        patch(
                            "api.publishing_service.FactualCorrectionRequest.save",
                            new=fail_completion,
                        )
                    )

                with patches[0], self.assertRaises(RuntimeError):
                    self.handoff(context)
                self.assert_handoff_rolled_back(context, before)

    def test_editorial_revision_then_later_factual_correction_remain_supported(self):
        context = self.make_prepared_context(suffix="correction-one")
        first = self.handoff(context)["fact_check"]
        context.update(
            published=first,
            seal=first.publication_snapshot,
            decision=first.adjudication_decision,
        )

        editorial = create_editorial_revision_draft(
            predecessor_id=first.id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=first.version,
            expected_decision_revision=context["decision"].revision_number,
            revision_reason="Clarify the corrected article without changing verdict.",
        )
        editorial = submit_fact_check_for_review(
            fact_check=editorial,
            actor=self.lead,
        )
        editorial = publish_editorial_revision(
            revision_id=editorial.id,
            predecessor_id=first.id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=first.version,
            expected_revision_version=editorial.version,
            expected_decision_revision=context["decision"].revision_number,
        )["fact_check"]
        context.update(published=editorial, seal=editorial.publication_snapshot)

        reservation = self.request_correction(context)
        context.update(
            correction_request=reservation["request"],
            correction_case=reservation["case"],
        )
        context["correction_review"] = self.review_correction(context)
        proposal = self.save_proposal(context)
        context["prepared_proposal"] = self.prepare_proposal(
            context,
            proposal,
        )["proposal"]
        second = self.handoff(context)["fact_check"]

        self.assertEqual(second.supersedes_id, editorial.id)
        self.assertEqual(second.adjudication_decision.revision_number, 3)
        self.assertEqual(
            self.validate_history({**context, "published": second}),
            second.publication_snapshot,
        )


class FactualCorrectionHandoffPostgresTests(
    FactualCorrectionHandoffFixtures,
    TransactionTestCase,
):
    def test_competing_handoffs_terminate_with_one_winner(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")
        context = self.make_prepared_context(suffix="concurrent-handoff")
        barrier = threading.Barrier(2)
        outcomes = {}
        errors = {}

        def handoff(worker_name):
            try:
                close_old_connections()
                actor = User.objects.get(pk=self.publisher.id)
                barrier.wait(timeout=10)
                publish_factual_correction(
                    correction_request_id=context["correction_request"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_proposal_version=context["prepared_proposal"].version,
                    expected_predecessor_version=context["published"].version,
                    expected_decision_revision=context["decision"].revision_number,
                )
            except PublishingConflict:
                outcomes[worker_name] = "conflict"
            except Exception as error:  # pragma: no cover - asserted below
                outcomes[worker_name] = f"error:{type(error).__name__}"
                errors[worker_name] = repr(error)
            else:
                outcomes[worker_name] = "published"
            finally:
                try:
                    connections["default"].close()
                except Exception as error:  # pragma: no cover - asserted below
                    outcomes[worker_name] = f"error:{type(error).__name__}"
                    errors[worker_name] = repr(error)

        workers = [
            threading.Thread(target=handoff, args=(f"handoff-{index}",))
            for index in (1, 2)
        ]
        with patch("api.publishing_service._queue_fact_check_index"):
            for worker in workers:
                worker.start()
            deadline = time.monotonic() + 90.0
            for worker in workers:
                worker.join(timeout=max(0.0, deadline - time.monotonic()))

        self.assertFalse(
            any(worker.is_alive() for worker in workers),
            "Handoff workers exceeded the shared 90-second deadline.",
        )
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(list(outcomes.values()), ["published", "conflict"])
        self.assertEqual(
            AdjudicationDecision.objects.filter(
                claim=context["claim"], is_current=True
            ).count(),
            1,
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ).count(),
            1,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=context["correction_case"],
                event_type=ModerationEvent.EventType.VERDICT_REVISED,
            ).count(),
            1,
        )

    def test_handoff_serializes_against_editorial_work(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")
        context = self.make_prepared_context(suffix="ordinary-work-race")
        handoff_holds_lock = threading.Event()
        allow_handoff = threading.Event()
        ordinary_attempted = threading.Event()
        outcomes = []
        errors = []
        original_create_sources = publishing_service._create_factual_correction_sources

        def hold_handoff(*args, **kwargs):
            handoff_holds_lock.set()
            allow_handoff.wait(timeout=10)
            return original_create_sources(*args, **kwargs)

        def run_handoff():
            try:
                close_old_connections()
                actor = User.objects.get(pk=self.publisher.id)
                publish_factual_correction(
                    correction_request_id=context["correction_request"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_proposal_version=context["prepared_proposal"].version,
                    expected_predecessor_version=context["published"].version,
                    expected_decision_revision=context["decision"].revision_number,
                )
            except Exception as error:  # pragma: no cover - asserted below
                errors.append(repr(error))
            else:
                outcomes.append("handoff-published")
            finally:
                try:
                    connections["default"].close()
                except Exception as error:  # pragma: no cover - asserted below
                    errors.append(repr(error))

        def run_ordinary_work():
            try:
                close_old_connections()
                ordinary_attempted.set()
                actor = User.objects.get(pk=self.lead.id)
                try:
                    create_editorial_revision_draft(
                        predecessor_id=context["published"].id,
                        actor=actor,
                        organization_id=self.organization.id,
                        expected_predecessor_version=context["published"].version,
                        expected_decision_revision=context["decision"].revision_number,
                        revision_reason="This stale ordinary branch must lose.",
                    )
                except PublishingConflict:
                    outcomes.append("editorial-conflict")
            except Exception as error:  # pragma: no cover - asserted below
                errors.append(repr(error))
            finally:
                try:
                    connections["default"].close()
                except Exception as error:  # pragma: no cover - asserted below
                    errors.append(repr(error))

        with patch(
            "api.publishing_service._create_factual_correction_sources",
            side_effect=hold_handoff,
        ), patch("api.publishing_service._queue_fact_check_index"):
            handoff_worker = threading.Thread(target=run_handoff)
            ordinary_worker = threading.Thread(target=run_ordinary_work)
            handoff_worker.start()
            self.assertTrue(handoff_holds_lock.wait(timeout=10))
            ordinary_worker.start()
            self.assertTrue(ordinary_attempted.wait(timeout=10))
            self.assertTrue(ordinary_worker.is_alive())
            allow_handoff.set()
            deadline = time.monotonic() + 90.0
            for worker in (handoff_worker, ordinary_worker):
                worker.join(timeout=max(0.0, deadline - time.monotonic()))

        self.assertFalse(handoff_worker.is_alive())
        self.assertFalse(ordinary_worker.is_alive())
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(
            outcomes,
            ["handoff-published", "editorial-conflict"],
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ).count(),
            1,
        )

    def test_handoff_serializes_against_assignment_creation(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")
        context = self.make_prepared_context(suffix="assignment-race")
        handoff_holds_lock = threading.Event()
        allow_handoff = threading.Event()
        assignment_attempted = threading.Event()
        outcomes = []
        errors = []
        original_create_sources = publishing_service._create_factual_correction_sources

        def hold_handoff(*args, **kwargs):
            handoff_holds_lock.set()
            allow_handoff.wait(timeout=10)
            return original_create_sources(*args, **kwargs)

        def run_handoff():
            try:
                close_old_connections()
                actor = User.objects.get(pk=self.publisher.id)
                publish_factual_correction(
                    correction_request_id=context["correction_request"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_proposal_version=context["prepared_proposal"].version,
                    expected_predecessor_version=context["published"].version,
                    expected_decision_revision=context["decision"].revision_number,
                )
            except Exception as error:  # pragma: no cover - asserted below
                errors.append(repr(error))
            else:
                outcomes.append("handoff-published")
            finally:
                try:
                    connections["default"].close()
                except Exception as error:  # pragma: no cover - asserted below
                    errors.append(repr(error))

        def run_assignment():
            try:
                close_old_connections()
                claim = type(context["claim"]).objects.get(pk=context["claim"].id)
                assignment_attempted.set()
                assignment = ensure_verification_assignment(claim=claim)
                outcomes.append(
                    "assignment-none" if assignment is None else "assignment-created"
                )
            except Exception as error:  # pragma: no cover - asserted below
                errors.append(repr(error))
            finally:
                try:
                    connections["default"].close()
                except Exception as error:  # pragma: no cover - asserted below
                    errors.append(repr(error))

        with patch(
            "api.publishing_service._create_factual_correction_sources",
            side_effect=hold_handoff,
        ), patch("api.publishing_service._queue_fact_check_index"):
            handoff_worker = threading.Thread(target=run_handoff)
            assignment_worker = threading.Thread(target=run_assignment)
            handoff_worker.start()
            self.assertTrue(handoff_holds_lock.wait(timeout=10))
            assignment_worker.start()
            self.assertTrue(assignment_attempted.wait(timeout=10))
            self.assertTrue(assignment_worker.is_alive())
            allow_handoff.set()
            deadline = time.monotonic() + 90.0
            for worker in (handoff_worker, assignment_worker):
                worker.join(timeout=max(0.0, deadline - time.monotonic()))

        self.assertFalse(handoff_worker.is_alive())
        self.assertFalse(assignment_worker.is_alive())
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(
            outcomes,
            ["handoff-published", "assignment-none"],
        )
        self.assertEqual(
            AdjudicationDecision.objects.filter(
                claim=context["claim"], is_current=True
            ).count(),
            1,
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ).count(),
            1,
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
