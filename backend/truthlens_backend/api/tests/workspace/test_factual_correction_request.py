import threading
import time
import uuid
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
)
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from api.factual_correction_service import (
    FactualCorrectionAuthorizationError,
    FactualCorrectionConflict,
    InvalidFactualCorrectionRequest,
    request_factual_correction,
)
from api.evidence_review_service import (
    EvidenceReviewAuthorizationError,
    EvidenceReviewConflict,
    review_correction_evidence,
)
from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    EvidenceSubmission,
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
from api.moderation_service import DuplicateActiveModerationCase
from api.organization_service import PartnerCapability
from api.publishing_service import (
    PublishingConflict,
    create_editorial_revision_draft,
    create_fact_check_draft,
    publish_editorial_revision,
    publish_fact_check,
    submit_fact_check_for_review,
    update_fact_check_draft,
)
from api.adjudication_service import (
    AdjudicationConflict,
    ensure_adjudication_case,
    ensure_claim_adjudication_readiness,
)
from api.tests.workspace.test_editorial_revision_publication import (
    EditorialReplacementFixtures,
)
from api.verification_assignment_service import ensure_verification_assignment


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

    def make_reserved_draft(
        self,
        context,
        *,
        publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
        revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        supersedes=None,
    ):
        return OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Reserved competing draft",
            summary="This draft must not bypass correction work.",
            article_body="Reserved publication content.",
            publication_status=publication_status,
            version=context["published"].version + 1,
            drafted_by=self.lead,
            supersedes=supersedes,
            revision_kind=revision_kind,
            revision_reason=(
                "Editorial replacement prepared before correction work."
                if revision_kind
                == OfficialFactCheck.RevisionKind.EDITORIAL_REVISION
                else None
            ),
            revision_requested_by=(
                self.lead
                if revision_kind
                == OfficialFactCheck.RevisionKind.EDITORIAL_REVISION
                else None
            ),
            revision_requested_at=(
                timezone.now()
                if revision_kind
                == OfficialFactCheck.RevisionKind.EDITORIAL_REVISION
                else None
            ),
        )

    def make_correction_review_context(self, *, suffix="correction-review"):
        context = self.make_published_context(suffix=suffix)
        evidence = context["evidence"][0]
        evidence_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=evidence.evidence_status,
            resolution_summary="Original evidence review.",
            resolved_by=self.moderator,
            resolved_at=timezone.now(),
        )
        reservation = self.request_correction(context)
        context.update(
            correction_request=reservation["request"],
            correction_case=reservation["case"],
            evidence_case=evidence_case,
        )
        return context

    def review_correction(self, context, **overrides):
        values = {
            "correction_request_id": context["correction_request"].id,
            "evidence_id": context["evidence"][0].id,
            "actor": self.moderator,
            "evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
            "expected_evidence_status": (
                EvidenceSubmission.EvidenceStatus.VERIFIED
            ),
            "expected_case_id": context["evidence_case"].id,
            "moderator_notes": "Correction review reaffirmed this evidence.",
            "expected_predecessor_version": context["published"].version,
            "expected_decision_revision": context["decision"].revision_number,
        }
        values.update(overrides)
        return review_correction_evidence(**values)

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

    def test_unrelated_adjudication_case_integrity_failure_is_not_reclassified(self):
        context = self.make_published_context(suffix="unrelated-integrity")
        unrelated_error = IntegrityError("unrelated moderation event constraint")

        def fail_with_unrelated_integrity(**_kwargs):
            raise DuplicateActiveModerationCase(
                "A different persistence failure occurred."
            ) from unrelated_error

        with patch(
            "api.factual_correction_service.create_moderation_case",
            side_effect=fail_with_unrelated_integrity,
        ), self.assertRaises(IntegrityError) as raised:
            self.request_correction(context)

        self.assertIs(raised.exception, unrelated_error)

    def test_causeless_duplicate_case_error_is_not_assumed_to_be_uniqueness(self):
        context = self.make_published_context(suffix="causeless-duplicate")

        with patch(
            "api.factual_correction_service.create_moderation_case",
            side_effect=DuplicateActiveModerationCase("causeless failure"),
        ), self.assertRaises(DuplicateActiveModerationCase):
            self.request_correction(context)


