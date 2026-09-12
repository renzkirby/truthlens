import threading
import time
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from api.factual_correction_proposal_schema import (
    FactualCorrectionProposalSchemaError,
    validate_factual_correction_proposal,
)
from api.factual_correction_proposal_service import (
    FactualCorrectionProposalAuthorizationError,
    FactualCorrectionProposalConflict,
    InvalidFactualCorrectionProposal,
    prepare_factual_correction_proposal,
    save_factual_correction_proposal,
)
from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    EvidenceSubmission,
    FactualCorrectionProposal,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OrganizationMembership,
    VerificationAssignment,
    VerificationRun,
)
from api.tests.workspace.test_factual_correction_request import (
    FactualCorrectionRequestFixtures,
)


class FactualCorrectionProposalFixtures(FactualCorrectionRequestFixtures):
    def setUp(self):
        super().setUp()
        self.researcher = User.objects.create_user(
            username="correction-proposal-researcher",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.researcher,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )

    def make_proposal_context(self, *, suffix="proposal", review=True):
        context = self.make_correction_review_context(suffix=suffix)
        if review:
            context["correction_review"] = self.review_correction(context)
        return context

    def save_proposal(self, context, **overrides):
        values = {
            "correction_request_id": context["correction_request"].id,
            "actor": self.researcher,
            "organization_id": self.organization.id,
            "expected_proposal_version": 0,
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
            "verdict": AdjudicationDecision.Verdict.FACT,
            "canonical_claim": "The corrected canonical claim is supported.",
            "rationale": "Fresh correction review supports the replacement verdict.",
            "headline": "Corrected factual finding",
            "summary": "A human-reviewed correction proposal.",
            "article_body": "Replacement analysis based on the fresh evidence review.",
            "source_urls": [
                context["evidence"][0].evidence_url,
                f"https://example.com/editorial-proposal-{context['claim'].id}",
            ],
            "verification_run_id": None,
        }
        values.update(overrides)
        return save_factual_correction_proposal(**values)

    def prepare_proposal(self, context, proposal, **overrides):
        values = {
            "correction_request_id": context["correction_request"].id,
            "actor": self.lead,
            "organization_id": self.organization.id,
            "expected_proposal_version": proposal.version,
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
        }
        values.update(overrides)
        return prepare_factual_correction_proposal(**values)


