"""Authenticated ASGI streaming endpoint for notification invalidation."""

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .notification_realtime import notification_event_stream


async def _authenticated_user(request):
    authentication = JWTAuthentication()
    try:
        result = await sync_to_async(
            authentication.authenticate,
            thread_sensitive=True,
        )(request)
    except AuthenticationFailed:
        return None
    return result[0] if result else None


async def notification_stream(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)
    if not settings.NOTIFICATION_SSE_ENABLED:
        return JsonResponse({"detail": "Notification streaming is disabled."}, status=404)

    user = await _authenticated_user(request)
    if user is None:
        response = JsonResponse(
            {"detail": "Authentication credentials were not provided or are invalid."},
            status=401,
        )
        response["WWW-Authenticate"] = "Bearer"
        return response

    response = StreamingHttpResponse(
        notification_event_stream(user.pk),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["X-Accel-Buffering"] = "no"
    return response
