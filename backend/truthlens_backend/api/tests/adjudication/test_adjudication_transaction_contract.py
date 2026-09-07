import threading
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.adjudication_service import (
    AdjudicationAuthorizationError,
    AdjudicationConflict,
    AdjudicationNotFound,
    ensure_adjudication_case,
    issue_adjudication_decision,
)
from api.models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    ModerationEvent,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
    VerificationRun,
)


class AdjudicationContractFixtures:
    def setUp(self):
        super().setUp()
        self.lead = User.objects.create_user(
            username="transaction-adjudication-lead",
            password="test-password",
        )
        self.moderator = User.objects.create_user(
            username="transaction-adjudication-moderator",
            password="test-password",
        )
        self.author = User.objects.create_user(
            username="transaction-adjudication-author",
            password="test-password",
        )
        self.contributor = User.objects.create_user(
            username="transaction-adjudication-contributor",
            password="test-password",
        )
        self.second_contributor = User.objects.create_user(
            username="transaction-adjudication-contributor-two",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Transaction Adjudication Partner",
            slug="transaction-adjudication-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.other_organization = Organization.objects.create(
            name="Other Transaction Adjudication Partner",
            slug="other-transaction-adjudication-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        for user, role in (
            (self.lead, OrganizationMembership.Role.LEAD_VERIFIER),
            (self.moderator, OrganizationMembership.Role.MODERATOR),
        ):
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=user,
                role=role,
                status=OrganizationMembership.Status.ACTIVE,
            )

    def make_context(self, *, evidence_statuses=()):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="A claim awaiting a first authoritative adjudication.",
            ai_verdict="FAKE",
            ai_summary="Automated context only.",
            consensus_score=73.0,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.author,
            caption="Community context for adjudication.",
            status=Thread.Status.OPEN,
        )
        assignment = VerificationAssignment.objects.create(
            claim=claim,
            organization=self.organization,
            claimed_by=self.lead,
            status=VerificationAssignment.Status.ACTIVE,
        )
        evidence = []
        for index, evidence_status in enumerate(evidence_statuses):
            evidence.append(
                EvidenceSubmission.objects.create(
                    thread=thread,
                    contributor=self.contributor,
                    evidence_caption=f"Evidence submission {index}.",
                    evidence_url=f"https://example.com/evidence-{claim.id}-{index}",
                    evidence_type=(
                        EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION
                    ),
                    evidence_status=evidence_status,
                )
            )
        case = ensure_adjudication_case(
            claim=claim,
            actor=self.lead,
            organization=self.organization,
        )
        return {
            "claim": claim,
            "thread": thread,
            "assignment": assignment,
            "evidence": evidence,
            "case": case,
        }

    def issue(self, context, **overrides):
        values = {
            "case_id": context["case"].id,
            "organization_id": self.organization.id,
            "actor": self.lead,
            "verdict": AdjudicationDecision.Verdict.FAKE,
            "canonical_claim": "The reviewed claim is false.",
            "rationale": "Reviewed evidence does not support the claim.",
            "expected_revision": 0,
            "verification_run_id": None,
        }
        values.update(overrides)
        return issue_adjudication_decision(**values)

    def action_url(self, context, organization=None):
        organization = organization or self.organization
        return (
            reverse(
                "adjudication_case_action",
                kwargs={"case_id": context["case"].id},
            )
            + f"?organization_id={organization.id}"
        )

    @staticmethod
    def action_payload(**overrides):
        values = {
            "moderator_verdict": AdjudicationDecision.Verdict.FAKE,
            "canonical_claim": "The reviewed claim is false.",
            "moderator_notes": "Reviewed evidence does not support the claim.",
            "expected_revision": 0,
        }
        values.update(overrides)
        return values


