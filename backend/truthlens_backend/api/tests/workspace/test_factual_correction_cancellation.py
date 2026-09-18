import threading
import time
from copy import deepcopy

from django.contrib.auth.models import User
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase

from api.factual_correction_proposal_service import (
    FactualCorrectionProposalConflict,
    prepare_factual_correction_proposal,
)
from api.factual_correction_service import (
    FactualCorrectionAuthorizationError,
    FactualCorrectionConflict,
    InvalidFactualCorrectionRequest,
    cancel_factual_correction,
)
from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
)
from api.publishing_service import PublishingConflict, publish_factual_correction
from api.tests.workspace.test_factual_correction_proposal import (
    FactualCorrectionProposalFixtures,
)
from api.tests.workspace.test_factual_correction_handoff import (
    FactualCorrectionHandoffFixtures,
)


class FactualCorrectionCancellationTests(
    FactualCorrectionProposalFixtures,
    TestCase,
):
    def cancel(self, context, **overrides):
        proposal = context.get("proposal")
        values = {
            "correction_request_id": context["correction_request"].id,
            "actor": self.lead,
            "organization_id": self.organization.id,
            "expected_proposal_version": proposal.version if proposal else 0,
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
            "cancellation_reason": "New information makes this correction unnecessary.",
        }
        values.update(overrides)
        return cancel_factual_correction(**values)

    def correction_context(self, *, suffix, proposal_state=None):
        context = self.make_proposal_context(
            suffix=suffix,
            review=proposal_state == "PREPARED",
        )
        if proposal_state is not None:
            context["proposal"] = self.save_proposal(context)
        if proposal_state == "PREPARED":
            self.prepare_proposal(context, context["proposal"])
            context["proposal"].refresh_from_db()
        return context

    def test_cancel_succeeds_without_or_with_draft_or_prepared_proposal(self):
        for proposal_state in (None, "DRAFT", "PREPARED"):
            with self.subTest(proposal_state=proposal_state):
                context = self.correction_context(
                    suffix=f"cancel-{proposal_state or 'none'}",
                    proposal_state=proposal_state,
                )
                proposal_id = (
                    context["proposal"].id if context.get("proposal") else None
                )
                result = self.cancel(context)

                result["request"].refresh_from_db()
                result["case"].refresh_from_db()
                self.assertEqual(
                    result["request"].status,
                    FactualCorrectionRequest.Status.CANCELLED,
                )
                self.assertEqual(
                    result["case"].status,
                    ModerationCase.Status.CANCELLED,
                )
                self.assertEqual(
                    result["case"].resolution_summary,
                    "New information makes this correction unnecessary.",
                )
                if proposal_id is not None:
                    self.assertTrue(
                        type(context["proposal"]).objects.filter(
                            pk=proposal_id
                        ).exists()
                    )

    def test_cancellation_preserves_all_factual_and_public_authority(self):
        context = self.correction_context(
            suffix="cancel-authority",
            proposal_state="PREPARED",
        )
        decision_snapshot = context["decision"].evidence_snapshot
        decision_records = deepcopy(decision_snapshot.evidence_records)
        publication_payload = deepcopy(context["seal"].payload)
        decision_count = AdjudicationDecision.objects.filter(
            claim=context["claim"]
        ).count()
        publication_count = OfficialFactCheck.objects.filter(
            claim=context["claim"]
        ).count()
        decision_snapshot_count = AdjudicationDecisionEvidenceSnapshot.objects.filter(
            decision__claim=context["claim"]
        ).count()
        publication_snapshot_count = (
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count()
        )

        self.cancel(context)

        context["claim"].refresh_from_db()
        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        decision_snapshot.refresh_from_db()
        context["seal"].refresh_from_db()
        self.assertTrue(context["decision"].is_current)
        self.assertEqual(context["claim"].final_verdict, context["decision"].verdict)
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(decision_snapshot.evidence_records, decision_records)
        self.assertEqual(context["seal"].payload, publication_payload)
        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            decision_count,
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            publication_count,
        )
        self.assertEqual(
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision__claim=context["claim"]
            ).count(),
            decision_snapshot_count,
        )
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count(),
            publication_snapshot_count,
        )

    def test_cancellation_requires_adjudicate_and_exact_concurrency(self):
        denied = self.correction_context(suffix="cancel-denied")
        with self.assertRaises(FactualCorrectionAuthorizationError):
            self.cancel(denied, actor=self.researcher)

        for field, value in (
            ("expected_predecessor_version", 999),
            ("expected_decision_revision", 999),
            ("expected_proposal_version", 1),
        ):
            with self.subTest(field=field):
                context = self.correction_context(suffix=f"cancel-stale-{field}")
                with self.assertRaises(FactualCorrectionConflict):
                    self.cancel(context, **{field: value})
                context["correction_request"].refresh_from_db()
                self.assertEqual(
                    context["correction_request"].status,
                    FactualCorrectionRequest.Status.ACTIVE,
                )

        proposal_context = self.correction_context(
            suffix="cancel-stale-existing-proposal",
            proposal_state="DRAFT",
        )
        with self.assertRaises(FactualCorrectionConflict):
            self.cancel(proposal_context, expected_proposal_version=0)

    def test_cancellation_reason_is_required_bounded_and_attributable(self):
        for invalid_reason in ("", "   ", "x" * 2001):
            context = self.correction_context(
                suffix=f"cancel-invalid-reason-{len(invalid_reason)}"
            )
            with self.assertRaises(InvalidFactualCorrectionRequest):
                self.cancel(context, cancellation_reason=invalid_reason)

        context = self.correction_context(suffix="cancel-provenance")
        result = self.cancel(context, cancellation_reason="  Duplicate report.  ")
        event = result["event"]
        self.assertEqual(event.event_type, ModerationEvent.EventType.CASE_CANCELLED)
        self.assertEqual(event.actor_id, self.lead.id)
        self.assertEqual(event.notes, "Duplicate report.")
        self.assertEqual(
            event.metadata["correction_request_id"],
            str(context["correction_request"].id),
        )
        self.assertEqual(
            event.metadata["predecessor_fact_check_id"],
            str(context["published"].id),
        )
        self.assertEqual(event.metadata["cancellation_reason"], "Duplicate report.")
        self.assertEqual(
            event.metadata["cancelled_by"],
            {"id": str(self.lead.id), "username": self.lead.username},
        )

    def test_terminal_request_cannot_cancel_prepare_or_publish(self):
        context = self.correction_context(
            suffix="cancel-terminal",
            proposal_state="PREPARED",
        )
        self.cancel(context)
        with self.assertRaises(FactualCorrectionConflict):
            self.cancel(context)
        with self.assertRaises(FactualCorrectionProposalConflict):
            prepare_factual_correction_proposal(
                correction_request_id=context["correction_request"].id,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_proposal_version=context["proposal"].version,
                expected_predecessor_version=context["published"].version,
                expected_decision_revision=context["decision"].revision_number,
            )
        with self.assertRaises(PublishingConflict):
            publish_factual_correction(
                correction_request_id=context["correction_request"].id,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_proposal_version=context["proposal"].version,
                expected_predecessor_version=context["published"].version,
                expected_decision_revision=context["decision"].revision_number,
            )

    def test_new_request_can_be_created_after_cancellation(self):
        context = self.correction_context(suffix="cancel-rerequest")
        first = context["correction_request"]
        self.cancel(context)

        second = self.request_correction(
            context,
            correction_reason="A separate later report requires fresh review.",
        )["request"]

        first.refresh_from_db()
        self.assertEqual(first.status, FactualCorrectionRequest.Status.CANCELLED)
        self.assertEqual(second.status, FactualCorrectionRequest.Status.ACTIVE)
        self.assertNotEqual(first.id, second.id)


