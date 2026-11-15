from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from .community_account_enforcement_serializers import (
    AccountEnforcementIssueSerializer,
    AccountEnforcementLiftSerializer,
    AccountEnforcementListQuerySerializer,
    AccountEnforcementReviewRequestSerializer,
    AccountEnforcementReviewResolveSerializer,
    AccountEnforcementReviewStartSerializer,
)
from .community_account_enforcement_service import (
    CommunityAccountEnforcementAuthorizationError,
    CommunityAccountEnforcementConflict,
    CommunityAccountEnforcementNotFound,
    CommunityAccountEnforcementValidationError,
    issue_account_enforcement,
    lift_enforcement_early,
    list_safety_account_enforcements,
    mark_enforcement_seen,
    resolve_enforcement_review,
    serialize_enforcement,
    start_enforcement_review,
    submit_enforcement_review,
)
from .models import (
    CommunityAccountEnforcement,
    CommunityAccountEnforcementReview,
    CommunitySafetyDecision,
)
from .platform_identity_service import can_review_platform_safety


class CanReviewCommunityAccountEnforcement(BasePermission):
    def has_permission(self, request, view):
        return can_review_platform_safety(request.user)


def _domain_error_response(error):
    if isinstance(error, CommunityAccountEnforcementAuthorizationError):
        raise PermissionDenied(str(error)) from error
    if isinstance(error, CommunityAccountEnforcementNotFound):
        raise NotFound("This Community account action is not available.") from error
    if isinstance(error, CommunityAccountEnforcementValidationError):
        key = error.field or "detail"
        return Response(
            {key: str(error)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(error, CommunityAccountEnforcementConflict):
        return Response(
            {
                "code": "COMMUNITY_ACCOUNT_ENFORCEMENT_CONFLICT",
                "detail": str(error),
            },
            status=status.HTTP_409_CONFLICT,
        )
    raise error


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def community_account_enforcement_seen(request, enforcement_id):
    try:
        enforcement = mark_enforcement_seen(
            enforcement_id=enforcement_id,
            actor=request.user,
        )
    except CommunityAccountEnforcementNotFound as error:
        return _domain_error_response(error)
    return Response(
        serialize_enforcement(enforcement, actor=request.user),
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def community_account_enforcement_review(request, enforcement_id):
    serializer = AccountEnforcementReviewRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        review = submit_enforcement_review(
            enforcement_id=enforcement_id,
            actor=request.user,
            **serializer.validated_data,
        )
        enforcement = CommunityAccountEnforcement.objects.select_related(
            "review",
            "review__reviewer",
            "issued_by",
            "safety_decision",
        ).get(pk=review.enforcement_id)
    except (
        CommunityAccountEnforcementNotFound,
        CommunityAccountEnforcementConflict,
        CommunityAccountEnforcementValidationError,
    ) as error:
        return _domain_error_response(error)

    return Response(
        serialize_enforcement(enforcement, actor=request.user),
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanReviewCommunityAccountEnforcement])
def safety_account_enforcement_collection(request):
    serializer = AccountEnforcementListQuerySerializer(
        data=request.query_params
    )
    serializer.is_valid(raise_exception=True)
    try:
        results = list_safety_account_enforcements(
            actor=request.user,
            status_filter=serializer.validated_data["status"],
            limit=serializer.validated_data["limit"],
        )
    except CommunityAccountEnforcementAuthorizationError as error:
        return _domain_error_response(error)

    return Response(
        {
            "count": len(results),
            "results": results,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanReviewCommunityAccountEnforcement])
def safety_case_account_enforcement(request, case_id):
    serializer = AccountEnforcementIssueSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    decision = (
        CommunitySafetyDecision.objects.select_related("content_owner")
        .filter(moderation_case_id=case_id)
        .first()
    )
    if decision is None:
        return Response(
            {
                "code": "CONTENT_DECISION_REQUIRED",
                "detail": (
                    "Complete a removed-content Safety decision before issuing "
                    "an account-level action."
                ),
            },
            status=status.HTTP_409_CONFLICT,
        )

    try:
        enforcement = issue_account_enforcement(
            safety_decision=decision,
            actor=request.user,
            **serializer.validated_data,
        )
    except (
        CommunityAccountEnforcementAuthorizationError,
        CommunityAccountEnforcementConflict,
        CommunityAccountEnforcementValidationError,
    ) as error:
        return _domain_error_response(error)

    return Response(
        serialize_enforcement(
            enforcement,
            actor=request.user,
            include_internal=True,
        ),
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanReviewCommunityAccountEnforcement])
def safety_account_enforcement_review_start(request, review_id):
    serializer = AccountEnforcementReviewStartSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        review = start_enforcement_review(
            review_id=review_id,
            actor=request.user,
            **serializer.validated_data,
        )
    except CommunityAccountEnforcementReview.DoesNotExist as error:
        raise NotFound("This account-action review is not available.") from error
    except (
        CommunityAccountEnforcementAuthorizationError,
        CommunityAccountEnforcementConflict,
        CommunityAccountEnforcementValidationError,
    ) as error:
        return _domain_error_response(error)

    enforcement = CommunityAccountEnforcement.objects.select_related(
        "user",
        "issued_by",
        "safety_decision",
        "review",
        "review__reviewer",
    ).get(pk=review.enforcement_id)
    return Response(
        serialize_enforcement(
            enforcement,
            actor=request.user,
            include_internal=True,
        ),
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanReviewCommunityAccountEnforcement])
def safety_account_enforcement_review_resolve(request, review_id):
    serializer = AccountEnforcementReviewResolveSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        review = resolve_enforcement_review(
            review_id=review_id,
            actor=request.user,
            **serializer.validated_data,
        )
    except CommunityAccountEnforcementReview.DoesNotExist as error:
        raise NotFound("This account-action review is not available.") from error
    except (
        CommunityAccountEnforcementAuthorizationError,
        CommunityAccountEnforcementConflict,
        CommunityAccountEnforcementValidationError,
    ) as error:
        return _domain_error_response(error)

    enforcement = CommunityAccountEnforcement.objects.select_related(
        "user",
        "issued_by",
        "safety_decision",
        "review",
        "review__reviewer",
    ).get(pk=review.enforcement_id)
    return Response(
        serialize_enforcement(
            enforcement,
            actor=request.user,
            include_internal=True,
        ),
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanReviewCommunityAccountEnforcement])
def safety_account_enforcement_lift(request, enforcement_id):
    serializer = AccountEnforcementLiftSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        enforcement = lift_enforcement_early(
            enforcement_id=enforcement_id,
            actor=request.user,
            **serializer.validated_data,
        )
    except CommunityAccountEnforcement.DoesNotExist as error:
        raise NotFound("This Community restriction is not available.") from error
    except (
        CommunityAccountEnforcementAuthorizationError,
        CommunityAccountEnforcementConflict,
        CommunityAccountEnforcementValidationError,
    ) as error:
        return _domain_error_response(error)

    return Response(
        serialize_enforcement(
            enforcement,
            actor=request.user,
            include_internal=True,
        ),
        status=status.HTTP_200_OK,
    )