class CorrectionReservationEnforcementTests(
    FactualCorrectionRequestFixtures,
    TestCase,
):
    def assert_reserved(self, action):
        with self.assertRaisesRegex(PublishingConflict, "reserves publication"):
            action()

    def test_active_request_blocks_initial_and_editorial_draft_creation(self):
        initial = self.make_published_context(suffix="block-initial-draft")
        self.request_correction(initial)
        self.assert_reserved(
            lambda: create_fact_check_draft(
                decision=initial["decision"],
                actor=self.lead,
                headline="Blocked initial draft",
                summary="An active correction owns this publication work.",
            )
        )

        editorial = self.make_published_context(suffix="block-editorial-draft")
        self.request_correction(editorial)
        self.assert_reserved(
            lambda: create_editorial_revision_draft(
                predecessor_id=editorial["published"].id,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_predecessor_version=editorial["published"].version,
                expected_decision_revision=editorial["decision"].revision_number,
                revision_reason="This ordinary revision is blocked.",
            )
        )

    def test_active_request_blocks_update_submission_and_first_publication(self):
        for action_name in ("update", "submit", "publish"):
            with self.subTest(action=action_name):
                context = self.make_published_context(
                    suffix=f"block-{action_name}"
                )
                self.request_correction(context)
                draft = self.make_reserved_draft(
                    context,
                    publication_status=(
                        OfficialFactCheck.PublicationStatus.IN_REVIEW
                        if action_name == "publish"
                        else OfficialFactCheck.PublicationStatus.DRAFT
                    ),
                )
                actions = {
                    "update": lambda: update_fact_check_draft(
                        fact_check=draft,
                        actor=self.lead,
                        summary="This update must remain blocked.",
                    ),
                    "submit": lambda: submit_fact_check_for_review(
                        fact_check=draft,
                        actor=self.lead,
                    ),
                    "publish": lambda: publish_fact_check(
                        fact_check=draft,
                        actor=self.lead,
                    ),
                }
                self.assert_reserved(actions[action_name])

    def test_active_request_blocks_editorial_replacement(self):
        context = self.make_published_context(suffix="block-replacement")
        self.request_correction(context)
        revision = self.make_reserved_draft(
            context,
            publication_status=OfficialFactCheck.PublicationStatus.IN_REVIEW,
            revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            supersedes=context["published"],
        )

        self.assert_reserved(
            lambda: publish_editorial_revision(
                revision_id=revision.id,
                predecessor_id=context["published"].id,
                actor=self.lead,
                organization_id=self.organization.id,
                expected_predecessor_version=context["published"].version,
                expected_revision_version=revision.version,
                expected_decision_revision=context["decision"].revision_number,
            )
        )

    def test_terminal_requests_do_not_permanently_block_editorial_work(self):
        for request_status, case_status in (
            (
                FactualCorrectionRequest.Status.CANCELLED,
                ModerationCase.Status.CANCELLED,
            ),
            (
                FactualCorrectionRequest.Status.COMPLETED,
                ModerationCase.Status.RESOLVED,
            ),
        ):
            with self.subTest(request_status=request_status):
                context = self.make_published_context(
                    suffix=f"terminal-{request_status.lower()}"
                )
                result = self.request_correction(context)
                result["request"].status = request_status
                result["request"].save(update_fields=["status", "updated_at"])
                ModerationCase.objects.filter(pk=result["case"].pk).update(
                    status=case_status
                )

                revision = create_editorial_revision_draft(
                    predecessor_id=context["published"].id,
                    actor=self.lead,
                    organization_id=self.organization.id,
                    expected_predecessor_version=context["published"].version,
                    expected_decision_revision=context["decision"].revision_number,
                    revision_reason="Legitimate work after terminal correction.",
                )

                self.assertEqual(
                    revision.revision_kind,
                    OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
                )

    def test_assignment_and_first_adjudication_helpers_do_not_reuse_reservation(self):
        context = self.make_published_context(suffix="ordinary-helper-guards")
        reservation = self.request_correction(context)

        self.assertIsNone(ensure_verification_assignment(claim=context["claim"]))
        self.assertIsNone(
            ensure_claim_adjudication_readiness(
                claim=context["claim"],
                actor=self.lead,
                organization=self.organization,
            )
        )
        with self.assertRaisesRegex(AdjudicationConflict, "first-decision"):
            ensure_adjudication_case(
                claim=context["claim"],
                actor=self.lead,
                organization=self.organization,
            )
        reservation["case"].refresh_from_db()
        self.assertEqual(reservation["case"].status, ModerationCase.Status.OPEN)