class FactualCorrectionPublishCancelRaceTests(
    FactualCorrectionHandoffFixtures,
    TransactionTestCase,
):
    reset_sequences = True

    def test_publish_and_cancel_have_exactly_one_terminal_winner(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")
        context = self.make_prepared_context(suffix="publish-cancel-race")
        barrier = threading.Barrier(2)
        outcomes = {}
        errors = {}

        def publish():
            try:
                close_old_connections()
                actor = User.objects.get(pk=self.publisher.pk)
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
                outcomes["publish"] = "conflict"
            except Exception as error:  # pragma: no cover - asserted below
                errors["publish"] = repr(error)
            else:
                outcomes["publish"] = "completed"
            finally:
                connections["default"].close()

        def cancel():
            try:
                close_old_connections()
                actor = User.objects.get(pk=self.lead.pk)
                barrier.wait(timeout=10)
                cancel_factual_correction(
                    correction_request_id=context["correction_request"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_proposal_version=context["prepared_proposal"].version,
                    expected_predecessor_version=context["published"].version,
                    expected_decision_revision=context["decision"].revision_number,
                    cancellation_reason="A concurrent cancellation won the lock.",
                )
            except FactualCorrectionConflict:
                outcomes["cancel"] = "conflict"
            except Exception as error:  # pragma: no cover - asserted below
                errors["cancel"] = repr(error)
            else:
                outcomes["cancel"] = "cancelled"
            finally:
                connections["default"].close()

        workers = [
            threading.Thread(target=publish, name="correction-publish"),
            threading.Thread(target=cancel, name="correction-cancel"),
        ]
        for worker in workers:
            worker.start()
        deadline = time.monotonic() + 90.0
        for worker in workers:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))

        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertFalse(errors, str(errors))
        self.assertEqual(list(outcomes.values()).count("conflict"), 1)
        self.assertEqual(
            len({"completed", "cancelled"}.intersection(outcomes.values())),
            1,
        )

        request = FactualCorrectionRequest.objects.get(
            pk=context["correction_request"].id
        )
        correction_case = ModerationCase.objects.get(
            pk=context["correction_case"].id
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ).count(),
            1,
        )
        self.assertEqual(
            AdjudicationDecision.objects.filter(
                claim=context["claim"],
                is_current=True,
            ).count(),
            1,
        )
        if request.status == FactualCorrectionRequest.Status.COMPLETED:
            self.assertEqual(correction_case.status, ModerationCase.Status.RESOLVED)
        else:
            self.assertEqual(request.status, FactualCorrectionRequest.Status.CANCELLED)
            self.assertEqual(correction_case.status, ModerationCase.Status.CANCELLED)
