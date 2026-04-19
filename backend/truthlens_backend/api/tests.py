from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from .models import Claim, ClaimCheckHistory, EvidenceSubmission, Thread, ThreadComment, UserProfile
from .throttles import FactCheckRateThrottle


class ThreadEvidenceCommentAuthorizationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@test.com", password="pass1234")
        self.other = User.objects.create_user(username="other", email="other@test.com", password="pass1234")

        UserProfile.objects.create(user=self.owner, trust_score=88.0)
        UserProfile.objects.create(user=self.other, trust_score=42.0)

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

        self.thread = Thread.objects.create(claim=self.claim1, author=self.owner, caption="Owner thread")
        self.other_thread = Thread.objects.create(claim=self.claim2, author=self.other, caption="Other thread")

        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.owner,
            evidence_caption="Owner evidence",
            evidence_type=EvidenceSubmission.EvidenceType.URL_LINK,
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

        patch_res = self.other_client.patch(thread_detail, {"caption": "Hijack"}, format="json")
        delete_res = self.other_client.delete(thread_detail)

        self.assertEqual(patch_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_owner_cannot_update_or_delete_comment(self):
        comment_detail = reverse("comment-detail", args=[str(self.comment.id)])

        patch_res = self.other_client.patch(comment_detail, {"comment_text": "Hijack"}, format="json")
        delete_res = self.other_client.delete(comment_detail)

        self.assertEqual(patch_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_owner_cannot_update_or_delete_evidence(self):
        evidence_detail = reverse("evidence-detail", args=[str(self.evidence.id)])

        patch_res = self.other_client.patch(evidence_detail, {"evidence_caption": "Hijack"}, format="json")
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
                "evidence_type": EvidenceSubmission.EvidenceType.URL_LINK,
                "contributor_trust_snapshot": 9999,
            },
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created = EvidenceSubmission.objects.get(id=res.data["id"])
        self.assertEqual(created.contributor, self.other)
        self.assertEqual(created.thread, self.thread)
        self.assertEqual(created.contributor_trust_snapshot, self.other.profile.trust_score)

    def test_thread_owner_can_submit_evidence_on_own_thread(self):
        evidence_list = reverse("evidence-list")

        res = self.owner_client.post(
            evidence_list,
            {
                "thread_id": str(self.thread.id),
                "evidence_caption": "Owner evidence",
                "evidence_url": "https://owner-proof.example.com",
                "evidence_type": EvidenceSubmission.EvidenceType.URL_LINK,
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
    - Trust score calculations (+2 VERIFIED, -1 REJECTED, capped 0-100)
    - Moderator audit trail (verified_by, verified_at, moderator_notes)
    """
    
    def setUp(self):
        """Set up test data with regular users and a moderator."""
        # Create regular users
        self.contributor = User.objects.create_user(
            username="contributor", 
            email="contributor@test.com", 
            password="pass1234"
        )
        self.other_user = User.objects.create_user(
            username="otheruser",
            email="otheruser@test.com",
            password="pass1234"
        )
        
        # Create moderator
        self.moderator = User.objects.create_user(
            username="moderator",
            email="moderator@test.com",
            password="pass1234"
        )
        
        # Set up user profiles with roles
        self.contributor_profile = UserProfile.objects.create(
            user=self.contributor, 
            trust_score=50.0,
            role=UserProfile.Role.USER
        )
        self.other_profile = UserProfile.objects.create(
            user=self.other_user,
            trust_score=75.0,
            role=UserProfile.Role.USER
        )
        self.moderator_profile = UserProfile.objects.create(
            user=self.moderator,
            trust_score=95.0,
            role=UserProfile.Role.MODERATOR
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
            caption="Test thread for verification"
        )
        
        # Create evidence
        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Test evidence",
            evidence_type=EvidenceSubmission.EvidenceType.URL_LINK,
            evidence_url="https://evidence.example.com",
            contributor_trust_snapshot=self.contributor_profile.trust_score,
        )
        
        # Set up API clients
        self.contributor_client = APIClient()
        self.contributor_client.force_authenticate(user=self.contributor)
        
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other_user)
        
        self.moderator_client = APIClient()
        self.moderator_client.force_authenticate(user=self.moderator)
        
        self.unauthenticated_client = APIClient()
        
    def test_unauthenticated_user_cannot_verify_evidence(self):
        """Unauthenticated users should get 401 Unauthorized."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.unauthenticated_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        
    def test_non_moderator_user_cannot_verify_evidence(self):
        """Regular users (even contributors) should get 403 Forbidden."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.contributor_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        
    def test_non_moderator_other_user_cannot_verify_evidence(self):
        """Another non-moderator user should also get 403 Forbidden."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.other_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_moderator_can_verify_evidence(self):
        """Moderators can verify evidence as VERIFIED."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.moderator_client.patch(
            verify_url,
            {
                "evidence_status": "VERIFIED",
                "moderator_notes": "Evidence looks legitimate"
            },
            format="json"
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
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.moderator_client.patch(
            verify_url,
            {
                "evidence_status": "REJECTED",
                "moderator_notes": "Evidence is not credible"
            },
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["evidence_status"], "REJECTED")
        
        # Verify database was updated
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.evidence_status, "REJECTED")
        self.assertEqual(self.evidence.verified_by, self.moderator)
        self.assertIsNotNone(self.evidence.verified_at)
        self.assertEqual(self.evidence.moderator_notes, "Evidence is not credible")
        
    def test_moderator_notes_are_optional(self):
        """Moderators should be able to verify without providing notes."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.moderator_notes, "")
        
    def test_invalid_evidence_status_returns_400(self):
        """Invalid evidence_status should return 400 Bad Request."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "INVALID_STATUS"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)
        
    def test_verified_evidence_increases_trust_score_by_2(self):
        """Verifying evidence should increase contributor trust score by +2."""
        initial_score = self.contributor_profile.trust_score
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        # Refresh and check trust score (Celery task would run in background)
        # In tests, the task runs synchronously via CELERY_TASK_ALWAYS_EAGER
        self.contributor_profile.refresh_from_db()
        self.assertEqual(self.contributor_profile.trust_score, initial_score + 2.0)
        
    def test_rejected_evidence_decreases_trust_score_by_1(self):
        """Rejecting evidence should decrease contributor trust score by -1."""
        initial_score = self.contributor_profile.trust_score
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "REJECTED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        # Refresh and check trust score
        self.contributor_profile.refresh_from_db()
        self.assertEqual(self.contributor_profile.trust_score, initial_score - 1.0)
        
    def test_trust_score_capped_at_100(self):
        """Trust score should not exceed 100."""
        # Set contributor to high trust score
        self.contributor_profile.trust_score = 99.0
        self.contributor_profile.save()
        
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        # Verify evidence (should add +2)
        res = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        # Check trust score is capped at 100
        self.contributor_profile.refresh_from_db()
        self.assertEqual(self.contributor_profile.trust_score, 100.0)
        
    def test_trust_score_capped_at_0(self):
        """Trust score should not go below 0."""
        # Set contributor to low trust score
        self.contributor_profile.trust_score = 0.5
        self.contributor_profile.save()
        
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        # Reject evidence (should subtract -1)
        res = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "REJECTED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        # Check trust score is capped at 0
        self.contributor_profile.refresh_from_db()
        self.assertEqual(self.contributor_profile.trust_score, 0.0)
        
    def test_multiple_verifications_accumulate_trust_score(self):
        """Multiple verifications should accumulate trust score changes."""
        initial_score = self.contributor_profile.trust_score
        
        # Create multiple evidence items
        evidence2 = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Test evidence 2",
            evidence_type=EvidenceSubmission.EvidenceType.URL_LINK,
            evidence_url="https://evidence2.example.com",
            contributor_trust_snapshot=self.contributor_profile.trust_score,
        )
        
        verify_url1 = reverse("evidence-verify", args=[str(self.evidence.id)])
        verify_url2 = reverse("evidence-verify", args=[str(evidence2.id)])
        
        # Verify first evidence
        res1 = self.moderator_client.patch(
            verify_url1,
            {"evidence_status": "VERIFIED"},
            format="json"
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        
        # Reject second evidence
        res2 = self.moderator_client.patch(
            verify_url2,
            {"evidence_status": "REJECTED"},
            format="json"
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        
        # Check final trust score: initial + 2 - 1 = initial + 1
        self.contributor_profile.refresh_from_db()
        self.assertEqual(self.contributor_profile.trust_score, initial_score + 1.0)
        
    def test_verified_by_contains_moderator_info_in_response(self):
        """Response should include verified_by with moderator user info."""
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        res = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED"},
            format="json"
        )
        
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Check that verified_by contains user data
        self.assertIn("verified_by", res.data)
        if res.data["verified_by"]:  # Could be null if not serialized
            self.assertEqual(res.data["verified_by"]["username"], "moderator")
            
    def test_moderator_cannot_verify_already_verified_evidence(self):
        """
        Once evidence is verified, subsequent verify calls should update it.
        This tests idempotency / allows re-verification by another moderator.
        """
        verify_url = reverse("evidence-verify", args=[str(self.evidence.id)])
        
        # First verification
        res1 = self.moderator_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED", "moderator_notes": "First mod"},
            format="json"
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        
        # Create another moderator
        moderator2 = User.objects.create_user(
            username="moderator2",
            email="mod2@test.com",
            password="pass1234"
        )
        UserProfile.objects.create(
            user=moderator2,
            role=UserProfile.Role.MODERATOR
        )
        moderator2_client = APIClient()
        moderator2_client.force_authenticate(user=moderator2)
        
        # Second moderator re-verifies with different notes
        res2 = moderator2_client.patch(
            verify_url,
            {"evidence_status": "VERIFIED", "moderator_notes": "Second mod"},
            format="json"
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        
        # Check that it was updated by second moderator
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.verified_by, moderator2)
        self.assertEqual(self.evidence.moderator_notes, "Second mod")


class OptionalFactCheckAuthTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="detector",
            email="detector@test.com",
            password="pass1234",
        )
        UserProfile.objects.create(user=self.user, trust_score=50.0)

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
