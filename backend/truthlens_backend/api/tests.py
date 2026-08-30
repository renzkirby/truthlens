from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import (
    IntegrityError,
    transaction,
)

from .models import (
    Claim,
    ClaimCheckHistory,
    EvidenceSubmission,
    Thread,
    ThreadComment,
    UserProfile,
    CanonicalSource,
    EvidenceSource,
    VerificationRun,
    VerificationEvidence,
    ModerationCase,
    ModerationEvent,
    ThreadFlag,
    FlagResolutionLog,
    Organization,
    OrganizationMembership,
)
from .throttles import FactCheckRateThrottle
from .trust_service import (
    calculate_trust_components,
    get_reputation_progression,
    recompute_user_trust_score,
)
from .moderation_service import (
    DuplicateActiveModerationCase,
    InvalidModerationCaseTarget,
    InvalidModerationTransition,
    assign_moderation_case,
    create_moderation_case,
    transition_moderation_case,
    unassign_moderation_case,
)
from .organization_service import (
    PartnerCapability,
    get_user_capabilities,
    has_capability,
    has_case_capability,
)
from .evidence_review_service import (
    EvidenceReviewConflict,
    InvalidEvidenceDecision,
    ensure_evidence_case,
    review_evidence_submission,
)


class ThreadEvidenceCommentAuthorizationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="pass1234"
        )
        self.other = User.objects.create_user(
            username="other", email="other@test.com", password="pass1234"
        )

        self.owner_profile = UserProfile.objects.get(user=self.owner)
        self.owner_profile.trust_score = 88.0
        self.owner_profile.save(update_fields=["trust_score"])

        self.other_profile = UserProfile.objects.get(user=self.other)
        self.other_profile.trust_score = 42.0
        self.other_profile.save(update_fields=["trust_score"])

        self.claim1 = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/1",
            verified_via=Claim.VerificationSource.PENDING,
        )
        self.claim2 = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/2",
            verified_via=Claim.VerificationSource.PENDING,
        )

        self.thread = Thread.objects.create(
            claim=self.claim1, author=self.owner, caption="Owner thread"
        )
        self.other_thread = Thread.objects.create(
            claim=self.claim2, author=self.other, caption="Other thread"
        )

        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.owner,
            evidence_caption="Owner evidence",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_url="https://evidence.example.com",
            contributor_trust_snapshot=self.owner.profile.trust_score,
        )
        self.comment = ThreadComment.objects.create(
            thread=self.thread,
            commenter=self.owner,
            comment_text="Owner comment",
        )

        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.owner)

        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)

    def test_non_owner_cannot_update_or_delete_thread(self):
        thread_detail = reverse("thread-detail", args=[str(self.thread.id)])

        patch_res = self.other_client.patch(
            thread_detail, {"caption": "Hijack"}, format="json"
        )
        delete_res = self.other_client.delete(thread_detail)

        self.assertEqual(patch_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_owner_cannot_update_or_delete_comment(self):
        comment_detail = reverse("comment-detail", args=[str(self.comment.id)])

        patch_res = self.other_client.patch(
            comment_detail, {"comment_text": "Hijack"}, format="json"
        )
        delete_res = self.other_client.delete(comment_detail)

        self.assertEqual(patch_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_owner_cannot_update_or_delete_evidence(self):
        evidence_detail = reverse("evidence-detail", args=[str(self.evidence.id)])

        patch_res = self.other_client.patch(
            evidence_detail, {"evidence_caption": "Hijack"}, format="json"
        )
        delete_res = self.other_client.delete(evidence_detail)

        self.assertEqual(patch_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_can_comment_on_other_users_thread(self):
        comment_list = reverse("comment-list")

        res = self.other_client.post(
            comment_list,
            {"thread_id": str(self.thread.id), "comment_text": "Allowed comment"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ThreadComment.objects.filter(
                thread=self.thread,
                commenter=self.other,
                comment_text="Allowed comment",
            ).exists()
        )

    def test_authenticated_user_can_submit_evidence_on_other_users_thread(self):
        evidence_list = reverse("evidence-list")

        res = self.other_client.post(
            evidence_list,
            {
                "thread_id": str(self.thread.id),
                "evidence_caption": "Allowed evidence",
                "evidence_url": "https://proof.example.com",
                "evidence_type": EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
                "contributor_trust_snapshot": 9999,
            },
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created = EvidenceSubmission.objects.get(id=res.data["id"])
        self.assertEqual(created.contributor, self.other)
        self.assertEqual(created.thread, self.thread)
        self.assertEqual(
            created.contributor_trust_snapshot, self.other.profile.trust_score
        )

    def test_thread_owner_can_submit_evidence_on_own_thread(self):
        evidence_list = reverse("evidence-list")

        res = self.owner_client.post(
            evidence_list,
            {
                "thread_id": str(self.thread.id),
                "evidence_caption": "Owner evidence",
                "evidence_url": "https://owner-proof.example.com",
                "evidence_type": EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            },
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            EvidenceSubmission.objects.filter(
                id=res.data["id"],
                contributor=self.owner,
                thread=self.thread,
            ).exists()
        )

    def test_thread_claim_id_is_immutable_on_update(self):
        thread_detail = reverse("thread-detail", args=[str(self.thread.id)])

        res = self.owner_client.patch(
            thread_detail,
            {"claim_id": str(self.claim2.id), "caption": "Try update"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("claim_id", res.data)

    def test_comment_thread_id_is_immutable_on_update(self):
        comment_detail = reverse("comment-detail", args=[str(self.comment.id)])

        res = self.owner_client.patch(
            comment_detail,
            {"thread_id": str(self.other_thread.id), "comment_text": "Try move"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("thread_id", res.data)

    def test_evidence_thread_id_is_immutable_on_update(self):
        evidence_detail = reverse("evidence-detail", args=[str(self.evidence.id)])

        res = self.owner_client.patch(
            evidence_detail,
            {"thread_id": str(self.other_thread.id), "evidence_caption": "Try move"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("thread_id", res.data)

    def test_thread_status_is_read_only_for_normal_thread_flow(self):
        thread_detail = reverse("thread-detail", args=[str(self.thread.id)])

        res = self.owner_client.patch(
            thread_detail,
            {"status": "CLOSED", "caption": "Updated caption"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.caption, "Updated caption")
        self.assertEqual(self.thread.status, "OPEN")

    def test_escalation_reason_is_immutable_on_update(self):
        thread_detail = reverse("thread-detail", args=[str(self.thread.id)])

        res = self.owner_client.patch(
            thread_detail,
            {"escalation_reason": "LOW_CONFIDENCE", "caption": "Try update"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("escalation_reason", res.data)


class ModeratorEvidenceVerificationTests(APITestCase):
    """
    Tests for the moderator evidence verification workflow.

    Coverage:
    - Permission checks (only MODERATOR role can verify)
    - Verification status updates (VERIFIED/REJECTED)
    - Trust Score v2 recalculation and reputation progression
    - Moderator audit trail (verified_by, verified_at, moderator_notes)
    """

    def setUp(self):
        """Set up test data with regular users and a moderator."""
        # Create regular users
        self.contributor = User.objects.create_user(
            username="contributor", email="contributor@test.com", password="pass1234"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="otheruser@test.com", password="pass1234"
        )

        # Create moderator
        self.moderator = User.objects.create_user(
            username="moderator", email="moderator@test.com", password="pass1234"
        )

        # Set up user profiles with roles
        self.contributor_profile = self.contributor.profile
        self.contributor_profile.trust_score = 50.0
        self.contributor_profile.role = UserProfile.Role.USER
        self.contributor_profile.save(
            update_fields=[
                "trust_score",
                "role",
            ]
        )

        self.other_profile = self.other_user.profile
        self.other_profile.trust_score = 75.0
        self.other_profile.role = UserProfile.Role.USER
        self.other_profile.save(
            update_fields=[
                "trust_score",
                "role",
            ]
        )

        self.moderator_profile = self.moderator.profile
        self.moderator_profile.trust_score = 95.0
        self.moderator_profile.role = UserProfile.Role.MOD
        self.moderator_profile.save(
            update_fields=[
                "trust_score",
                "role",
            ]
        )

        # Create claim and thread
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/claim",
            verified_via=Claim.VerificationSource.PENDING,
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.other_user,
            caption="Test thread for verification",
        )

        # Create evidence
        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Test evidence",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_url="https://evidence.example.com",
            contributor_trust_snapshot=self.contributor_profile.trust_score,
        )

        # Set up API clients
        self.contributor_client = APIClient()
        self.contributor_client.force_authenticate(user=self.contributor)

        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other_user)

        self.assertEqual(
            UserProfile.objects.get(user=self.moderator).role,
            UserProfile.Role.MOD,
        )

        self.assertEqual(
            self.moderator.profile.role,
            UserProfile.Role.MOD,
        )

        self.moderator_client = APIClient()
        self.moderator_client.force_authenticate(user=self.moderator)

        self.unauthenticated_client = APIClient()

    def test_unauthenticated_user_cannot_verify_evidence(self):
        """Unauthenticated users should get 401 Unauthorized."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])

        res = self.unauthenticated_client.patch(
            verify_url, {"evidence_status": "VERIFIED"}, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_moderator_user_cannot_verify_evidence(self):
        """Regular users (even contributors) should get 403 Forbidden."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])

        res = self.contributor_client.patch(
            verify_url, {"evidence_status": "VERIFIED"}, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_moderator_other_user_cannot_verify_evidence(self):
        """Another non-moderator user should also get 403 Forbidden."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])

        res = self.other_client.patch(
            verify_url, {"evidence_status": "VERIFIED"}, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_can_verify_evidence(self):
        """Moderators can verify evidence as VERIFIED."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])

        res = self.moderator_client.patch(
            verify_url,
            {
                "evidence_status": "VERIFIED",
                "moderator_notes": "Evidence looks legitimate",
            },
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["evidence_status"], "VERIFIED")

        # Verify database was updated
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.evidence_status, "VERIFIED")
        self.assertEqual(self.evidence.verified_by, self.moderator)
        self.assertIsNotNone(self.evidence.verified_at)
        self.assertEqual(self.evidence.moderator_notes, "Evidence looks legitimate")

    def test_moderator_can_reject_evidence(self):
        """Moderators can reject evidence as REJECTED."""

        verify_url = reverse(
            "evidence-verify",
            args=[str(self.evidence.id)],
        )

        res = self.moderator_client.patch(
            verify_url,
            {
                "evidence_status": (EvidenceSubmission.EvidenceStatus.REJECTED),
                "rejection_reason": (
                    EvidenceSubmission.RejectionReason.UNRELIABLE_SOURCE
                ),
                "moderator_notes": "Evidence is not credible",
            },
            format="json",
        )

        self.assertEqual(
            res.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            res.data["evidence_status"],
            EvidenceSubmission.EvidenceStatus.REJECTED,
        )

        self.evidence.refresh_from_db()

        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        )

        self.assertEqual(
            self.evidence.rejection_reason,
            EvidenceSubmission.RejectionReason.UNRELIABLE_SOURCE,
        )

        self.assertEqual(
            self.evidence.verified_by,
            self.moderator,
        )

        self.assertIsNotNone(self.evidence.verified_at)

        self.assertEqual(
            self.evidence.moderator_notes,
            "Evidence is not credible",
        )

    def test_moderator_notes_are_optional(self):
        """Moderators should be able to verify without providing notes."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])

        res = self.moderator_client.patch(
            verify_url, {"evidence_status": "VERIFIED"}, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.moderator_notes, "")

    def test_invalid_evidence_status_returns_400(self):
        """Invalid evidence_status should return 400 Bad Request."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])

        res = self.moderator_client.patch(
            verify_url, {"evidence_status": "INVALID_STATUS"}, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_new_user_starts_at_neutral_baseline(self):
        self.evidence.delete()

        components = calculate_trust_components(self.contributor)

        self.assertEqual(
            components["resolved_actions"],
            0,
        )
        self.assertEqual(
            components["smoothed_accuracy"],
            0.5,
        )
        self.assertEqual(
            components["trust_score"],
            50.0,
        )

    def test_one_verified_action_does_not_jump_to_high_trust(self):
        self.evidence.evidence_status = EvidenceSubmission.EvidenceStatus.VERIFIED
        self.evidence.verified_at = timezone.now()
        self.evidence.save(
            update_fields=[
                "evidence_status",
                "verified_at",
            ]
        )

        components = calculate_trust_components(self.contributor)

        self.assertEqual(
            components["resolved_actions"],
            1,
        )

        self.assertAlmostEqual(
            components["smoothed_accuracy"],
            0.6,
            places=4,
        )

        self.assertLess(
            components["trust_score"],
            60,
        )

    def test_rejected_action_can_reduce_score_below_baseline(self):
        self.evidence.evidence_status = EvidenceSubmission.EvidenceStatus.REJECTED
        self.evidence.verified_at = timezone.now()
        self.evidence.save(
            update_fields=[
                "evidence_status",
                "verified_at",
            ]
        )

        components = calculate_trust_components(self.contributor)

        self.assertEqual(
            components["resolved_actions"],
            1,
        )

        self.assertLess(
            components["trust_score"],
            50,
        )

    def test_unresolved_evidence_does_not_affect_quality_score(self):
        self.evidence.evidence_status = EvidenceSubmission.EvidenceStatus.UNVERIFIED
        self.evidence.save(update_fields=["evidence_status"])

        components = calculate_trust_components(self.contributor)

        self.assertEqual(
            components["resolved_actions"],
            0,
        )
        self.assertEqual(
            components["trust_score"],
            50.0,
        )

    def test_user_is_provisional_with_less_than_three_resolved_actions(self):
        components = calculate_trust_components(self.contributor)

        progression = get_reputation_progression(components)

        self.assertEqual(
            progression["status"],
            "PROVISIONAL",
        )
        self.assertEqual(
            progression["current_rank"],
            "Provisional",
        )

    def test_recompute_persists_calculated_score(self):
        self.evidence.evidence_status = EvidenceSubmission.EvidenceStatus.VERIFIED
        self.evidence.verified_at = timezone.now()
        self.evidence.save(
            update_fields=[
                "evidence_status",
                "verified_at",
            ]
        )

        components = recompute_user_trust_score(self.contributor.id)

        self.contributor_profile.refresh_from_db()

        self.assertEqual(
            self.contributor_profile.trust_score,
            components["trust_score"],
        )

    def test_verified_by_contains_moderator_info_in_response(self):
        """Response should include verified_by with moderator user info."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])

        res = self.moderator_client.patch(
            verify_url, {"evidence_status": "VERIFIED"}, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Check that verified_by contains user data
        self.assertIn("verified_by", res.data)
        if res.data["verified_by"]:  # Could be null if not serialized
            self.assertEqual(res.data["verified_by"]["username"], "moderator")

    def test_moderator_can_reverify_already_verified_evidence(self):
        """
        Once evidence is verified, subsequent verify calls should update it.
        This tests idempotency / allows re-verification by another moderator.
        """
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])

        # First verification
        res1 = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED", "moderator_notes": "First mod"},
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # Create another moderator
        moderator2 = User.objects.create_user(
            username="moderator2", email="mod2@test.com", password="pass1234"
        )
        moderator2_profile = moderator2.profile
        moderator2_profile.role = UserProfile.Role.MOD
        moderator2_profile.save(update_fields=["role"])
        moderator2_client = APIClient()
        moderator2_client.force_authenticate(user=moderator2)

        # Second moderator re-verifies with different notes
        res2 = moderator2_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED", "moderator_notes": "Second mod"},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

        # Check that it was updated by second moderator
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.verified_by, moderator2)
        self.assertEqual(self.evidence.moderator_notes, "Second mod")


class ModerationCaseFoundationTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="caseauthor",
            email="caseauthor@test.com",
            password="pass1234",
        )

        self.moderator = User.objects.create_user(
            username="casemoderator",
            email="casemoderator@test.com",
            password="pass1234",
        )

        self.moderator.profile.role = UserProfile.Role.MOD
        self.moderator.profile.save(update_fields=["role"])

        self.other_moderator = User.objects.create_user(
            username="othercasemod",
            email="othercasemod@test.com",
            password="pass1234",
        )

        self.other_moderator.profile.role = UserProfile.Role.MOD
        self.other_moderator.profile.save(update_fields=["role"])

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Moderation case test claim.",
            verified_via=Claim.VerificationSource.PENDING,
        )

        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.author,
            caption="Moderation case test thread.",
        )

        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.author,
            evidence_caption="Moderation case evidence.",
            evidence_type=(EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION),
            evidence_url="https://example.com/evidence",
            contributor_trust_snapshot=50.0,
        )

    def test_create_safety_case_creates_audit_event(self):
        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.moderator,
            source=ModerationCase.Source.USER_REPORT,
            thread=self.thread,
        )

        self.assertEqual(
            case.status,
            ModerationCase.Status.OPEN,
        )
        self.assertEqual(
            case.thread,
            self.thread,
        )
        self.assertIsNone(case.claim)
        self.assertIsNone(case.evidence_submission)

        event = case.events.get()

        self.assertEqual(
            event.event_type,
            ModerationEvent.EventType.CASE_CREATED,
        )
        self.assertEqual(
            event.actor,
            self.moderator,
        )

    def test_case_type_requires_correct_target(self):
        with self.assertRaises(InvalidModerationCaseTarget):
            create_moderation_case(
                case_type=ModerationCase.CaseType.SAFETY,
                actor=self.moderator,
                claim=self.claim,
            )

    def test_duplicate_active_safety_case_is_rejected(self):
        create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.moderator,
            source=ModerationCase.Source.USER_REPORT,
            thread=self.thread,
        )

        with self.assertRaises(DuplicateActiveModerationCase):
            create_moderation_case(
                case_type=ModerationCase.CaseType.SAFETY,
                actor=self.moderator,
                source=ModerationCase.Source.USER_REPORT,
                thread=self.thread,
            )

    def test_valid_case_lifecycle(self):
        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.moderator,
            thread=self.thread,
        )

        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.IN_REVIEW,
            actor=self.moderator,
        )

        self.assertEqual(
            case.status,
            ModerationCase.Status.IN_REVIEW,
        )

        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.ESCALATED,
            actor=self.moderator,
            reason_code="SPECIALIST_REVIEW",
        )

        self.assertEqual(
            case.status,
            ModerationCase.Status.ESCALATED,
        )

        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.IN_REVIEW,
            actor=self.other_moderator,
        )

        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.RESOLVED,
            actor=self.other_moderator,
            resolution_code="NO_VIOLATION",
            resolution_summary="No policy violation found.",
        )

        self.assertEqual(
            case.status,
            ModerationCase.Status.RESOLVED,
        )
        self.assertEqual(
            case.resolved_by,
            self.other_moderator,
        )
        self.assertIsNotNone(case.resolved_at)
        self.assertEqual(
            case.resolution_code,
            "NO_VIOLATION",
        )

        self.assertEqual(
            case.events.count(),
            5,
        )

    def test_invalid_direct_resolution_is_rejected(self):
        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.moderator,
            thread=self.thread,
        )

        with self.assertRaises(InvalidModerationTransition):
            transition_moderation_case(
                case,
                next_status=ModerationCase.Status.RESOLVED,
                actor=self.moderator,
            )

        case.refresh_from_db()

        self.assertEqual(
            case.status,
            ModerationCase.Status.OPEN,
        )

    def test_case_can_be_claimed_and_unassigned(self):
        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.moderator,
            thread=self.thread,
        )

        case = assign_moderation_case(
            case,
            assignee=self.moderator,
            actor=self.moderator,
        )

        self.assertEqual(
            case.assigned_to,
            self.moderator,
        )
        self.assertIsNotNone(case.assigned_at)

        self.assertTrue(
            case.events.filter(
                event_type=(ModerationEvent.EventType.CASE_CLAIMED)
            ).exists()
        )

        case = unassign_moderation_case(
            case,
            actor=self.moderator,
        )

        self.assertIsNone(case.assigned_to)
        self.assertIsNone(case.assigned_at)

    def test_thread_flag_can_preserve_resolution_history(self):
        flag = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.moderator,
            reason=ThreadFlag.Reason.SPAM,
            notes="Test report",
        )

        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.moderator,
            source=ModerationCase.Source.USER_REPORT,
            thread=self.thread,
        )

        flag.resolution_case = case
        flag.resolved_at = timezone.now()

        flag.save(
            update_fields=[
                "resolution_case",
                "resolved_at",
            ]
        )

        flag.refresh_from_db()

        self.assertEqual(
            flag.resolution_case,
            case,
        )
        self.assertIsNotNone(flag.resolved_at)

    def test_moderation_event_is_append_only(self):
        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.moderator,
            thread=self.thread,
        )

        event = case.events.get(event_type=(ModerationEvent.EventType.CASE_CREATED))

        event.notes = "Attempted rewrite"

        with self.assertRaises(ValidationError):
            event.save()

        with self.assertRaises(ValidationError):
            event.delete()

    def test_ensure_safety_case_reuses_active_case(self):
        from .moderation_service import ensure_safety_case

        first = ensure_safety_case(
            thread=self.thread,
            actor=self.moderator,
        )

        second = ensure_safety_case(
            thread=self.thread,
            actor=self.other_moderator,
        )

        self.assertEqual(
            first.id,
            second.id,
        )

        self.assertEqual(
            ModerationCase.objects.filter(
                case_type=ModerationCase.CaseType.SAFETY,
                thread=self.thread,
            ).count(),
            1,
        )

    def test_escalating_safety_case_does_not_close_thread(self):
        from .moderation_service import (
            ensure_safety_case,
            escalate_safety_case,
        )

        flag = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.moderator,
            reason=ThreadFlag.Reason.SPAM,
        )

        case = ensure_safety_case(
            thread=self.thread,
            actor=self.moderator,
        )

        case = escalate_safety_case(
            thread=self.thread,
            actor=self.moderator,
            notes="Needs deeper review.",
        )

        self.thread.refresh_from_db()
        flag.refresh_from_db()

        self.assertEqual(
            case.status,
            ModerationCase.Status.ESCALATED,
        )

        self.assertEqual(
            self.thread.status,
            Thread.Status.OPEN,
        )

        self.assertIsNone(flag.resolved_at)

        self.assertEqual(
            FlagResolutionLog.objects.filter(thread=self.thread).count(),
            0,
        )

    def test_dismiss_preserves_report_history(self):
        from .moderation_service import (
            ensure_safety_case,
            resolve_safety_case,
        )

        flag = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.moderator,
            reason=ThreadFlag.Reason.SPAM,
            notes="Possible spam",
        )

        case = ensure_safety_case(
            thread=self.thread,
            actor=self.moderator,
        )

        result = resolve_safety_case(
            thread=self.thread,
            actor=self.moderator,
            action="DISMISS",
            notes="No violation found.",
        )

        flag.refresh_from_db()
        self.thread.refresh_from_db()
        case.refresh_from_db()

        self.assertEqual(
            result["case"].status,
            ModerationCase.Status.RESOLVED,
        )

        self.assertEqual(
            self.thread.status,
            Thread.Status.OPEN,
        )

        self.assertIsNotNone(flag.resolved_at)

        self.assertEqual(
            flag.resolution_case,
            case,
        )

        log = FlagResolutionLog.objects.get(thread=self.thread)

        self.assertEqual(
            log.resolved_action,
            "DISMISS",
        )

        self.assertFalse(log.is_valid_report)

    def test_remove_resolves_case_and_hides_thread(self):
        from .moderation_service import (
            ensure_safety_case,
            resolve_safety_case,
        )

        flag = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.moderator,
            reason=ThreadFlag.Reason.HARASSMENT,
        )

        ensure_safety_case(
            thread=self.thread,
            actor=self.moderator,
        )

        result = resolve_safety_case(
            thread=self.thread,
            actor=self.moderator,
            action="REMOVE",
            notes="Confirmed policy violation.",
        )

        self.thread.refresh_from_db()
        flag.refresh_from_db()

        self.assertEqual(
            self.thread.status,
            Thread.Status.REJECTED,
        )

        self.assertEqual(
            result["case"].status,
            ModerationCase.Status.RESOLVED,
        )

        self.assertIsNotNone(flag.resolved_at)

        log = FlagResolutionLog.objects.get(thread=self.thread)

        self.assertTrue(log.is_valid_report)

    def test_same_user_can_report_again_after_resolution(self):
        from .moderation_service import (
            ensure_safety_case,
            resolve_safety_case,
        )

        first_flag = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.moderator,
            reason=ThreadFlag.Reason.SPAM,
        )

        ensure_safety_case(
            thread=self.thread,
            actor=self.moderator,
        )

        resolve_safety_case(
            thread=self.thread,
            actor=self.moderator,
            action="DISMISS",
        )

        first_flag.refresh_from_db()

        self.assertIsNotNone(first_flag.resolved_at)

        second_flag = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.moderator,
            reason=ThreadFlag.Reason.HARASSMENT,
        )

        self.assertNotEqual(
            first_flag.id,
            second_flag.id,
        )

        self.assertIsNone(second_flag.resolved_at)

    def test_reporting_thread_does_not_change_community_status(self):
        client = APIClient()
        client.force_authenticate(user=self.author)

        self.assertEqual(
            self.thread.status,
            Thread.Status.OPEN,
        )

        response = client.post(
            reverse("thread-flag-list"),
            {
                "thread_id": str(self.thread.id),
                "reason": (ThreadFlag.Reason.SPAM),
                "notes": "Possible spam.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.thread.refresh_from_db()

        self.assertEqual(
            self.thread.status,
            Thread.Status.OPEN,
        )

        self.assertEqual(
            ModerationCase.objects.filter(
                case_type=(ModerationCase.CaseType.SAFETY),
                thread=self.thread,
                status=(ModerationCase.Status.OPEN),
            ).count(),
            1,
        )

        self.assertEqual(
            ThreadFlag.objects.filter(
                thread=self.thread,
                resolved_at__isnull=True,
            ).count(),
            1,
        )


class OrganizationFoundationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="partneruser",
            email="partner@test.com",
            password="pass1234",
        )

        self.other_user = User.objects.create_user(
            username="partneruser2",
            email="partner2@test.com",
            password="pass1234",
        )

        self.system_moderator = User.objects.create_user(
            username="systemmod",
            email="systemmod@test.com",
            password="pass1234",
        )

        self.system_moderator.profile.role = UserProfile.Role.MOD
        self.system_moderator.profile.save(update_fields=["role"])

        self.organization = Organization.objects.create(
            name="Truth Research Lab",
            slug="truth-research-lab",
            organization_type=(Organization.OrganizationType.RESEARCH),
        )

    def test_organization_starts_unverified_and_not_partner(self):
        self.assertEqual(
            self.organization.verification_status,
            (Organization.VerificationStatus.UNVERIFIED),
        )

        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.NONE,
        )

    def test_organization_name_is_case_insensitively_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(
                    name="truth research lab",
                    slug="truth-research-lab-2",
                )

    def test_user_can_only_have_one_membership_per_organization(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.RESEARCHER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=self.organization,
                    user=self.user,
                    role=(OrganizationMembership.Role.MODERATOR),
                    status=(OrganizationMembership.Status.ACTIVE),
                )

    def test_verified_partner_lead_verifier_gets_fact_check_capabilities(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        capabilities = get_user_capabilities(
            self.user,
            organization=self.organization,
        )

        self.assertIn(
            PartnerCapability.REVIEW_EVIDENCE,
            capabilities,
        )

        self.assertIn(
            PartnerCapability.ADJUDICATE,
            capabilities,
        )

        self.assertIn(
            PartnerCapability.PUBLISH_FACT_CHECK,
            capabilities,
        )

        self.assertNotIn(
            PartnerCapability.REVIEW_SAFETY,
            capabilities,
        )

    def test_unverified_partner_does_not_get_verification_capabilities(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        capabilities = get_user_capabilities(
            self.user,
            organization=self.organization,
        )

        self.assertNotIn(
            PartnerCapability.ADJUDICATE,
            capabilities,
        )

        self.assertNotIn(
            PartnerCapability.PUBLISH_FACT_CHECK,
            capabilities,
        )

    def test_researcher_can_draft_but_not_adjudicate(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.RESEARCHER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.assertTrue(
            has_capability(
                self.user,
                (PartnerCapability.CREATE_FACT_CHECK_DRAFT),
                organization=self.organization,
            )
        )

        self.assertFalse(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

    def test_owner_can_manage_unverified_organization(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.OWNER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.assertTrue(
            has_capability(
                self.user,
                (PartnerCapability.MANAGE_ORGANIZATION),
                organization=self.organization,
            )
        )

        self.assertFalse(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

    def test_suspended_membership_grants_no_partner_capabilities(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.SUSPENDED),
        )

        self.assertEqual(
            get_user_capabilities(
                self.user,
                organization=self.organization,
            ),
            set(),
        )

    def test_system_moderator_retains_system_capabilities(self):
        capabilities = get_user_capabilities(self.system_moderator)

        self.assertIn(
            PartnerCapability.REVIEW_SAFETY,
            capabilities,
        )

        self.assertIn(
            PartnerCapability.REVIEW_EVIDENCE,
            capabilities,
        )

        self.assertIn(
            PartnerCapability.ADJUDICATE,
            capabilities,
        )

        self.assertIn(
            PartnerCapability.PUBLISH_FACT_CHECK,
            capabilities,
        )

    def test_moderation_case_can_record_responsible_organization(self):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Partner case test.",
        )

        thread = Thread.objects.create(
            claim=claim,
            author=self.user,
            caption="Partner case thread.",
        )

        case = create_moderation_case(
            case_type=(ModerationCase.CaseType.SAFETY),
            actor=self.system_moderator,
            thread=thread,
            organization=self.organization,
        )

        self.assertEqual(
            case.organization,
            self.organization,
        )

    def test_partner_capability_does_not_leak_across_organizations(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        other_organization = Organization.objects.create(
            name="Independent Verification Lab",
            slug="independent-verification-lab",
            organization_type=(Organization.OrganizationType.RESEARCH),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.assertTrue(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

        self.assertFalse(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
                organization=other_organization,
            )
        )

    def test_partner_verification_capability_requires_organization_scope(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.assertFalse(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
            )
        )

    def test_partner_suspension_revokes_verification_capabilities(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.assertTrue(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED

        self.organization.save(update_fields=["partner_status"])

        self.assertFalse(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

        self.assertFalse(
            has_capability(
                self.user,
                PartnerCapability.PUBLISH_FACT_CHECK,
                organization=self.organization,
            )
        )

    def test_organization_verification_revocation_removes_authority(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.MODERATOR),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.assertTrue(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

        self.organization.verification_status = Organization.VerificationStatus.REJECTED

        self.organization.save(update_fields=["verification_status"])

        self.assertFalse(
            has_capability(
                self.user,
                PartnerCapability.ADJUDICATE,
                organization=self.organization,
            )
        )

    def test_partner_can_only_handle_case_for_own_organization(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Scoped partner case.",
        )

        case = create_moderation_case(
            case_type=(ModerationCase.CaseType.ADJUDICATION),
            actor=self.system_moderator,
            claim=claim,
            organization=self.organization,
        )

        self.assertTrue(
            has_case_capability(
                self.user,
                case,
                PartnerCapability.ADJUDICATE,
            )
        )

        other_organization = Organization.objects.create(
            name="Another Verification Group",
            slug="another-verification-group",
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        case.organization = other_organization
        case.save(
            update_fields=[
                "organization",
                "updated_at",
            ]
        )

        self.assertFalse(
            has_case_capability(
                self.user,
                case,
                PartnerCapability.ADJUDICATE,
            )
        )

    def test_partner_cannot_handle_unscoped_platform_case(self):
        self.organization.verification_status = Organization.VerificationStatus.VERIFIED

        self.organization.partner_status = Organization.PartnerStatus.ACTIVE

        self.organization.save(
            update_fields=[
                "verification_status",
                "partner_status",
            ]
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Platform-owned adjudication.",
        )

        case = create_moderation_case(
            case_type=(ModerationCase.CaseType.ADJUDICATION),
            actor=self.system_moderator,
            claim=claim,
        )

        self.assertIsNone(case.organization)

        self.assertFalse(
            has_case_capability(
                self.user,
                case,
                PartnerCapability.ADJUDICATE,
            )
        )

        self.assertTrue(
            has_case_capability(
                self.system_moderator,
                case,
                PartnerCapability.ADJUDICATE,
            )
        )


class EvidenceCaseFoundationTests(APITestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="evidencecontributor",
            email="evidence@test.com",
            password="pass1234",
        )

        self.moderator = User.objects.create_user(
            username="evidencemoderator",
            email="evidencemod@test.com",
            password="pass1234",
        )

        self.moderator.profile.role = UserProfile.Role.MOD

        self.moderator.profile.save(update_fields=["role"])

        self.second_moderator = User.objects.create_user(
            username="evidencemoderator2",
            email="evidencemod2@test.com",
            password="pass1234",
        )

        self.second_moderator.profile.role = UserProfile.Role.MOD

        self.second_moderator.profile.save(update_fields=["role"])

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("Evidence review test claim."),
        )

        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.contributor,
            caption="Evidence review thread.",
        )

        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption=("Evidence review submission."),
            evidence_url=("https://example.com/evidence"),
            evidence_type=(EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION),
            evidence_status=(EvidenceSubmission.EvidenceStatus.UNVERIFIED),
            contributor_trust_snapshot=50.0,
        )

    def test_ensure_evidence_case_creates_one_active_case(self):
        first = ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        second = ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        self.assertEqual(
            first.id,
            second.id,
        )

        self.assertEqual(
            first.case_type,
            ModerationCase.CaseType.EVIDENCE,
        )

        self.assertEqual(
            first.status,
            ModerationCase.Status.OPEN,
        )

    def test_verified_evidence_resolves_case(self):
        case = ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        result = review_evidence_submission(
            evidence=self.evidence,
            actor=self.moderator,
            evidence_status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
            moderator_notes=("Source directly supports the claim."),
        )

        self.evidence.refresh_from_db()
        case.refresh_from_db()

        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.VERIFIED,
        )

        self.assertIsNone(self.evidence.rejection_reason)

        self.assertEqual(
            case.status,
            ModerationCase.Status.RESOLVED,
        )

        self.assertEqual(
            result["contributor_id"],
            self.contributor.id,
        )

    def test_rejected_evidence_requires_reason(self):
        ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        with self.assertRaises(InvalidEvidenceDecision):
            review_evidence_submission(
                evidence=self.evidence,
                actor=self.moderator,
                evidence_status=(EvidenceSubmission.EvidenceStatus.REJECTED),
            )

    def test_rejected_evidence_records_structured_reason(self):
        ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        review_evidence_submission(
            evidence=self.evidence,
            actor=self.moderator,
            evidence_status=(EvidenceSubmission.EvidenceStatus.REJECTED),
            rejection_reason=(EvidenceSubmission.RejectionReason.UNRELIABLE_SOURCE),
            moderator_notes=("Publisher cannot be verified."),
        )

        self.evidence.refresh_from_db()

        self.assertEqual(
            self.evidence.rejection_reason,
            (EvidenceSubmission.RejectionReason.UNRELIABLE_SOURCE),
        )

    def test_verified_decision_clears_old_rejection_reason(self):
        self.evidence.evidence_status = EvidenceSubmission.EvidenceStatus.REJECTED

        self.evidence.rejection_reason = EvidenceSubmission.RejectionReason.IRRELEVANT

        self.evidence.save(
            update_fields=[
                "evidence_status",
                "rejection_reason",
            ]
        )

        ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        review_evidence_submission(
            evidence=self.evidence,
            actor=self.moderator,
            evidence_status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
        )

        self.evidence.refresh_from_db()

        self.assertIsNone(self.evidence.rejection_reason)

    def test_resolved_evidence_case_can_be_reopened_for_review(self):
        case = ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        review_evidence_submission(
            evidence=self.evidence,
            actor=self.moderator,
            evidence_status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
        )

        review_evidence_submission(
            evidence=self.evidence,
            actor=self.second_moderator,
            evidence_status=(EvidenceSubmission.EvidenceStatus.REJECTED),
            rejection_reason=(EvidenceSubmission.RejectionReason.MISREPRESENTS_SOURCE),
        )

        case.refresh_from_db()
        self.evidence.refresh_from_db()

        self.assertEqual(
            case.status,
            ModerationCase.Status.RESOLVED,
        )

        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        )

        self.assertTrue(
            case.events.filter(
                event_type=(ModerationEvent.EventType.EVIDENCE_REOPENED)
            ).exists()
        )

        self.assertEqual(
            case.events.filter(
                event_type=(ModerationEvent.EventType.EVIDENCE_VERIFIED)
            ).count(),
            1,
        )

        self.assertEqual(
            case.events.filter(
                event_type=(ModerationEvent.EventType.EVIDENCE_REJECTED)
            ).count(),
            1,
        )

    def test_stale_evidence_review_is_rejected(self):
        ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        self.evidence.evidence_status = EvidenceSubmission.EvidenceStatus.VERIFIED

        self.evidence.save(
            update_fields=[
                "evidence_status",
            ]
        )

        with self.assertRaises(EvidenceReviewConflict):
            review_evidence_submission(
                evidence=self.evidence,
                actor=self.moderator,
                evidence_status=(EvidenceSubmission.EvidenceStatus.REJECTED),
                rejection_reason=(EvidenceSubmission.RejectionReason.IRRELEVANT),
                expected_status=(EvidenceSubmission.EvidenceStatus.UNVERIFIED),
            )


class EvidenceReviewCapabilityTests(APITestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="partner-evidence-author",
            email="partner-author@test.com",
            password="pass1234",
        )

        self.partner_reviewer = User.objects.create_user(
            username="partner-reviewer",
            email="partner-reviewer@test.com",
            password="pass1234",
        )

        self.outsider = User.objects.create_user(
            username="partner-outsider",
            email="partner-outsider@test.com",
            password="pass1234",
        )

        self.organization = Organization.objects.create(
            name="Evidence Verification Lab",
            slug="evidence-verification-lab",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.partner_reviewer,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("Partner evidence review claim."),
        )

        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.contributor,
            caption=("Partner evidence review thread."),
        )

        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption=("Partner-reviewed evidence."),
            evidence_url=("https://example.com/" "partner-evidence"),
            evidence_type=(EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION),
            contributor_trust_snapshot=50.0,
        )

        self.case = ensure_evidence_case(
            evidence=self.evidence,
            actor=self.contributor,
        )

        self.case.organization = self.organization

        self.case.save(
            update_fields=[
                "organization",
                "updated_at",
            ]
        )

    def test_partner_reviewer_can_review_own_organization_case(self):
        client = APIClient()

        client.force_authenticate(user=self.partner_reviewer)

        response = client.patch(
            reverse(
                "evidence-verify",
                kwargs={
                    "pk": self.evidence.id,
                },
            ),
            {
                "evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
                "expected_status": EvidenceSubmission.EvidenceStatus.UNVERIFIED,
                "moderator_notes": "Source is credible.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.evidence.refresh_from_db()

        self.assertEqual(
            self.evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.VERIFIED,
        )

    def test_outsider_cannot_review_partner_case(self):
        client = APIClient()

        client.force_authenticate(user=self.outsider)

        response = client.patch(
            reverse(
                "evidence-verify",
                kwargs={
                    "pk": self.evidence.id,
                },
            ),
            {
                "evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_reviewer_cannot_review_own_evidence(self):
        own_evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=(self.partner_reviewer),
            evidence_caption=("Reviewer-owned evidence."),
            evidence_url=("https://example.com/" "reviewer-evidence"),
            contributor_trust_snapshot=50.0,
        )

        own_case = ensure_evidence_case(
            evidence=own_evidence,
            actor=self.partner_reviewer,
        )

        own_case.organization = self.organization

        own_case.save(
            update_fields=[
                "organization",
                "updated_at",
            ]
        )

        client = APIClient()

        client.force_authenticate(user=self.partner_reviewer)

        response = client.patch(
            reverse(
                "evidence-verify",
                kwargs={
                    "pk": own_evidence.id,
                },
            ),
            {
                "evidence_status": EvidenceSubmission.EvidenceStatus.VERIFIED,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_rejection_requires_structured_reason(self):
        client = APIClient()

        client.force_authenticate(user=self.partner_reviewer)

        response = client.patch(
            reverse(
                "evidence-verify",
                kwargs={
                    "pk": self.evidence.id,
                },
            ),
            {
                "evidence_status": EvidenceSubmission.EvidenceStatus.REJECTED,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_partner_can_read_scoped_evidence_queue(self):
        client = APIClient()

        client.force_authenticate(user=self.partner_reviewer)

        response = client.get(
            reverse("moderation_evidence_queue"),
            {
                "organization_id": str(self.organization.id),
                "status": EvidenceSubmission.EvidenceStatus.UNVERIFIED,
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

    def test_partner_queue_requires_organization_scope(self):
        client = APIClient()

        client.force_authenticate(user=self.partner_reviewer)

        response = client.get(reverse("moderation_evidence_queue"))

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_evidence_queue_rejects_invalid_pagination(self):
        self.partner_reviewer.profile.role = UserProfile.Role.MOD

        self.partner_reviewer.profile.save(update_fields=["role"])

        client = APIClient()

        client.force_authenticate(user=self.partner_reviewer)

        response = client.get(
            reverse("moderation_evidence_queue"),
            {
                "limit": "not-a-number",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        response = client.get(
            reverse("moderation_evidence_queue"),
            {
                "limit": "101",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )


class OptionalFactCheckAuthTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="detector",
            email="detector@test.com",
            password="pass1234",
        )
        self.user_profile = UserProfile.objects.get(user=self.user)
        self.user_profile.trust_score = 50.0
        self.user_profile.save(update_fields=["trust_score"])

        self.auth_client = APIClient()
        self.auth_client.force_authenticate(user=self.user)

    @patch("api.views.text_fact_check_process.delay")
    @patch("api.views.find_matching_claim")
    @patch("api.views.compute_fingerprint")
    def test_verify_text_allows_guest_without_history_or_points(
        self,
        mock_compute_fingerprint,
        mock_find_matching_claim,
        mock_delay,
    ):
        mock_compute_fingerprint.return_value = None
        mock_find_matching_claim.return_value = None
        mock_delay.return_value = None

        res = self.client.post(
            reverse("verify_text"),
            {"text": "Guest fact-check request."},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(ClaimCheckHistory.objects.count(), 0)

    @patch("api.views.text_fact_check_process.delay")
    @patch("api.views.find_matching_claim")
    @patch("api.views.compute_fingerprint")
    def test_verify_text_records_history_and_points_for_authenticated_user(
        self,
        mock_compute_fingerprint,
        mock_find_matching_claim,
        mock_delay,
    ):
        mock_compute_fingerprint.return_value = None
        mock_find_matching_claim.return_value = None
        mock_delay.return_value = None

        initial_points = self.user.profile.fact_check_points

        res = self.auth_client.post(
            reverse("verify_text"),
            {"text": "Authenticated fact-check request."},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        claim_id = res.json()["claim_id"]

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.fact_check_points, initial_points + 1)
        self.assertTrue(
            ClaimCheckHistory.objects.filter(user=self.user, claim_id=claim_id).exists()
        )


class FactCheckThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self._original_rates = FactCheckRateThrottle.THROTTLE_RATES
        FactCheckRateThrottle.THROTTLE_RATES = {
            **(self._original_rates or {}),
            "fact_check": "3/minute",
        }

    def tearDown(self):
        FactCheckRateThrottle.THROTTLE_RATES = self._original_rates
        cache.clear()

    def _assert_endpoint_throttled(self, url, payload):
        first = self.client.post(url, payload, format="json")
        second = self.client.post(url, payload, format="json")
        third = self.client.post(url, payload, format="json")
        fourth = self.client.post(url, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(third.status_code, status.HTTP_200_OK)
        self.assertEqual(fourth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch("api.views.text_fact_check_process.delay")
    @patch("api.views.find_matching_claim")
    @patch("api.views.compute_fingerprint")
    def test_verify_text_endpoint_is_rate_limited(
        self,
        mock_compute_fingerprint,
        mock_find_matching_claim,
        mock_delay,
    ):
        mock_compute_fingerprint.return_value = None
        mock_find_matching_claim.return_value = None
        mock_delay.return_value = None
        self._assert_endpoint_throttled(
            reverse("verify_text"),
            {"text": "Claim text for throttling test."},
        )

    @patch("api.views.url_fact_check_process.delay")
    @patch("api.views.check_url_threat_reputation")
    @patch("api.views.validate_public_url")
    def test_verify_url_endpoint_is_rate_limited(
        self,
        mock_validate_public_url,
        mock_check_url_threat_reputation,
        mock_delay,
    ):
        mock_validate_public_url.return_value = ("https://example.com/safe", None)
        mock_check_url_threat_reputation.return_value = {"status": "SAFE"}
        mock_delay.return_value = None

        self._assert_endpoint_throttled(
            reverse("verify_url"),
            {"url": "https://example.com/source"},
        )

    @patch("api.views.snippet_fact_check_process.delay")
    @patch("api.views.upload_image_to_database")
    @patch("api.views.process_image")
    def test_analyze_snippet_endpoint_is_rate_limited(
        self,
        mock_process_image,
        mock_upload_image_to_database,
        mock_delay,
    ):
        mock_process_image.return_value = ("imagehash", None)
        mock_upload_image_to_database.return_value = "https://example.com/media.png"
        mock_delay.return_value = None

        self._assert_endpoint_throttled(
            reverse("analyze_snippet"),
            {"image_data": "data:image/png;base64,AAA"},
        )


@override_settings(
    CORS_ALLOW_ALL_ORIGINS=False,
    CORS_ALLOWED_ORIGINS=[
        "http://localhost:5173",
        "chrome-extension://akdengbmiapbfmlcbogjbeafcbbanpgp",
    ],
)
class CorsPolicyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self._original_rates = FactCheckRateThrottle.THROTTLE_RATES
        FactCheckRateThrottle.THROTTLE_RATES = {
            **(self._original_rates or {}),
            "fact_check": "100/minute",
        }

    def tearDown(self):
        FactCheckRateThrottle.THROTTLE_RATES = self._original_rates
        cache.clear()

    def test_preflight_allows_extension_origin_for_analyze(self):
        origin = "chrome-extension://akdengbmiapbfmlcbogjbeafcbbanpgp"
        res = self.client.options(
            reverse("analyze_snippet"),
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
        )

        self.assertIn(res.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])
        self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), origin)

    def test_preflight_blocks_disallowed_web_origin_for_analyze(self):
        disallowed_origin = "https://www.facebook.com"
        res = self.client.options(
            reverse("analyze_snippet"),
            HTTP_ORIGIN=disallowed_origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
        )

        self.assertIn(res.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])
        self.assertIsNone(res.headers.get("Access-Control-Allow-Origin"))

    @patch("api.views.text_fact_check_process.delay")
    @patch("api.views.find_matching_claim")
    @patch("api.views.compute_fingerprint")
    def test_post_allows_extension_origin_for_verify_text(
        self,
        mock_compute_fingerprint,
        mock_find_matching_claim,
        mock_delay,
    ):
        mock_compute_fingerprint.return_value = None
        mock_find_matching_claim.return_value = None
        mock_delay.return_value = None

        origin = "chrome-extension://akdengbmiapbfmlcbogjbeafcbbanpgp"
        res = self.client.post(
            reverse("verify_text"),
            {"text": "Origin header CORS validation."},
            format="json",
            HTTP_ORIGIN=origin,
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), origin)

    @patch("api.views.text_fact_check_process.delay")
    @patch("api.views.find_matching_claim")
    @patch("api.views.compute_fingerprint")
    def test_post_blocks_disallowed_web_origin_for_verify_text(
        self,
        mock_compute_fingerprint,
        mock_find_matching_claim,
        mock_delay,
    ):
        mock_compute_fingerprint.return_value = None
        mock_find_matching_claim.return_value = None
        mock_delay.return_value = None

        disallowed_origin = "https://www.facebook.com"
        res = self.client.post(
            reverse("verify_text"),
            {"text": "Disallowed origin validation."},
            format="json",
            HTTP_ORIGIN=disallowed_origin,
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNone(res.headers.get("Access-Control-Allow-Origin"))


class VerificationEvidenceModelTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="pass1234",
        )

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Test claim",
        )

    def test_canonical_source_creation(self):
        source = CanonicalSource.objects.create(
            name="Reuters",
            domain="reuters.com",
            source_type="NEWS",
            canonical_url="https://www.reuters.com",
        )

        self.assertEqual(source.name, "Reuters")
        self.assertEqual(source.domain, "reuters.com")
        self.assertEqual(source.source_type, "NEWS")

    def test_evidence_source_creation(self):
        source = EvidenceSource.objects.create(
            provider="TAVILY",
            url="https://example.com/article",
            canonical_url="https://example.com/article",
            title="Example Article",
            publisher="Example News",
            source_type="NEWS",
            content="Example article content",
            content_hash="a" * 64,
        )

        self.assertEqual(source.provider, "TAVILY")
        self.assertEqual(source.publisher, "Example News")
        self.assertEqual(source.content_hash, "a" * 64)

    def test_evidence_source_can_link_to_canonical_source(self):
        canonical = CanonicalSource.objects.create(
            name="Reuters",
            domain="reuters.com",
            source_type="NEWS",
        )

        evidence = EvidenceSource.objects.create(
            canonical_source=canonical,
            provider="TAVILY",
            url="https://www.reuters.com/example",
            publisher="Reuters",
            source_type="NEWS",
        )

        self.assertEqual(evidence.canonical_source, canonical)
        self.assertIn(evidence, canonical.evidence_sources.all())

    def test_verification_run_creation(self):
        run = VerificationRun.objects.create(
            claim=self.claim,
            triggered_by=self.user,
            pipeline_version="1.0.0",
        )

        self.assertEqual(run.status, VerificationRun.Status.PENDING)
        self.assertEqual(run.pipeline_version, "1.0.0")
        self.assertEqual(run.triggered_by, self.user)

    def test_verification_evidence_creation(self):
        run = VerificationRun.objects.create(
            claim=self.claim,
            triggered_by=self.user,
        )

        source = EvidenceSource.objects.create(
            provider="TAVILY",
            url="https://example.com/article",
            title="Example Article",
            publisher="Example News",
        )

        evidence = VerificationEvidence.objects.create(
            verification_run=run,
            evidence_source=source,
            relevance_score=0.90,
            directness_score=0.80,
            recency_score=0.75,
            stance=VerificationEvidence.Stance.SUPPORTS,
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
        )

        self.assertEqual(evidence.verification_run, run)
        self.assertEqual(evidence.evidence_source, source)
        self.assertEqual(evidence.stance, "SUPPORTS")
        self.assertEqual(evidence.evidence_role, "SECONDARY")


class UserFactCheckLibraryTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="library_user",
            email="library@test.com",
            password="pass1234",
        )

        self.other_user = User.objects.create_user(
            username="other_library_user",
            email="other-library@test.com",
            password="pass1234",
        )

        self.client.force_authenticate(user=self.user)

        self.claim_fact = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Verified renewable energy claim",
            ai_summary="Renewable energy summary",
            ai_verdict="FACT",
            verified_via=Claim.VerificationSource.AI_EXTENSION,
        )

        self.claim_misleading = Claim.objects.create(
            claim_type=Claim.ClaimType.IMAGE,
            context_text="Misleading school incident claim",
            ai_summary="School incident summary",
            ai_verdict="MISLEADING",
            verified_via=Claim.VerificationSource.AI_EXTENSION,
        )

        self.claim_other_user = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="Other user's private history",
            ai_verdict="FAKE",
            verified_via=Claim.VerificationSource.AI_EXTENSION,
        )

        ClaimCheckHistory.objects.create(
            user=self.user,
            claim=self.claim_fact,
        )

        ClaimCheckHistory.objects.create(
            user=self.user,
            claim=self.claim_misleading,
        )

        ClaimCheckHistory.objects.create(
            user=self.other_user,
            claim=self.claim_other_user,
        )

        self.user.profile.saved_claims.add(self.claim_fact)

        self.url = reverse("user_fact_check_library")

    def test_library_requires_authentication(self):
        client = APIClient()

        response = client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_history_only_returns_current_users_claims(self):
        response = self.client.get(
            self.url,
            {"view": "history"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {item["id"] for item in response.data["results"]}

        self.assertIn(
            str(self.claim_fact.id),
            returned_ids,
        )

        self.assertIn(
            str(self.claim_misleading.id),
            returned_ids,
        )

        self.assertNotIn(
            str(self.claim_other_user.id),
            returned_ids,
        )

    def test_saved_view_only_returns_saved_claims(self):
        response = self.client.get(
            self.url,
            {"view": "saved"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            str(self.claim_fact.id),
        )

        self.assertTrue(response.data["results"][0]["is_saved"])

    def test_response_includes_collection_counts(self):
        response = self.client.get(
            self.url,
            {"view": "history"},
        )

        self.assertEqual(
            response.data["counts"]["history"],
            2,
        )

        self.assertEqual(
            response.data["counts"]["saved"],
            1,
        )

    def test_search_filters_server_side(self):
        response = self.client.get(
            self.url,
            {
                "view": "history",
                "search": "renewable",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            str(self.claim_fact.id),
        )

    def test_verdict_filter(self):
        response = self.client.get(
            self.url,
            {
                "view": "history",
                "verdict": "MISLEADING",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            str(self.claim_misleading.id),
        )

    def test_claim_type_filter(self):
        response = self.client.get(
            self.url,
            {
                "view": "history",
                "type": "IMAGE",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            str(self.claim_misleading.id),
        )

    def test_invalid_view_returns_400(self):
        response = self.client.get(
            self.url,
            {"view": "invalid"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_invalid_verdict_returns_400(self):
        response = self.client.get(
            self.url,
            {
                "view": "history",
                "verdict": "UNKNOWN",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_invalid_claim_type_returns_400(self):
        response = self.client.get(
            self.url,
            {
                "view": "history",
                "type": "UNKNOWN",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_page_size_is_capped(self):
        response = self.client.get(
            self.url,
            {
                "view": "history",
                "page_size": 500,
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["page_size"],
            50,
        )

    def test_activity_at_is_returned(self):
        response = self.client.get(
            self.url,
            {"view": "history"},
        )

        self.assertIsNotNone(response.data["results"][0]["activity_at"])

    def test_toggle_save_returns_authoritative_count(self):
        toggle_url = reverse(
            "toggle_save_claim",
            args=[str(self.claim_misleading.id)],
        )

        response = self.client.post(toggle_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(response.data["is_saved"])

        self.assertEqual(
            response.data["saved_count"],
            2,
        )

        self.assertTrue(
            self.user.profile.saved_claims.filter(id=self.claim_misleading.id).exists()
        )

    def test_toggle_save_can_unsave(self):
        toggle_url = reverse(
            "toggle_save_claim",
            args=[str(self.claim_fact.id)],
        )

        response = self.client.post(toggle_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertFalse(response.data["is_saved"])

        self.assertEqual(
            response.data["saved_count"],
            0,
        )

        self.assertFalse(
            self.user.profile.saved_claims.filter(id=self.claim_fact.id).exists()
        )

    def test_history_is_paginated(self):
        for index in range(12):
            claim = Claim.objects.create(
                claim_type=Claim.ClaimType.TEXT,
                context_text=f"Pagination claim {index}",
                ai_verdict="FACT",
                verified_via=(Claim.VerificationSource.AI_EXTENSION),
            )

            ClaimCheckHistory.objects.create(
                user=self.user,
                claim=claim,
            )

        response = self.client.get(
            self.url,
            {
                "view": "history",
                "page": 1,
                "page_size": 10,
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data["results"]),
            10,
        )

        self.assertTrue(response.data["has_next"])

        self.assertEqual(
            response.data["page"],
            1,
        )

        self.assertGreater(
            response.data["total_pages"],
            1,
        )
