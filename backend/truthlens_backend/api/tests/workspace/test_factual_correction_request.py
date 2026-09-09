import threading
import uuid
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from api.factual_correction_service import (
    FactualCorrectionAuthorizationError,
    FactualCorrectionConflict,
    InvalidFactualCorrectionRequest,
    request_factual_correction,
)
from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    Organization,
    OrganizationMembership,
    UserProfile,
    VerificationAssignment,
)
from api.tests.workspace.test_editorial_revision_publication import (
    EditorialReplacementFixtures,
)


class FactualCorrectionRequestFixtures(EditorialReplacementFixtures):
    def request_correction(self, context, **overrides):
        values = {
            "predecessor_id": context["published"].id,
            "actor": self.lead,
            "organization_id": self.organization.id,
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
            "correction_reason": "New reporting may materially change the verdict.",
        }
        values.update(overrides)
        return request_factual_correction(**values)

    @staticmethod
    def assert_authority_unchanged(test_case, context, *, assignment_count):
        context["claim"].refresh_from_db()
        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        context["assignment"].refresh_from_db()
        context["seal"].refresh_from_db()
        test_case.assertTrue(context["decision"].is_current)
        test_case.assertEqual(
            context["claim"].final_verdict,
            context["decision"].verdict,
        )
        test_case.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        test_case.assertEqual(
            context["published"].adjudication_decision_id,
            context["decision"].id,
        )
        test_case.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        test_case.assertEqual(
            VerificationAssignment.objects.filter(claim=context["claim"]).count(),
            assignment_count,
        )


