from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from .models import Claim, EvidenceSubmission, Thread, ThreadComment, UserProfile


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

    def test_thread_status_and_flag_reason_are_read_only_for_normal_thread_flow(self):
        thread_detail = reverse("thread-detail", args=[str(self.thread.id)])

        res = self.owner_client.patch(
            thread_detail,
            {"status": "CLOSED", "flag_reason": "FAKE", "caption": "Updated caption"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.caption, "Updated caption")
        self.assertEqual(self.thread.status, "OPEN")
        self.assertIsNone(self.thread.flag_reason)