class AdjudicationTransactionContractTests(
    AdjudicationContractFixtures,
    TestCase,
):
    def test_action_time_readiness_rejects_incomplete_evidence_states(self):
        zero_evidence = self.make_context()
        unreviewed = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.UNVERIFIED]
        )
        active_evidence_case = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=active_evidence_case["evidence"][0],
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
        )

        for label, context in (
            ("zero evidence", zero_evidence),
            ("unreviewed evidence", unreviewed),
            ("active Evidence case", active_evidence_case),
        ):
            with self.subTest(label=label):
                with self.assertRaises(AdjudicationConflict):
                    self.issue(context)
                context["case"].refresh_from_db()
                self.assertEqual(context["case"].status, ModerationCase.Status.OPEN)
                self.assertFalse(
                    AdjudicationDecision.objects.filter(
                        claim=context["claim"]
                    ).exists()
                )

    def test_all_reviewed_including_all_rejected_is_ready(self):
        context = self.make_context(
            evidence_statuses=[
                EvidenceSubmission.EvidenceStatus.REJECTED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
            ]
        )

        result = self.issue(
            context,
            verdict=AdjudicationDecision.Verdict.UNVERIFIED,
        )

        self.assertEqual(result["decision"].revision_number, 1)
        self.assertEqual(
            result["decision"].verdict,
            AdjudicationDecision.Verdict.UNVERIFIED,
        )
        self.assertEqual(result["case"].status, ModerationCase.Status.RESOLVED)

    def test_eligible_partner_moderator_may_issue_the_first_decision(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )

        result = self.issue(context, actor=self.moderator)

        self.assertEqual(result["decision"].decided_by, self.moderator)
        self.assertEqual(result["decision"].organization, self.organization)

    def test_case_and_organization_identity_are_required_and_scoped(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )

        with self.assertRaises(AdjudicationNotFound):
            self.issue(context, case_id="00000000-0000-0000-0000-000000000000")
        with self.assertRaises(AdjudicationNotFound):
            self.issue(context, organization_id=self.other_organization.id)

        self.assertFalse(
            AdjudicationDecision.objects.filter(claim=context["claim"]).exists()
        )

    def test_stale_expected_revision_is_rejected_before_mutation(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )

        with self.assertRaises(AdjudicationConflict):
            self.issue(context, expected_revision=1)

        context["case"].refresh_from_db()
        self.assertEqual(context["case"].status, ModerationCase.Status.OPEN)
        self.assertFalse(
            AdjudicationDecision.objects.filter(claim=context["claim"]).exists()
        )

    def test_assignment_and_capability_are_rechecked_under_lock(self):
        released = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        released["assignment"].status = VerificationAssignment.Status.RELEASED
        released["assignment"].save(update_fields=["status"])

        with self.assertRaises(AdjudicationConflict):
            self.issue(released)

        reassigned = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        reassigned["assignment"].organization = self.other_organization
        reassigned["assignment"].save(update_fields=["organization"])

        with self.assertRaises(AdjudicationConflict):
            self.issue(reassigned)

        suspended = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        membership = OrganizationMembership.objects.get(
            organization=self.organization,
            user=self.lead,
        )
        membership.status = OrganizationMembership.Status.SUSPENDED
        membership.save(update_fields=["status"])

        with self.assertRaises(AdjudicationAuthorizationError):
            self.issue(suspended)

    def test_direct_author_and_contributor_conflicts_are_rechecked(self):
        for user in (self.author, self.contributor):
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=user,
                role=OrganizationMembership.Role.MODERATOR,
                status=OrganizationMembership.Status.ACTIVE,
            )
        author_context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        contributor_context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )

        with self.assertRaises(AdjudicationAuthorizationError):
            self.issue(author_context, actor=self.author)
        with self.assertRaises(AdjudicationAuthorizationError):
            self.issue(contributor_context, actor=self.contributor)

    def test_verification_run_must_be_same_claim_and_completed(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        other_context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        incomplete = VerificationRun.objects.create(
            claim=context["claim"],
            status=VerificationRun.Status.RUNNING,
        )
        cross_claim = VerificationRun.objects.create(
            claim=other_context["claim"],
            status=VerificationRun.Status.COMPLETED,
        )
        completed = VerificationRun.objects.create(
            claim=context["claim"],
            status=VerificationRun.Status.COMPLETED,
            pipeline_version="transaction-test-1",
        )

        with self.assertRaises(AdjudicationConflict):
            self.issue(context, verification_run_id=incomplete.id)
        with self.assertRaises(AdjudicationNotFound):
            self.issue(context, verification_run_id=cross_claim.id)

        result = self.issue(context, verification_run_id=completed.id)
        self.assertEqual(result["decision"].verification_run, completed)
        self.assertEqual(
            result["decision"].ai_pipeline_version_snapshot,
            "transaction-test-1",
        )

    def test_first_decision_is_single_use_and_has_no_duplicate_resolution(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )

        first = self.issue(context)
        with self.assertRaises(AdjudicationConflict):
            self.issue(context, actor=self.moderator, expected_revision=1)

        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            1,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=context["case"],
                event_type=ModerationEvent.EventType.VERDICT_ISSUED,
            ).count(),
            1,
        )
        self.assertEqual(first["decision"].revision_number, 1)

    def test_new_active_case_cannot_bypass_existing_current_decision(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        self.issue(context)
        context["case"] = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=context["claim"],
            organization=self.organization,
            source=ModerationCase.Source.MODERATOR,
        )

        with self.assertRaises(AdjudicationConflict):
            self.issue(context, expected_revision=1)

        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            1,
        )

    def test_thread_compatibility_mirror_preserves_status_and_skips_rejected(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        rejected = Thread.objects.create(
            claim=context["claim"],
            author=self.author,
            caption="Previously removed community thread.",
            status=Thread.Status.REJECTED,
            moderator_verdict=AdjudicationDecision.Verdict.FACT,
        )

        self.issue(context)

        context["thread"].refresh_from_db()
        rejected.refresh_from_db()
        self.assertEqual(context["thread"].status, Thread.Status.OPEN)
        self.assertEqual(
            context["thread"].moderator_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )
        self.assertEqual(rejected.status, Thread.Status.REJECTED)
        self.assertEqual(
            rejected.moderator_verdict,
            AdjudicationDecision.Verdict.FACT,
        )

    def test_compatibility_mirrors_roll_back_with_authoritative_failure(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        original_create = ModerationEvent.objects.create

        def fail_verdict_event(*args, **kwargs):
            if kwargs.get("event_type") == ModerationEvent.EventType.VERDICT_ISSUED:
                raise RuntimeError("forced adjudication event failure")
            return original_create(*args, **kwargs)

        with patch.object(
            ModerationEvent.objects,
            "create",
            side_effect=fail_verdict_event,
        ):
            with self.assertRaises(RuntimeError):
                self.issue(context)

        context["claim"].refresh_from_db()
        context["case"].refresh_from_db()
        context["thread"].refresh_from_db()
        self.assertIsNone(context["claim"].final_verdict)
        self.assertEqual(context["case"].status, ModerationCase.Status.OPEN)
        self.assertIsNone(context["thread"].moderator_verdict)
        self.assertFalse(
            AdjudicationDecision.objects.filter(claim=context["claim"]).exists()
        )


class AdjudicationActionApiContractTests(
    AdjudicationContractFixtures,
    TestCase,
):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.lead)

    def test_canonical_action_requires_identity_and_rejects_unknown_fields(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        base_url = reverse(
            "adjudication_case_action",
            kwargs={"case_id": context["case"].id},
        )

        missing_organization = self.client.post(
            base_url,
            self.action_payload(),
            format="json",
        )
        missing_revision_payload = self.action_payload()
        missing_revision_payload.pop("expected_revision")
        missing_revision = self.client.post(
            self.action_url(context),
            missing_revision_payload,
            format="json",
        )
        unknown_field = self.client.post(
            self.action_url(context),
            self.action_payload(claim_id=str(context["claim"].id)),
            format="json",
        )

        self.assertEqual(missing_organization.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing_revision.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unknown_field.status_code, status.HTTP_400_BAD_REQUEST)

    def test_canonical_action_requires_authentication(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        anonymous = APIClient()

        response = anonymous.post(
            self.action_url(context),
            self.action_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_organization_is_privacy_safe(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )

        response = self.client.post(
            self.action_url(context, self.other_organization),
            self.action_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unknown_selected_case_is_unavailable(self):
        url = (
            reverse(
                "adjudication_case_action",
                kwargs={
                    "case_id": "00000000-0000-0000-0000-000000000000",
                },
            )
            + f"?organization_id={self.organization.id}"
        )

        response = self.client.post(url, self.action_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authoritative_conflict_is_not_swallowed_or_scheduled(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        first = self.client.post(
            self.action_url(context),
            self.action_payload(),
            format="json",
        )

        with patch("api.views.schedule_adjudication_trust_updates") as schedule:
            second = self.client.post(
                self.action_url(context),
                self.action_payload(expected_revision=1),
                format="json",
            )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        schedule.assert_not_called()

    def test_rolled_back_action_does_not_schedule_trust_work(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        original_create = ModerationEvent.objects.create

        def fail_verdict_event(*args, **kwargs):
            if kwargs.get("event_type") == ModerationEvent.EventType.VERDICT_ISSUED:
                raise RuntimeError("forced adjudication event failure")
            return original_create(*args, **kwargs)

        with patch.object(
            ModerationEvent.objects,
            "create",
            side_effect=fail_verdict_event,
        ), patch("api.views.schedule_adjudication_trust_updates") as schedule:
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.action_url(context),
                    self.action_payload(),
                    format="json",
                )

        schedule.assert_not_called()
        self.assertFalse(
            AdjudicationDecision.objects.filter(claim=context["claim"]).exists()
        )

    def test_broker_failure_does_not_turn_committed_action_into_http_500(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )

        with patch(
            "api.tasks.recompute_user_trust_score_task.delay",
            side_effect=ConnectionError("broker unavailable"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    self.action_url(context),
                    self.action_payload(),
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        context["claim"].refresh_from_db()
        context["case"].refresh_from_db()
        self.assertEqual(
            context["claim"].final_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )
        self.assertEqual(context["case"].status, ModerationCase.Status.RESOLVED)

    def test_trust_dispatch_targets_each_distinct_contributor_once(self):
        context = self.make_context(
            evidence_statuses=[
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
            ]
        )
        EvidenceSubmission.objects.create(
            thread=context["thread"],
            contributor=self.second_contributor,
            evidence_caption="A second contributor's reviewed evidence.",
            evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
        )

        with patch(
            "api.tasks.recompute_user_trust_score_task.delay",
        ) as dispatch:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.client.post(
                    self.action_url(context),
                    self.action_payload(),
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(dispatch.call_count, 2)
        self.assertEqual(
            {call.args[0] for call in dispatch.call_args_list},
            {self.contributor.id, self.second_contributor.id},
        )

    def test_legacy_claim_and_thread_adapters_require_same_hardened_identity(self):
        for route_name in ("adjudicate_claim", "moderation_resolve_thread"):
            with self.subTest(route=route_name):
                context = self.make_context(
                    evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
                )
                route_kwargs = (
                    {"claim_id": context["claim"].id}
                    if route_name == "adjudicate_claim"
                    else {"thread_id": context["thread"].id}
                )
                url = (
                    reverse(route_name, kwargs=route_kwargs)
                    + f"?organization_id={self.organization.id}"
                )
                payload = self.action_payload(case_id=str(context["case"].id))

                response = self.client.post(url, payload, format="json")

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    AdjudicationDecision.objects.filter(
                        claim=context["claim"],
                        is_current=True,
                    ).count(),
                    1,
                )

    def test_legacy_adapter_does_not_select_a_case_when_case_id_is_missing(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        url = (
            reverse("adjudicate_claim", kwargs={"claim_id": context["claim"].id})
            + f"?organization_id={self.organization.id}"
        )

        response = self.client.post(url, self.action_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            AdjudicationDecision.objects.filter(claim=context["claim"]).exists()
        )


class AdjudicationPostgresConcurrencyTests(
    AdjudicationContractFixtures,
    TransactionTestCase,
):
    def require_postgres(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")

    def test_competing_decisions_create_only_one_authoritative_result(self):
        self.require_postgres()
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        barrier = threading.Barrier(2)
        outcomes = []

        def decide(user_id):
            close_old_connections()
            actor = User.objects.get(pk=user_id)
            barrier.wait()
            try:
                issue_adjudication_decision(
                    case_id=context["case"].id,
                    organization_id=self.organization.id,
                    actor=actor,
                    verdict=AdjudicationDecision.Verdict.FAKE,
                    canonical_claim="The reviewed claim is false.",
                    rationale="Reviewed evidence does not support the claim.",
                    expected_revision=0,
                )
            except AdjudicationConflict:
                outcomes.append("conflict")
            else:
                outcomes.append("success")
            finally:
                close_old_connections()

        workers = [
            threading.Thread(target=decide, args=(self.lead.id,)),
            threading.Thread(target=decide, args=(self.moderator.id,)),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertCountEqual(outcomes, ["success", "conflict"])
        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            1,
        )

    def test_evidence_creation_commits_before_readiness_or_is_serialized_after(self):
        self.require_postgres()
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        evidence_inserted = threading.Event()
        allow_commit = threading.Event()
        adjudication_started = threading.Event()
        outcomes = []

        def create_unreviewed_evidence():
            close_old_connections()
            with transaction.atomic():
                Claim.objects.select_for_update().get(pk=context["claim"].id)
                VerificationAssignment.objects.select_for_update().get(
                    pk=context["assignment"].id
                )
                EvidenceSubmission.objects.create(
                    thread_id=context["thread"].id,
                    contributor_id=self.second_contributor.id,
                    evidence_caption="Concurrent unreviewed evidence.",
                    evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
                    evidence_status=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
                )
                evidence_inserted.set()
                allow_commit.wait(timeout=10)
            outcomes.append("evidence-committed")
            close_old_connections()

        def adjudicate():
            close_old_connections()
            evidence_inserted.wait(timeout=10)
            adjudication_started.set()
            actor = User.objects.get(pk=self.lead.id)
            try:
                issue_adjudication_decision(
                    case_id=context["case"].id,
                    organization_id=self.organization.id,
                    actor=actor,
                    verdict=AdjudicationDecision.Verdict.FAKE,
                    canonical_claim="The reviewed claim is false.",
                    rationale="Reviewed evidence does not support the claim.",
                    expected_revision=0,
                )
            except AdjudicationConflict:
                outcomes.append("readiness-conflict")
            finally:
                close_old_connections()

        creator = threading.Thread(target=create_unreviewed_evidence)
        adjudicator = threading.Thread(target=adjudicate)
        creator.start()
        adjudicator.start()
        adjudication_started.wait(timeout=10)
        allow_commit.set()
        creator.join(timeout=10)
        adjudicator.join(timeout=10)

        self.assertFalse(creator.is_alive())
        self.assertFalse(adjudicator.is_alive())
        self.assertCountEqual(
            outcomes,
            ["evidence-committed", "readiness-conflict"],
        )
        self.assertFalse(
            AdjudicationDecision.objects.filter(claim=context["claim"]).exists()
        )