class FactualCorrectionRequestTests(FactualCorrectionRequestFixtures, TestCase):
    def test_success_reserves_attributable_case_without_changing_authority(self):
        context = self.make_published_context(suffix="correction-request")
        context["thread"].refresh_from_db()
        thread_verdict = context["thread"].moderator_verdict
        decision_count = AdjudicationDecision.objects.filter(
            claim=context["claim"]
        ).count()
        decision_snapshot_count = (
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision__claim=context["claim"]
            ).count()
        )
        fact_check_count = OfficialFactCheck.objects.filter(
            claim=context["claim"]
        ).count()
        seal_count = OfficialFactCheckPublicationSnapshot.objects.filter(
            fact_check__claim=context["claim"]
        ).count()
        assignment_count = VerificationAssignment.objects.filter(
            claim=context["claim"]
        ).count()
        published_payload = deepcopy(context["seal"].payload)

        result = self.request_correction(context)
        correction_request = result["request"]
        correction_case = result["case"]

        self.assertEqual(correction_request.claim_id, context["claim"].id)
        self.assertEqual(correction_request.organization_id, self.organization.id)
        self.assertEqual(
            correction_request.predecessor_decision_id,
            context["decision"].id,
        )
        self.assertEqual(
            correction_request.predecessor_fact_check_id,
            context["published"].id,
        )
        self.assertEqual(
            correction_request.predecessor_publication_snapshot_id,
            context["seal"].id,
        )
        self.assertEqual(correction_request.requested_by_id, self.lead.id)
        self.assertEqual(
            correction_request.requested_by_snapshot,
            {"id": str(self.lead.id), "username": self.lead.username},
        )
        self.assertEqual(
            correction_request.organization_snapshot,
            {
                "id": str(self.organization.id),
                "name": self.organization.name,
                "slug": self.organization.slug,
            },
        )
        self.assertEqual(
            correction_request.correction_reason,
            "New reporting may materially change the verdict.",
        )
        self.assertIsNotNone(correction_request.requested_at)
        self.assertEqual(
            correction_request.status,
            FactualCorrectionRequest.Status.ACTIVE,
        )
        self.assertEqual(correction_request.moderation_case_id, correction_case.id)
        self.assertEqual(
            correction_case.case_type,
            ModerationCase.CaseType.ADJUDICATION,
        )
        self.assertEqual(correction_case.status, ModerationCase.Status.OPEN)
        self.assertEqual(correction_case.organization_id, self.organization.id)
        self.assertEqual(correction_case.claim_id, context["claim"].id)

        event = ModerationEvent.objects.get(
            case=correction_case,
            event_type=ModerationEvent.EventType.FACTUAL_CORRECTION_REQUESTED,
        )
        self.assertEqual(event.actor_id, self.lead.id)
        self.assertEqual(event.notes, correction_request.correction_reason)
        self.assertEqual(
            event.metadata,
            {
                "correction_request_id": str(correction_request.id),
                "predecessor_decision_id": str(context["decision"].id),
                "predecessor_decision_revision": context["decision"].revision_number,
                "predecessor_fact_check_id": str(context["published"].id),
                "predecessor_fact_check_version": context["published"].version,
                "predecessor_publication_snapshot_id": str(context["seal"].id),
            },
        )
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=correction_case,
                event_type=ModerationEvent.EventType.CASE_CREATED,
            ).count(),
            1,
        )

        self.assert_authority_unchanged(
            self,
            context,
            assignment_count=assignment_count,
        )
        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            decision_count,
        )
        self.assertEqual(
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision__claim=context["claim"]
            ).count(),
            decision_snapshot_count,
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            fact_check_count,
        )
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count(),
            seal_count,
        )
        self.assertEqual(context["seal"].payload, published_payload)
        context["thread"].refresh_from_db()
        self.assertEqual(context["thread"].moderator_verdict, thread_verdict)

    def test_partner_moderator_with_adjudicate_capability_can_request(self):
        context = self.make_published_context(suffix="moderator-authority")

        result = self.request_correction(context, actor=self.moderator)

        self.assertEqual(result["request"].requested_by_id, self.moderator.id)
        self.assertEqual(result["case"].organization_id, self.organization.id)

    def test_request_provenance_is_stable_and_terminal_request_cannot_be_reused(
        self,
    ):
        context = self.make_published_context(suffix="stable-provenance")
        correction_request = self.request_correction(context)["request"]
        actor_snapshot = deepcopy(correction_request.requested_by_snapshot)
        organization_snapshot = deepcopy(correction_request.organization_snapshot)
        User.objects.filter(pk=self.lead.pk).update(username="renamed-correction-actor")
        type(self.organization).objects.filter(pk=self.organization.pk).update(
            name="Renamed Correction Organization",
            slug="renamed-correction-organization",
        )

        correction_request.refresh_from_db()
        self.assertEqual(correction_request.requested_by_snapshot, actor_snapshot)
        self.assertEqual(
            correction_request.organization_snapshot,
            organization_snapshot,
        )

        correction_request.correction_reason = "Changed reason."
        with self.assertRaises(ValidationError):
            correction_request.save()
        correction_request.refresh_from_db()
        correction_request.requested_by = self.moderator
        with self.assertRaises(ValidationError):
            correction_request.save()
        correction_request.refresh_from_db()
        correction_request.organization = self.other_organization
        with self.assertRaises(ValidationError):
            correction_request.save()
        correction_request.refresh_from_db()
        correction_request.predecessor_fact_check_id = uuid.uuid4()
        with self.assertRaises(ValidationError):
            correction_request.save()
        correction_request.refresh_from_db()
        correction_request.status = FactualCorrectionRequest.Status.COMPLETED
        correction_request.save(update_fields=["status", "updated_at"])
        correction_request.status = FactualCorrectionRequest.Status.ACTIVE
        with self.assertRaises(ValidationError):
            correction_request.save(update_fields=["status", "updated_at"])
        with self.assertRaises(ValidationError):
            correction_request.delete()

    def test_inputs_and_stale_versions_fail_before_reservation(self):
        context = self.make_published_context(suffix="invalid-input")
        invalid_values = (
            ("predecessor_id", "not-a-uuid"),
            ("predecessor_id", True),
            ("organization_id", "not-a-uuid"),
            ("organization_id", False),
            ("expected_predecessor_version", 0),
            ("expected_predecessor_version", True),
            ("expected_decision_revision", -1),
            ("expected_decision_revision", False),
            ("correction_reason", "   "),
            ("correction_reason", None),
            ("correction_reason", "x" * 2001),
        )
        for field, value in invalid_values:
            with self.subTest(field=field, value=type(value).__name__):
                with self.assertRaises(InvalidFactualCorrectionRequest):
                    self.request_correction(context, **{field: value})

        for field, value in (
            ("expected_predecessor_version", context["published"].version + 1),
            ("expected_decision_revision", context["decision"].revision_number + 1),
        ):
            with self.subTest(field=field):
                with self.assertRaises(FactualCorrectionConflict):
                    self.request_correction(context, **{field: value})

        self.assertFalse(
            FactualCorrectionRequest.objects.filter(claim=context["claim"]).exists()
        )

    def test_exact_organization_capability_is_required_under_lock(self):
        unauthenticated = self.make_published_context(suffix="unauthenticated")
        with self.assertRaises(FactualCorrectionAuthorizationError):
            self.request_correction(unauthenticated, actor=None)

        wrong_organization = self.make_published_context(suffix="wrong-organization")
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.lead,
            role=OrganizationMembership.Role.MODERATOR,
            status=OrganizationMembership.Status.ACTIVE,
        )
        with self.assertRaises(FactualCorrectionConflict):
            self.request_correction(
                wrong_organization,
                organization_id=self.other_organization.id,
            )

        insufficient = self.make_published_context(suffix="insufficient-role")
        researcher = User.objects.create_user(
            username="factual-correction-researcher",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=researcher,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        with self.assertRaises(FactualCorrectionAuthorizationError):
            self.request_correction(insufficient, actor=researcher)

        system_moderator = self.make_published_context(suffix="system-moderator")
        self.author.profile.role = UserProfile.Role.MOD
        self.author.profile.save(update_fields=["role"])
        with self.assertRaises(FactualCorrectionAuthorizationError):
            self.request_correction(system_moderator, actor=self.author)

        revoked = self.make_published_context(suffix="revoked-membership")
        OrganizationMembership.objects.filter(
            organization=self.organization,
            user=self.lead,
        ).update(status=OrganizationMembership.Status.SUSPENDED)
        with self.assertRaises(FactualCorrectionAuthorizationError):
            self.request_correction(revoked)

        OrganizationMembership.objects.filter(
            organization=self.organization,
            user=self.lead,
        ).update(status=OrganizationMembership.Status.ACTIVE)
        ineligible_organization = self.make_published_context(
            suffix="ineligible-organization"
        )
        Organization.objects.filter(pk=self.organization.pk).update(
            partner_status=Organization.PartnerStatus.SUSPENDED
        )
        with self.assertRaises(FactualCorrectionAuthorizationError):
            self.request_correction(ineligible_organization)

    def test_missing_malformed_or_ambiguous_publication_history_fails_closed(self):
        missing = self.make_published_context(suffix="missing-correction-seal")
        OfficialFactCheckPublicationSnapshot.objects.filter(
            pk=missing["seal"].pk
        ).delete()
        with self.assertRaises(FactualCorrectionConflict):
            self.request_correction(missing)

        malformed = self.make_published_context(suffix="malformed-correction-seal")
        payload = deepcopy(malformed["seal"].payload)
        payload["fact_check_id"] = str(uuid.uuid4())
        OfficialFactCheckPublicationSnapshot.objects.filter(
            pk=malformed["seal"].pk
        ).update(payload=payload)
        with self.assertRaises(FactualCorrectionConflict):
            self.request_correction(malformed)

        ambiguous = self.make_published_context(suffix="ambiguous-history")
        OfficialFactCheck.objects.create(
            claim=ambiguous["claim"],
            adjudication_decision=ambiguous["decision"],
            organization=self.organization,
            canonical_claim=ambiguous["decision"].canonical_claim,
            verdict=ambiguous["decision"].verdict,
            headline="Disconnected historical publication",
            summary="This recorded history has no attributable seal.",
            article_body="Historical content is not reconstructed.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=ambiguous["published"].version + 1,
            published_at=timezone.now(),
            archived_at=timezone.now(),
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        with self.assertRaises(FactualCorrectionConflict):
            self.request_correction(ambiguous)

    def test_competing_request_publication_case_and_assignment_work_are_blocked(self):
        repeated = self.make_published_context(suffix="repeated-request")
        first = self.request_correction(repeated)
        with self.assertRaises(FactualCorrectionConflict):
            self.request_correction(repeated)
        self.assertEqual(
            FactualCorrectionRequest.objects.filter(claim=repeated["claim"]).count(),
            1,
        )
        self.assertEqual(
            ModerationCase.objects.filter(
                claim=repeated["claim"],
                case_type=ModerationCase.CaseType.ADJUDICATION,
            ).count(),
            2,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=first["case"],
                event_type=ModerationEvent.EventType.FACTUAL_CORRECTION_REQUESTED,
            ).count(),
            1,
        )

        publication_work = self.make_published_context(suffix="publication-work")
        OfficialFactCheck.objects.create(
            claim=publication_work["claim"],
            adjudication_decision=publication_work["decision"],
            organization=self.organization,
            canonical_claim=publication_work["decision"].canonical_claim,
            verdict=publication_work["decision"].verdict,
            headline="Competing draft",
            summary="Competing publication work.",
            publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            version=publication_work["published"].version + 1,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        with self.assertRaises(FactualCorrectionConflict):
            self.request_correction(publication_work)

        adjudication_work = self.make_published_context(suffix="adjudication-work")
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=adjudication_work["claim"],
            organization=self.organization,
            source=ModerationCase.Source.MODERATOR,
        )
        with self.assertRaises(FactualCorrectionConflict):
            self.request_correction(adjudication_work)

        assignment_work = self.make_published_context(suffix="assignment-work")
        VerificationAssignment.objects.create(
            claim=assignment_work["claim"],
            organization=self.organization,
            claimed_by=self.lead,
            status=VerificationAssignment.Status.ACTIVE,
        )
        with self.assertRaises(FactualCorrectionConflict):
            self.request_correction(assignment_work)

    def test_case_request_and_event_failures_roll_back_the_reservation(self):
        for failure_target in (
            "case",
            "request",
            "event",
            "case_event_integrity",
        ):
            context = self.make_published_context(suffix=f"rollback-{failure_target}")
            existing_case_ids = set(
                ModerationCase.objects.filter(claim=context["claim"]).values_list(
                    "id", flat=True
                )
            )
            existing_event_count = ModerationEvent.objects.filter(
                case__claim=context["claim"]
            ).count()
            original_event_create = ModerationEvent.objects.create

            def create_event(*args, **kwargs):
                if (
                    kwargs.get("event_type")
                    == ModerationEvent.EventType.FACTUAL_CORRECTION_REQUESTED
                ):
                    raise RuntimeError("correction event unavailable")
                return original_event_create(*args, **kwargs)

            if failure_target == "case":
                patcher = patch(
                    "api.factual_correction_service.create_moderation_case",
                    side_effect=RuntimeError("case unavailable"),
                )
            elif failure_target == "request":
                patcher = patch(
                    "api.factual_correction_service.FactualCorrectionRequest.save",
                    side_effect=RuntimeError("request unavailable"),
                )
            elif failure_target == "event":
                patcher = patch.object(
                    ModerationEvent.objects,
                    "create",
                    side_effect=create_event,
                )
            else:
                patcher = patch.object(
                    ModerationEvent.objects,
                    "create",
                    side_effect=IntegrityError("correction case event unavailable"),
                )

            with self.subTest(failure_target=failure_target):
                expected_error = (
                    IntegrityError
                    if failure_target == "case_event_integrity"
                    else RuntimeError
                )
                with patcher, self.assertRaises(expected_error):
                    self.request_correction(context)

                self.assertFalse(
                    FactualCorrectionRequest.objects.filter(
                        claim=context["claim"]
                    ).exists()
                )
                self.assertEqual(
                    set(
                        ModerationCase.objects.filter(
                            claim=context["claim"]
                        ).values_list("id", flat=True)
                    ),
                    existing_case_ids,
                )
                self.assertEqual(
                    ModerationEvent.objects.filter(
                        case__claim=context["claim"]
                    ).count(),
                    existing_event_count,
                )

    def test_historical_null_initial_publication_can_reserve_correction(self):
        context = self.make_published_context(suffix="historical-null-correction")
        original_payload = deepcopy(context["seal"].payload)
        OfficialFactCheck.objects.filter(pk=context["published"].pk).update(
            revision_kind=None
        )

        result = self.request_correction(context)

        context["published"].refresh_from_db()
        context["seal"].refresh_from_db()
        self.assertIsNone(context["published"].revision_kind)
        self.assertEqual(context["seal"].payload, original_payload)
        self.assertEqual(
            result["request"].predecessor_publication_snapshot_id,
            context["seal"].id,
        )


class FactualCorrectionRequestPostgresTests(
    FactualCorrectionRequestFixtures,
    TransactionTestCase,
):
    def test_competing_requests_serialize_to_one_valid_winner(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")

        context = self.make_published_context(suffix="concurrent-correction")
        barrier = threading.Barrier(2)
        outcomes = []

        def request():
            close_old_connections()
            actor = User.objects.get(pk=self.lead.pk)
            barrier.wait(timeout=10)
            try:
                request_factual_correction(
                    predecessor_id=context["published"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_predecessor_version=context["published"].version,
                    expected_decision_revision=context["decision"].revision_number,
                    correction_reason="Concurrent correction request.",
                )
            except FactualCorrectionConflict:
                outcomes.append("conflict")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"error:{type(error).__name__}")
            else:
                outcomes.append("requested")
            finally:
                close_old_connections()

        workers = [threading.Thread(target=request) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertCountEqual(outcomes, ["requested", "conflict"])
        self.assertEqual(
            FactualCorrectionRequest.objects.filter(
                claim=context["claim"],
                status=FactualCorrectionRequest.Status.ACTIVE,
            ).count(),
            1,
        )
        correction_request = FactualCorrectionRequest.objects.get(
            claim=context["claim"]
        )
        self.assertEqual(
            ModerationCase.objects.filter(
                claim=context["claim"],
                case_type=ModerationCase.CaseType.ADJUDICATION,
                status__in={
                    ModerationCase.Status.OPEN,
                    ModerationCase.Status.IN_REVIEW,
                    ModerationCase.Status.ESCALATED,
                    ModerationCase.Status.REOPENED,
                },
            ).count(),
            1,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=correction_request.moderation_case,
                event_type=ModerationEvent.EventType.FACTUAL_CORRECTION_REQUESTED,
            ).count(),
            1,
        )
        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        context["assignment"].refresh_from_db()
        self.assertTrue(context["decision"].is_current)
        self.assertEqual(context["published"].publication_status, "PUBLISHED")
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
