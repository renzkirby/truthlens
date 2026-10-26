from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    Claim,
    EvidenceSubmission,
    Thread,
    ThreadComment,
    UserProfile,
)
from api.trust_service import recompute_user_trust_score


class PlatformStaffCommunityIdentityTests(TestCase):
    def setUp(self):
        self.community_user = User.objects.create_user(
            username="community-person",
            email="community-person@example.com",
            password="test-password",
        )
        self.platform_admin = User.objects.create_superuser(
            username="platform-admin",
            email="platform-admin@example.com",
            password="test-password",
        )
        self.safety_moderator = User.objects.create_user(
            username="platform-safety",
            email="platform-safety@example.com",
            password="test-password",
        )
        self.safety_moderator.profile.role = UserProfile.Role.MOD
        self.safety_moderator.profile.save(update_fields=["role"])

    @staticmethod
    def _client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_current_user_marks_platform_admin_as_non_community_identity(self):
        self.platform_admin.profile.trust_score = 88.0
        self.platform_admin.profile.save(update_fields=["trust_score"])

        response = self._client_for(self.platform_admin).get(reverse("auth_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["trust_score"])
        self.assertIsNone(response.data["trust_breakdown"])
        self.assertEqual(
            response.data["community_identity"],
            {
                "can_participate": False,
                "public_profile_available": False,
                "reputation_applicable": False,
                "platform_role": "PLATFORM_ADMIN",
                "platform_role_label": "Platform Admin",
            },
        )

    def test_current_user_marks_safety_moderator_as_non_community_identity(self):
        response = self._client_for(self.safety_moderator).get(reverse("auth_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["trust_score"])
        self.assertIsNone(response.data["trust_breakdown"])
        self.assertEqual(
            response.data["community_identity"]["platform_role"],
            "PLATFORM_SAFETY_MODERATOR",
        )
        self.assertEqual(
            response.data["community_identity"]["platform_role_label"],
            "Platform Safety Moderator",
        )
        self.assertFalse(response.data["community_identity"]["can_participate"])
        self.assertFalse(response.data["community_identity"]["reputation_applicable"])

    def test_ordinary_user_keeps_community_reputation_identity(self):
        response = self._client_for(self.community_user).get(reverse("auth_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["trust_score"])
        self.assertIsNotNone(response.data["trust_breakdown"])
        self.assertEqual(
            response.data["community_identity"],
            {
                "can_participate": True,
                "public_profile_available": True,
                "reputation_applicable": True,
                "platform_role": None,
                "platform_role_label": None,
            },
        )

    def test_platform_staff_are_not_public_community_profiles_or_search_results(self):
        viewer = self._client_for(self.community_user)

        for staff_user in (self.platform_admin, self.safety_moderator):
            with self.subTest(username=staff_user.username):
                profile_response = viewer.get(f"/api/users/{staff_user.username}/")
                search_response = viewer.get(
                    "/api/users/search/",
                    {"search": staff_user.username},
                )

                self.assertEqual(profile_response.status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(search_response.status_code, status.HTTP_200_OK)
                self.assertEqual(search_response.data, [])

    def test_platform_staff_cannot_follow_or_be_followed_as_community_profiles(self):
        admin_client = self._client_for(self.platform_admin)
        ordinary_client = self._client_for(self.community_user)

        actor_response = admin_client.post(
            f"/api/users/{self.community_user.username}/follow/"
        )
        target_response = ordinary_client.post(
            f"/api/users/{self.platform_admin.username}/follow/"
        )

        self.assertEqual(actor_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(target_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_platform_staff_cannot_mutate_community_resources(self):
        mutation_urls = [
            reverse("thread-list"),
            reverse("evidence-list"),
            reverse("comment-list"),
            reverse("vote-list"),
            reverse("thread-flag-list"),
        ]

        for staff_user in (self.platform_admin, self.safety_moderator):
            client = self._client_for(staff_user)
            for url in mutation_urls:
                with self.subTest(username=staff_user.username, url=url):
                    response = client.post(url, {}, format="json")
                    self.assertEqual(
                        response.status_code,
                        status.HTTP_403_FORBIDDEN,
                    )

    def test_platform_staff_can_still_read_community_threads(self):
        for staff_user in (self.platform_admin, self.safety_moderator):
            response = self._client_for(staff_user).get(reverse("thread-list"))
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_platform_staff_do_not_have_reputation_dashboard(self):
        for staff_user in (self.platform_admin, self.safety_moderator):
            response = self._client_for(staff_user).get(reverse("user_hub"))
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_trust_recomputation_skips_platform_staff(self):
        for staff_user in (self.platform_admin, self.safety_moderator):
            staff_user.profile.trust_score = 73.0
            staff_user.profile.save(update_fields=["trust_score"])

            result = recompute_user_trust_score(staff_user.id)

            staff_user.profile.refresh_from_db()
            self.assertEqual(
                result,
                {
                    "applicable": False,
                    "trust_score": None,
                },
            )
            self.assertEqual(staff_user.profile.trust_score, 73.0)

    def test_public_social_counts_exclude_legacy_platform_staff_relationships(self):
        self.community_user.profile.followers.add(
            self.platform_admin,
            self.safety_moderator,
        )

        response = self._client_for(
            User.objects.create_user(
                username="community-viewer",
                password="test-password",
            )
        ).get(f"/api/users/{self.community_user.username}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["followers_count"], 0)

    def test_historical_platform_staff_activity_is_hidden_from_community_projection(self):
        ordinary_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Ordinary community claim",
        )
        ordinary_thread = Thread.objects.create(
            claim=ordinary_claim,
            author=self.community_user,
            caption="Ordinary discussion",
            status=Thread.Status.OPEN,
        )
        EvidenceSubmission.objects.create(
            thread=ordinary_thread,
            contributor=self.platform_admin,
            evidence_caption="Historical admin evidence",
            evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
        )
        ThreadComment.objects.create(
            thread=ordinary_thread,
            commenter=self.safety_moderator,
            comment_text="Historical safety staff comment",
        )

        staff_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Historical staff-authored claim",
        )
        staff_thread = Thread.objects.create(
            claim=staff_claim,
            author=self.platform_admin,
            caption="Historical staff-authored discussion",
            status=Thread.Status.OPEN,
        )

        viewer = self._client_for(
            User.objects.create_user(
                username="projection-viewer",
                password="test-password",
            )
        )

        feed_response = viewer.get(reverse("thread-list"))
        detail_response = viewer.get(
            reverse("thread-detail", args=[ordinary_thread.id])
        )
        staff_detail_response = viewer.get(
            reverse("thread-detail", args=[staff_thread.id])
        )

        self.assertEqual(feed_response.status_code, status.HTTP_200_OK)
        feed_ids = {
            str(item["id"])
            for item in feed_response.data["results"]
        }
        self.assertIn(str(ordinary_thread.id), feed_ids)
        self.assertNotIn(str(staff_thread.id), feed_ids)

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["evidence_submissions"], [])
        self.assertEqual(detail_response.data["comments"], [])
        self.assertEqual(staff_detail_response.status_code, status.HTTP_404_NOT_FOUND)
