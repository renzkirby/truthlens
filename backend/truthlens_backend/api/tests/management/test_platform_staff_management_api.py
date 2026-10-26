from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import AccountabilityEvent, UserProfile
from api.platform_staff_service import MANAGE_PLATFORM_STAFF


class PlatformStaffManagementApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="platform-admin",
            email="platform-admin@example.com",
            password="test-password",
        )
        self.moderator = User.objects.create_user(
            username="safety-moderator",
            email="safety@example.com",
            password="test-password",
        )
        moderator_profile, _ = UserProfile.objects.get_or_create(user=self.moderator)
        moderator_profile.role = UserProfile.Role.MOD
        moderator_profile.save(update_fields=["role"])

        self.ordinary = User.objects.create_user(
            username="eligible-user",
            email="eligible@example.com",
            password="test-password",
        )
        UserProfile.objects.get_or_create(user=self.ordinary)

        self.inactive = User.objects.create_user(
            username="inactive-user",
            email="inactive@example.com",
            password="test-password",
            is_active=False,
        )
        UserProfile.objects.get_or_create(user=self.inactive)

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def test_platform_admin_can_list_platform_staff(self):
        response = self.client_for(self.admin).get(reverse("management_platform_staff"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_username = {
            item["username"]: item for item in response.data["results"]
        }
        self.assertEqual(
            by_username[self.admin.username]["platform_role"],
            "PLATFORM_ADMIN",
        )
        self.assertFalse(by_username[self.admin.username]["can_revoke"])
        self.assertEqual(
            by_username[self.moderator.username]["platform_role"],
            "PLATFORM_SAFETY_MODERATOR",
        )
        self.assertTrue(by_username[self.moderator.username]["can_revoke"])
        self.assertNotIn(self.ordinary.username, by_username)

    def test_candidate_search_returns_only_eligible_active_accounts(self):
        client = self.client_for(self.admin)

        response = client.get(
            reverse("management_platform_staff_candidates"),
            {"q": "user"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = {item["username"] for item in response.data["results"]}
        self.assertIn(self.ordinary.username, usernames)
        self.assertNotIn(self.inactive.username, usernames)
        self.assertNotIn(self.moderator.username, usernames)
        self.assertNotIn(self.admin.username, usernames)

    def test_candidate_search_requires_two_characters_before_returning_results(self):
        response = self.client_for(self.admin).get(
            reverse("management_platform_staff_candidates"),
            {"q": "e"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_platform_admin_can_grant_safety_moderator_role_and_audit_it(self):
        response = self.client_for(self.admin).post(
            reverse("management_platform_staff"),
            {"user_id": self.ordinary.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["platform_role"],
            "PLATFORM_SAFETY_MODERATOR",
        )
        self.ordinary.profile.refresh_from_db()
        self.assertEqual(self.ordinary.profile.role, UserProfile.Role.MOD)

        event = AccountabilityEvent.objects.get(
            action_type=(
                AccountabilityEvent.ActionType.PLATFORM_SAFETY_MODERATOR_GRANTED
            ),
            resource_id=str(self.ordinary.id),
        )
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(
            event.authority_scope,
            AccountabilityEvent.AuthorityScope.PLATFORM,
        )
        self.assertEqual(event.capability, MANAGE_PLATFORM_STAFF)
        self.assertEqual(
            event.resource_type,
            AccountabilityEvent.ResourceType.USER_ACCOUNT,
        )
        self.assertEqual(
            event.previous_state,
            {"platform_role": "COMMUNITY_USER"},
        )
        self.assertEqual(
            event.new_state,
            {"platform_role": "PLATFORM_SAFETY_MODERATOR"},
        )

    def test_grant_rejects_admin_existing_moderator_and_inactive_account(self):
        client = self.client_for(self.admin)
        cases = (
            (self.admin.id, status.HTTP_409_CONFLICT),
            (self.moderator.id, status.HTTP_409_CONFLICT),
            (self.inactive.id, status.HTTP_400_BAD_REQUEST),
        )

        for user_id, expected_status in cases:
            with self.subTest(user_id=user_id):
                response = client.post(
                    reverse("management_platform_staff"),
                    {"user_id": user_id},
                    format="json",
                )
                self.assertEqual(response.status_code, expected_status)

    def test_platform_admin_can_revoke_safety_moderator_role_and_audit_it(self):
        response = self.client_for(self.admin).delete(
            reverse(
                "management_platform_staff_detail",
                kwargs={"user_id": self.moderator.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moderator.profile.refresh_from_db()
        self.assertEqual(self.moderator.profile.role, UserProfile.Role.USER)

        event = AccountabilityEvent.objects.get(
            action_type=(
                AccountabilityEvent.ActionType.PLATFORM_SAFETY_MODERATOR_REVOKED
            ),
            resource_id=str(self.moderator.id),
        )
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.capability, MANAGE_PLATFORM_STAFF)
        self.assertEqual(
            event.previous_state,
            {"platform_role": "PLATFORM_SAFETY_MODERATOR"},
        )
        self.assertEqual(
            event.new_state,
            {"platform_role": "COMMUNITY_USER"},
        )

    def test_safety_moderator_cannot_manage_platform_staff(self):
        client = self.client_for(self.moderator)

        list_response = client.get(reverse("management_platform_staff"))
        candidate_response = client.get(
            reverse("management_platform_staff_candidates"),
            {"q": "eligible"},
        )
        grant_response = client.post(
            reverse("management_platform_staff"),
            {"user_id": self.ordinary.id},
            format="json",
        )
        revoke_response = client.delete(
            reverse(
                "management_platform_staff_detail",
                kwargs={"user_id": self.moderator.id},
            )
        )

        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(candidate_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(grant_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(revoke_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_staff_change_is_visible_in_governance_audit(self):
        client = self.client_for(self.admin)
        grant = client.post(
            reverse("management_platform_staff"),
            {"user_id": self.ordinary.id},
            format="json",
        )
        self.assertEqual(grant.status_code, status.HTTP_201_CREATED)

        response = client.get(
            reverse("management_governance_audit"),
            {"action_type": "PLATFORM_SAFETY_MODERATOR_GRANTED"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        event = response.data["results"][0]
        self.assertEqual(
            event["action_type"],
            "PLATFORM_SAFETY_MODERATOR_GRANTED",
        )
        self.assertEqual(event["resource"]["type"], "USER_ACCOUNT")
        self.assertEqual(
            event["context"]["target_username"],
            self.ordinary.username,
        )
