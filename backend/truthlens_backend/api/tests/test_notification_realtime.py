import asyncio
import uuid
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import AsyncClient, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from api.models import Notification
from api.notification_realtime import (
    INBOX_CHANGED_EVENT,
    notification_channel,
    notification_event_stream,
    publish_notification_inbox_changed,
)
from api.notification_service import create_notification_once


class RealtimeNotificationMutationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="realtime-owner")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create(self, dedupe_key="realtime:test"):
        return create_notification_once(
            recipient_id=self.user.pk,
            notification_type=Notification.NotificationType.THREAD_COMMENTED,
            target_type=Notification.TargetType.THREAD,
            target_id=uuid.uuid4(),
            dedupe_key=dedupe_key,
            title="Realtime test",
            message="Inbox changed.",
        )

    def test_new_notification_publishes_once_but_deduped_row_does_not(self):
        with patch(
            "api.notification_service.publish_notification_inbox_changed"
        ) as publish:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.create()
                second = self.create()
        self.assertEqual(first.pk, second.pk)
        publish.assert_called_once_with(self.user.pk)

    def test_mark_read_only_publishes_for_the_state_change(self):
        row = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.THREAD_COMMENTED,
            target_type=Notification.TargetType.THREAD,
            target_id=uuid.uuid4(),
            dedupe_key="read-change",
            title="Read test",
            message="Read test.",
        )
        url = reverse("notification_mark_read", args=[row.pk])
        with patch("api.views.publish_notification_inbox_changed") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.patch(url).status_code, 200)
            publish.assert_called_once_with(self.user.pk)
            publish.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.patch(url).status_code, 200)
            publish.assert_not_called()

    def test_mark_all_only_publishes_when_rows_change(self):
        self.create("mark-all:one")
        self.create("mark-all:two")
        with patch("api.views.publish_notification_inbox_changed") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("notification_mark_all_read"))
            self.assertEqual(response.data["updated_count"], 2)
            publish.assert_called_once_with(self.user.pk)
            publish.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("notification_mark_all_read"))
            self.assertEqual(response.data["updated_count"], 0)
            publish.assert_not_called()

    @override_settings(NOTIFICATION_SSE_ENABLED=True)
    def test_authoritative_state_survives_redis_client_construction_failure(self):
        with patch(
            "api.notification_realtime.redis.Redis.from_url",
            side_effect=ValueError("invalid redis URL"),
        ):
            with self.assertLogs("api.notification_realtime", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    row = self.create("redis-config:create")

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.patch(
                        reverse("notification_mark_read", args=[row.pk])
                    )

        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertIsNotNone(row.read_at)

    @override_settings(NOTIFICATION_SSE_ENABLED=True)
    def test_authoritative_state_survives_redis_publish_failure(self):
        client = Mock()
        client.publish.side_effect = OSError("redis unavailable")
        with patch(
            "api.notification_realtime.redis.Redis.from_url",
            return_value=client,
        ):
            with self.assertLogs("api.notification_realtime", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    row = self.create("redis-publish:create")

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.patch(
                        reverse("notification_mark_read", args=[row.pk])
                    )

        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertIsNotNone(row.read_at)


class FakePubSub:
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.subscribed = []
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def get_message(self, **_kwargs):
        if self.messages:
            message = self.messages.pop(0)
            if isinstance(message, BaseException):
                raise message
            return message
        return None

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def aclose(self):
        self.closed = True


class FakeAsyncRedis:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        self.closed = True


@override_settings(
    NOTIFICATION_SSE_ENABLED=True,
    NOTIFICATION_REDIS_URL="redis://realtime.invalid/0",
)
class NotificationRealtimeTransportTests(TestCase):
    def test_recipient_channel_is_private_and_stable(self):
        self.assertEqual(
            notification_channel(42),
            "truthlens:notifications:user:42",
        )
        self.assertNotEqual(notification_channel(42), notification_channel(43))

    def test_publish_failure_is_logged_and_isolated(self):
        client = Mock()
        client.publish.side_effect = OSError("redis unavailable")
        with patch("api.notification_realtime.redis.Redis.from_url", return_value=client):
            with self.assertLogs("api.notification_realtime", level="ERROR"):
                self.assertFalse(publish_notification_inbox_changed(42))
        client.close.assert_called_once_with()

    def test_client_construction_failure_is_logged_and_isolated(self):
        with patch(
            "api.notification_realtime.redis.Redis.from_url",
            side_effect=ValueError("invalid redis URL"),
        ):
            with self.assertLogs("api.notification_realtime", level="ERROR"):
                self.assertFalse(publish_notification_inbox_changed(42))

    def test_close_failure_is_logged_without_changing_publish_success(self):
        client = Mock()
        client.close.side_effect = OSError("close failed")
        with patch(
            "api.notification_realtime.redis.Redis.from_url",
            return_value=client,
        ) as from_url:
            with self.assertLogs("api.notification_realtime", level="ERROR"):
                self.assertTrue(publish_notification_inbox_changed(42))

        from_url.assert_called_once_with(
            "redis://realtime.invalid/0",
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    async def test_stream_formats_heartbeat_and_inbox_event_and_cleans_up(self):
        pubsub = FakePubSub([None, {"type": "message", "data": b"{}"}])
        client = FakeAsyncRedis(pubsub)
        with patch(
            "api.notification_realtime.async_redis.Redis.from_url",
            return_value=client,
        ):
            stream = notification_event_stream(
                42,
                max_lifetime=60,
                heartbeat_interval=1,
            )
            frames = [
                await anext(stream),
                await anext(stream),
                await anext(stream),
            ]
            await stream.aclose()

        self.assertEqual(frames, [b": connected\n\n", b": heartbeat\n\n", INBOX_CHANGED_EVENT])
        self.assertEqual(pubsub.subscribed, [notification_channel(42)])
        self.assertEqual(pubsub.unsubscribed, [notification_channel(42)])
        self.assertTrue(pubsub.closed)
        self.assertTrue(client.closed)

    async def test_stream_lifetime_is_bounded(self):
        pubsub = FakePubSub()
        client = FakeAsyncRedis(pubsub)
        with patch(
            "api.notification_realtime.async_redis.Redis.from_url",
            return_value=client,
        ):
            stream = notification_event_stream(7, max_lifetime=0)
            self.assertEqual(await anext(stream), b": connected\n\n")
            with self.assertRaises(StopAsyncIteration):
                await anext(stream)
        self.assertTrue(pubsub.closed)
        self.assertTrue(client.closed)

    async def test_stream_cancellation_cleans_up_subscription(self):
        pubsub = FakePubSub([asyncio.CancelledError()])
        client = FakeAsyncRedis(pubsub)
        with patch(
            "api.notification_realtime.async_redis.Redis.from_url",
            return_value=client,
        ):
            stream = notification_event_stream(9, max_lifetime=60)
            await anext(stream)
            with self.assertRaises(asyncio.CancelledError):
                await anext(stream)
        self.assertEqual(pubsub.unsubscribed, [notification_channel(9)])
        self.assertTrue(pubsub.closed)
        self.assertTrue(client.closed)


class NotificationStreamEndpointTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="stream-owner")
        self.other = User.objects.create_user(username="other-stream-owner")
        self.token = str(AccessToken.for_user(self.user))
        self.client = AsyncClient()

    @override_settings(NOTIFICATION_SSE_ENABLED=False)
    async def test_disabled_stream_returns_not_found(self):
        response = await self.client.get(
            reverse("notification_stream"),
            headers={"authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(response.status_code, 404)

    @override_settings(NOTIFICATION_SSE_ENABLED=True)
    async def test_unauthenticated_stream_is_rejected(self):
        response = await self.client.get(reverse("notification_stream"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Bearer")

    @override_settings(NOTIFICATION_SSE_ENABLED=True)
    async def test_authenticated_stream_is_scoped_to_authenticated_recipient(self):
        recipients = []

        async def fake_stream(recipient_id):
            recipients.append(recipient_id)
            yield INBOX_CHANGED_EVENT

        with patch(
            "api.notification_stream.notification_event_stream",
            side_effect=fake_stream,
        ):
            response = await self.client.get(
                reverse("notification_stream"),
                headers={"authorization": f"Bearer {self.token}"},
            )
            frame = await anext(response.streaming_content)
            await response.streaming_content.aclose()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-cache, no-store, must-revalidate")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertEqual(frame, INBOX_CHANGED_EVENT)
        self.assertEqual(recipients, [self.user.pk])
        self.assertNotIn(self.other.pk, recipients)