class FactualCorrectionProposalTests(FactualCorrectionProposalFixtures, TestCase):
    def test_create_and_update_use_positive_optimistic_versions(self):
        context = self.make_proposal_context(suffix="draft-version")

        proposal = self.save_proposal(context)

        self.assertEqual(proposal.status, FactualCorrectionProposal.Status.DRAFT)
        self.assertEqual(proposal.version, 1)
        self.assertEqual(proposal.correction_request, context["correction_request"])
        self.assertIsNone(proposal.prepared_payload)

        proposal = self.save_proposal(
            context,
            expected_proposal_version=1,
            headline="Updated corrected factual finding",
        )
        self.assertEqual(proposal.version, 2)
        self.assertEqual(proposal.headline, "Updated corrected factual finding")

        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(context, expected_proposal_version=1)
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(context, expected_proposal_version=0)

    def test_identifiers_versions_and_content_are_validated_strictly(self):
        context = self.make_proposal_context(suffix="invalid-input")
        invalid = (
            {"correction_request_id": True},
            {"organization_id": True},
            {"expected_proposal_version": True},
            {"expected_predecessor_version": 0},
            {"expected_decision_revision": 0},
            {"verification_run_id": True},
            {"verdict": "NOT_A_VERDICT"},
            {"canonical_claim": "  "},
            {"rationale": None},
            {"headline": "x" * 301},
            {"summary": ""},
            {"article_body": ""},
            {"source_urls": []},
            {"source_urls": ["not-a-url"]},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(
                InvalidFactualCorrectionProposal
            ):
                self.save_proposal(context, **overrides)

    def test_draft_authority_is_distinct_from_adjudication_authority(self):
        context = self.make_proposal_context(suffix="role-separation")

        proposal = self.save_proposal(context, actor=self.researcher)

        with self.assertRaises(FactualCorrectionProposalAuthorizationError):
            self.prepare_proposal(context, proposal, actor=self.researcher)
        result = self.prepare_proposal(context, proposal, actor=self.moderator)
        self.assertEqual(result["proposal"].prepared_by, self.moderator)

    def test_wrong_organization_terminal_request_and_stale_authority_fail_closed(self):
        wrong = self.make_proposal_context(suffix="wrong-organization")
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(
                wrong,
                organization_id=self.other_organization.id,
            )

        stale = self.make_proposal_context(suffix="stale-authority")
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(
                stale,
                expected_predecessor_version=stale["published"].version + 1,
            )
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(
                stale,
                expected_decision_revision=stale["decision"].revision_number + 1,
            )

        terminal = self.make_proposal_context(suffix="terminal-request")
        proposal = self.save_proposal(terminal)
        terminal["correction_request"].status = FactualCorrectionRequest.Status.CANCELLED
        terminal["correction_request"].save(update_fields=["status", "updated_at"])
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(
                terminal,
                expected_proposal_version=proposal.version,
            )
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.prepare_proposal(terminal, proposal)

    def test_verification_run_is_optional_but_must_be_completed_for_same_claim(self):
        context = self.make_proposal_context(suffix="verification-run")
        incomplete = VerificationRun.objects.create(
            claim=context["claim"],
            status=VerificationRun.Status.RUNNING,
        )
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(context, verification_run_id=incomplete.id)

        other = self.make_published_context(suffix="wrong-run-claim")
        wrong_claim_run = VerificationRun.objects.create(
            claim=other["claim"],
            status=VerificationRun.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(context, verification_run_id=wrong_claim_run.id)

        completed = VerificationRun.objects.create(
            claim=context["claim"],
            triggered_by=self.author,
            status=VerificationRun.Status.COMPLETED,
            started_at=timezone.now(),
            completed_at=timezone.now(),
            pipeline_version="proposal-context-v1",
        )
        proposal = self.save_proposal(context, verification_run_id=completed.id)
        result = self.prepare_proposal(context, proposal)
        self.assertEqual(
            result["proposal"].prepared_payload["verification_run"]["id"],
            str(completed.id),
        )

    def test_prepare_freezes_fresh_complete_evidence_and_source_provenance(self):
        context = self.make_proposal_context(suffix="prepare-success")
        proposal = self.save_proposal(context)
        original_decision_snapshot = deepcopy(
            context["decision"].evidence_snapshot.evidence_records
        )
        counts = {
            "decisions": AdjudicationDecision.objects.filter(
                claim=context["claim"]
            ).count(),
            "decision_snapshots": AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision__claim=context["claim"]
            ).count(),
            "fact_checks": OfficialFactCheck.objects.filter(
                claim=context["claim"]
            ).count(),
            "seals": OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count(),
            "assignments": VerificationAssignment.objects.filter(
                claim=context["claim"]
            ).count(),
        }

        result = self.prepare_proposal(context, proposal)
        prepared = result["proposal"]
        payload = prepared.prepared_payload

        self.assertEqual(prepared.status, FactualCorrectionProposal.Status.PREPARED)
        self.assertEqual(prepared.version, 1)
        self.assertEqual(prepared.prepared_payload_schema_version, 1)
        self.assertEqual(payload["proposal_id"], str(prepared.id))
        self.assertEqual(payload["correction_request_id"], str(context["correction_request"].id))
        self.assertEqual(payload["predecessor"]["decision_id"], str(context["decision"].id))
        self.assertEqual(payload["predecessor"]["fact_check_id"], str(context["published"].id))
        evidence_item = payload["evidence_basis"]["items"][0]
        self.assertEqual(
            evidence_item["review_event_id"],
            str(context["correction_review"]["event"].id),
        )
        evidence_source, editorial_source = payload["sources"]
        self.assertEqual(evidence_source["provenance"], "CORRECTION_REVIEW_EVIDENCE")
        self.assertEqual(
            evidence_source["evidence"][0]["review_event_id"],
            str(context["correction_review"]["event"].id),
        )
        self.assertEqual(editorial_source["provenance"], "EDITORIAL")
        self.assertEqual(
            editorial_source["editorial_actor"]["id"],
            str(self.lead.id),
        )
        self.assertEqual(editorial_source["evidence"], [])
        self.assertEqual(result["case"].status, ModerationCase.Status.OPEN)
        self.assertEqual(
            result["event"].event_type,
            ModerationEvent.EventType.FACTUAL_CORRECTION_PROPOSAL_PREPARED,
        )
        context["correction_request"].refresh_from_db()
        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        context["claim"].refresh_from_db()
        self.assertEqual(context["correction_request"].status, FactualCorrectionRequest.Status.ACTIVE)
        self.assertTrue(context["decision"].is_current)
        self.assertEqual(context["claim"].final_verdict, context["decision"].verdict)
        self.assertEqual(context["published"].publication_status, OfficialFactCheck.PublicationStatus.PUBLISHED)
        self.assertEqual(context["decision"].evidence_snapshot.evidence_records, original_decision_snapshot)
        self.assertEqual(
            counts["decisions"],
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
        )
        self.assertEqual(
            counts["decision_snapshots"],
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision__claim=context["claim"]
            ).count(),
        )
        self.assertEqual(counts["fact_checks"], OfficialFactCheck.objects.filter(claim=context["claim"]).count())
        self.assertEqual(counts["seals"], OfficialFactCheckPublicationSnapshot.objects.filter(fact_check__claim=context["claim"]).count())
        self.assertEqual(counts["assignments"], VerificationAssignment.objects.filter(claim=context["claim"]).count())

    def test_prepare_rejects_missing_stale_or_active_evidence_review_state(self):
        missing = self.make_proposal_context(suffix="missing-review", review=False)
        missing_proposal = self.save_proposal(missing)
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.prepare_proposal(missing, missing_proposal)

        stale = self.make_proposal_context(suffix="stale-review")
        stale_proposal = self.save_proposal(stale)
        EvidenceSubmission.objects.filter(pk=stale["evidence"][0].pk).update(
            moderator_notes="Changed after the captured correction review."
        )
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.prepare_proposal(stale, stale_proposal)

        active = self.make_proposal_context(suffix="active-evidence-case")
        active_proposal = self.save_proposal(active)
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=active["evidence"][0],
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
        )
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.prepare_proposal(active, active_proposal)

    def test_prepare_requires_every_current_evidence_item_to_have_fresh_review(self):
        context = self.make_proposal_context(suffix="complete-basis")
        EvidenceSubmission.objects.create(
            thread=context["thread"],
            contributor=self.second_contributor,
            evidence_caption="Added after the reviewed correction basis.",
            evidence_url=f"https://example.com/new-evidence-{context['claim'].id}",
            evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
        )
        proposal = self.save_proposal(context)
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.prepare_proposal(context, proposal)

    def test_approving_adjudicator_cannot_have_contributed_evidence(self):
        context = self.make_proposal_context(suffix="direct-contribution")
        EvidenceSubmission.objects.filter(pk=context["evidence"][0].pk).update(
            contributor=self.lead
        )
        proposal = self.save_proposal(context)
        with self.assertRaises(FactualCorrectionProposalAuthorizationError):
            self.prepare_proposal(context, proposal, actor=self.lead)

    def test_prepared_proposal_is_immutable_and_cannot_be_prepared_twice(self):
        context = self.make_proposal_context(suffix="immutable")
        proposal = self.save_proposal(context)
        prepared = self.prepare_proposal(context, proposal)["proposal"]
        payload = deepcopy(prepared.prepared_payload)

        prepared.headline = "Attempted overwrite"
        with self.assertRaises(ValidationError):
            prepared.save()
        prepared.refresh_from_db()
        self.assertEqual(prepared.prepared_payload, payload)
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.save_proposal(
                context,
                expected_proposal_version=prepared.version,
            )
        with self.assertRaises(FactualCorrectionProposalConflict):
            self.prepare_proposal(context, prepared)

    def test_preparation_rolls_back_proposal_and_event_at_each_persistence_step(self):
        for failure_target in ("proposal", "event"):
            with self.subTest(failure_target=failure_target):
                context = self.make_proposal_context(suffix=f"rollback-{failure_target}")
                proposal = self.save_proposal(context)
                original_event_count = ModerationEvent.objects.filter(
                    case=context["correction_case"]
                ).count()
                if failure_target == "proposal":
                    patcher = patch.object(
                        FactualCorrectionProposal,
                        "save",
                        side_effect=RuntimeError("proposal persistence unavailable"),
                    )
                else:
                    original_create = ModerationEvent.objects.create

                    def create_event(*args, **kwargs):
                        if kwargs.get("event_type") == (
                            ModerationEvent.EventType.FACTUAL_CORRECTION_PROPOSAL_PREPARED
                        ):
                            raise RuntimeError("approval event persistence unavailable")
                        return original_create(*args, **kwargs)

                    patcher = patch.object(
                        ModerationEvent.objects,
                        "create",
                        side_effect=create_event,
                    )
                with patcher, self.assertRaises(RuntimeError):
                    self.prepare_proposal(context, proposal)

                proposal.refresh_from_db()
                context["correction_case"].refresh_from_db()
                self.assertEqual(proposal.status, FactualCorrectionProposal.Status.DRAFT)
                self.assertIsNone(proposal.prepared_payload)
                self.assertEqual(context["correction_case"].status, ModerationCase.Status.OPEN)
                self.assertEqual(
                    ModerationEvent.objects.filter(
                        case=context["correction_case"]
                    ).count(),
                    original_event_count,
                )

    def test_pure_schema_validator_rejects_unknown_or_tampered_payloads(self):
        context = self.make_proposal_context(suffix="schema")
        prepared = self.prepare_proposal(context, self.save_proposal(context))["proposal"]
        payload = deepcopy(prepared.prepared_payload)
        self.assertIs(
            validate_factual_correction_proposal(schema_version=1, payload=payload),
            payload,
        )
        with self.assertRaises(FactualCorrectionProposalSchemaError):
            validate_factual_correction_proposal(schema_version=True, payload=payload)
        payload["unexpected"] = True
        with self.assertRaises(FactualCorrectionProposalSchemaError):
            validate_factual_correction_proposal(schema_version=1, payload=payload)


    def test_approving_adjudicator_cannot_have_authored_a_claim_thread(self):
        context = self.make_proposal_context(suffix="thread-author-conflict")
        context["thread"].author = self.lead
        context["thread"].save(update_fields=["author"])
        proposal = self.save_proposal(context)

        with self.assertRaises(FactualCorrectionProposalAuthorizationError):
            self.prepare_proposal(context, proposal, actor=self.lead)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, FactualCorrectionProposal.Status.DRAFT)
        self.assertIsNone(proposal.prepared_payload)

    def test_prepared_snapshot_survives_approver_fk_set_null(self):
        context = self.make_proposal_context(suffix="deleted-approver")
        proposal = self.save_proposal(context)
        prepared = self.prepare_proposal(context, proposal)["proposal"]
        payload = deepcopy(prepared.prepared_payload)

        # Ordinary code must not erase a still-existing approver.
        prepared.prepared_by = None
        with self.assertRaises(ValidationError):
            prepared.save(update_fields=["prepared_by"])
        prepared.refresh_from_db()

        # Simulate the database's SET_NULL action after account deletion.
        FactualCorrectionProposal.objects.filter(pk=prepared.pk).update(
            prepared_by=None
        )
        prepared.refresh_from_db()
        prepared.full_clean()
        prepared.save(update_fields=["updated_at"])

        self.assertIsNone(prepared.prepared_by_id)
        self.assertEqual(prepared.prepared_payload, payload)
        self.assertEqual(
            prepared.prepared_by_snapshot,
            payload["approval"]["actor"],
        )

    def test_pure_schema_rejects_unhashable_values_and_boolean_version(self):
        context = self.make_proposal_context(suffix="schema-invalid-types")
        prepared = self.prepare_proposal(
            context, self.save_proposal(context)
        )["proposal"]
        original = prepared.prepared_payload

        for mutation in (
            lambda p: p["decision"].update(verdict=["FACT"]),
            lambda p: p["evidence_basis"].update(schema_version=True),
            lambda p: p["evidence_basis"]["items"][0]["record"].update(
                evidence_status=["VERIFIED"]
            ),
            lambda p: p["sources"][0].update(provenance=["EDITORIAL"]),
            lambda p: p["sources"][0].update(url="https://[invalid"),
        ):
            with self.subTest(mutation=mutation):
                payload = deepcopy(original)
                mutation(payload)
                with self.assertRaises(FactualCorrectionProposalSchemaError):
                    validate_factual_correction_proposal(
                        schema_version=1, payload=payload
                    )


