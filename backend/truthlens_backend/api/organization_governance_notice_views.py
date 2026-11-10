"""Authenticated Partner governance notice endpoints."""

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .organization_governance_notice_service import (
    GovernanceNoticeNotFound,
    get_governance_notice_for_user,
    list_governance_notices_for_user,
    mark_governance_notice_viewed,
    serialize_governance_notice,
)


class GovernanceNoticeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notices = list_governance_notices_for_user(request.user)
        return Response(
            {
                "results": [
                    serialize_governance_notice(notice)
                    for notice in notices
                ]
            }
        )


class GovernanceNoticeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, notice_id):
        try:
            notice = get_governance_notice_for_user(
                notice_id=notice_id,
                user=request.user,
            )
        except GovernanceNoticeNotFound:
            return Response(
                {"detail": "Governance notice not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(serialize_governance_notice(notice))


class GovernanceNoticeViewedView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, notice_id):
        try:
            notice = mark_governance_notice_viewed(
                notice_id=notice_id,
                user=request.user,
                viewed_at=timezone.now(),
            )
        except GovernanceNoticeNotFound:
            return Response(
                {"detail": "Governance notice not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(serialize_governance_notice(notice))
