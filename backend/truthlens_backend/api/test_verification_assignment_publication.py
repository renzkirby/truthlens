from django.contrib.auth.models import User

from django.test import TestCase

from .adjudication_service import (
    ensure_adjudication_case,
    issue_adjudication_decision,
)
from .models import (
    AdjudicationDecision,
    Claim,
    OfficialFactCheck,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
)
from .publishing_service import (
    InvalidPublicationTransition,
    create_fact_check_draft,
    publish_fact_check,
    submit_fact_check_for_review,
)
from .verification_assignment_service import (
    claim_verification_assignment,
    ensure_verification_assignment,
)


class VerificationAssignmentPublicationTests(TestCase):
    def setUp(self):
        self.community_user = User.objects.create_user(
            username=("assignment-publication-community"),
            password="test-password",
        )

        self.lead_verifier = User.objects.create_user(
            username=("assignment-publication-lead"),
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name=("Assignment Publication Partner"),
            slug=("assignment-publication-partner"),
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead_verifier,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=(
                "A claim that will complete its "
                "verification assignment after "
                "publication."
            ),
            ai_verdict="FAKE",
            ai_summary=("Automated analysis suggests the " "claim is unsupported."),
            consensus_score=88.0,
        )

        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.community_user,
            caption=("Community investigation awaiting " "professional verification."),
            status=Thread.Status.OPEN,
        )

        assignment = ensure_verification_assignment(
            claim=self.claim,
        )

        self.assignment = claim_verification_assignment(
            assignment=assignment,
            organization=self.organization,
            actor=self.lead_verifier,
        )

        ensure_adjudication_case(
            claim=self.claim,
            actor=self.community_user,
            organization=self.organization,
        )

        result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.lead_verifier,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale=("The available authoritative " "sources contradict the claim."),
            organization=self.organization,
            expected_revision=0,
        )

        self.decision = result["decision"]

        self.draft = create_fact_check_draft(
            decision=self.decision,
            actor=self.lead_verifier,
            headline=("Fact Check: Reviewed Claim Is False"),
            summary=("Professional review found the " "claim unsupported."),
            article_body=(
                "TruthLens partner reviewers "
                "examined the available sources "
                "and determined that the claim "
                "is false."
            ),
            source_urls=[
                ("https://example.com/" "authoritative-source"),
            ],
        )

    def test_successful_publication_completes_assignment(
        self,
    ):
        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            VerificationAssignment.Status.ACTIVE,
        )

        self.assertIsNone(self.assignment.completed_at)

        submitted = submit_fact_check_for_review(
            fact_check=self.draft,
            actor=self.lead_verifier,
        )

        result = publish_fact_check(
            fact_check=submitted,
            actor=self.lead_verifier,
        )

        published = result["fact_check"]

        self.assignment.refresh_from_db()

        self.assertEqual(
            published.publication_status,
            (OfficialFactCheck.PublicationStatus.PUBLISHED),
        )

        self.assertEqual(
            self.assignment.status,
            VerificationAssignment.Status.COMPLETED,
        )

        self.assertEqual(
            self.assignment.organization_id,
            self.organization.id,
        )

        self.assertEqual(
            self.assignment.claimed_by_id,
            self.lead_verifier.id,
        )

        self.assertIsNotNone(self.assignment.completed_at)

    def test_failed_publication_does_not_complete_assignment(
        self,
    ):
        with self.assertRaises(InvalidPublicationTransition):
            publish_fact_check(
                fact_check=self.draft,
                actor=self.lead_verifier,
            )

        self.assignment.refresh_from_db()
        self.draft.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            VerificationAssignment.Status.ACTIVE,
        )

        self.assertIsNone(self.assignment.completed_at)

        self.assertEqual(
            self.draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

    def test_completed_assignment_preserves_claim_provenance(
        self,
    ):
        submitted = submit_fact_check_for_review(
            fact_check=self.draft,
            actor=self.lead_verifier,
        )

        publish_fact_check(
            fact_check=submitted,
            actor=self.lead_verifier,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.claim_id,
            self.claim.id,
        )

        self.assertEqual(
            self.assignment.organization_id,
            self.organization.id,
        )

        self.assertEqual(
            self.assignment.claimed_by_id,
            self.lead_verifier.id,
        )

        self.assertIsNotNone(self.assignment.claimed_at)

        self.assertIsNotNone(self.assignment.completed_at)

        self.assertIsNone(self.assignment.released_at)
