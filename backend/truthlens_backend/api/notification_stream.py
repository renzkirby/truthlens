"""Authenticated ASGI streaming endpoint for notification invalidation."""

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connection
from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .notification_realtime import notification_event_stream


def _authenticate_user_id_and_release_db(request):
    """Authenticate the request, then release the DB connection before streaming."""
    authentication = JWTAuthentication()

    try:
        result = authentication.authenticate(request)
        if not result:
            return None

        user, _validated_token = result
        return user.pk
    except AuthenticationFailed:
        return None
    finally:
        # SSE requests can live for several minutes. Do not keep the database
        # connection used during authentication attached to the long-lived stream.
        connection.close()


async def _authenticated_user_id(request):
    return await sync_to_async(
        _authenticate_user_id_and_release_db,
        thread_sensitive=True,
    )(request)


async def notification_stream(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    if not settings.NOTIFICATION_SSE_ENABLED:
        return JsonResponse(
            {"detail": "Notification streaming is disabled."},
            status=404,
        )

    user_id = await _authenticated_user_id(request)
    if user_id is None:
        response = JsonResponse(
            {
                "detail": (
                    "Authentication credentials were not provided or are invalid."
                )
            },
            status=401,
        )
        response["WWW-Authenticate"] = "Bearer"
        return response

    response = StreamingHttpResponse(
        notification_event_stream(user_id),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["X-Accel-Buffering"] = "no"
    return response
