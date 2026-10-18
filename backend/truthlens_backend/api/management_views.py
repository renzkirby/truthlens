from django.db.models import Count, Q
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .accountability_query_service import (
    AccountabilityQueryAuthorizationError,
    AccountabilityQueryInputError,
    AccountabilityQueryNotFound,
    get_management_governance_accountability_event,
    list_management_governance_accountability_events,
)
from .management_permissions import IsPlatformManagementAdmin
from .management_pipeline_service import (
    ManagementPipelineRunNotFound,
    build_management_pipeline_overview,
    get_management_pipeline_run,
    list_management_pipeline_runs,
    serialize_management_pipeline_run,
)
from .management_governance_service import (
    ManagementGovernanceAuthorizationError,
    ManagementGovernanceConflict,
    ManagementGovernanceValidationError,
    create_partner_organization,
    update_organization_platform_trust,
)
from .management_serializers import (
    ManagementEmptyMutationSerializer,
    ManagementGovernanceAuditDetailQuerySerializer,
    ManagementGovernanceAuditQuerySerializer,
    ManagementInvitationSerializer,
    ManagementMembershipSerializer,
    ManagementOrganizationCreateSerializer,
    ManagementOrganizationDetailSerializer,
    ManagementOrganizationListSerializer,
    ManagementPlatformTrustUpdateSerializer,
    ManagementPrimaryAdminInvitationSerializer,
    ManagementPrimaryAdminProvisionSerializer,
    ManagementPipelineOverviewQuerySerializer,
    ManagementPipelineRunDetailQuerySerializer,
    ManagementPipelineRunListQuerySerializer,
)
from .models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from .organization_provisioning_service import (
    OrganizationProvisioningAuthorizationError,
    OrganizationProvisioningConflict,
    OrganizationProvisioningDeliveryError,
    OrganizationProvisioningError,
    cancel_primary_admin_invitation,
    create_and_send_primary_admin_invitation,
    resend_primary_admin_invitation,
)
from .serializers import AccountabilityEventSerializer, AccountabilityPageSerializer


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


class ManagementPipelineOverviewView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request):
        serializer = ManagementPipelineOverviewQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = build_management_pipeline_overview(
            window_value=serializer.validated_data["window"]
        )
        return Response(payload, status=status.HTTP_200_OK)


class ManagementPipelineRunListView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request):
        serializer = ManagementPipelineRunListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = list_management_pipeline_runs(
            window_value=data["window"],
            status=data.get("status", ""),
            claim_type=data.get("claim_type", ""),
        )
        paginator = ManagementPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [serialize_management_pipeline_run(run) for run in page]
        )