class FactualCorrectionProposalPostgresTests(
    FactualCorrectionProposalFixtures,
    TransactionTestCase,
):
    def test_competing_preparations_serialize_to_one_winner(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")
        context = self.make_proposal_context(suffix="competing-prepare")
        proposal = self.save_proposal(context)
        barrier = threading.Barrier(2)
        outcomes = {}
        errors = {}

        def prepare(worker_name, actor_id):
            outcome = None
            try:
                close_old_connections()
                actor = User.objects.get(pk=actor_id)
                barrier.wait(timeout=10)
                prepare_factual_correction_proposal(
                    correction_request_id=context["correction_request"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_proposal_version=proposal.version,
                    expected_predecessor_version=context["published"].version,
                    expected_decision_revision=context["decision"].revision_number,
                )
            except FactualCorrectionProposalConflict:
                outcome = "conflict"
            except Exception as error:  # pragma: no cover - asserted below
                outcome = f"error:{type(error).__name__}"
                errors[worker_name] = repr(error)
            else:
                outcome = "prepared"
            finally:
                try:
                    connections["default"].close()
                except Exception as error:  # pragma: no cover - asserted below
                    outcome = f"error:{type(error).__name__}"
                    errors[worker_name] = repr(error)
                outcomes[worker_name] = outcome

        workers = [
            threading.Thread(target=prepare, args=("lead", self.lead.id)),
            threading.Thread(target=prepare, args=("moderator", self.moderator.id)),
        ]
        for worker in workers:
            worker.start()
        deadline = time.monotonic() + 90.0
        for worker in workers:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))

        self.assertFalse(
            any(worker.is_alive() for worker in workers),
            "Preparation workers exceeded the shared 90-second deadline.",
        )
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(list(outcomes.values()), ["prepared", "conflict"])
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, FactualCorrectionProposal.Status.PREPARED)
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=context["correction_case"],
                event_type=(
                    ModerationEvent.EventType.FACTUAL_CORRECTION_PROPOSAL_PREPARED
                ),
            ).count(),
            1,
        )
