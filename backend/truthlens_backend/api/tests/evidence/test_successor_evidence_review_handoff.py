from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.adjudication_service import (
    is_claim_ready_for_adjudication,
    issue_adjudication_decision,
)
from api.evidence_review_service import (
    accept_prior_evidence_review,
    ensure_evidence_case,
    review_evidence_submission,
)
from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceReviewBasis,
    Claim,
    EvidenceReviewDecision,
    EvidenceSubmission,
    ModerationCase,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
)
from api.organization_partnership_lifecycle_service import (
    end_partner_organization_partnership,
)
from api.verification_assignment_service import (
    claim_verification_assignment,
    ensure_verification_assignment,
)


class SuccessorEvidenceReviewHandoffTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="successor-platform-admin",
            email="successor-platform@example.com",
            password="test-password",
        )
        self.contributor = User.objects.create_user(
            username="successor-contributor",
            password="test-password",
        )
        self.reviewer_a = User.objects.create_user(
            username="successor-reviewer-a",
            password="test-password",
        )
        self.reviewer_b = User.objects.create_user(
            username="successor-reviewer-b",
            password="test-password",
        )
        self.org_a = self.create_org("successor-org-a")
        self.org_b = self.create_org("successor-org-b")
        for user, organization in (
            (self.reviewer_a, self.org_a),
            (self.reviewer_b, self.org_b),
        ):
            OrganizationMembership.objects.create(
                organization=organization,
                user=user,
                role=OrganizationMembership.Role.LEAD_VERIFIER,
                status=OrganizationMembership.Status.ACTIVE,
            )

        self.claim = Claim.objects.create(
            context_text="Successor evidence review claim.",
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.contributor,
            caption="Successor evidence discussion",
        )
        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Institutionally reviewed source",
            evidence_url="https://example.com/successor-source",
        )

    @staticmethod
    def create_org(slug):
        return Organization.objects.create(
            name=slug.replace("-", " ").title(),
            slug=slug,
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    def establish_org_a_review(self):
        assignment = ensure_verification_assignment(claim=self.claim)
        assignment = claim_verification_assignment(
            assignment=assignment,
            organization=self.org_a,
            actor=self.reviewer_a,
        )
        case = ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
            organization=self.org_a,
        )
        result = review_evidence_submission(
            evidence=self.evidence,
            actor=self.reviewer_a,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            expected_status=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
            expected_case_id=case.pk,
            expected_organization_id=self.org_a.pk,
            allow_reopen=False,
        )
        return assignment, result

    def retire_a_and_claim_b(self):
        end_partner_organization_partnership(
            organization_id=self.org_a.pk,
            actor=self.platform_admin,
        )
        replacement = VerificationAssignment.objects.get(
            claim=self.claim,
            status=VerificationAssignment.Status.AVAILABLE,
        )
        return claim_verification_assignment(
            assignment=replacement,
            organization=self.org_b,
            actor=self.reviewer_b,
        )

    def successor_case(self):
        return ModerationCase.objects.get(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=self.evidence,
            organization=self.org_b,
            status__in=[
                ModerationCase.Status.OPEN,
                ModerationCase.Status.IN_REVIEW,
                ModerationCase.Status.ESCALATED,
                ModerationCase.Status.REOPENED,
            ],
        )

    def test_successor_claim_requires_explicit_review_basis(self):
        _assignment, first = self.establish_org_a_review()
        original_review = first["review_decision"]
        original_case = first["case"]

        self.retire_a_and_claim_b()

        original_case.refresh_from_db()
        self.assertEqual(original_case.status, ModerationCase.Status.RESOLVED)
        self.assertEqual(original_case.organization_id, self.org_a.pk)
        successor_case = self.successor_case()
        self.assertEqual(successor_case.status, ModerationCase.Status.OPEN)
        self.assertFalse(
            EvidenceReviewDecision.objects.filter(
                evidence_submission=self.evidence,
                organization=self.org_b,
            ).exists()
        )
        self.assertFalse(
            is_claim_ready_for_adjudication(
                self.claim,
                organization=self.org_b,
            )
        )
        original_review.refresh_from_db()
        self.assertEqual(original_review.organization_id, self.org_a.pk)
        self.assertEqual(
            original_review.disposition,
            EvidenceReviewDecision.Disposition.VERIFIED,
        )

    def test_successor_can_accept_prior_review_without_rewriting_original_review(self):
        _assignment, first = self.establish_org_a_review()
        original_review = first["review_decision"]
        self.evidence.refresh_from_db()
        original_reviewer_id = self.evidence.verified_by_id
        original_reviewed_at = self.evidence.verified_at

        self.retire_a_and_claim_b()
        successor_case = self.successor_case()

        result = accept_prior_evidence_review(
            evidence=self.evidence,
            actor=self.reviewer_b,
            source_review_id=original_review.pk,
            expected_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            expected_case_id=successor_case.pk,
            expected_organization_id=self.org_b.pk,
        )

        accepted = result["review_decision"]
        self.assertEqual(
            accepted.decision_type,
            EvidenceReviewDecision.DecisionType.PRIOR_REVIEW_ACCEPTED,
        )
        self.assertEqual(accepted.organization_id, self.org_b.pk)
        self.assertEqual(accepted.source_review_id, original_review.pk)
        self.assertEqual(
            accepted.disposition,
            EvidenceReviewDecision.Disposition.VERIFIED,
        )
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.verified_by_id, original_reviewer_id)
        self.assertEqual(self.evidence.verified_at, original_reviewed_at)
        self.assertTrue(
            is_claim_ready_for_adjudication(
                self.claim,
                organization=self.org_b,
            )
        )

        original_review.refresh_from_db()
        self.assertEqual(original_review.organization_id, self.org_a.pk)
        self.assertEqual(
            original_review.decision_type,
            EvidenceReviewDecision.DecisionType.INDEPENDENT_REVIEW,
        )

    def test_successor_can_independently_reverse_prior_disposition(self):
        _assignment, first = self.establish_org_a_review()
        original_review = first["review_decision"]

        self.retire_a_and_claim_b()
        successor_case = self.successor_case()

        result = review_evidence_submission(
            evidence=self.evidence,
            actor=self.reviewer_b,
            evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
            expected_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            expected_case_id=successor_case.pk,
            expected_organization_id=self.org_b.pk,
            moderator_notes="The source is authentic but does not support this claim.",
            rejection_reason=EvidenceSubmission.RejectionReason.IRRELEVANT,
            allow_reopen=False,
        )

        successor_review = result["review_decision"]
        self.assertEqual(
            successor_review.decision_type,
            EvidenceReviewDecision.DecisionType.INDEPENDENT_REVIEW,
        )
        self.assertEqual(successor_review.organization_id, self.org_b.pk)
        self.assertIsNone(successor_review.source_review_id)
        self.assertEqual(
            successor_review.disposition,
            EvidenceReviewDecision.Disposition.REJECTED,
        )
        original_review.refresh_from_db()
        self.assertEqual(
            original_review.disposition,
            EvidenceReviewDecision.Disposition.VERIFIED,
        )
        self.evidence.refresh_from_db()
        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        )
        self.assertEqual(self.evidence.verified_by_id, self.reviewer_b.pk)
        self.assertTrue(
            is_claim_ready_for_adjudication(
                self.claim,
                organization=self.org_b,
            )
        )

    def test_adjudication_captures_exact_successor_review_basis(self):
        _assignment, first = self.establish_org_a_review()
        original_review = first["review_decision"]
        self.retire_a_and_claim_b()
        successor_case = self.successor_case()
        accepted = accept_prior_evidence_review(
            evidence=self.evidence,
            actor=self.reviewer_b,
            source_review_id=original_review.pk,
            expected_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            expected_case_id=successor_case.pk,
            expected_organization_id=self.org_b.pk,
        )["review_decision"]

        adjudication_case = ModerationCase.objects.get(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=self.claim,
            organization=self.org_b,
        )
        result = issue_adjudication_decision(
            case_id=adjudication_case.pk,
            organization_id=self.org_b.pk,
            actor=self.reviewer_b,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim="The successor organization accepts the prior evidence review.",
            rationale="The evidence basis was explicitly adopted before adjudication.",
            expected_revision=0,
        )

        basis = AdjudicationDecisionEvidenceReviewBasis.objects.get(
            decision=result["decision"],
            evidence_submission=self.evidence,
        )
        self.assertEqual(basis.review_decision_id, accepted.pk)
        self.assertEqual(basis.review_decision.organization_id, self.org_b.pk)
        self.assertEqual(
            basis.review_decision.source_review_id,
            original_review.pk,
        )
