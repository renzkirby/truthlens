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
from django.core.management import (
    call_command,
)
from io import StringIO

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
    AdjudicationDecision,
    VerificationRun,
    OfficialFactCheck,
    OfficialFactCheckSource,
    KnowledgeReuseEvent,
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
from .adjudication_service import (
    AdjudicationConflict,
    InvalidAdjudicationDecision,
    ensure_adjudication_case,
    ensure_claim_adjudication_readiness,
    is_claim_ready_for_adjudication,
    issue_adjudication_decision,
)
from .publishing_service import (
    InvalidFactCheckContent,
    InvalidPublicationTransition,
    PublishingAuthorizationError,
    PublishingConflict,
    create_fact_check_draft,
    publish_fact_check,
    submit_fact_check_for_review,
    update_fact_check_draft,
)
from .knowledge_reuse_service import (
    InvalidKnowledgeReuse,
    build_published_fact_check_payload,
    build_query_fingerprint,
    find_published_fact_check_match,
    record_knowledge_reuse,
    index_published_fact_check,
)
from .services import (
    search_official_vault,
)
from .claim_matching import (
    compute_fingerprint,
    find_matching_claim,
    get_match_result,
)
from .serializers import ClaimMatchSerializer
from .tasks import execute_core_text_pipeline


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


class AdjudicationFoundationTests(APITestCase):
    def setUp(self):
        self.moderator = User.objects.create_user(
            username="adjudicationmod",
            email="adjudicationmod@test.com",
            password="pass1234",
        )

        self.moderator.profile.role = UserProfile.Role.MOD
        self.moderator.profile.save(update_fields=["role"])

        self.second_moderator = User.objects.create_user(
            username="adjudicationmod2",
            email="adjudicationmod2@test.com",
            password="pass1234",
        )

        self.second_moderator.profile.role = UserProfile.Role.MOD
        self.second_moderator.profile.save(update_fields=["role"])

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("The original claim being " "reviewed by moderators."),
            ai_verdict="FAKE",
            ai_summary=(
                "AI analysis found the claim " "unsupported by available sources."
            ),
            consensus_score=82.5,
        )

    def test_ensure_adjudication_case_creates_and_reuses_active_case(
        self,
    ):
        first = ensure_adjudication_case(
            claim=self.claim,
            actor=self.moderator,
        )

        second = ensure_adjudication_case(
            claim=self.claim,
            actor=self.second_moderator,
        )

        self.assertEqual(
            first.id,
            second.id,
        )

        self.assertEqual(
            first.case_type,
            ModerationCase.CaseType.ADJUDICATION,
        )

        self.assertEqual(
            first.status,
            ModerationCase.Status.OPEN,
        )

        self.assertEqual(
            ModerationCase.objects.filter(
                claim=self.claim,
                case_type=(ModerationCase.CaseType.ADJUDICATION),
                status__in=[
                    ModerationCase.Status.OPEN,
                    ModerationCase.Status.IN_REVIEW,
                    ModerationCase.Status.ESCALATED,
                    ModerationCase.Status.REOPENED,
                ],
            ).count(),
            1,
        )

    def test_first_decision_resolves_adjudication_case(
        self,
    ):
        case = ensure_adjudication_case(
            claim=self.claim,
            actor=self.moderator,
        )

        result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale=("Verified evidence contradicts " "the claim."),
            expected_revision=0,
        )

        case.refresh_from_db()

        self.assertEqual(
            case.status,
            ModerationCase.Status.RESOLVED,
        )

        self.assertEqual(
            result["case"].id,
            case.id,
        )

        self.assertEqual(
            result["decision"].moderation_case_id,
            case.id,
        )

    def test_first_decision_updates_claim_final_verdict(
        self,
    ):
        result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.MISLEADING),
            canonical_claim=("The reviewed claim omits " "important context."),
            rationale=(
                "The central statement contains "
                "some accurate information but "
                "creates a misleading conclusion."
            ),
            expected_revision=0,
        )

        self.claim.refresh_from_db()

        self.assertEqual(
            self.claim.final_verdict,
            AdjudicationDecision.Verdict.MISLEADING,
        )

        self.assertEqual(
            result["claim"].final_verdict,
            AdjudicationDecision.Verdict.MISLEADING,
        )

    def test_decision_snapshots_current_ai_output(
        self,
    ):
        result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale=("Reliable evidence contradicts " "the claim."),
            expected_revision=0,
        )

        decision = result["decision"]

        self.assertEqual(
            decision.ai_verdict_snapshot,
            "FAKE",
        )

        self.assertEqual(
            decision.ai_confidence_snapshot,
            82.5,
        )

        self.assertEqual(
            decision.ai_summary_snapshot,
            ("AI analysis found the claim " "unsupported by available sources."),
        )

        self.assertIsNone(decision.ai_pipeline_version_snapshot)

        self.assertTrue(decision.ai_agrees)

    def test_second_decision_supersedes_first_and_increments_revision(
        self,
    ):
        first_result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale="Initial review.",
            expected_revision=0,
        )

        first_decision = first_result["decision"]

        second_result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.second_moderator,
            verdict=(AdjudicationDecision.Verdict.MISLEADING),
            canonical_claim=("The reviewed claim contains " "misleading context."),
            rationale=(
                "A second review found that "
                "the claim is better classified "
                "as misleading."
            ),
            expected_revision=1,
        )

        second_decision = second_result["decision"]

        first_decision.refresh_from_db()

        self.assertEqual(
            first_decision.revision_number,
            1,
        )

        self.assertFalse(first_decision.is_current)

        self.assertEqual(
            second_decision.revision_number,
            2,
        )

        self.assertTrue(second_decision.is_current)

        self.assertEqual(
            second_decision.supersedes_id,
            first_decision.id,
        )

        self.assertEqual(
            first_decision.superseded_by.id,
            second_decision.id,
        )

    def test_only_one_current_decision_exists_after_revision(
        self,
    ):
        issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale="Initial decision.",
            expected_revision=0,
        )

        issue_adjudication_decision(
            claim=self.claim,
            actor=self.second_moderator,
            verdict=(AdjudicationDecision.Verdict.FACT),
            canonical_claim=("The reviewed claim is accurate."),
            rationale=("New authoritative evidence " "supports the claim."),
            expected_revision=1,
        )

        decisions = AdjudicationDecision.objects.filter(claim=self.claim)

        self.assertEqual(
            decisions.count(),
            2,
        )

        self.assertEqual(
            decisions.filter(is_current=True).count(),
            1,
        )

        current = decisions.get(is_current=True)

        self.assertEqual(
            current.revision_number,
            2,
        )

        self.assertEqual(
            current.verdict,
            AdjudicationDecision.Verdict.FACT,
        )

    def test_revision_records_reopen_and_revised_events(
        self,
    ):
        first_result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale="Initial adjudication.",
            expected_revision=0,
        )

        case = first_result["case"]

        issue_adjudication_decision(
            claim=self.claim,
            actor=self.second_moderator,
            verdict=(AdjudicationDecision.Verdict.MISLEADING),
            canonical_claim=("The reviewed claim is misleading."),
            rationale=("Additional context requires " "revision of the verdict."),
            expected_revision=1,
        )

        self.assertTrue(
            case.events.filter(
                event_type=(ModerationEvent.EventType.VERDICT_REOPENED)
            ).exists()
        )

        self.assertTrue(
            case.events.filter(
                event_type=(ModerationEvent.EventType.VERDICT_REVISED)
            ).exists()
        )

        self.assertEqual(
            case.events.filter(
                event_type=(ModerationEvent.EventType.VERDICT_ISSUED)
            ).count(),
            1,
        )

        self.assertEqual(
            case.events.filter(
                event_type=(ModerationEvent.EventType.VERDICT_REVISED)
            ).count(),
            1,
        )

    def test_stale_expected_revision_is_rejected(
        self,
    ):
        issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale="Initial decision.",
            expected_revision=0,
        )

        with self.assertRaises(AdjudicationConflict):
            issue_adjudication_decision(
                claim=self.claim,
                actor=self.second_moderator,
                verdict=(AdjudicationDecision.Verdict.FACT),
                canonical_claim=("The reviewed claim is true."),
                rationale=("Attempt based on stale " "review state."),
                expected_revision=0,
            )

        self.claim.refresh_from_db()

        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=self.claim).count(),
            1,
        )

        self.assertEqual(
            self.claim.final_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

    def test_canonical_claim_and_rationale_are_required(
        self,
    ):
        with self.subTest("canonical claim required"):
            with self.assertRaises(InvalidAdjudicationDecision):
                issue_adjudication_decision(
                    claim=self.claim,
                    actor=self.moderator,
                    verdict=(AdjudicationDecision.Verdict.FAKE),
                    canonical_claim="",
                    rationale=("There is a rationale."),
                    expected_revision=0,
                )

        with self.subTest("rationale required"):
            with self.assertRaises(InvalidAdjudicationDecision):
                issue_adjudication_decision(
                    claim=self.claim,
                    actor=self.moderator,
                    verdict=(AdjudicationDecision.Verdict.FAKE),
                    canonical_claim=("A canonical claim."),
                    rationale="",
                    expected_revision=0,
                )

        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=self.claim).count(),
            0,
        )

    def test_verification_run_must_match_claim_and_snapshots_pipeline_version(
        self,
    ):
        other_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("A completely different claim."),
        )

        wrong_run = VerificationRun.objects.create(
            claim=other_claim,
            status=(VerificationRun.Status.COMPLETED),
            pipeline_version=("wrong-1.0.0"),
        )

        with self.assertRaises(InvalidAdjudicationDecision):
            issue_adjudication_decision(
                claim=self.claim,
                actor=self.moderator,
                verdict=(AdjudicationDecision.Verdict.FAKE),
                canonical_claim=("The reviewed claim is false."),
                rationale=("This should reject the " "unrelated verification run."),
                verification_run=wrong_run,
                expected_revision=0,
            )

        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=self.claim).count(),
            0,
        )

        valid_run = VerificationRun.objects.create(
            claim=self.claim,
            status=(VerificationRun.Status.COMPLETED),
            pipeline_version=("test-2.0.0"),
        )

        result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale=("The submitted sources " "contradict the claim."),
            verification_run=valid_run,
            expected_revision=0,
        )

        decision = result["decision"]

        self.assertEqual(
            decision.verification_run,
            valid_run,
        )

        self.assertEqual(
            decision.ai_pipeline_version_snapshot,
            "test-2.0.0",
        )


class AdjudicationApiFoundationTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="adjudication-author",
            email="adjudication-author@test.com",
            password="pass1234",
        )

        self.moderator = User.objects.create_user(
            username="adjudication-api-mod",
            email="adjudication-api-mod@test.com",
            password="pass1234",
        )

        self.moderator.profile.role = UserProfile.Role.MOD
        self.moderator.profile.save(update_fields=["role"])

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("The API adjudication test claim."),
            ai_verdict="FAKE",
            ai_summary=("AI analysis found the claim " "unsupported."),
            consensus_score=87.0,
        )

        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.author,
            caption=("Community discussion for " "adjudication API testing."),
            status=Thread.Status.OPEN,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.moderator)

        self.url = reverse(
            "moderation_resolve_thread",
            kwargs={
                "thread_id": self.thread.id,
            },
        )

    def _valid_payload(
        self,
        *,
        verdict=None,
        expected_revision=0,
    ):
        return {
            "moderator_verdict": (verdict or AdjudicationDecision.Verdict.FAKE),
            "moderator_notes": ("Verified sources contradict " "the claim."),
            "canonical_claim": ("The reviewed claim is false."),
            # Legacy frontend compatibility.
            # This must NOT actually close
            # the community thread anymore.
            "status": Thread.Status.CLOSED,
            "expected_revision": expected_revision,
        }

    def test_system_moderator_can_adjudicate_through_legacy_thread_endpoint(
        self,
    ):
        response = self.client.post(
            self.url,
            self._valid_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            AdjudicationDecision.objects.filter(
                claim=self.claim,
                is_current=True,
            ).count(),
            1,
        )

        decision = AdjudicationDecision.objects.get(
            claim=self.claim,
            is_current=True,
        )

        self.assertEqual(
            decision.verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        self.assertEqual(
            decision.decided_by,
            self.moderator,
        )

        self.assertEqual(
            decision.revision_number,
            1,
        )

        self.claim.refresh_from_db()

        self.assertEqual(
            self.claim.final_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        self.assertIn(
            "adjudication",
            response.data,
        )

        self.assertEqual(
            response.data["adjudication"]["revision_number"],
            1,
        )

    def test_adjudication_does_not_change_thread_community_status(
        self,
    ):
        original_status = self.thread.status

        response = self.client.post(
            self.url,
            self._valid_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.thread.refresh_from_db()

        self.assertEqual(
            self.thread.status,
            original_status,
        )

        # Temporary compatibility mirror
        # still receives the verdict.
        self.assertEqual(
            self.thread.moderator_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        self.assertEqual(
            self.thread.moderator_notes,
            ("Verified sources contradict " "the claim."),
        )

        self.assertEqual(
            self.thread.moderated_by,
            self.moderator,
        )

        self.assertIsNotNone(self.thread.moderated_at)

    def test_adjudication_does_not_publish_official_fact_check(
        self,
    ):
        initial_count = OfficialFactCheck.objects.count()

        response = self.client.post(
            self.url,
            self._valid_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            OfficialFactCheck.objects.count(),
            initial_count,
        )

        self.assertTrue(
            AdjudicationDecision.objects.filter(
                claim=self.claim,
                is_current=True,
            ).exists()
        )

    def test_invalid_verdict_returns_400(
        self,
    ):
        payload = self._valid_payload()

        payload["moderator_verdict"] = "TOTALLY_INVALID"

        response = self.client.post(
            self.url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=self.claim).count(),
            0,
        )

        self.claim.refresh_from_db()

        self.assertIsNone(self.claim.final_verdict)

    def test_stale_expected_revision_returns_409(
        self,
    ):
        first_response = self.client.post(
            self.url,
            self._valid_payload(
                expected_revision=0,
            ),
            format="json",
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )

        stale_response = self.client.post(
            self.url,
            self._valid_payload(
                verdict=(AdjudicationDecision.Verdict.MISLEADING),
                expected_revision=0,
            ),
            format="json",
        )

        self.assertEqual(
            stale_response.status_code,
            status.HTTP_409_CONFLICT,
        )

        self.assertIn(
            "detail",
            stale_response.data,
        )

        decisions = AdjudicationDecision.objects.filter(claim=self.claim)

        self.assertEqual(
            decisions.count(),
            1,
        )

        current = decisions.get(is_current=True)

        self.assertEqual(
            current.revision_number,
            1,
        )

        self.assertEqual(
            current.verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        self.claim.refresh_from_db()

        self.assertEqual(
            self.claim.final_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

    def test_conflicted_legacy_adjudication_does_not_leave_case_behind(
        self,
    ):
        conflicted_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("Claim authored for conflict " "rollback testing."),
            ai_verdict="FAKE",
        )

        conflicted_thread = Thread.objects.create(
            claim=conflicted_claim,
            author=self.moderator,
            caption=("Moderator-authored thread."),
            status=Thread.Status.OPEN,
        )

        url = reverse(
            "moderation_resolve_thread",
            kwargs={
                "thread_id": conflicted_thread.id,
            },
        )

        response = self.client.post(
            url,
            self._valid_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertFalse(
            ModerationCase.objects.filter(
                claim=conflicted_claim,
                case_type=(ModerationCase.CaseType.ADJUDICATION),
            ).exists()
        )

        self.assertFalse(
            AdjudicationDecision.objects.filter(claim=conflicted_claim).exists()
        )

        conflicted_claim.refresh_from_db()

        self.assertIsNone(conflicted_claim.final_verdict)


class AdjudicationReadinessAndQueueTests(APITestCase):
    def setUp(self):
        # ---------------------------------
        # Users
        # ---------------------------------
        self.author = User.objects.create_user(
            username="readiness-author",
            email="readiness-author@test.com",
            password="pass1234",
        )

        self.contributor = User.objects.create_user(
            username="readiness-contributor",
            email="readiness-contributor@test.com",
            password="pass1234",
        )

        self.moderator = User.objects.create_user(
            username="readiness-mod",
            email="readiness-mod@test.com",
            password="pass1234",
        )

        self.moderator.profile.role = UserProfile.Role.MOD

        self.moderator.profile.save(update_fields=["role"])

        self.partner_reviewer = User.objects.create_user(
            username="partner-adjudicator",
            email="partner-adjudicator@test.com",
            password="pass1234",
        )

        # ---------------------------------
        # Partner organizations
        # ---------------------------------
        self.organization = Organization.objects.create(
            name=("TruthLens Adjudication " "Partner"),
            slug=("truthlens-adjudication-" "partner"),
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.other_organization = Organization.objects.create(
            name="Other Fact Check Lab",
            slug="other-fact-check-lab",
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

        # ---------------------------------
        # API clients
        # ---------------------------------
        self.moderator_client = APIClient()

        self.moderator_client.force_authenticate(user=self.moderator)

        self.partner_client = APIClient()

        self.partner_client.force_authenticate(user=self.partner_reviewer)

    # =====================================
    # Test helpers
    # =====================================

    def _create_claim_and_thread(
        self,
        *,
        suffix="default",
    ):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=(f"Adjudication readiness " f"claim {suffix}."),
            ai_verdict="FAKE",
            ai_summary=("AI analysis suggests the " "claim is false."),
            consensus_score=84.0,
        )

        thread = Thread.objects.create(
            claim=claim,
            author=self.author,
            caption=(f"Community discussion " f"{suffix}."),
            status=Thread.Status.OPEN,
        )

        return claim, thread

    def _create_evidence(
        self,
        thread,
        *,
        suffix,
    ):
        evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.contributor,
            evidence_caption=(f"Evidence submission " f"{suffix}."),
            evidence_url=("https://example.com/" f"evidence-{suffix}"),
            evidence_type=(EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION),
            evidence_status=(EvidenceSubmission.EvidenceStatus.UNVERIFIED),
            contributor_trust_snapshot=50.0,
        )

        ensure_evidence_case(
            evidence=evidence,
            actor=self.contributor,
        )

        return evidence

    def _verify_evidence(
        self,
        evidence,
    ):
        return review_evidence_submission(
            evidence=evidence,
            actor=self.moderator,
            evidence_status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
            moderator_notes=("Evidence source was reviewed " "and accepted."),
            expected_status=(EvidenceSubmission.EvidenceStatus.UNVERIFIED),
        )

    def _reject_evidence(
        self,
        evidence,
    ):
        return review_evidence_submission(
            evidence=evidence,
            actor=self.moderator,
            evidence_status=(EvidenceSubmission.EvidenceStatus.REJECTED),
            rejection_reason=(EvidenceSubmission.RejectionReason.UNRELIABLE_SOURCE),
            moderator_notes=("The submitted source is " "not sufficiently reliable."),
            expected_status=(EvidenceSubmission.EvidenceStatus.UNVERIFIED),
        )

    def _make_claim_ready(
        self,
        *,
        suffix="ready",
    ):
        claim, thread = self._create_claim_and_thread(suffix=suffix)

        first_evidence = self._create_evidence(
            thread,
            suffix=f"{suffix}-1",
        )

        second_evidence = self._create_evidence(
            thread,
            suffix=f"{suffix}-2",
        )

        self._verify_evidence(first_evidence)

        self._reject_evidence(second_evidence)

        case = ModerationCase.objects.get(
            claim=claim,
            case_type=(ModerationCase.CaseType.ADJUDICATION),
        )

        return {
            "claim": claim,
            "thread": thread,
            "case": case,
            "first_evidence": first_evidence,
            "second_evidence": second_evidence,
        }

    # =====================================
    # 1. Unreviewed evidence blocks readiness
    # =====================================

    def test_unverified_evidence_prevents_adjudication_readiness(
        self,
    ):
        claim, thread = self._create_claim_and_thread(suffix="blocked")

        verified_evidence = self._create_evidence(
            thread,
            suffix="blocked-verified",
        )

        unresolved_evidence = self._create_evidence(
            thread,
            suffix="blocked-pending",
        )

        self._verify_evidence(verified_evidence)

        unresolved_evidence.refresh_from_db()

        self.assertEqual(
            unresolved_evidence.evidence_status,
            EvidenceSubmission.EvidenceStatus.UNVERIFIED,
        )

        self.assertFalse(is_claim_ready_for_adjudication(claim))

        case = ensure_claim_adjudication_readiness(
            claim=claim,
            actor=self.moderator,
        )

        self.assertIsNone(case)

        self.assertFalse(
            ModerationCase.objects.filter(
                claim=claim,
                case_type=(ModerationCase.CaseType.ADJUDICATION),
            ).exists()
        )

    # =====================================
    # 2. Final evidence resolution creates
    #    the adjudication case
    # =====================================

    def test_resolving_final_evidence_creates_open_adjudication_case(
        self,
    ):
        claim, thread = self._create_claim_and_thread(suffix="final-evidence")

        first = self._create_evidence(
            thread,
            suffix="final-1",
        )

        final = self._create_evidence(
            thread,
            suffix="final-2",
        )

        first_result = self._verify_evidence(first)

        self.assertIsNone(first_result["adjudication_case"])

        self.assertFalse(
            ModerationCase.objects.filter(
                claim=claim,
                case_type=(ModerationCase.CaseType.ADJUDICATION),
            ).exists()
        )

        final_result = self._reject_evidence(final)

        adjudication_case = final_result["adjudication_case"]

        self.assertIsNotNone(adjudication_case)

        self.assertEqual(
            adjudication_case.case_type,
            ModerationCase.CaseType.ADJUDICATION,
        )

        self.assertEqual(
            adjudication_case.status,
            ModerationCase.Status.OPEN,
        )

        self.assertEqual(
            adjudication_case.claim,
            claim,
        )

        self.assertEqual(
            ModerationCase.objects.filter(
                claim=claim,
                case_type=(ModerationCase.CaseType.ADJUDICATION),
            ).count(),
            1,
        )

        self.assertTrue(is_claim_ready_for_adjudication(claim))

    # =====================================
    # 3. Zero evidence must not make a
    #    claim automatically ready
    # =====================================

    def test_claim_without_evidence_is_not_automatically_ready(
        self,
    ):
        claim, _thread = self._create_claim_and_thread(suffix="no-evidence")

        self.assertFalse(is_claim_ready_for_adjudication(claim))

        result = ensure_claim_adjudication_readiness(
            claim=claim,
            actor=self.moderator,
        )

        self.assertIsNone(result)

        self.assertFalse(
            ModerationCase.objects.filter(
                claim=claim,
                case_type=(ModerationCase.CaseType.ADJUDICATION),
            ).exists()
        )

    # =====================================
    # 4. System moderator sees actual
    #    ready cases in pending queue
    # =====================================

    def test_system_moderator_sees_ready_claim_in_pending_queue(
        self,
    ):
        ready = self._make_claim_ready(suffix="system-queue")

        response = self.moderator_client.get(
            reverse("moderation_verdict_queue"),
            {
                "reviewed": "pending",
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
            len(response.data["results"]),
            1,
        )

        result = response.data["results"][0]

        self.assertEqual(
            str(result["id"]),
            str(ready["case"].id),
        )

        self.assertEqual(
            str(result["claim"]["id"]),
            str(ready["claim"].id),
        )

        self.assertEqual(
            result["status"],
            ModerationCase.Status.OPEN,
        )

        self.assertEqual(
            result["total_evidence"],
            2,
        )

        self.assertEqual(
            result["verified_evidence"],
            1,
        )

        self.assertEqual(
            result["rejected_evidence"],
            1,
        )

    # =====================================
    # 5. Resolved case moves from pending
    #    queue to resolved queue
    # =====================================

    def test_resolved_adjudication_case_moves_from_pending_to_resolved_queue(
        self,
    ):
        ready = self._make_claim_ready(suffix="resolved-queue")

        issue_adjudication_decision(
            claim=ready["claim"],
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim is false."),
            rationale=("Reviewed community evidence " "does not support the claim."),
            expected_revision=0,
        )

        pending_response = self.moderator_client.get(
            reverse("moderation_verdict_queue"),
            {
                "reviewed": "pending",
            },
        )

        self.assertEqual(
            pending_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            pending_response.data["count"],
            0,
        )

        resolved_response = self.moderator_client.get(
            reverse("moderation_verdict_queue"),
            {
                "reviewed": "resolved",
            },
        )

        self.assertEqual(
            resolved_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            resolved_response.data["count"],
            1,
        )

        self.assertEqual(
            str(resolved_response.data["results"][0]["id"]),
            str(ready["case"].id),
        )

        self.assertEqual(
            resolved_response.data["results"][0]["status"],
            ModerationCase.Status.RESOLVED,
        )

    # =====================================
    # 6. Partner queue requires explicit
    #    organization scope
    # =====================================

    def test_partner_adjudicator_queue_requires_organization_scope(
        self,
    ):
        claim, _thread = self._create_claim_and_thread(suffix="partner-scope")

        ensure_adjudication_case(
            claim=claim,
            actor=self.moderator,
            organization=self.organization,
        )

        response = self.partner_client.get(
            reverse("moderation_verdict_queue"),
            {
                "reviewed": "pending",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "organization_id",
            response.data["detail"],
        )

    # =====================================
    # 7. Partner can only see organization
    #    cases within their capability scope
    # =====================================

    def test_partner_can_only_view_own_organization_adjudication_queue(
        self,
    ):
        own_claim, _own_thread = self._create_claim_and_thread(suffix="own-org")

        own_case = ensure_adjudication_case(
            claim=own_claim,
            actor=self.moderator,
            organization=(self.organization),
        )

        other_claim, _other_thread = self._create_claim_and_thread(suffix="other-org")

        ensure_adjudication_case(
            claim=other_claim,
            actor=self.moderator,
            organization=(self.other_organization),
        )

        own_response = self.partner_client.get(
            reverse("moderation_verdict_queue"),
            {
                "reviewed": "pending",
                "organization_id": (str(self.organization.id)),
            },
        )

        self.assertEqual(
            own_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            own_response.data["count"],
            1,
        )

        self.assertEqual(
            str(own_response.data["results"][0]["id"]),
            str(own_case.id),
        )

        self.assertEqual(
            str(own_response.data["results"][0]["organization"]["id"]),
            str(self.organization.id),
        )

        other_response = self.partner_client.get(
            reverse("moderation_verdict_queue"),
            {
                "reviewed": "pending",
                "organization_id": (str(self.other_organization.id)),
            },
        )

        self.assertEqual(
            other_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # =====================================
    # 8. Canonical Claim endpoint performs
    #    adjudication without closing thread
    # =====================================

    def test_canonical_claim_adjudication_endpoint_creates_decision_without_changing_thread_status(
        self,
    ):
        ready = self._make_claim_ready(suffix="canonical-endpoint")

        claim = ready["claim"]
        thread = ready["thread"]

        original_thread_status = thread.status

        response = self.moderator_client.post(
            reverse(
                "adjudicate_claim",
                kwargs={
                    "claim_id": claim.id,
                },
            ),
            {
                "moderator_verdict": (AdjudicationDecision.Verdict.FAKE),
                "moderator_notes": ("The reviewed evidence " "contradicts the claim."),
                "canonical_claim": ("The reviewed claim " "is false."),
                "expected_revision": 0,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["verdict"],
            AdjudicationDecision.Verdict.FAKE,
        )

        self.assertEqual(
            response.data["revision_number"],
            1,
        )

        self.assertTrue(response.data["is_current"])

        decision = AdjudicationDecision.objects.get(
            claim=claim,
            is_current=True,
        )

        self.assertEqual(
            decision.verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        self.assertEqual(
            decision.decided_by,
            self.moderator,
        )

        claim.refresh_from_db()
        thread.refresh_from_db()

        self.assertEqual(
            claim.final_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        # Community lifecycle must remain
        # independent from adjudication.
        self.assertEqual(
            thread.status,
            original_thread_status,
        )

        # Compatibility mirror remains
        # available temporarily.
        self.assertEqual(
            thread.moderator_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        self.assertEqual(
            thread.moderated_by,
            self.moderator,
        )


class PublishingFoundationTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="publishing-author",
            email="publishing-author@test.com",
            password="pass1234",
        )

        self.contributor = User.objects.create_user(
            username="publishing-contributor",
            email=("publishing-contributor" "@test.com"),
            password="pass1234",
        )

        self.moderator = User.objects.create_user(
            username="publishing-mod",
            email="publishing-mod@test.com",
            password="pass1234",
        )

        self.moderator.profile.role = UserProfile.Role.MOD

        self.moderator.profile.save(update_fields=["role"])

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("Publishing foundation " "test claim."),
            ai_verdict="FAKE",
            ai_summary=("AI analysis suggests " "the claim is false."),
            consensus_score=86.0,
        )

        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.author,
            caption=("Publishing foundation " "community thread."),
            status=Thread.Status.OPEN,
        )

        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=(self.contributor),
            evidence_caption=("Authoritative source " "for publication."),
            evidence_url=("https://example.com/" "publishing-source"),
            evidence_type=(EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION),
            evidence_status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
            contributor_trust_snapshot=(50.0),
            verified_by=self.moderator,
            verified_at=timezone.now(),
        )

        self.decision_result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The reviewed claim " "is false."),
            rationale=("The verified evidence " "contradicts the claim."),
            expected_revision=0,
        )

        self.decision = self.decision_result["decision"]

    def _create_complete_draft(
        self,
        *,
        suffix="default",
    ):
        return create_fact_check_draft(
            decision=self.decision,
            actor=self.moderator,
            headline=(f"Fact Check {suffix}"),
            summary=(
                "The reviewed claim is " "not supported by the " "available evidence."
            ),
            article_body=(
                "TruthLens reviewed the "
                "available evidence and "
                "found that the claim is "
                "not supported."
            ),
        )

    def _publish(
        self,
        fact_check,
    ):
        fact_check = submit_fact_check_for_review(
            fact_check=fact_check,
            actor=self.moderator,
        )

        return publish_fact_check(
            fact_check=fact_check,
            actor=self.moderator,
        )

    def test_create_draft_uses_authoritative_decision_snapshot(
        self,
    ):
        draft = self._create_complete_draft()

        self.assertEqual(
            draft.claim,
            self.claim,
        )

        self.assertEqual(
            draft.adjudication_decision,
            self.decision,
        )

        self.assertEqual(
            draft.canonical_claim,
            self.decision.canonical_claim,
        )

        self.assertEqual(
            draft.verdict,
            self.decision.verdict,
        )

        self.assertEqual(
            draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

        self.assertEqual(
            draft.version,
            1,
        )

        self.assertEqual(
            draft.drafted_by,
            self.moderator,
        )

    def test_draft_automatically_includes_verified_evidence_source(
        self,
    ):
        draft = self._create_complete_draft(suffix="sources")

        source = OfficialFactCheckSource.objects.get(
            fact_check=draft,
            url=self.evidence.evidence_url,
        )

        self.assertEqual(
            source.source_type,
            OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE,
        )

        self.assertEqual(
            source.evidence_submission,
            self.evidence,
        )

        draft.refresh_from_db()

        self.assertIn(
            self.evidence.evidence_url,
            draft.sources,
        )

    def test_only_one_active_draft_exists_per_claim(
        self,
    ):
        self._create_complete_draft(suffix="first")

        with self.assertRaises(PublishingConflict):
            self._create_complete_draft(suffix="second")

        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=self.claim,
                publication_status__in=[
                    OfficialFactCheck.PublicationStatus.DRAFT,
                    OfficialFactCheck.PublicationStatus.IN_REVIEW,
                ],
            ).count(),
            1,
        )

    def test_submit_requires_complete_article_content(
        self,
    ):
        draft = create_fact_check_draft(
            decision=self.decision,
            actor=self.moderator,
            headline="Incomplete article",
            summary=("The article has no " "analysis body yet."),
            article_body="",
        )

        with self.assertRaises(InvalidFactCheckContent):
            submit_fact_check_for_review(
                fact_check=draft,
                actor=self.moderator,
            )

        draft.refresh_from_db()

        self.assertEqual(
            draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

    def test_submit_moves_draft_into_review_and_records_event(
        self,
    ):
        draft = self._create_complete_draft(suffix="review")

        submitted = submit_fact_check_for_review(
            fact_check=draft,
            actor=self.moderator,
        )

        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )

        self.assertIsNotNone(submitted.submitted_for_review_at)

        self.assertTrue(
            self.decision.moderation_case.events.filter(
                event_type=(ModerationEvent.EventType.ARTICLE_SUBMITTED)
            ).exists()
        )

    def test_draft_cannot_skip_directly_to_published(
        self,
    ):
        draft = self._create_complete_draft(suffix="skip")

        with self.assertRaises(InvalidPublicationTransition):
            publish_fact_check(
                fact_check=draft,
                actor=self.moderator,
            )

        draft.refresh_from_db()

        self.assertEqual(
            draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

    def test_publish_sets_publication_identity_and_timestamp(
        self,
    ):
        draft = self._create_complete_draft(suffix="publish")

        result = self._publish(draft)

        published = result["fact_check"]

        self.assertEqual(
            published.publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )

        self.assertEqual(
            published.reviewed_by,
            self.moderator,
        )

        self.assertEqual(
            published.published_by,
            self.moderator,
        )

        self.assertIsNotNone(published.reviewed_at)

        self.assertIsNotNone(published.published_at)

        self.assertIsNone(result["archived_fact_check"])

        self.assertTrue(
            self.decision.moderation_case.events.filter(
                event_type=(ModerationEvent.EventType.ARTICLE_PUBLISHED)
            ).exists()
        )

    def test_stale_adjudication_blocks_existing_draft(
        self,
    ):
        draft = self._create_complete_draft(suffix="stale")

        revised_result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.MISLEADING),
            canonical_claim=("The reviewed claim " "is misleading."),
            rationale=("Additional review " "changed the verdict."),
            expected_revision=1,
        )

        self.assertEqual(
            revised_result["decision"].revision_number,
            2,
        )

        with self.assertRaises(PublishingConflict):
            submit_fact_check_for_review(
                fact_check=draft,
                actor=self.moderator,
            )

        draft.refresh_from_db()

        self.assertEqual(
            draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

    def test_new_published_version_archives_previous_version(
        self,
    ):
        first_draft = self._create_complete_draft(suffix="v1")

        first_result = self._publish(first_draft)

        first_published = first_result["fact_check"]

        second_draft = self._create_complete_draft(suffix="v2")

        self.assertEqual(
            second_draft.version,
            2,
        )

        second_result = self._publish(second_draft)

        second_published = second_result["fact_check"]

        first_published.refresh_from_db()

        self.assertEqual(
            first_published.publication_status,
            OfficialFactCheck.PublicationStatus.ARCHIVED,
        )

        self.assertIsNotNone(first_published.archived_at)

        self.assertEqual(
            second_published.publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )

        self.assertEqual(
            second_published.version,
            2,
        )

        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=self.claim,
                publication_status=(OfficialFactCheck.PublicationStatus.PUBLISHED),
            ).count(),
            1,
        )

        self.assertEqual(
            second_result["archived_fact_check"].id,
            first_published.id,
        )

    def test_update_draft_cannot_change_authoritative_fields(
        self,
    ):
        draft = self._create_complete_draft(suffix="editable")

        original_claim = draft.canonical_claim

        original_verdict = draft.verdict

        updated = update_fact_check_draft(
            fact_check=draft,
            actor=self.moderator,
            headline=("Updated editorial " "headline"),
            summary=("Updated editorial " "summary."),
            article_body=(
                "Updated analysis " "without changing the " "authoritative verdict."
            ),
            source_urls=[
                ("https://example.org/" "additional-source"),
            ],
        )

        self.assertEqual(
            updated.headline,
            ("Updated editorial " "headline"),
        )

        self.assertEqual(
            updated.canonical_claim,
            original_claim,
        )

        self.assertEqual(
            updated.verdict,
            original_verdict,
        )

        self.assertTrue(
            updated.source_items.filter(
                url=("https://example.org/" "additional-source"),
                source_type=(OfficialFactCheckSource.SourceType.MODERATOR_ADDED),
            ).exists()
        )

    def test_publication_does_not_mutate_claim_or_thread_adjudication_state(
        self,
    ):
        # The adjudication service updates a
        # locked/refetched Claim instance.
        # Refresh our test instances so the
        # baseline reflects persisted state.
        self.claim.refresh_from_db()
        self.thread.refresh_from_db()
        self.decision.refresh_from_db()

        original_thread_status = self.thread.status

        original_final_verdict = self.claim.final_verdict

        original_decision_count = AdjudicationDecision.objects.filter(
            claim=self.claim
        ).count()

        draft = self._create_complete_draft(suffix="separation")

        self._publish(draft)

        self.thread.refresh_from_db()
        self.claim.refresh_from_db()
        self.decision.refresh_from_db()

        self.assertEqual(
            self.thread.status,
            original_thread_status,
        )

        self.assertEqual(
            self.claim.final_verdict,
            original_final_verdict,
        )

        self.assertEqual(
            original_final_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        self.assertTrue(self.decision.is_current)

        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=self.claim).count(),
            original_decision_count,
        )

    def test_replacing_moderator_sources_preserves_verified_evidence_sources(
        self,
    ):
        draft = create_fact_check_draft(
            decision=self.decision,
            actor=self.moderator,
            headline=("Source provenance test"),
            summary=("Testing publication source " "replacement behavior."),
            article_body=(
                "This article contains enough " "content for publication review."
            ),
            source_urls=[
                ("https://example.org/" "manual-source-one"),
            ],
        )

        updated = update_fact_check_draft(
            fact_check=draft,
            actor=self.moderator,
            source_urls=[
                ("https://example.org/" "manual-source-two"),
            ],
        )

        self.assertTrue(
            updated.source_items.filter(
                url=self.evidence.evidence_url,
                source_type=(OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE),
            ).exists()
        )

        self.assertFalse(
            updated.source_items.filter(
                url=("https://example.org/" "manual-source-one"),
            ).exists()
        )

        self.assertTrue(
            updated.source_items.filter(
                url=("https://example.org/" "manual-source-two"),
                source_type=(OfficialFactCheckSource.SourceType.MODERATOR_ADDED),
            ).exists()
        )

        updated.refresh_from_db()

        self.assertIn(
            self.evidence.evidence_url,
            updated.sources,
        )

        self.assertIn(
            ("https://example.org/" "manual-source-two"),
            updated.sources,
        )

    def test_new_adjudication_retires_stale_in_review_article(
        self,
    ):
        stale_article = self._create_complete_draft(suffix="stale-review")

        stale_article = submit_fact_check_for_review(
            fact_check=stale_article,
            actor=self.moderator,
        )

        self.assertEqual(
            stale_article.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )

        revised = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.MISLEADING),
            canonical_claim=("The revised reviewed claim " "is misleading."),
            rationale=("Additional review changed " "the authoritative verdict."),
            expected_revision=1,
        )

        fresh_draft = create_fact_check_draft(
            decision=(revised["decision"]),
            actor=self.moderator,
            headline=("Updated Fact Check"),
            summary=("The updated adjudication " "requires a new article."),
            article_body=("This article reflects the " "new authoritative decision."),
        )

        stale_article.refresh_from_db()

        self.assertEqual(
            stale_article.publication_status,
            OfficialFactCheck.PublicationStatus.ARCHIVED,
        )

        self.assertIsNotNone(stale_article.archived_at)

        self.assertEqual(
            fresh_draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

        self.assertEqual(
            fresh_draft.version,
            2,
        )

        self.assertEqual(
            fresh_draft.adjudication_decision,
            revised["decision"],
        )

    def test_publication_queues_knowledge_index_after_commit(
        self,
    ):
        draft = self._create_complete_draft(suffix="index-queue")

        draft = submit_fact_check_for_review(
            fact_check=draft,
            actor=self.moderator,
        )

        with patch(("api.publishing_service" "._queue_fact_check_index")) as queue_mock:
            with self.captureOnCommitCallbacks(execute=True):
                result = publish_fact_check(
                    fact_check=draft,
                    actor=self.moderator,
                )

        published = result["fact_check"]

        queue_mock.assert_called_once_with(published.id)


class PublishingApiAuthorizationTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="publishing-api-author",
            email=("publishing-api-author" "@test.com"),
            password="pass1234",
        )

        self.system_moderator = User.objects.create_user(
            username=("publishing-api-system"),
            email=("publishing-api-system" "@test.com"),
            password="pass1234",
        )

        self.system_moderator.profile.role = UserProfile.Role.MOD

        self.system_moderator.profile.save(update_fields=["role"])

        self.researcher = User.objects.create_user(
            username=("publishing-researcher"),
            email=("publishing-researcher" "@test.com"),
            password="pass1234",
        )

        self.partner_moderator = User.objects.create_user(
            username=("publishing-partner-mod"),
            email=("publishing-partner-mod" "@test.com"),
            password="pass1234",
        )

        self.lead_verifier = User.objects.create_user(
            username=("publishing-lead"),
            email=("publishing-lead" "@test.com"),
            password="pass1234",
        )

        self.organization = Organization.objects.create(
            name=("Publishing Partner"),
            slug=("publishing-partner"),
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.other_organization = Organization.objects.create(
            name=("Other Publishing " "Partner"),
            slug=("other-publishing-" "partner"),
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.researcher,
            role=(OrganizationMembership.Role.RESEARCHER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.partner_moderator,
            role=(OrganizationMembership.Role.MODERATOR),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead_verifier,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        (
            self.platform_claim,
            self.platform_decision,
        ) = self._create_decision(
            suffix="platform",
            organization=None,
        )

        (
            self.partner_claim,
            self.partner_decision,
        ) = self._create_decision(
            suffix="partner",
            organization=(self.organization),
        )

        (
            self.other_claim,
            self.other_decision,
        ) = self._create_decision(
            suffix="other",
            organization=(self.other_organization),
        )

        self.system_client = APIClient()
        self.system_client.force_authenticate(user=self.system_moderator)

        self.researcher_client = APIClient()
        self.researcher_client.force_authenticate(user=self.researcher)

        self.partner_mod_client = APIClient()
        self.partner_mod_client.force_authenticate(user=self.partner_moderator)

        self.lead_client = APIClient()
        self.lead_client.force_authenticate(user=self.lead_verifier)

    def _create_decision(
        self,
        *,
        suffix,
        organization,
    ):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=(f"Publishing API claim " f"{suffix}."),
            ai_verdict="FAKE",
            ai_summary=("AI analysis indicates " "the claim is false."),
            consensus_score=82.0,
        )

        Thread.objects.create(
            claim=claim,
            author=self.author,
            caption=(f"Publishing API thread " f"{suffix}."),
            status=Thread.Status.OPEN,
        )

        if organization is not None:
            ensure_adjudication_case(
                claim=claim,
                actor=(self.system_moderator),
                organization=organization,
            )

        result = issue_adjudication_decision(
            claim=claim,
            actor=self.system_moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=(f"The reviewed {suffix} " f"claim is false."),
            rationale=("The reviewed evidence " "does not support the " "claim."),
            organization=organization,
            expected_revision=0,
        )

        return (
            claim,
            result["decision"],
        )

    def _draft_payload(
        self,
        *,
        expected_revision=1,
    ):
        return {
            "headline": ("TruthLens Fact Check"),
            "summary": ("The reviewed claim is " "not supported."),
            "article_body": (
                "TruthLens reviewed the "
                "available information and "
                "found the claim unsupported."
            ),
            "source_urls": [
                ("https://example.com/" "publishing-api-source"),
            ],
            "expected_revision": (expected_revision),
        }

    def _create_draft(
        self,
        client,
        claim,
    ):
        return client.post(
            reverse(
                ("moderation_fact_check_" "draft_create"),
                kwargs={
                    "claim_id": claim.id,
                },
            ),
            self._draft_payload(),
            format="json",
        )

    def _submit(
        self,
        client,
        fact_check_id,
    ):
        return client.post(
            reverse(
                "moderation_fact_check_submit",
                kwargs={
                    "fact_check_id": fact_check_id,
                },
            ),
            {},
            format="json",
        )

    def _publish(
        self,
        client,
        fact_check_id,
    ):
        return client.post(
            reverse(
                ("moderation_fact_check_" "publish"),
                kwargs={
                    "fact_check_id": fact_check_id,
                },
            ),
            {},
            format="json",
        )

    # ---------------------------------
    # 1. System moderator full lifecycle
    # ---------------------------------

    def test_system_moderator_can_complete_publication_lifecycle(
        self,
    ):
        create_response = self._create_draft(
            self.system_client,
            self.platform_claim,
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )

        fact_check_id = create_response.data["id"]

        self.assertEqual(
            create_response.data["publication_status"],
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

        self.assertEqual(
            create_response.data["verdict"],
            self.platform_decision.verdict,
        )

        update_response = self.system_client.patch(
            reverse(
                ("moderation_fact_check_" "draft_update"),
                kwargs={
                    "fact_check_id": fact_check_id,
                },
            ),
            {
                "headline": ("Updated TruthLens " "Fact Check"),
            },
            format="json",
        )

        self.assertEqual(
            update_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            update_response.data["headline"],
            ("Updated TruthLens " "Fact Check"),
        )

        submit_response = self._submit(
            self.system_client,
            fact_check_id,
        )

        self.assertEqual(
            submit_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            submit_response.data["publication_status"],
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )

        publish_response = self._publish(
            self.system_client,
            fact_check_id,
        )

        self.assertEqual(
            publish_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            publish_response.data["publication_status"],
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )

        self.assertIsNotNone(publish_response.data["published_at"])

    # ---------------------------------
    # 2. Researcher can draft/submit
    #    but cannot publish
    # ---------------------------------

    def test_researcher_can_submit_but_cannot_publish(
        self,
    ):
        create_response = self._create_draft(
            self.researcher_client,
            self.partner_claim,
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )

        fact_check_id = create_response.data["id"]

        submit_response = self._submit(
            self.researcher_client,
            fact_check_id,
        )

        self.assertEqual(
            submit_response.status_code,
            status.HTTP_200_OK,
        )

        publish_response = self._publish(
            self.researcher_client,
            fact_check_id,
        )

        self.assertEqual(
            publish_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        fact_check = OfficialFactCheck.objects.get(id=fact_check_id)

        self.assertEqual(
            fact_check.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )

    # ---------------------------------
    # 3. Partner moderator cannot publish
    # ---------------------------------

    def test_partner_moderator_cannot_publish(
        self,
    ):
        create_response = self._create_draft(
            self.partner_mod_client,
            self.partner_claim,
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )

        fact_check_id = create_response.data["id"]

        submit_response = self._submit(
            self.partner_mod_client,
            fact_check_id,
        )

        self.assertEqual(
            submit_response.status_code,
            status.HTTP_200_OK,
        )

        publish_response = self._publish(
            self.partner_mod_client,
            fact_check_id,
        )

        self.assertEqual(
            publish_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # ---------------------------------
    # 4. Lead verifier can publish
    # ---------------------------------

    def test_lead_verifier_can_publish_for_own_organization(
        self,
    ):
        create_response = self._create_draft(
            self.lead_client,
            self.partner_claim,
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )

        fact_check_id = create_response.data["id"]

        self.assertEqual(
            str(create_response.data["organization"]["id"]),
            str(self.organization.id),
        )

        self.assertEqual(
            self._submit(
                self.lead_client,
                fact_check_id,
            ).status_code,
            status.HTTP_200_OK,
        )

        publish_response = self._publish(
            self.lead_client,
            fact_check_id,
        )

        self.assertEqual(
            publish_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            publish_response.data["publication_status"],
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )

    # ---------------------------------
    # 5. Cross-org access denied
    # ---------------------------------

    def test_partner_cannot_edit_another_organizations_draft(
        self,
    ):
        create_response = self._create_draft(
            self.system_client,
            self.other_claim,
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )

        fact_check_id = create_response.data["id"]

        response = self.lead_client.patch(
            reverse(
                ("moderation_fact_check_" "draft_update"),
                kwargs={
                    "fact_check_id": fact_check_id,
                },
            ),
            {
                "headline": "Unauthorized edit",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # ---------------------------------
    # 6. Stale existing draft → 409
    # ---------------------------------

    def test_stale_adjudication_returns_409_on_submit(
        self,
    ):
        create_response = self._create_draft(
            self.lead_client,
            self.partner_claim,
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )

        fact_check_id = create_response.data["id"]

        revised = issue_adjudication_decision(
            claim=self.partner_claim,
            actor=self.system_moderator,
            verdict=(AdjudicationDecision.Verdict.MISLEADING),
            canonical_claim=("The reviewed partner " "claim is misleading."),
            rationale=("Additional evidence " "changed the decision."),
            organization=(self.organization),
            expected_revision=1,
        )

        self.assertEqual(
            revised["decision"].revision_number,
            2,
        )

        response = self._submit(
            self.lead_client,
            fact_check_id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

    # ---------------------------------
    # 7. Cannot skip review
    # ---------------------------------

    def test_draft_cannot_be_published_directly(
        self,
    ):
        create_response = self._create_draft(
            self.system_client,
            self.platform_claim,
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )

        response = self._publish(
            self.system_client,
            create_response.data["id"],
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    # ---------------------------------
    # 8. Published article cannot use
    #    draft edit endpoint
    # ---------------------------------

    def test_published_fact_check_cannot_be_edited_as_draft(
        self,
    ):
        created = self._create_draft(
            self.system_client,
            self.platform_claim,
        )

        fact_check_id = created.data["id"]

        self._submit(
            self.system_client,
            fact_check_id,
        )

        self._publish(
            self.system_client,
            fact_check_id,
        )

        response = self.system_client.patch(
            reverse(
                ("moderation_fact_check_" "draft_update"),
                kwargs={
                    "fact_check_id": fact_check_id,
                },
            ),
            {
                "headline": "Should not change",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    # ---------------------------------
    # 9. Authoritative fields rejected
    # ---------------------------------

    def test_draft_api_rejects_authoritative_field_edits(
        self,
    ):
        created = self._create_draft(
            self.system_client,
            self.platform_claim,
        )

        fact_check_id = created.data["id"]

        response = self.system_client.patch(
            reverse(
                ("moderation_fact_check_" "draft_update"),
                kwargs={
                    "fact_check_id": fact_check_id,
                },
            ),
            {
                "verdict": "FACT",
                "canonical_claim": ("Editor attempted " "replacement."),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        fact_check = OfficialFactCheck.objects.get(id=fact_check_id)

        self.assertEqual(
            fact_check.verdict,
            self.platform_decision.verdict,
        )

        self.assertEqual(
            fact_check.canonical_claim,
            (self.platform_decision.canonical_claim),
        )

    # ---------------------------------
    # 10. Stale workspace revision
    #     rejected before draft creation
    # ---------------------------------

    def test_create_draft_rejects_stale_expected_revision(
        self,
    ):
        issue_adjudication_decision(
            claim=self.partner_claim,
            actor=self.system_moderator,
            verdict=(AdjudicationDecision.Verdict.MISLEADING),
            canonical_claim=("The newer canonical " "claim is misleading."),
            rationale=("The decision changed."),
            organization=(self.organization),
            expected_revision=1,
        )

        response = self.lead_client.post(
            reverse(
                ("moderation_fact_check_" "draft_create"),
                kwargs={
                    "claim_id": self.partner_claim.id,
                },
            ),
            self._draft_payload(expected_revision=1),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

        self.assertFalse(
            OfficialFactCheck.objects.filter(
                claim=self.partner_claim,
                publication_status=(OfficialFactCheck.PublicationStatus.DRAFT),
            ).exists()
        )

    # ---------------------------------
    # 11. New adjudication retires stale
    #     draft and permits fresh draft
    # ---------------------------------

    def test_new_decision_archives_stale_draft_when_fresh_draft_is_created(
        self,
    ):
        first_response = self._create_draft(
            self.lead_client,
            self.partner_claim,
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED,
        )

        stale_draft_id = first_response.data["id"]

        revised = issue_adjudication_decision(
            claim=self.partner_claim,
            actor=self.system_moderator,
            verdict=(AdjudicationDecision.Verdict.MISLEADING),
            canonical_claim=("The revised claim is " "misleading."),
            rationale=("New evidence changed " "the authoritative result."),
            organization=(self.organization),
            expected_revision=1,
        )

        second_response = self.lead_client.post(
            reverse(
                ("moderation_fact_check_" "draft_create"),
                kwargs={
                    "claim_id": self.partner_claim.id,
                },
            ),
            self._draft_payload(expected_revision=2),
            format="json",
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_201_CREATED,
        )

        stale_draft = OfficialFactCheck.objects.get(id=stale_draft_id)

        self.assertEqual(
            stale_draft.publication_status,
            OfficialFactCheck.PublicationStatus.ARCHIVED,
        )

        self.assertIsNotNone(stale_draft.archived_at)

        self.assertEqual(
            second_response.data["version"],
            2,
        )

        self.assertEqual(
            second_response.data["verdict"],
            revised["decision"].verdict,
        )


class KnowledgeReuseFoundationTests(APITestCase):
    def setUp(self):
        self.moderator = User.objects.create_user(
            username="reuse-mod",
            email="reuse-mod@test.com",
            password="pass1234",
        )

        self.moderator.profile.role = UserProfile.Role.MOD

        self.moderator.profile.save(update_fields=["role"])

        self.organization = Organization.objects.create(
            name=("Knowledge Reuse Lab"),
            slug=("knowledge-reuse-lab"),
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.claim = Claim.objects.create(
            claim_type=(Claim.ClaimType.TEXT),
            context_text=("The original knowledge " "reuse test claim."),
            ai_verdict="FAKE",
            ai_summary=("AI analysis suggests " "the claim is false."),
            consensus_score=90.0,
        )

        ensure_adjudication_case(
            claim=self.claim,
            actor=self.moderator,
            organization=(self.organization),
        )

        result = issue_adjudication_decision(
            claim=self.claim,
            actor=self.moderator,
            verdict=(AdjudicationDecision.Verdict.FAKE),
            canonical_claim=("The moon is made " "entirely of cheese."),
            rationale=("Authoritative evidence " "does not support the " "claim."),
            organization=(self.organization),
            expected_revision=0,
        )

        self.decision = result["decision"]

        # issue_adjudication_decision() updates a
        # locked/refetched Claim instance.
        # Refresh the fixture so subsequent tests
        # see the persisted authoritative verdict.
        self.claim.refresh_from_db()
        self.decision.refresh_from_db()

        self.assertEqual(
            self.claim.final_verdict,
            AdjudicationDecision.Verdict.FAKE,
        )

        self.fact_check = OfficialFactCheck.objects.create(
            claim=self.claim,
            adjudication_decision=(self.decision),
            organization=(self.organization),
            canonical_claim=(self.decision.canonical_claim),
            verdict=(self.decision.verdict),
            headline=("Fact Check: " "The Moon Is Not Cheese"),
            summary=(
                "Available evidence " "shows that the moon " "is not made of cheese."
            ),
            article_body=(
                "The published " "fact-check explains " "the available evidence."
            ),
            publication_status=(OfficialFactCheck.PublicationStatus.PUBLISHED),
            version=1,
            drafted_by=(self.moderator),
            reviewed_by=(self.moderator),
            published_by=(self.moderator),
            submitted_for_review_at=(timezone.now()),
            reviewed_at=(timezone.now()),
            published_at=(timezone.now()),
        )

        self.source = OfficialFactCheckSource.objects.create(
            fact_check=(self.fact_check),
            url=("https://example.com/" "moon-source"),
            title=("Authoritative Moon " "Source"),
            source_type=(OfficialFactCheckSource.SourceType.MODERATOR_ADDED),
            added_by=(self.moderator),
        )

    def test_exact_search_returns_only_published_fact_check(
        self,
    ):
        match = find_published_fact_check_match(
            ("The moon is made " "entirely of cheese.")
        )

        self.assertIsNotNone(match)

        self.assertEqual(
            match.fact_check,
            self.fact_check,
        )

        self.assertEqual(
            match.match_method,
            KnowledgeReuseEvent.MatchMethod.EXACT_TEXT,
        )

        self.assertEqual(
            match.similarity_score,
            1.0,
        )

    def test_archived_fact_check_is_not_reusable(
        self,
    ):
        archived_claim = Claim.objects.create(
            claim_type=(Claim.ClaimType.TEXT),
            context_text=("Archived knowledge " "reuse claim."),
        )

        archived = OfficialFactCheck.objects.create(
            claim=archived_claim,
            canonical_claim=("Archived exact " "knowledge claim."),
            verdict=(AdjudicationDecision.Verdict.FAKE),
            headline=("Archived article"),
            summary=("Archived summary."),
            article_body=("Archived body."),
            publication_status=(OfficialFactCheck.PublicationStatus.ARCHIVED),
            version=1,
            archived_at=(timezone.now()),
        )

        with patch(
            ("api.knowledge_reuse_service" ".generate_embedding"),
            return_value=None,
        ):
            match = find_published_fact_check_match(archived.canonical_claim)

        self.assertIsNone(match)

    def test_reuse_payload_contains_partner_attribution_and_sources(
        self,
    ):
        match = find_published_fact_check_match(self.fact_check.canonical_claim)

        payload = build_published_fact_check_payload(match)

        self.assertEqual(
            payload["fact_check_id"],
            str(self.fact_check.id),
        )

        self.assertEqual(
            payload["verdict"],
            (AdjudicationDecision.Verdict.FAKE),
        )

        self.assertEqual(
            payload["organization"]["name"],
            self.organization.name,
        )

        self.assertEqual(
            payload["organization"]["slug"],
            self.organization.slug,
        )

        self.assertEqual(
            payload["sources"][0]["url"],
            self.source.url,
        )

    def test_reuse_event_stores_hash_not_raw_query(
        self,
    ):
        query_text = "A future user asks whether " "the moon is made of cheese."

        event = record_knowledge_reuse(
            fact_check=self.fact_check,
            reuse_type=(KnowledgeReuseEvent.ReuseType.USER_RESPONSE),
            match_method=(KnowledgeReuseEvent.MatchMethod.EXACT_TEXT),
            target_claim=self.claim,
            triggered_by=(self.moderator),
            similarity_score=1.0,
            query_text=query_text,
            metadata={
                "channel": "TEST",
            },
        )

        self.assertEqual(
            len(event.query_fingerprint),
            64,
        )

        self.assertNotEqual(
            event.query_fingerprint,
            query_text,
        )

        self.assertEqual(
            event.metadata["channel"],
            "TEST",
        )

        self.assertEqual(
            event.fact_check,
            self.fact_check,
        )

    def test_query_fingerprint_is_normalized_and_stable(
        self,
    ):
        first = build_query_fingerprint(("The Moon Is Made " "Of Cheese"))

        second = build_query_fingerprint(("  the moon is made   " "of cheese  "))

        self.assertEqual(
            first,
            second,
        )

    def test_non_published_article_cannot_record_reuse(
        self,
    ):
        draft_claim = Claim.objects.create(
            claim_type=(Claim.ClaimType.TEXT),
            context_text=("Draft knowledge claim."),
        )

        draft = OfficialFactCheck.objects.create(
            claim=draft_claim,
            canonical_claim=("A draft should " "never be reused."),
            verdict=(AdjudicationDecision.Verdict.UNVERIFIED),
            headline=("Draft article"),
            summary=("Draft summary."),
            article_body=("Draft body."),
            publication_status=(OfficialFactCheck.PublicationStatus.DRAFT),
            version=1,
        )

        with self.assertRaises(InvalidKnowledgeReuse):
            record_knowledge_reuse(
                fact_check=draft,
                reuse_type=(KnowledgeReuseEvent.ReuseType.USER_RESPONSE),
                match_method=(KnowledgeReuseEvent.MatchMethod.CLAIM_CACHE),
            )

    def test_published_fact_check_can_be_indexed(
        self,
    ):
        self.fact_check.embedding = None

        (
            OfficialFactCheck.objects.filter(id=self.fact_check.id).update(
                embedding=None,
                search_vector=None,
            )
        )

        fake_embedding = [0.01] * 384

        with patch(
            ("api.knowledge_reuse_service" ".generate_embedding"),
            return_value=fake_embedding,
        ):
            indexed = index_published_fact_check(self.fact_check)

        self.assertTrue(indexed)

        self.fact_check.refresh_from_db()

        self.assertIsNotNone(self.fact_check.embedding)

        self.assertIsNotNone(self.fact_check.search_vector)

    def test_draft_fact_check_is_not_knowledge_indexed(
        self,
    ):
        draft_claim = Claim.objects.create(
            claim_type=(Claim.ClaimType.TEXT),
            context_text=("Draft indexing claim."),
        )

        draft = OfficialFactCheck.objects.create(
            claim=draft_claim,
            canonical_claim=("Draft articles should " "not enter the vault."),
            verdict=(AdjudicationDecision.Verdict.UNVERIFIED),
            headline="Draft",
            summary="Draft summary.",
            article_body="Draft body.",
            publication_status=(OfficialFactCheck.PublicationStatus.DRAFT),
            version=1,
        )

        with patch(
            ("api.knowledge_reuse_service" ".generate_embedding")
        ) as embedding_mock:
            indexed = index_published_fact_check(draft)

        self.assertFalse(indexed)

        embedding_mock.assert_not_called()

        draft.refresh_from_db()

        self.assertIsNone(draft.embedding)

    def test_vault_search_records_verification_context_reuse(
        self,
    ):
        payload = search_official_vault(
            self.fact_check.canonical_claim,
            target_claim=self.claim,
            triggered_by=self.moderator,
        )

        self.assertIsNotNone(payload)

        self.assertEqual(
            payload["fact_check_id"],
            str(self.fact_check.id),
        )

        event = KnowledgeReuseEvent.objects.get(
            fact_check=self.fact_check,
            reuse_type=(KnowledgeReuseEvent.ReuseType.VERIFICATION_CONTEXT),
        )

        self.assertEqual(
            event.target_claim,
            self.claim,
        )

        self.assertEqual(
            event.triggered_by,
            self.moderator,
        )

        self.assertEqual(
            event.match_method,
            KnowledgeReuseEvent.MatchMethod.EXACT_TEXT,
        )

    def test_reuse_event_failure_does_not_hide_valid_vault_match(
        self,
    ):
        with patch(
            ("api.knowledge_reuse_service" ".record_knowledge_reuse"),
            side_effect=Exception("analytics unavailable"),
        ):
            payload = search_official_vault(
                self.fact_check.canonical_claim,
                target_claim=self.claim,
            )

        self.assertIsNotNone(payload)

        self.assertEqual(
            payload["verdict"],
            self.fact_check.verdict,
        )

    def test_claim_cache_prefers_published_fact_check_content(
        self,
    ):
        result = get_match_result(self.claim)

        self.assertEqual(
            result["match_type"],
            "resolved",
        )

        self.assertEqual(
            result["resolution_source"],
            "OFFICIAL_FACT_CHECK",
        )

        self.assertEqual(
            result["verdict"],
            self.fact_check.verdict,
        )

        self.assertEqual(
            result["summary"],
            self.fact_check.summary,
        )

        self.assertIsNone(result["moderator_notes"])

        self.assertEqual(
            result["official_fact_check"]["fact_check_id"],
            str(self.fact_check.id),
        )

        self.assertEqual(
            result["official_fact_check"]["organization"]["name"],
            self.organization.name,
        )

        self.assertIn(
            self.source.url,
            result["sources"],
        )

    def test_user_facing_claim_cache_records_reuse_event(
        self,
    ):
        query_text = "Is the moon made entirely " "of cheese?"

        get_match_result(
            self.claim,
            triggered_by=self.moderator,
            record_reuse=True,
            query_text=query_text,
        )

        event = KnowledgeReuseEvent.objects.get(
            fact_check=self.fact_check,
            reuse_type=(KnowledgeReuseEvent.ReuseType.USER_RESPONSE),
        )

        self.assertEqual(
            event.target_claim,
            self.claim,
        )

        self.assertEqual(
            event.triggered_by,
            self.moderator,
        )

        self.assertEqual(
            event.match_method,
            KnowledgeReuseEvent.MatchMethod.CLAIM_CACHE,
        )

        self.assertIsNotNone(event.query_fingerprint)

    def test_unpublished_adjudication_does_not_expose_thread_moderator_notes(
        self,
    ):
        unpublished_claim = Claim.objects.create(
            claim_type=(Claim.ClaimType.TEXT),
            context_text=("An adjudicated but " "unpublished claim."),
            ai_verdict="FAKE",
            ai_summary=("Public-safe AI summary."),
            final_verdict="FAKE",
        )

        Thread.objects.create(
            claim=unpublished_claim,
            author=self.moderator,
            caption="Legacy thread",
            status=Thread.Status.CLOSED,
            moderator_verdict="FAKE",
            moderator_notes=("PRIVATE INTERNAL " "MODERATOR NOTE"),
            moderated_by=self.moderator,
            moderated_at=timezone.now(),
        )

        result = get_match_result(unpublished_claim)

        self.assertEqual(
            result["resolution_source"],
            "ADJUDICATION",
        )

        self.assertEqual(
            result["summary"],
            "Public-safe AI summary.",
        )

        self.assertIsNone(result["moderator_notes"])

        self.assertIsNone(result["official_fact_check"])

        self.assertNotIn(
            "PRIVATE INTERNAL",
            result["summary"],
        )

    def test_claim_match_serializer_preserves_fact_check_attribution(
        self,
    ):
        payload = get_match_result(self.claim)

        serializer = ClaimMatchSerializer(data=payload)

        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data

        self.assertEqual(
            validated["resolution_source"],
            "OFFICIAL_FACT_CHECK",
        )

        self.assertEqual(
            validated["official_fact_check"]["fact_check_id"],
            str(self.fact_check.id),
        )

        self.assertIn(
            self.source.url,
            validated["sources"],
        )

    def test_polling_uses_published_fact_check_without_recording_reuse(
        self,
    ):
        client = APIClient()

        response = client.get(
            reverse(
                "claim_status",
                kwargs={
                    "claim_id": (self.claim.id),
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        data = response.json()

        self.assertEqual(
            data["resolution_source"],
            "OFFICIAL_FACT_CHECK",
        )

        self.assertEqual(
            data["summary"],
            self.fact_check.summary,
        )

        self.assertEqual(
            data["official_fact_check"]["fact_check_id"],
            str(self.fact_check.id),
        )

        self.assertFalse(
            KnowledgeReuseEvent.objects.filter(
                reuse_type=(KnowledgeReuseEvent.ReuseType.USER_RESPONSE)
            ).exists()
        )

    def test_cached_text_endpoint_records_user_facing_fact_check_reuse(
        self,
    ):
        query_text = self.fact_check.canonical_claim

        self.claim.context_text = query_text

        self.claim.claim_fingerprint = compute_fingerprint(
            "TEXT",
            query_text,
        )

        self.claim.save(
            update_fields=[
                "context_text",
                "claim_fingerprint",
            ]
        )

        client = APIClient()

        client.force_authenticate(user=self.moderator)

        response = client.post(
            reverse("verify_text"),
            {
                "text": query_text,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        data = response.json()

        self.assertTrue(data["cached"])

        self.assertEqual(
            data["match"]["resolution_source"],
            "OFFICIAL_FACT_CHECK",
        )

        self.assertEqual(
            data["match"]["official_fact_check"]["fact_check_id"],
            str(self.fact_check.id),
        )

        self.assertTrue(
            KnowledgeReuseEvent.objects.filter(
                fact_check=(self.fact_check),
                reuse_type=(KnowledgeReuseEvent.ReuseType.USER_RESPONSE),
                triggered_by=(self.moderator),
            ).exists()
        )

    def test_claim_cache_does_not_use_semantic_fallback(
        self,
    ):
        with patch(
            "api.claim_matching.find_semantic_match",
            return_value=self.claim,
        ) as semantic_mock:
            result = find_matching_claim(
                "txt:definitely-not-an-exact-match",
                "TEXT",
                context_text=(
                    "A semantically related but " "factually distinct statement."
                ),
                allow_semantic_fallback=False,
            )

        semantic_mock.assert_not_called()
        self.assertIsNone(result)

    def test_text_endpoint_does_not_return_semantic_match_as_cached_verdict(
        self,
    ):
        query_text = (
            "A different claim that is only "
            "semantically related to the "
            "published fact-check."
        )

        client = APIClient()

        with patch(
            "api.claim_matching.find_semantic_match",
            return_value=self.claim,
        ) as semantic_mock:
            with patch("api.views.text_fact_check_process.delay"):
                response = client.post(
                    reverse("verify_text"),
                    {
                        "text": query_text,
                    },
                    format="json",
                )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertFalse(response.json()["cached"])

        semantic_mock.assert_not_called()

    def test_second_chance_dedup_does_not_copy_semantic_final_verdict(
        self,
    ):
        new_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=("A semantically related but " "distinct new claim."),
        )

        with patch(
            "api.claim_matching.find_semantic_match",
            return_value=self.claim,
        ) as semantic_mock:
            with patch(
                "api.tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "OUT_OF_SCOPE",
                    "search_query": "test",
                    "article_stance": "NEUTRAL",
                },
            ):
                execute_core_text_pipeline(
                    new_claim.context_text,
                    new_claim.id,
                )

        semantic_mock.assert_not_called()

        new_claim.refresh_from_db()

        self.assertIsNone(new_claim.final_verdict)


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
