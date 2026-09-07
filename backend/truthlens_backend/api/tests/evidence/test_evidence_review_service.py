from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.evidence_review_service import (
    EvidenceReviewAuthorizationError,
    EvidenceReviewConflict,
    review_evidence_submission,
    schedule_evidence_review_trust_updates,
)
from api.models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
)


class EvidenceReviewServiceTests(TestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="service-contributor",
            password="test-password",
        )
        self.reviewer = User.objects.create_user(
            username="service-reviewer",
            password="test-password",
        )
        self.second_reviewer = User.objects.create_user(
            username="service-second-reviewer",
            password="test-password",
        )
        self.organization = self._create_organization("service-primary")
        self.other_organization = self._create_organization("service-other")
        for reviewer in (self.reviewer, self.second_reviewer):
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=reviewer,
                role=OrganizationMembership.Role.LEAD_VERIFIER,
                status=OrganizationMembership.Status.ACTIVE,
            )

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Service evidence review claim",
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.contributor,
            caption="Service evidence review thread",
        )
        self.assignment = VerificationAssignment.objects.create(
            claim=self.claim,
            organization=self.organization,
            claimed_by=self.reviewer,
            status=VerificationAssignment.Status.ACTIVE,
            claimed_at=timezone.now(),
        )
        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Service evidence item",
        )
        self.case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=self.evidence,
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
        )

    @staticmethod
    def _create_organization(slug):
        return Organization.objects.create(
            name=slug.replace("-", " ").title(),
            slug=slug,
            organization_type=Organization.OrganizationType.RESEARCH,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    def _review(self, **overrides):
        values = {
            "evidence": self.evidence,
            "actor": self.reviewer,
            "evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
            "expected_status": EvidenceSubmission.EvidenceStatus.UNVERIFIED,
            "expected_case_id": self.case.id,
            "expected_organization_id": self.organization.id,
            "allow_reopen": False,
        }
        values.update(overrides)
        return review_evidence_submission(**values)

    def test_canonical_review_requires_current_active_assignment(self):
        self.assignment.status = VerificationAssignment.Status.RELEASED
        self.assignment.save(update_fields=["status"])

        with self.assertRaises(EvidenceReviewConflict):
            self._review()

        self.evidence.refresh_from_db()
        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.UNVERIFIED,
        )

    def test_current_assignment_must_match_expected_organization(self):
        self.assignment.organization = self.other_organization
        self.assignment.save(update_fields=["organization"])

        with self.assertRaises(EvidenceReviewConflict):
            self._review()

    def test_stale_historical_case_cannot_mutate_new_active_case(self):
        self.case.status = ModerationCase.Status.RESOLVED
        self.case.save(update_fields=["status"])
        current_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=self.evidence,
            organization=self.organization,
        )

        with self.assertRaises(EvidenceReviewConflict):
            self._review(expected_case_id=self.case.id)

        self.evidence.refresh_from_db()
        current_case.refresh_from_db()
        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.UNVERIFIED,
        )
        self.assertEqual(current_case.status, ModerationCase.Status.OPEN)

    def test_canonical_resolved_case_is_read_only(self):
        self.case.status = ModerationCase.Status.RESOLVED
        self.case.save(update_fields=["status"])

        with self.assertRaises(EvidenceReviewConflict):
            self._review()

    def test_expected_status_prevents_second_reviewer_overwrite(self):
        first = self._review()
        self.assertEqual(
            first["evidence"].evidence_status,
            EvidenceSubmission.EvidenceStatus.VERIFIED,
        )

        with self.assertRaises(EvidenceReviewConflict):
            self._review(
                actor=self.second_reviewer,
                evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
                rejection_reason=EvidenceSubmission.RejectionReason.IRRELEVANT,
            )

        self.evidence.refresh_from_db()
        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.VERIFIED,
        )

    def test_self_review_is_rejected_at_service_boundary(self):
        with self.assertRaises(EvidenceReviewAuthorizationError):
            self._review(actor=self.contributor)

    def test_existing_adjudication_blocks_evidence_mutation(self):
        AdjudicationDecision.objects.create(
            claim=self.claim,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim="Canonical claim",
            rationale="Existing human adjudication",
            decided_by=self.reviewer,
            organization=self.organization,
        )

        with self.assertRaisesRegex(EvidenceReviewConflict, "revision workflow"):
            self._review()

        self.evidence.refresh_from_db()
        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.UNVERIFIED,
        )

    def test_success_preserves_adjudication_handoff_without_setting_verdict(self):
        result = self._review()

        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.final_verdict)
        self.assertIsNotNone(result["adjudication_case"])
        self.assertEqual(
            result["adjudication_case"].case_type,
            ModerationCase.CaseType.ADJUDICATION,
        )
        self.assertFalse(AdjudicationDecision.objects.filter(claim=self.claim).exists())

    def test_safe_trust_dispatch_attempts_immediate_and_async_work(self):
        result = {
            "evidence": self.evidence,
            "case": self.case,
            "contributor_id": self.contributor.id,
        }
        with patch(
            "api.trust_service.recompute_user_trust_score"
        ) as immediate, patch(
            "api.tasks.recompute_user_trust_score_task.delay"
        ) as asynchronous:
            with self.captureOnCommitCallbacks(execute=True):
                schedule_evidence_review_trust_updates(result)

        immediate.assert_called_once_with(self.contributor.id)
        asynchronous.assert_called_once_with(self.contributor.id)

    def test_safe_trust_dispatch_contains_secondary_failures(self):
        result = {
            "evidence": self.evidence,
            "case": self.case,
            "contributor_id": self.contributor.id,
        }
        with patch(
            "api.trust_service.recompute_user_trust_score",
            side_effect=RuntimeError("reputation unavailable"),
        ), patch(
            "api.tasks.recompute_user_trust_score_task.delay",
            side_effect=RuntimeError("broker unavailable"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                schedule_evidence_review_trust_updates(result)
