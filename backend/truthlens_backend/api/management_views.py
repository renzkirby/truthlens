from django.db.models import Count, Q
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
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
from .institution_affiliation_service import (
    create_institution,
    set_organization_institution_affiliation,
)
from .claim_institution_context_service import (
    set_claim_institution_context,
)
from .management_serializers import (
    ManagementClaimInstitutionContextSerializer,
    ManagementClaimInstitutionContextUpdateSerializer,
    ManagementEmptyMutationSerializer,
    ManagementGovernanceAuditDetailQuerySerializer,
    ManagementGovernanceAuditQuerySerializer,
    ManagementInstitutionAffiliationUpdateSerializer,
    ManagementInstitutionCreateSerializer,
    ManagementInstitutionSerializer,
    ManagementInvitationSerializer,
    ManagementMembershipSerializer,
    ManagementOrganizationCreateSerializer,
    ManagementOrganizationDetailSerializer,
    ManagementOrganizationInstitutionAffiliationSerializer,
    ManagementOrganizationListSerializer,
    ManagementPlatformStaffInvitationCreateSerializer,
    ManagementPlatformStaffInvitationPublicSerializer,
    ManagementPlatformStaffInvitationSerializer,
    ManagementPlatformStaffSerializer,
    ManagementPlatformTrustUpdateSerializer,
    ManagementPrimaryAdminInvitationSerializer,
    ManagementPrimaryAdminProvisionSerializer,
    ManagementPipelineOverviewQuerySerializer,
    ManagementPipelineRunDetailQuerySerializer,
    ManagementPipelineRunListQuerySerializer,
)
from .models import (
    ClaimInvestigationClassification,
    Institution,
    Organization,
    OrganizationInstitutionAffiliation,
    OrganizationInvitation,
    OrganizationMembership,
    PlatformStaffInvitation,
)
from .platform_staff_invitation_service import (
    PlatformStaffInvitationAuthorizationError,
    PlatformStaffInvitationConflict,
    PlatformStaffInvitationDeliveryError,
    PlatformStaffInvitationError,
    PlatformStaffInvitationNotFound,
    accept_platform_staff_invitation,
    cancel_platform_staff_invitation,
    create_and_send_platform_staff_invitation,
    get_platform_staff_invitation_by_token,
    get_platform_staff_invitations,
    resend_platform_staff_invitation,
)
from .platform_staff_service import (
    PlatformStaffAuthorizationError,
    PlatformStaffConflict,
    PlatformStaffNotFound,
    PlatformStaffValidationError,
    list_platform_staff,
    revoke_platform_safety_moderator,
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


def _platform_staff_error_response(error):
    if isinstance(error, PlatformStaffAuthorizationError):
        response_status = status.HTTP_403_FORBIDDEN
    elif isinstance(error, PlatformStaffNotFound):
        response_status = status.HTTP_404_NOT_FOUND
    elif isinstance(error, PlatformStaffConflict):
        response_status = status.HTTP_409_CONFLICT
    else:
        response_status = status.HTTP_400_BAD_REQUEST
    return Response({"detail": str(error)}, status=response_status)


def _platform_staff_invitation_error_response(error):
    if isinstance(error, PlatformStaffInvitationAuthorizationError):
        response_status = status.HTTP_403_FORBIDDEN
    elif isinstance(error, PlatformStaffInvitationNotFound):
        response_status = status.HTTP_404_NOT_FOUND
    elif isinstance(error, PlatformStaffInvitationConflict):
        response_status = status.HTTP_409_CONFLICT
    elif isinstance(error, PlatformStaffInvitationDeliveryError):
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response_status = status.HTTP_400_BAD_REQUEST
    return Response({"detail": str(error)}, status=response_status)


class ManagementPlatformStaffListView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request):
        try:
            queryset = list_platform_staff(
                actor=request.user,
                query=request.query_params.get("q", ""),
            )
        except PlatformStaffAuthorizationError as error:
            return _platform_staff_error_response(error)

        paginator = ManagementPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            ManagementPlatformStaffSerializer(page, many=True).data
        )


