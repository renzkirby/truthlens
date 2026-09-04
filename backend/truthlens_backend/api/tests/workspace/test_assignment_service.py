from django.contrib.auth.models import User
from django.test import TestCase

from api.adjudication_service import (
    ensure_adjudication_case,
    ensure_claim_adjudication_readiness,
)
from api.evidence_review_service import (
    ensure_evidence_case,
)
from api.models import (
    Claim,
    EvidenceSubmission,
    ModerationCase,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
    UserProfile,
)
from api.moderation_service import (
    ensure_safety_case,
)
from api.verification_assignment_service import (
    VerificationAssignmentAuthorizationError,
    VerificationAssignmentConflict,
    VerificationAssignmentReleaseBlocked,
    claim_verification_assignment,
    ensure_verification_assignment,
    get_claim_verification_organization,
    release_verification_assignment,
)
from api.organization_service import (
    PartnerCapability,
    get_user_capabilities,
    has_capability,
    has_case_capability,
)


class VerificationAssignmentServiceTests(TestCase):
    def setUp(self):
        self.community_user = User.objects.create_user(
            username="assignment-community-user",
            password="test-password",
        )

        self.lead_a = User.objects.create_user(
            username="lead-a",
            password="test-password",
        )

        self.lead_b = User.objects.create_user(
            username="lead-b",
            password="test-password",
        )

        self.organization_a = Organization.objects.create(
            name="Verification Partner A",
            slug="verification-partner-a",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.organization_b = Organization.objects.create(
            name="Verification Partner B",
            slug="verification-partner-b",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization_a,
            user=self.lead_a,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization_b,
            user=self.lead_b,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("A claim awaiting professional " "verification."),
        )

        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.community_user,
            caption="Community investigation",
        )

        self.safety_moderator = User.objects.create_user(
            username="platform-safety-moderator",
            password="test-password",
        )

        self.safety_moderator.profile.role = UserProfile.Role.MOD

        self.safety_moderator.profile.save(update_fields=["role"])

    def _create_assignment(self):
        return ensure_verification_assignment(
            claim=self.claim,
        )

    def _claim_for_organization_a(self):
        assignment = self._create_assignment()

        return claim_verification_assignment(
            assignment=assignment,
            organization=self.organization_a,
            actor=self.lead_a,
        )

    def _create_evidence(
        self,
        *,
        status=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
    ):
        return EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.community_user,
            evidence_caption="Supporting source",
            evidence_url="https://example.com/source",
            evidence_status=status,
        )

    def test_ensure_assignment_creates_one_available_assignment(
        self,
    ):
        first = self._create_assignment()
        second = self._create_assignment()

        self.assertEqual(
            first.id,
            second.id,
        )

        self.assertEqual(
            first.status,
            VerificationAssignment.Status.AVAILABLE,
        )

        self.assertIsNone(first.organization_id)
        self.assertIsNone(first.claimed_by_id)

        self.assertEqual(
            VerificationAssignment.objects.filter(
                claim=self.claim,
                status__in=[
                    VerificationAssignment.Status.AVAILABLE,
                    VerificationAssignment.Status.ACTIVE,
                ],
            ).count(),
            1,
        )

    def test_finalized_claim_is_not_automatically_reopened(
        self,
    ):
        self.claim.final_verdict = "FACT"
        self.claim.save(update_fields=["final_verdict"])

        assignment = self._create_assignment()

        self.assertIsNone(assignment)

        self.assertFalse(
            VerificationAssignment.objects.filter(claim=self.claim).exists()
        )

    def test_lead_verifier_can_claim_available_work(
        self,
    ):
        claimed = self._claim_for_organization_a()

        self.assertEqual(
            claimed.status,
            VerificationAssignment.Status.ACTIVE,
        )
        self.assertEqual(
            claimed.organization_id,
            self.organization_a.id,
        )
        self.assertEqual(
            claimed.claimed_by_id,
            self.lead_a.id,
        )
        self.assertIsNotNone(claimed.claimed_at)

        organization = get_claim_verification_organization(self.claim)

        self.assertEqual(
            organization.id,
            self.organization_a.id,
        )

    def test_second_organization_cannot_take_active_assignment(
        self,
    ):
        assignment = self._claim_for_organization_a()

        with self.assertRaises(VerificationAssignmentConflict):
            claim_verification_assignment(
                assignment=assignment,
                organization=self.organization_b,
                actor=self.lead_b,
            )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.organization_id,
            self.organization_a.id,
        )
        self.assertEqual(
            assignment.claimed_by_id,
            self.lead_a.id,
        )
        self.assertEqual(
            assignment.status,
            VerificationAssignment.Status.ACTIVE,
        )

    def test_claiming_attaches_only_factual_cases(
        self,
    ):
        evidence = self._create_evidence()

        evidence_case = ensure_evidence_case(
            evidence=evidence,
            actor=self.community_user,
        )

        adjudication_case = ensure_adjudication_case(
            claim=self.claim,
            actor=self.community_user,
        )

        safety_case = ensure_safety_case(
            thread=self.thread,
            actor=self.community_user,
        )

        self.assertIsNone(evidence_case.organization_id)
        self.assertIsNone(adjudication_case.organization_id)
        self.assertIsNone(safety_case.organization_id)

        self._claim_for_organization_a()

        evidence_case.refresh_from_db()
        adjudication_case.refresh_from_db()
        safety_case.refresh_from_db()

        self.assertEqual(
            evidence_case.organization_id,
            self.organization_a.id,
        )

        self.assertEqual(
            adjudication_case.organization_id,
            self.organization_a.id,
        )

        # Safety moderation remains a platform concern.
        self.assertIsNone(safety_case.organization_id)

    def test_release_before_review_returns_work_to_intake(
        self,
    ):
        evidence = self._create_evidence()

        evidence_case = ensure_evidence_case(
            evidence=evidence,
            actor=self.community_user,
        )

        adjudication_case = ensure_adjudication_case(
            claim=self.claim,
            actor=self.community_user,
        )

        assignment = self._claim_for_organization_a()

        result = release_verification_assignment(
            assignment=assignment,
            actor=self.lead_a,
        )

        released = result["released_assignment"]
        available = result["available_assignment"]

        released.refresh_from_db()
        available.refresh_from_db()
        evidence_case.refresh_from_db()
        adjudication_case.refresh_from_db()

        self.assertEqual(
            released.status,
            VerificationAssignment.Status.RELEASED,
        )

        # Historical institutional provenance is kept.
        self.assertEqual(
            released.organization_id,
            self.organization_a.id,
        )
        self.assertEqual(
            released.claimed_by_id,
            self.lead_a.id,
        )
        self.assertIsNotNone(released.released_at)

        self.assertEqual(
            available.status,
            VerificationAssignment.Status.AVAILABLE,
        )
        self.assertIsNone(available.organization_id)

        # Untouched OPEN factual cases return to
        # unassigned intake ownership.
        self.assertIsNone(evidence_case.organization_id)
        self.assertIsNone(adjudication_case.organization_id)

    def test_release_is_blocked_after_authoritative_review(
        self,
    ):
        assignment = self._claim_for_organization_a()

        self._create_evidence(
            status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
        )

        with self.assertRaises(VerificationAssignmentReleaseBlocked):
            release_verification_assignment(
                assignment=assignment,
                actor=self.lead_a,
            )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.status,
            VerificationAssignment.Status.ACTIVE,
        )
        self.assertEqual(
            assignment.organization_id,
            self.organization_a.id,
        )

    def test_adjudication_readiness_preserves_assignment_owner(
        self,
    ):
        self._claim_for_organization_a()

        self._create_evidence(
            status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
        )

        case = ensure_claim_adjudication_readiness(
            claim=self.claim,
            actor=self.lead_a,
            organization=self.organization_a,
        )

        self.assertIsNotNone(case)

        self.assertEqual(
            case.case_type,
            ModerationCase.CaseType.ADJUDICATION,
        )

        self.assertEqual(
            case.organization_id,
            self.organization_a.id,
        )

    def test_platform_safety_moderator_has_only_safety_capability(
        self,
    ):
        capabilities = get_user_capabilities(self.safety_moderator)

        self.assertEqual(
            capabilities,
            {
                PartnerCapability.REVIEW_SAFETY,
            },
        )

    def test_partner_lead_has_no_platform_safety_capability(
        self,
    ):
        self.assertTrue(
            has_capability(
                self.lead_a,
                PartnerCapability.CLAIM_VERIFICATION_WORK,
                organization=self.organization_a,
            )
        )

        self.assertTrue(
            has_capability(
                self.lead_a,
                PartnerCapability.REVIEW_EVIDENCE,
                organization=self.organization_a,
            )
        )

        self.assertTrue(
            has_capability(
                self.lead_a,
                PartnerCapability.ADJUDICATE,
                organization=self.organization_a,
            )
        )

        self.assertFalse(
            has_capability(
                self.lead_a,
                PartnerCapability.REVIEW_SAFETY,
                organization=self.organization_a,
            )
        )

    def test_platform_safety_moderator_cannot_claim_verification_work(
        self,
    ):
        assignment = self._create_assignment()

        with self.assertRaises(VerificationAssignmentAuthorizationError):
            claim_verification_assignment(
                assignment=assignment,
                organization=self.organization_a,
                actor=self.safety_moderator,
            )

    def test_case_capabilities_separate_safety_from_fact_checking(
        self,
    ):
        evidence = self._create_evidence()

        evidence_case = ensure_evidence_case(
            evidence=evidence,
            actor=self.community_user,
            organization=self.organization_a,
        )

        adjudication_case = ensure_adjudication_case(
            claim=self.claim,
            actor=self.community_user,
            organization=self.organization_a,
        )

        safety_case = ensure_safety_case(
            thread=self.thread,
            actor=self.community_user,
        )

        self.assertTrue(
            has_case_capability(
                self.safety_moderator,
                safety_case,
                PartnerCapability.REVIEW_SAFETY,
            )
        )

        self.assertFalse(
            has_case_capability(
                self.safety_moderator,
                evidence_case,
                PartnerCapability.REVIEW_EVIDENCE,
            )
        )

        self.assertFalse(
            has_case_capability(
                self.safety_moderator,
                adjudication_case,
                PartnerCapability.ADJUDICATE,
            )
        )

        # Correct capability, wrong case type:
        self.assertFalse(
            has_case_capability(
                self.safety_moderator,
                evidence_case,
                PartnerCapability.REVIEW_SAFETY,
            )
        )