class CorrectionEvidenceReviewTests(
    FactualCorrectionRequestFixtures,
    TestCase,
):
    def test_review_evidence_capability_is_the_only_required_factual_capability(self):
        context = self.make_correction_review_context(
            suffix="review-capability-contract"
        )
        review_only = {PartnerCapability.REVIEW_EVIDENCE}

        with patch(
            "api.publishing_service.get_membership_capabilities",
            return_value=review_only,
        ), patch(
            "api.organization_service.get_membership_capabilities",
            return_value=review_only,
        ):
            result = self.review_correction(context)

        self.assertEqual(result["event"].actor_id, self.moderator.id)

    def test_authorized_review_records_exact_durable_provenance_without_rehandoff(self):
        context = self.make_correction_review_context(suffix="review-success")
        context["case"].refresh_from_db()
        context["claim"].refresh_from_db()
        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        original_case_state = (
            context["case"].status,
            context["case"].resolution_code,
            context["case"].resolved_by_id,
            context["case"].resolved_at,
        )
        original_case_event_count = ModerationEvent.objects.filter(
            case=context["case"]
        ).count()
        original_decision_snapshot = deepcopy(
            context["decision"].evidence_snapshot.evidence_records
        )
        original_decision_state = (
            context["decision"].verdict,
            context["decision"].canonical_claim,
            context["decision"].rationale,
            context["decision"].revision_number,
            context["decision"].is_current,
            context["decision"].moderation_case_id,
        )
        original_claim_verdict = context["claim"].final_verdict
        original_article_state = (
            context["published"].publication_status,
            context["published"].headline,
            context["published"].summary,
            context["published"].article_body,
            context["published"].version,
            context["published"].adjudication_decision_id,
        )
        original_seal = deepcopy(context["seal"].payload)
        assignment_count = VerificationAssignment.objects.filter(
            claim=context["claim"]
        ).count()

        result = self.review_correction(
            context,
            evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
            rejection_reason=EvidenceSubmission.RejectionReason.OUTDATED,
            moderator_notes="Correction review found the evidence outdated.",
        )
        evidence = result["evidence"]
        expected_record = {
            "id": str(evidence.id),
            "thread_id": str(evidence.thread_id),
            "evidence_status": EvidenceSubmission.EvidenceStatus.REJECTED,
            "evidence_type": evidence.evidence_type,
            "evidence_caption": evidence.evidence_caption,
            "evidence_url": evidence.evidence_url,
            "contributor_id": str(evidence.contributor_id),
            "reviewer_id": str(self.moderator.id),
            "submitted_at": evidence.submitted_at.isoformat(),
            "reviewed_at": evidence.verified_at.isoformat(),
            "moderator_notes": "Correction review found the evidence outdated.",
            "rejection_reason": EvidenceSubmission.RejectionReason.OUTDATED,
        }
        self.assertEqual(result["evidence_record"], expected_record)
        self.assertEqual(result["event"].case_id, context["evidence_case"].id)
        self.assertEqual(
            result["event"].metadata,
            {
                "correction_request_id": str(context["correction_request"].id),
                "correction_case_id": str(context["correction_case"].id),
                "evidence_case_id": str(context["evidence_case"].id),
                "reviewer_snapshot": {
                    "id": str(self.moderator.id),
                    "username": self.moderator.username,
                },
                "previous_evidence_status": (
                    EvidenceSubmission.EvidenceStatus.VERIFIED
                ),
                "new_evidence_status": EvidenceSubmission.EvidenceStatus.REJECTED,
                "is_reaffirmation": False,
                "evidence_snapshot_schema_version": 1,
                "evidence_record": expected_record,
            },
        )
        self.assertNotEqual(expected_record, original_decision_snapshot[0])

        context["claim"].refresh_from_db()
        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        context["seal"].refresh_from_db()
        context["assignment"].refresh_from_db()
        context["case"].refresh_from_db()
        context["correction_case"].refresh_from_db()
        self.assertTrue(context["decision"].is_current)
        self.assertEqual(context["claim"].final_verdict, context["decision"].verdict)
        self.assertEqual(context["claim"].final_verdict, original_claim_verdict)
        self.assertEqual(
            (
                context["decision"].verdict,
                context["decision"].canonical_claim,
                context["decision"].rationale,
                context["decision"].revision_number,
                context["decision"].is_current,
                context["decision"].moderation_case_id,
            ),
            original_decision_state,
        )
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(
            (
                context["published"].publication_status,
                context["published"].headline,
                context["published"].summary,
                context["published"].article_body,
                context["published"].version,
                context["published"].adjudication_decision_id,
            ),
            original_article_state,
        )
        self.assertEqual(context["seal"].payload, original_seal)
        self.assertEqual(
            context["decision"].evidence_snapshot.evidence_records,
            original_decision_snapshot,
        )
        self.assertEqual(
            (
                context["case"].status,
                context["case"].resolution_code,
                context["case"].resolved_by_id,
                context["case"].resolved_at,
            ),
            original_case_state,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(case=context["case"]).count(),
            original_case_event_count,
        )
        self.assertEqual(
            context["correction_case"].status,
            ModerationCase.Status.OPEN,
        )
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertEqual(
            VerificationAssignment.objects.filter(claim=context["claim"]).count(),
            assignment_count,
        )

        EvidenceSubmission.objects.filter(pk=evidence.pk).update(
            evidence_caption="Later mutable evidence text"
        )
        User.objects.filter(pk=self.moderator.pk).update(
            username="renamed-correction-reviewer"
        )
        result["event"].refresh_from_db()
        self.assertEqual(result["event"].metadata["evidence_record"], expected_record)
        self.assertEqual(
            result["event"].metadata["reviewer_snapshot"]["username"],
            "transaction-adjudication-moderator",
        )

    def test_explicit_reaffirmation_creates_a_new_attributable_record(self):
        context = self.make_correction_review_context(suffix="reaffirmation")

        first = self.review_correction(context)
        second = self.review_correction(context)

        events = ModerationEvent.objects.filter(
            case=context["evidence_case"],
            event_type=ModerationEvent.EventType.EVIDENCE_VERIFIED,
            metadata__correction_request_id=str(context["correction_request"].id),
        ).order_by("created_at", "id")
        self.assertEqual(events.count(), 2)
        self.assertNotEqual(first["event"].id, second["event"].id)
        self.assertEqual(events[0].metadata["evidence_record"], first["evidence_record"])
        self.assertEqual(events[1].metadata["evidence_record"], second["evidence_record"])
        self.assertTrue(events[0].metadata["is_reaffirmation"])
        self.assertTrue(events[1].metadata["is_reaffirmation"])

    def test_wrong_organization_and_missing_or_revoked_capability_are_rejected(self):
        wrong_organization = self.make_correction_review_context(
            suffix="wrong-evidence-organization"
        )
        ModerationCase.objects.filter(
            pk=wrong_organization["evidence_case"].pk
        ).update(organization=self.other_organization)
        with self.assertRaises(EvidenceReviewConflict):
            self.review_correction(wrong_organization)

        insufficient = self.make_correction_review_context(
            suffix="insufficient-review-capability"
        )
        researcher = User.objects.create_user(
            username="correction-evidence-researcher",
            password="test-password",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=researcher,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        with self.assertRaises(EvidenceReviewAuthorizationError):
            self.review_correction(insufficient, actor=researcher)

        platform_moderator = self.make_correction_review_context(
            suffix="platform-role-fallback"
        )
        self.author.profile.role = UserProfile.Role.MOD
        self.author.profile.save(update_fields=["role"])
        with self.assertRaises(EvidenceReviewAuthorizationError):
            self.review_correction(platform_moderator, actor=self.author)

        revoked = self.make_correction_review_context(suffix="revoked-reviewer")
        OrganizationMembership.objects.filter(
            organization=self.organization,
            user=self.moderator,
        ).update(status=OrganizationMembership.Status.SUSPENDED)
        with self.assertRaises(EvidenceReviewAuthorizationError):
            self.review_correction(revoked)

    def test_stale_authority_terminal_request_and_wrong_evidence_are_rejected(self):
        stale = self.make_correction_review_context(suffix="stale-review")
        for field, value in (
            (
                "expected_predecessor_version",
                stale["published"].version + 1,
            ),
            (
                "expected_decision_revision",
                stale["decision"].revision_number + 1,
            ),
            ("expected_evidence_status", EvidenceSubmission.EvidenceStatus.REJECTED),
        ):
            with self.subTest(field=field):
                with self.assertRaises(EvidenceReviewConflict):
                    self.review_correction(stale, **{field: value})

        terminal = self.make_correction_review_context(suffix="terminal-review")
        terminal["correction_request"].status = (
            FactualCorrectionRequest.Status.COMPLETED
        )
        terminal["correction_request"].save(
            update_fields=["status", "updated_at"]
        )
        with self.assertRaises(EvidenceReviewConflict):
            self.review_correction(terminal)

        with self.assertRaises(EvidenceReviewConflict):
            self.review_correction(
                terminal,
                correction_request_id=uuid.uuid4(),
            )

        inactive_case = self.make_correction_review_context(
            suffix="inactive-correction-case"
        )
        ModerationCase.objects.filter(
            pk=inactive_case["correction_case"].pk
        ).update(status=ModerationCase.Status.RESOLVED)
        with self.assertRaises(EvidenceReviewConflict):
            self.review_correction(inactive_case)

        wrong_evidence = self.make_correction_review_context(
            suffix="wrong-evidence-claim"
        )
        other = self.make_published_context(suffix="other-evidence-claim")
        with self.assertRaises(EvidenceReviewConflict):
            self.review_correction(
                wrong_evidence,
                evidence_id=other["evidence"][0].id,
            )

    def test_wrong_evidence_case_and_self_contribution_are_rejected(self):
        wrong_case = self.make_correction_review_context(suffix="wrong-case")
        other_evidence = EvidenceSubmission.objects.create(
            thread=wrong_case["thread"],
            contributor=self.second_contributor,
            evidence_caption="A different evidence item.",
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
        )
        other_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=other_evidence,
            organization=self.organization,
        )
        with self.assertRaises(EvidenceReviewConflict):
            self.review_correction(wrong_case, expected_case_id=other_case.id)

        self_review = self.make_correction_review_context(suffix="self-review")
        EvidenceSubmission.objects.filter(pk=self_review["evidence"][0].pk).update(
            contributor=self.moderator
        )
        with self.assertRaises(EvidenceReviewAuthorizationError):
            self.review_correction(self_review)

    def test_review_and_event_persistence_failures_roll_back_every_mutation(self):
        for failure_target in ("evidence", "event"):
            with self.subTest(failure_target=failure_target):
                context = self.make_correction_review_context(
                    suffix=f"review-rollback-{failure_target}"
                )
                evidence = context["evidence"][0]
                event_count = ModerationEvent.objects.filter(
                    case=context["evidence_case"]
                ).count()
                if failure_target == "evidence":
                    patcher = patch.object(
                        EvidenceSubmission,
                        "save",
                        side_effect=RuntimeError("evidence persistence unavailable"),
                    )
                else:
                    original_create = ModerationEvent.objects.create

                    def create_event(*args, **kwargs):
                        metadata = kwargs.get("metadata") or {}
                        if "correction_request_id" in metadata:
                            raise RuntimeError("review event persistence unavailable")
                        return original_create(*args, **kwargs)

                    patcher = patch.object(
                        ModerationEvent.objects,
                        "create",
                        side_effect=create_event,
                    )

                with patcher, self.assertRaises(RuntimeError):
                    self.review_correction(context)

                evidence.refresh_from_db()
                context["evidence_case"].refresh_from_db()
                context["correction_case"].refresh_from_db()
                self.assertEqual(
                    evidence.evidence_status,
                    EvidenceSubmission.EvidenceStatus.VERIFIED,
                )
                self.assertIsNone(evidence.verified_by_id)
                self.assertIsNone(evidence.verified_at)
                self.assertEqual(
                    context["evidence_case"].status,
                    ModerationCase.Status.RESOLVED,
                )
                self.assertEqual(
                    context["correction_case"].status,
                    ModerationCase.Status.OPEN,
                )
                self.assertEqual(
                    ModerationEvent.objects.filter(
                        case=context["evidence_case"]
                    ).count(),
                    event_count,
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
        outcomes = {}
        errors = {}

        def request(worker_name):
            outcome = None
            try:
                close_old_connections()
                actor = User.objects.get(pk=self.lead.pk)
                barrier.wait(timeout=10)
                request_factual_correction(
                    predecessor_id=context["published"].id,
                    actor=actor,
                    organization_id=self.organization.id,
                    expected_predecessor_version=context["published"].version,
                    expected_decision_revision=context["decision"].revision_number,
                    correction_reason="Concurrent correction request.",
                )
            except FactualCorrectionConflict:
                outcome = "conflict"
            except Exception as error:  # pragma: no cover - asserted below
                outcome = f"error:{type(error).__name__}"
                errors[worker_name] = repr(error)
            else:
                outcome = "requested"
            finally:
                try:
                    connections["default"].close()
                except Exception as error:  # pragma: no cover - asserted below
                    outcome = f"error:{type(error).__name__}"
                    errors[worker_name] = repr(error)
                outcomes[worker_name] = outcome

        workers = [
            threading.Thread(
                target=request,
                args=(f"correction-{index}",),
                name=f"correction-{index}",
            )
            for index in (1, 2)
        ]
        for worker in workers:
            worker.start()
        deadline = time.monotonic() + 90.0
        for worker in workers:
            remaining = max(0.0, deadline - time.monotonic())
            worker.join(timeout=remaining)

        self.assertFalse(
            any(worker.is_alive() for worker in workers),
            "Correction request workers did not terminate within the shared "
            "90-second deadline.",
        )
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(
            list(outcomes.values()),
            ["requested", "conflict"],
        )
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