class ManagementPlatformStaffInvitationListView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request):
        try:
            invitations = get_platform_staff_invitations(actor=request.user)
        except PlatformStaffInvitationError as error:
            return _platform_staff_invitation_error_response(error)

        serializer = ManagementPlatformStaffInvitationSerializer(
            invitations,
            many=True,
        )
        return Response(
            {
                "count": invitations.count(),
                "summary": {
                    "pending": invitations.filter(
                        status=PlatformStaffInvitation.Status.PENDING,
                    ).count(),
                    "accepted": invitations.filter(
                        status=PlatformStaffInvitation.Status.ACCEPTED,
                    ).count(),
                    "cancelled": invitations.filter(
                        status=PlatformStaffInvitation.Status.CANCELLED,
                    ).count(),
                    "expired": invitations.filter(
                        status=PlatformStaffInvitation.Status.EXPIRED,
                    ).count(),
                },
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = ManagementPlatformStaffInvitationCreateSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        try:
            invitation = create_and_send_platform_staff_invitation(
                email=serializer.validated_data["email"],
                actor=request.user,
            )
        except PlatformStaffInvitationError as error:
            return _platform_staff_invitation_error_response(error)

        return Response(
            ManagementPlatformStaffInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )


class ManagementPlatformStaffInvitationResendView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def post(self, request, invitation_id):
        invitation = get_object_or_404(
            PlatformStaffInvitation.objects.select_related("invited_by"),
            pk=invitation_id,
        )
        try:
            invitation = resend_platform_staff_invitation(
                invitation=invitation,
                actor=request.user,
            )
        except PlatformStaffInvitationError as error:
            return _platform_staff_invitation_error_response(error)

        return Response(
            ManagementPlatformStaffInvitationSerializer(invitation).data,
            status=status.HTTP_200_OK,
        )


class ManagementPlatformStaffInvitationCancelView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def post(self, request, invitation_id):
        invitation = get_object_or_404(
            PlatformStaffInvitation.objects.select_related("invited_by"),
            pk=invitation_id,
        )
        try:
            invitation = cancel_platform_staff_invitation(
                invitation=invitation,
                actor=request.user,
            )
        except PlatformStaffInvitationError as error:
            return _platform_staff_invitation_error_response(error)

        return Response(
            ManagementPlatformStaffInvitationSerializer(invitation).data,
            status=status.HTTP_200_OK,
        )


class ManagementPlatformStaffDetailView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def delete(self, request, user_id):
        try:
            target_user = revoke_platform_safety_moderator(
                actor=request.user,
                user_id=user_id,
            )
        except (
            PlatformStaffAuthorizationError,
            PlatformStaffConflict,
            PlatformStaffNotFound,
            PlatformStaffValidationError,
        ) as error:
            return _platform_staff_error_response(error)

        return Response(
            {
                "id": target_user.id,
                "username": target_user.username,
                "revoked": True,
            },
            status=status.HTTP_200_OK,
        )


class PlatformStaffInvitationDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            invitation = get_platform_staff_invitation_by_token(token)
        except PlatformStaffInvitationError as error:
            return _platform_staff_invitation_error_response(error)

        return Response(
            ManagementPlatformStaffInvitationPublicSerializer(
                invitation,
                context={"request": request},
            ).data,
            status=status.HTTP_200_OK,
        )


class PlatformStaffInvitationAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, token):
        try:
            invitation = accept_platform_staff_invitation(
                raw_token=token,
                actor=request.user,
            )
        except PlatformStaffInvitationError as error:
            return _platform_staff_invitation_error_response(error)

        return Response(
            {
                "invitation": ManagementPlatformStaffInvitationPublicSerializer(
                    invitation,
                    context={"request": request},
                ).data,
                "platform_role": invitation.platform_role,
                "status": "ACTIVE",
            },
            status=status.HTTP_200_OK,
        )


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


class ManagementClaimInstitutionContextView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def _classification(self, claim_id):
        return (
            ClaimInvestigationClassification.objects.select_related(
                "campus_context_reviewed_by"
            )
            .prefetch_related(
                "institution_associations__institution",
                "institution_associations__assigned_by",
            )
            .filter(claim_id=claim_id)
            .first()
        )

    def get(self, request, claim_id):
        classification = self._classification(claim_id)
        if classification is None:
            return Response(
                {"detail": "Investigation classification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            ManagementClaimInstitutionContextSerializer(classification).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, claim_id):
        serializer = ManagementClaimInstitutionContextUpdateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        try:
            classification = set_claim_institution_context(
                claim_id=claim_id,
                actor=request.user,
                **serializer.validated_data,
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
            ManagementClaimInstitutionContextSerializer(classification).data,
            status=status.HTTP_200_OK,
        )


class ManagementInstitutionListView(generics.ListCreateAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementInstitutionSerializer
    pagination_class = ManagementPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ManagementInstitutionCreateSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            institution = create_institution(
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
            ManagementInstitutionSerializer(institution).data,
            status=status.HTTP_201_CREATED,
        )

    def get_queryset(self):
        queryset = Institution.objects.all().order_by("name", "id")
        query = self.request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(slug__icontains=query)
            )

        active = self.request.query_params.get("is_active")
        if active:
            normalized = active.lower()
            if normalized not in {"true", "false"}:
                raise ValidationError({"is_active": "Use true or false."})
            queryset = queryset.filter(is_active=normalized == "true")

        return queryset


class ManagementInstitutionDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPlatformManagementAdmin]
    serializer_class = ManagementInstitutionSerializer
    queryset = Institution.objects.all()
    lookup_url_kwarg = "institution_id"


class ManagementOrganizationInstitutionAffiliationView(APIView):
    permission_classes = [IsPlatformManagementAdmin]

    def get(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        try:
            affiliation = organization.institution_affiliation
        except OrganizationInstitutionAffiliation.DoesNotExist:
            return Response(
                {"detail": "Institution affiliation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            ManagementOrganizationInstitutionAffiliationSerializer(affiliation).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, organization_id):
        serializer = ManagementInstitutionAffiliationUpdateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        try:
            affiliation = set_organization_institution_affiliation(
                organization_id=organization_id,
                actor=request.user,
                **serializer.validated_data,
            )
        except Organization.DoesNotExist:
            return Response(
                {"detail": "Organization not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Institution.DoesNotExist:
            return Response(
                {"detail": "Institution not found."},
                status=status.HTTP_404_NOT_FOUND,
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
            ManagementOrganizationInstitutionAffiliationSerializer(affiliation).data,
            status=status.HTTP_200_OK,
        )


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
                role=OrganizationMembership.Role.ADMIN,
            )
            .exclude(status=OrganizationMembership.Status.LEFT)
            .exists()
        )
        if has_current_primary_admin:
            return Response(
                {"detail": "This organization already has a current Organization Admin."},
                status=status.HTTP_409_CONFLICT,
            )

        invitation = (
            organization.invitations.filter(
                purpose=(
                    OrganizationInvitation.InvitationPurpose.ORGANIZATION_ADMIN_ONBOARDING
                ),
                invited_role=OrganizationMembership.Role.ADMIN,
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
                        "There is no active Organization Admin invitation to resend. "
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
                role=OrganizationMembership.Role.ADMIN,
            )
            .exclude(status=OrganizationMembership.Status.LEFT)
            .exists()
        )
        if has_current_primary_admin:
            return Response(
                {"detail": "This organization already has a current Organization Admin."},
                status=status.HTTP_409_CONFLICT,
            )

        invitation = (
            organization.invitations.filter(
                purpose=(
                    OrganizationInvitation.InvitationPurpose.ORGANIZATION_ADMIN_ONBOARDING
                ),
                invited_role=OrganizationMembership.Role.ADMIN,
                status=OrganizationInvitation.Status.PENDING,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if invitation is None:
            return Response(
                {"detail": "There is no active Organization Admin invitation to cancel."},
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
