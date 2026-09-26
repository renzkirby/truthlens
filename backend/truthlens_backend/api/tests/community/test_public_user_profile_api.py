from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Claim, EvidenceSubmission, Thread, ThreadComment


class PublicUserProfileApiTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="profile-viewer",
            email="viewer-private@example.com",
            password="test-password",
        )
        self.member = User.objects.create_user(
            username="community-member",
            email="member-private@example.com",
            password="test-password",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.viewer)

    def _url(self, suffix=""):
        return f"/api/users/{self.member.username}/{suffix}"

    def _create_thread(self, label, thread_status):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=f"Claim context for {label}",
        )
        return Thread.objects.create(
            claim=claim,
            author=self.member,
            caption=f"Discussion about {label}",
            status=thread_status,
        )

    def _assert_private_account_fields_absent(self, payload):
        for field in (
            "email",
            "is_email_verified",
            "has_completed_onboarding",
            "workspace",
            "auth_methods",
            "organization_name",
        ):
            self.assertNotIn(field, payload)

    def test_authenticated_member_can_retrieve_safe_community_profile(self):
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.member.username)
        self._assert_private_account_fields_absent(response.data)

    def test_profile_activity_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)

        for suffix in ("", "threads/", "evidence/"):
            with self.subTest(suffix=suffix):
                response = self.client.get(self._url(suffix))
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_follower_and_following_lists_use_safe_identity_projection(self):
        follower = User.objects.create_user(
            username="profile-follower",
            email="follower-private@example.com",
            password="test-password",
        )
        followed_member = User.objects.create_user(
            username="followed-member",
            email="followed-private@example.com",
            password="test-password",
        )
        self.member.profile.followers.add(follower)
        followed_member.profile.followers.add(self.member)

        followers_response = self.client.get(self._url("followers/"))
        following_response = self.client.get(self._url("following/"))

        self.assertEqual(followers_response.status_code, status.HTTP_200_OK)
        self.assertEqual(following_response.status_code, status.HTTP_200_OK)
        self.assertEqual(followers_response.data[0]["username"], follower.username)
        self.assertEqual(
            following_response.data[0]["username"], followed_member.username
        )
        for payload in (followers_response.data[0], following_response.data[0]):
            self.assertEqual(
                set(payload),
                {"id", "username", "avatar_url", "role", "trust_score"},
            )
            self._assert_private_account_fields_absent(payload)

    def test_threads_include_community_states_and_exclude_rejected_content(self):
        visible_threads = [
            self._create_thread("pending item", Thread.Status.PENDING),
            self._create_thread("open item", Thread.Status.OPEN),
            self._create_thread("closed item", Thread.Status.CLOSED),
        ]
        rejected_thread = self._create_thread("removed item", Thread.Status.REJECTED)
        EvidenceSubmission.objects.create(
            thread=visible_threads[1],
            contributor=self.viewer,
            evidence_caption="A visible source",
        )
        ThreadComment.objects.create(
            thread=visible_threads[1],
            commenter=self.viewer,
            comment_text="A visible comment",
        )

        response = self.client.get(self._url("threads/"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data}
        self.assertEqual(returned_ids, {str(thread.id) for thread in visible_threads})
        self.assertNotIn(str(rejected_thread.id), returned_ids)
        open_payload = next(
            item for item in response.data if item["id"] == str(visible_threads[1].id)
        )
        self.assertEqual(
            set(open_payload["claim"]), {"id", "claim_type", "context_text"}
        )
        self.assertEqual(open_payload["evidence_count"], 1)
        self.assertEqual(open_payload["comment_count"], 1)

    def test_contributions_include_safe_context_and_exclude_rejected_threads(self):
        visible_thread = self._create_thread("visible activity", Thread.Status.OPEN)
        rejected_thread = self._create_thread("removed activity", Thread.Status.REJECTED)
        visible_evidence = EvidenceSubmission.objects.create(
            thread=visible_thread,
            contributor=self.member,
            evidence_caption="Visible evidence contribution",
        )
        visible_comment = ThreadComment.objects.create(
            thread=visible_thread,
            commenter=self.member,
            comment_text="Visible comment contribution",
        )
        EvidenceSubmission.objects.create(
            thread=rejected_thread,
            contributor=self.member,
            evidence_caption="Removed evidence contribution",
        )
        ThreadComment.objects.create(
            thread=rejected_thread,
            commenter=self.member,
            comment_text="Removed comment contribution",
        )

        response = self.client.get(self._url("evidence/"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned = {(item["activity_type"], item["id"]) for item in response.data}
        self.assertEqual(
            returned,
            {
                ("EVIDENCE", str(visible_evidence.id)),
                ("COMMENT", str(visible_comment.id)),
            },
        )
        for item in response.data:
            self.assertEqual(
                set(item["thread"]),
                {"id", "caption", "status", "created_at", "claim"},
            )
            self.assertEqual(
                set(item["thread"]["claim"]),
                {"id", "claim_type", "context_text"},
            )
            self.assertEqual(
                item["thread"]["claim"]["context_text"],
                visible_thread.claim.context_text,
            )

    def test_follow_and_unfollow_behavior_is_preserved(self):
        follow_response = self.client.post(self._url("follow/"))
        unfollow_response = self.client.post(self._url("follow/"))

        self.assertEqual(follow_response.status_code, status.HTTP_200_OK)
        self.assertTrue(follow_response.data["is_following"])
        self.assertEqual(follow_response.data["followers_count"], 1)
        self.assertEqual(unfollow_response.status_code, status.HTTP_200_OK)
        self.assertFalse(unfollow_response.data["is_following"])
        self.assertEqual(unfollow_response.data["followers_count"], 0)

    def test_self_follow_remains_rejected(self):
        response = self.client.post(
            f"/api/users/{self.viewer.username}/follow/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "You cannot follow yourself.")

    def test_unknown_username_returns_safe_not_found_response(self):
        response = self.client.get("/api/users/missing-community-member/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)
        self.assertNotContains(
            response,
            self.member.email,
            status_code=status.HTTP_404_NOT_FOUND,
        )
