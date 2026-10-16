from django.db.models import Count, Q
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .management_permissions import IsPlatformManagementAdmin
from .management_serializers import (
    ManagementInvitationSerializer,
    ManagementMembershipSerializer,
    ManagementOrganizationDetailSerializer,
    ManagementOrganizationListSerializer,
)
from .models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)


class ManagementPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _filter_choice(queryset, params, parameter, choices, field=None):
    value = params.get(parameter)
    if not value:
        return queryset

    valid_values = {choice for choice, _label in choices}
    if value not in valid_values:
        raise ValidationError({parameter: "Select a valid choice."})

    return queryset.filter(**{field or parameter: value})


def _filter_organization_id(queryset, params):
    organization_id = params.get("organization_id")
    if not organization_id:
        return queryset

    try:
        return queryset.filter(organization_id=organization_id)
    except (ValueError, DjangoValidationError) as error:
        raise ValidationError(
            {"organization_id": "Enter a valid organization ID."}
        ) from error


class ManagementOverviewView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request):
        counts = Organization.objects.aggregate(
            total=Count("id"),
            active_partners=Count(
                "id",
                filter=Q(partner_status=Organization.PartnerStatus.ACTIVE),
            ),
            pending_verification=Count(
                "id",
                filter=Q(
                    verification_status=Organization.VerificationStatus.PENDING
                ),
            ),
            suspended_partners=Count(
                "id",
                filter=Q(partner_status=Organization.PartnerStatus.SUSPENDED),
            ),
        )
        return Response({"organizations": counts}, status=status.HTTP_200_OK)


class ManagementOrganizationListView(generics.ListAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementOrganizationListSerializer
    pagination_class = ManagementPagination

    def get_queryset(self):
        queryset = Organization.objects.all().order_by("name", "id")
        params = self.request.query_params
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(slug__icontains=query))

        queryset = _filter_choice(
            queryset,
            params,
            "verification_status",
            Organization.VerificationStatus.choices,
        )
        queryset = _filter_choice(
            queryset,
            params,
            "partner_status",
            Organization.PartnerStatus.choices,
        )
        queryset = _filter_choice(
            queryset,
            params,
            "organization_type",
            Organization.OrganizationType.choices,
        )

        public_profile_enabled = params.get("public_profile_enabled")
        if public_profile_enabled:
            normalized = public_profile_enabled.lower()
            if normalized not in {"true", "false"}:
                raise ValidationError(
                    {"public_profile_enabled": "Use true or false."}
                )
            queryset = queryset.filter(
                public_profile_enabled=normalized == "true"
            )

        return queryset


class ManagementOrganizationDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementOrganizationDetailSerializer
    queryset = Organization.objects.all()
    lookup_url_kwarg = "organization_id"

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "now": timezone.now()}


class ManagementMembershipListView(generics.ListAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementMembershipSerializer
    pagination_class = ManagementPagination

    def get_queryset(self):
        queryset = OrganizationMembership.objects.select_related(
            "organization",
            "user",
            "approved_by",
        ).order_by("-joined_at", "-id")
        params = self.request.query_params
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(organization__name__icontains=query)
                | Q(user__username__icontains=query)
                | Q(user__email__icontains=query)
            )

        queryset = _filter_organization_id(queryset, params)
        queryset = _filter_choice(
            queryset,
            params,
            "role",
            OrganizationMembership.Role.choices,
        )
        return _filter_choice(
            queryset,
            params,
            "status",
            OrganizationMembership.Status.choices,
        )


class ManagementMembershipDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementMembershipSerializer
    queryset = OrganizationMembership.objects.select_related(
        "organization",
        "user",
        "approved_by",
    )
    lookup_url_kwarg = "membership_id"


class ManagementInvitationListView(generics.ListAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementInvitationSerializer
    pagination_class = ManagementPagination

    def get_queryset(self):
        queryset = OrganizationInvitation.objects.select_related(
            "organization",
            "invited_by",
            "accepted_by",
            "cancelled_by",
        ).order_by("-created_at", "-id")
        params = self.request.query_params
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(organization__name__icontains=query)
                | Q(email__icontains=query)
                | Q(invited_by__username__icontains=query)
                | Q(invited_by__email__icontains=query)
            )

        queryset = _filter_organization_id(queryset, params)
        queryset = _filter_choice(
            queryset,
            params,
            "status",
            OrganizationInvitation.Status.choices,
        )
        queryset = _filter_choice(
            queryset,
            params,
            "purpose",
            OrganizationInvitation.InvitationPurpose.choices,
        )
        return _filter_choice(
            queryset,
            params,
            "invited_role",
            OrganizationMembership.Role.choices,
        )


class ManagementInvitationDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementInvitationSerializer
    queryset = OrganizationInvitation.objects.select_related(
        "organization",
        "invited_by",
        "accepted_by",
        "cancelled_by",
    )
    lookup_url_kwarg = "invitation_id"
