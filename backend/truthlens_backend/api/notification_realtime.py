"""Best-effort Redis delivery for notification inbox invalidation signals."""

import asyncio
import logging

import redis
import redis.asyncio as async_redis
from django.conf import settings

logger = logging.getLogger(__name__)
INBOX_CHANGED_EVENT = b"event: notification.inbox_changed\ndata: {}\n\n"
PUBLISH_CONNECT_TIMEOUT_SECONDS = 2
PUBLISH_SOCKET_TIMEOUT_SECONDS = 2


def notification_channel(recipient_id):
    return f"truthlens:notifications:user:{recipient_id}"


def publish_notification_inbox_changed(recipient_id):
    """Publish one non-authoritative signal without affecting caller success."""
    if not settings.NOTIFICATION_SSE_ENABLED or recipient_id is None:
        return False

    client = None
    try:
        client = redis.Redis.from_url(
            settings.NOTIFICATION_REDIS_URL,
            socket_connect_timeout=PUBLISH_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=PUBLISH_SOCKET_TIMEOUT_SECONDS,
        )
        client.publish(notification_channel(recipient_id), "{}")
        return True
    except (redis.RedisError, OSError, ValueError):
        logger.exception(
            "Realtime notification inbox publication failed for recipient %s",
            recipient_id,
        )
        return False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                logger.exception("Failed to close realtime notification publisher")


async def notification_event_stream(
    recipient_id,
    *,
    max_lifetime=None,
    heartbeat_interval=None,
):
    """Yield recipient-scoped SSE frames and always release Pub/Sub resources."""
    max_lifetime = (
        settings.NOTIFICATION_SSE_MAX_SECONDS
        if max_lifetime is None
        else max_lifetime
    )
    heartbeat_interval = (
        settings.NOTIFICATION_SSE_HEARTBEAT_SECONDS
        if heartbeat_interval is None
        else heartbeat_interval
    )
    client = async_redis.Redis.from_url(settings.NOTIFICATION_REDIS_URL)
    pubsub = client.pubsub()
    channel = notification_channel(recipient_id)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0, max_lifetime)

    try:
        await pubsub.subscribe(channel)
        yield b": connected\n\n"

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=min(max(0.1, heartbeat_interval), remaining),
            )
            if message and message.get("type") == "message":
                yield INBOX_CHANGED_EVENT
            else:
                yield b": heartbeat\n\n"
    except asyncio.CancelledError:
        raise
    finally:
        try:
            await pubsub.unsubscribe(channel)
        finally:
            await pubsub.aclose()
            await client.aclose()