class ManagementPipelineRunDetailView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request, run_id):
        serializer = ManagementPipelineRunDetailQuerySerializer(
            data=request.query_params
        )
        serializer.is_valid(raise_exception=True)
        try:
            payload = get_management_pipeline_run(run_id=run_id)
        except ManagementPipelineRunNotFound:
            return Response(
                {"detail": "Verification run not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(payload, status=status.HTTP_200_OK)


def _governance_conflict_response(error):
    payload = {"detail": str(error)}
    if error.field:
        payload[error.field] = [str(error)]
    return Response(payload, status=status.HTTP_409_CONFLICT)


def _governance_validation_response(error):
    payload = {"detail": str(error)}
    if error.field:
        payload[error.field] = [str(error)]
    return Response(payload, status=status.HTTP_400_BAD_REQUEST)


def _serialize_management_organization(organization):
    return ManagementOrganizationDetailSerializer(
        organization,
        context={"now": timezone.now()},
    ).data


def _provisioning_error_response(error):
    if isinstance(error, OrganizationProvisioningAuthorizationError):
        response_status = status.HTTP_403_FORBIDDEN
    elif isinstance(error, OrganizationProvisioningConflict):
        response_status = status.HTTP_409_CONFLICT
    elif isinstance(error, OrganizationProvisioningDeliveryError):
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response_status = status.HTTP_400_BAD_REQUEST

    return Response({"detail": str(error)}, status=response_status)


class ManagementOrganizationListView(generics.ListCreateAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementOrganizationListSerializer
    pagination_class = ManagementPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ManagementOrganizationCreateSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            organization = create_partner_organization(
                **serializer.validated_data,
                actor=request.user,
            )
        except ManagementGovernanceAuthorizationError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ManagementGovernanceValidationError as error:
            return _governance_validation_response(error)
        except ManagementGovernanceConflict as error:
            return _governance_conflict_response(error)

        return Response(
            _serialize_management_organization(organization),
            status=status.HTTP_201_CREATED,
        )

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


class ManagementOrganizationPlatformTrustView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def patch(self, request, organization_id):
        serializer = ManagementPlatformTrustUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            organization = update_organization_platform_trust(
                organization_id=organization_id,
                actor=request.user,
                **serializer.validated_data,
            )
        except Organization.DoesNotExist:
            return Response(
                {"detail": "Organization not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ManagementGovernanceAuthorizationError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ManagementGovernanceValidationError as error:
            return _governance_validation_response(error)

        return Response(
            _serialize_management_organization(organization),
            status=status.HTTP_200_OK,
        )


class ManagementPrimaryAdminProvisionView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def post(self, request, organization_id):
        serializer = ManagementPrimaryAdminProvisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(Organization, pk=organization_id)

        try:
            invitation = create_and_send_primary_admin_invitation(
                organization=organization,
                email=serializer.validated_data["email"],
                actor=request.user,
            )
        except OrganizationProvisioningError as error:
            return _provisioning_error_response(error)

        return Response(
            ManagementPrimaryAdminInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )


class ManagementPrimaryAdminResendView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def post(self, request, organization_id):
        serializer = ManagementEmptyMutationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(Organization, pk=organization_id)

        has_current_primary_admin = (
            organization.memberships.filter(
                role=OrganizationMembership.Role.OWNER,
            )
            .exclude(status=OrganizationMembership.Status.LEFT)
            .exists()
        )
        if has_current_primary_admin:
            return Response(
                {"detail": "This organization already has a current Primary Admin."},
                status=status.HTTP_409_CONFLICT,
            )

        invitation = (
            organization.invitations.filter(
                purpose=(
                    OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
                ),
                invited_role=OrganizationMembership.Role.OWNER,
                status=OrganizationInvitation.Status.PENDING,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if invitation is None:
            return Response(
                {
                    "detail": (
                        "There is no active Primary Admin invitation to resend. "
                        "Issue a replacement invitation if the previous one expired."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            invitation = resend_primary_admin_invitation(
                invitation=invitation,
                actor=request.user,
            )
        except OrganizationProvisioningError as error:
            return _provisioning_error_response(error)

        return Response(
            ManagementPrimaryAdminInvitationSerializer(invitation).data,
            status=status.HTTP_200_OK,
        )


class ManagementPrimaryAdminCancelView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def post(self, request, organization_id):
        serializer = ManagementEmptyMutationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(Organization, pk=organization_id)

        has_current_primary_admin = (
            organization.memberships.filter(
                role=OrganizationMembership.Role.OWNER,
            )
            .exclude(status=OrganizationMembership.Status.LEFT)
            .exists()
        )
        if has_current_primary_admin:
            return Response(
                {"detail": "This organization already has a current Primary Admin."},
                status=status.HTTP_409_CONFLICT,
            )

        invitation = (
            organization.invitations.filter(
                purpose=(
                    OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
                ),
                invited_role=OrganizationMembership.Role.OWNER,
                status=OrganizationInvitation.Status.PENDING,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if invitation is None:
            return Response(
                {"detail": "There is no active Primary Admin invitation to cancel."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            invitation = cancel_primary_admin_invitation(
                invitation=invitation,
                actor=request.user,
            )
        except OrganizationProvisioningError as error:
            return _provisioning_error_response(error)

        return Response(
            ManagementPrimaryAdminInvitationSerializer(invitation).data,
            status=status.HTTP_200_OK,
        )


class ManagementGovernanceAuditListView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request):
        serializer = ManagementGovernanceAuditQuerySerializer(
            data=request.query_params
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            payload = list_management_governance_accountability_events(
                actor=request.user,
                action_type=data.get("action_type", ""),
                organization_search=data.get("organization", ""),
                actor_search=data.get("actor", ""),
                created_after=data.get("created_after"),
                created_before=data.get("created_before"),
                limit=data["limit"],
                offset=data["offset"],
            )
        except AccountabilityQueryAuthorizationError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except AccountabilityQueryInputError as error:
            raise ValidationError({"detail": str(error)}) from error

        return Response(
            AccountabilityPageSerializer(payload).data,
            status=status.HTTP_200_OK,
        )


class ManagementGovernanceAuditDetailView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request, event_id):
        serializer = ManagementGovernanceAuditDetailQuerySerializer(
            data=request.query_params
        )
        serializer.is_valid(raise_exception=True)

        try:
            payload = get_management_governance_accountability_event(
                actor=request.user,
                event_id=event_id,
            )
        except AccountabilityQueryAuthorizationError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except AccountabilityQueryNotFound:
            return Response(
                {"detail": "Management governance audit event not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            AccountabilityEventSerializer(payload).data,
            status=status.HTTP_200_OK,
        )


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
