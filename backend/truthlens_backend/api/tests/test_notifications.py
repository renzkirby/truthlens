import uuid
from datetime import timedelta
from unittest.mock import Mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Notification
from api.notification_service import (
    NOTIFICATION_METADATA, create_notification_once, dispatch_after_commit,
    notification_destination,
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
        self.assertEqual(data["actor"], {"id": self.other.pk, "username": self.other.username})
        self.assertEqual(self.client.get(reverse("notification_list"), {"filter": "bad"}).status_code, 400)
