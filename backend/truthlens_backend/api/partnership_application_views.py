from django.db.models import Q
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .management_permissions import IsPlatformManagementAdmin
from .models import PartnershipApplication
from .partnership_application_serializers import (
    ManagementPartnershipApplicationSerializer,
    PartnershipApplicationApprovalSerializer,
    PartnershipApplicationCreateSerializer,
    PartnershipApplicationEmptySerializer,
    PartnershipApplicationRejectionSerializer,
)
from .partnership_application_service import (
    PartnershipApplicationAuthorizationError,
    PartnershipApplicationConflict,
    PartnershipApplicationValidationError,
    approve_partnership_application,
    reject_partnership_application,
    start_partnership_application_review,
    submit_partnership_application,
)


class PartnershipApplicationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _application_error_response(error):
    if isinstance(error, PartnershipApplicationAuthorizationError):
        response_status = status.HTTP_403_FORBIDDEN
    elif isinstance(error, PartnershipApplicationConflict):
        response_status = status.HTTP_409_CONFLICT
    else:
        response_status = status.HTTP_400_BAD_REQUEST

    payload = {"detail": str(error)}
    field = getattr(error, "field", None)
    if field:
        payload[field] = [str(error)]
    return Response(payload, status=response_status)


class PublicPartnershipApplicationCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PartnershipApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = submit_partnership_application(
                **serializer.validated_data,
            )
        except (
            PartnershipApplicationConflict,
            PartnershipApplicationValidationError,
        ) as error:
            return _application_error_response(error)

        return Response(
            {
                "application_id": str(application.pk),
                "status": application.status,
                "message": (
                    "Your partnership application was submitted for TruthLens review."
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class ManagementPartnershipApplicationListView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request):
        queryset = PartnershipApplication.objects.select_related(
            "organization",
            "reviewer",
            "decided_by",
        ).order_by("-created_at", "-id")

        application_status = request.query_params.get("status", "").strip()
        if application_status:
            valid_statuses = {
                value for value, _label in PartnershipApplication.Status.choices
            }
            if application_status not in valid_statuses:
                return Response(
                    {"status": ["Select a valid choice."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=application_status)

        query = request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(organization__name__icontains=query)
                | Q(applicant_full_name__icontains=query)
                | Q(applicant_email__icontains=query)
                | Q(official_contact_email__icontains=query)
            )

        paginator = PartnershipApplicationPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            ManagementPartnershipApplicationSerializer(page, many=True).data
        )


class ManagementPartnershipApplicationDetailView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get_application(self, application_id):
        return PartnershipApplication.objects.select_related(
            "organization",
            "reviewer",
            "decided_by",
        ).filter(pk=application_id).first()

    def get(self, request, application_id):
        application = self.get_application(application_id)
        if application is None:
            return Response(
                {"detail": "Partnership application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            ManagementPartnershipApplicationSerializer(application).data,
            status=status.HTTP_200_OK,
        )


class ManagementPartnershipApplicationReviewView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def post(self, request, application_id):
        serializer = PartnershipApplicationEmptySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = start_partnership_application_review(
                application_id=application_id,
                actor=request.user,
            )
        except PartnershipApplication.DoesNotExist:
            return Response(
                {"detail": "Partnership application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (
            PartnershipApplicationAuthorizationError,
            PartnershipApplicationConflict,
            PartnershipApplicationValidationError,
        ) as error:
            return _application_error_response(error)

        return Response(
            ManagementPartnershipApplicationSerializer(application).data,
            status=status.HTTP_200_OK,
        )


class ManagementPartnershipApplicationApproveView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def post(self, request, application_id):
        serializer = PartnershipApplicationApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = approve_partnership_application(
                application_id=application_id,
                actor=request.user,
                **serializer.validated_data,
            )
        except PartnershipApplication.DoesNotExist:
            return Response(
                {"detail": "Partnership application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (
            PartnershipApplicationAuthorizationError,
            PartnershipApplicationConflict,
            PartnershipApplicationValidationError,
        ) as error:
            return _application_error_response(error)

        return Response(
            ManagementPartnershipApplicationSerializer(application).data,
            status=status.HTTP_200_OK,
        )


class ManagementPartnershipApplicationRejectView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def post(self, request, application_id):
        serializer = PartnershipApplicationRejectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = reject_partnership_application(
                application_id=application_id,
                actor=request.user,
                **serializer.validated_data,
            )
        except PartnershipApplication.DoesNotExist:
            return Response(
                {"detail": "Partnership application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (
            PartnershipApplicationAuthorizationError,
            PartnershipApplicationConflict,
            PartnershipApplicationValidationError,
        ) as error:
            return _application_error_response(error)

        return Response(
            ManagementPartnershipApplicationSerializer(application).data,
            status=status.HTTP_200_OK,
        )
