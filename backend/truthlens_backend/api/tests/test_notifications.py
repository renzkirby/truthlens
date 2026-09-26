import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Notification
from api.notification_service import (
    NOTIFICATION_METADATA, create_notification_once, dispatch_after_commit,
    notification_destination, notify_user_followed,
)


class NotificationFoundationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="inbox-owner")
        self.other = User.objects.create_user(username="other-inbox")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create(self, **kwargs):
        values = dict(
            recipient_id=self.user.pk,
            notification_type=Notification.NotificationType.THREAD_COMMENTED,
            target_type=Notification.TargetType.THREAD, target_id=uuid.uuid4(),
            dedupe_key="comment:one", title="New comment", message="Someone commented.",
        )
        values.update(kwargs)
        return create_notification_once(**values)

    def test_every_type_has_metadata(self):
        self.assertEqual(set(NOTIFICATION_METADATA), set(Notification.NotificationType.values))

    def test_duplicate_is_immutable_and_read_state_is_preserved(self):
        first = self.create()
        self.client.patch(reverse("notification_mark_read", args=[first.pk]))
        second = self.create(title="Replacement")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.title, "New comment")
        self.assertTrue(second.is_read)
        self.assertEqual(Notification.objects.count(), 1)

    def test_database_enforces_recipient_dedupe(self):
        first = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notification.objects.create(recipient=self.user, dedupe_key=first.dedupe_key,
                                        notification_type=first.notification_type,
                                        target_type=first.target_type, title="x", message="x")
        self.create(recipient_id=self.other.pk)
        self.assertEqual(Notification.objects.count(), 2)

    def test_types_are_constrained_and_text_is_plain_and_bounded(self):
        with self.assertRaises(ValidationError):
            self.create(target_type="https://evil.example")
        with self.assertRaises(ValidationError):
            self.create(notification_type="MENTION")
        row = self.create(title="<b>Hi</b>", message="<p>" + "a" * 700 + "</p>")
        self.assertEqual(row.title, "Hi")
        self.assertEqual(len(row.message), 500)

    def test_self_suppression_and_account_exception(self):
        self.assertIsNone(self.create(actor_id=self.user.pk))
        self.assertIsNotNone(self.create(actor_id=self.user.pk,
            notification_type=Notification.NotificationType.ORGANIZATION_MEMBERSHIP_CHANGED))
        self.assertIsNone(self.create(recipient_id=None))

    def test_dispatch_only_after_commit_and_rollback_discards(self):
        callback = Mock()
        with self.captureOnCommitCallbacks(execute=True):
            dispatch_after_commit(callback, 7)
            callback.assert_not_called()
        callback.assert_called_once_with(7)
        callback.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValueError), transaction.atomic():
                dispatch_after_commit(callback)
                raise ValueError("rollback")
        callback.assert_not_called()

    def test_delivery_failure_is_logged_and_isolated(self):
        def broken():
            self.create()
            raise RuntimeError("delivery unavailable")
        with self.assertLogs("api.notification_service", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                dispatch_after_commit(broken)
        self.assertFalse(Notification.objects.exists())
        self.create()

    def test_list_is_private_read_only_and_paginated_newest_first(self):
        self.create(recipient_id=self.other.pk)
        rows = [self.create(dedupe_key=f"comment:{i}") for i in range(22)]
        # Creation calls can share a clock tick; insertion order is not timestamp order.
        first_created_at = timezone.now() - timedelta(minutes=1)
        for index, row in enumerate(rows):
            Notification.objects.filter(pk=row.pk).update(
                created_at=first_created_at + timedelta(seconds=index),
            )
        response = self.client.get(reverse("notification_list"), {"recipient_id": self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertEqual(response.data["results"][0]["id"], str(rows[-1].pk))
        self.assertNotIn("dedupe_key", response.data["results"][0])
        self.assertEqual(response.data["results"][0]["category"], "COMMUNITY")
        self.assertIsNotNone(response.data["next"])
        next_page = self.client.get(response.data["next"])
        self.assertEqual(len(next_page.data["results"]), 2)
        self.assertEqual(
            [item["id"] for item in response.data["results"] + next_page.data["results"]],
            [str(row.pk) for row in reversed(rows)],
        )
        self.assertIsNone(next_page.data["next"])
        self.assertEqual(self.client.post(reverse("notification_list"), {}).status_code, 405)

    def test_equal_timestamps_use_descending_uuid_across_cursor_pages(self):
        timestamp = timezone.now() - timedelta(minutes=1)
        # Deliberately insert out of UUID order, with ties spanning three pages.
        ids = list(range(1, 46, 2)) + list(range(2, 46, 2))
        for value in ids:
            Notification.objects.create(
                id=uuid.UUID(int=value), recipient=self.user,
                notification_type=Notification.NotificationType.THREAD_COMMENTED,
                target_type=Notification.TargetType.THREAD,
                dedupe_key=f"tie:{value}", title="New comment", message="Someone commented.",
            )
        Notification.objects.filter(recipient=self.user).update(created_at=timestamp)
        newest = self.create(dedupe_key="newest")
        oldest = self.create(dedupe_key="oldest")
        Notification.objects.filter(pk=newest.pk).update(created_at=timestamp + timedelta(seconds=1))
        Notification.objects.filter(pk=oldest.pk).update(created_at=timestamp - timedelta(seconds=1))
        self.create(recipient_id=self.other.pk)
        expected = [str(newest.pk)] + [str(uuid.UUID(int=i)) for i in range(45, 0, -1)] + [str(oldest.pk)]

        pages = []
        url = reverse("notification_list")
        while url:
            self.assertLess(len(pages), 3, "Cursor must advance and terminate")
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            repeated = self.client.get(url)
            self.assertEqual(response.data, repeated.data)
            pages.append(response.data)
            url = response.data["next"]
        actual = [item["id"] for page in pages for item in page["results"]]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual([len(page["results"]) for page in pages], [20, 20, 7])

    def test_page_size_is_bounded_without_changing_the_default(self):
        for index in range(22):
            self.create(dedupe_key=f"page-size:{index}")

        self.assertEqual(
            len(self.client.get(reverse("notification_list")).data["results"]),
            20,
        )
        for page_size in (1, 8, 20):
            with self.subTest(page_size=page_size):
                response = self.client.get(
                    reverse("notification_list"),
                    {"page_size": page_size},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.data["results"]), page_size)

        for page_size in ("invalid", 0, -1, 21, 1000):
            with self.subTest(page_size=page_size):
                response = self.client.get(
                    reverse("notification_list"),
                    {"page_size": page_size},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("page_size", response.data)

    def test_read_endpoints_are_scoped_and_idempotent(self):
        own = self.create()
        other = self.create(recipient_id=self.other.pk)
        url = reverse("notification_mark_read", args=[own.pk])
        first = self.client.patch(url)
        self.assertTrue(first.data["is_read"])
        self.assertEqual(self.client.patch(url).data["read_at"], first.data["read_at"])
        self.assertEqual(self.client.patch(reverse("notification_mark_read", args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("notification_unread_count")).data["unread_count"], 0)
        self.assertEqual(self.client.get(reverse("notification_list"), {"filter": "unread"}).data["results"], [])
        other.refresh_from_db()
        self.assertFalse(other.is_read)

    def test_mark_all_uses_shared_timestamp_and_only_own_unread_rows(self):
        rows = [self.create(dedupe_key=f"comment:{i}") for i in range(3)]
        other = self.create(recipient_id=self.other.pk)
        self.assertEqual(self.client.post(reverse("notification_mark_all_read")).data["updated_count"], 3)
        timestamps = set(Notification.objects.filter(pk__in=[r.pk for r in rows]).values_list("read_at", flat=True))
        self.assertEqual(len(timestamps), 1)
        self.assertNotIn(None, timestamps)
        self.assertEqual(self.client.post(reverse("notification_mark_all_read")).data["updated_count"], 0)
        other.refresh_from_db()
        self.assertFalse(other.is_read)

    def test_anonymous_requests_fail(self):
        self.client.force_authenticate(None)
        for name, method, args in (
            ("notification_list", "get", []), ("notification_unread_count", "get", []),
            ("notification_mark_all_read", "post", []), ("notification_mark_read", "patch", [uuid.uuid4()]),
        ):
            self.assertEqual(getattr(self.client, method)(reverse(name, args=args)).status_code, 401)

    def test_destinations_are_internal_or_null(self):
        row = self.create()
        self.assertEqual(notification_destination(row), f"/thread/detail/{row.target_id}")
        row.target_type = Notification.TargetType.CLAIM
        self.assertEqual(notification_destination(row), f"/analysis/{row.target_id}")
        row.target_type = Notification.TargetType.WORKSPACE
        self.assertEqual(notification_destination(row), "/workspace")
        row.target_type = Notification.TargetType.OFFICIAL_FACT_CHECK
        self.assertIsNone(notification_destination(row))
        row.target_type = Notification.TargetType.ORGANIZATION
        self.assertIsNone(notification_destination(row))

    def test_actor_summary_excludes_email_and_invalid_filter_fails(self):
        self.create(actor_id=self.other.pk)
        data = self.client.get(reverse("notification_list")).data["results"][0]
        self.assertEqual(data["actor"], {
            "id": self.other.pk,
            "username": self.other.username,
            "avatar_url": None,
        })
        self.assertEqual(self.client.get(reverse("notification_list"), {"filter": "bad"}).status_code, 400)


class FollowNotificationTests(TestCase):
    def setUp(self):
        self.follower = User.objects.create_user(username="follower+encoded")
        self.followed = User.objects.create_user(username="followed-user")
        self.unrelated = User.objects.create_user(username="unrelated-user")
        self.follower.profile.avatar_url = "https://cdn.example/follower.png"
        self.follower.profile.save(update_fields=["avatar_url"])
        self.client = APIClient()
        self.client.force_authenticate(self.follower)
        self.url = f"/api/users/{self.followed.username}/follow/"

    def follow(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url)

    def test_initial_follow_creates_private_social_notification(self):
        response = self.follow()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_following"])
        notification = Notification.objects.get()
        self.assertEqual(notification.notification_type, Notification.NotificationType.USER_FOLLOWED)
        self.assertEqual(notification.actor, self.follower)
        self.assertEqual(notification.recipient, self.followed)
        self.assertEqual(notification.target_type, Notification.TargetType.USER_PROFILE)
        self.assertIsNone(notification.target_id)
        self.assertEqual(
            notification_destination(notification),
            "/user/follower%2Bencoded",
        )

        self.client.force_authenticate(self.followed)
        item = self.client.get(reverse("notification_list")).data["results"][0]
        self.assertEqual(item["category"], "COMMUNITY")
        self.assertEqual(item["priority"], "SOCIAL")
        self.assertEqual(item["destination"], "/user/follower%2Bencoded")
        self.assertEqual(item["actor"], {
            "id": self.follower.pk,
            "username": self.follower.username,
            "avatar_url": "https://cdn.example/follower.png",
        })
        self.assertNotIn("email", item["actor"])

        self.client.force_authenticate(self.unrelated)
        self.assertEqual(
            self.client.get(reverse("notification_list")).data["results"],
            [],
        )

    def test_self_follow_and_unfollow_do_not_create_notifications(self):
        self.client.force_authenticate(self.followed)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Notification.objects.exists())

        self.client.force_authenticate(self.follower)
        self.follow()
        self.assertEqual(Notification.objects.count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url)
        self.assertFalse(response.data["is_following"])
        self.assertEqual(Notification.objects.count(), 1)

    def test_refollow_creates_a_new_generation_notification(self):
        self.follow()
        first = Notification.objects.get()
        first_key = first.dedupe_key
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url)
        self.follow()

        notifications = list(Notification.objects.order_by("created_at", "id"))
        self.assertEqual(len(notifications), 2)
        self.assertNotEqual(notifications[0].dedupe_key, notifications[1].dedupe_key)
        self.assertEqual(notifications[0].dedupe_key, first_key)

    def test_same_follow_generation_delivery_is_deduplicated(self):
        through_model = self.followed.profile.followers.through
        relationship = through_model.objects.create(
            userprofile=self.followed.profile,
            user=self.follower,
        )
        kwargs = {
            "relationship_id": relationship.pk,
            "actor_id": self.follower.pk,
            "recipient_id": self.followed.pk,
        }
        first = notify_user_followed(**kwargs)
        second = notify_user_followed(**kwargs)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Notification.objects.count(), 1)

    def test_delivery_failure_does_not_break_follow_transition(self):
        with patch("api.views.notify_user_followed", side_effect=RuntimeError("delivery")):
            with self.assertLogs("api.notification_service", level="ERROR"):
                response = self.follow()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_following"])
        self.assertTrue(self.followed.profile.followers.filter(pk=self.follower.pk).exists())
        self.assertFalse(Notification.objects.exists())

    def test_deleted_actor_removes_profile_destination(self):
        self.follow()
        notification = Notification.objects.get()
        self.follower.delete()
        notification.refresh_from_db()
        self.assertIsNone(notification.actor_id)
        self.assertIsNone(notification_destination(notification))


@skipUnlessDBFeature("has_select_for_update")
class FollowNotificationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.follower = User.objects.create_user(username="concurrent-follower")
        self.followed = User.objects.create_user(username="concurrent-followed")
        self.url = f"/api/users/{self.followed.username}/follow/"

    def test_concurrent_toggle_requests_serialize_one_follow_generation(self):
        barrier = Barrier(2)

        def toggle():
            close_old_connections()
            client = APIClient()
            client.force_authenticate(User.objects.get(pk=self.follower.pk))
            barrier.wait()
            response = client.post(self.url)
            close_old_connections()
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: toggle(), range(2)))

        self.assertEqual(statuses, [200, 200])
        self.assertFalse(self.followed.profile.followers.filter(pk=self.follower.pk).exists())
        self.assertEqual(Notification.objects.count(), 1)
