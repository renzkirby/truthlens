from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator, EmptyPage
from django.http import JsonResponse
from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db import IntegrityError, transaction
from django.db.models import Q, Count, F, Max
from rest_framework.decorators import (
    api_view,
    permission_classes,
    action,
    throttle_classes,
)
from rest_framework import status, viewsets
from rest_framework.permissions import (
    IsAuthenticated,
    BasePermission,
    SAFE_METHODS,
    AllowAny,
)
from rest_framework.response import Response
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.pagination import CursorPagination
from rest_framework.views import APIView
from datetime import timedelta
from django.shortcuts import get_object_or_404
from PIL import Image
import json
import secrets
import base64
import uuid
import io
import PyPDF2
import docx
import os
from .services import (
    detect_ai_image,
    generate_deepfake_explanation,
    process_image,
    upload_image_to_database,
    validate_public_url,
    check_url_threat_reputation,
)
from .claim_matching import compute_fingerprint, find_matching_claim, get_match_result
from .tasks import (
    snippet_fact_check_process,
    url_fact_check_process,
    text_fact_check_process,
    recompute_user_trust_score_task,
)
from .models import (
    Claim,
    ClaimCheckHistory,
    Thread,
    UserProfile,
    EvidenceSubmission,
    ThreadComment,
    ThreadFlag,
    FlagResolutionLog,
    Vote,
    ModerationCase,
    Organization,
    OrganizationMembership,
    AdjudicationDecision,
    VerificationRun,
    OfficialFactCheck,
    VerificationAssignment,
)
from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    ModerationCaseError,
    ensure_safety_case,
    escalate_safety_case,
    resolve_safety_case,
)
from .organization_service import (
    PartnerCapability,
    has_capability,
    has_case_capability,
)
from .evidence_review_service import (
    EvidenceReviewAuthorizationError,
    EvidenceReviewConflict,
    EvidenceReviewError,
    ensure_evidence_case,
    get_latest_evidence_case,
    review_evidence_submission,
)
from .adjudication_service import (
    AdjudicationAuthorizationError,
    AdjudicationConflict,
    AdjudicationError,
    ensure_adjudication_case,
    get_latest_adjudication_case,
    has_adjudication_conflict,
    issue_adjudication_decision,
)
from .trust_service import (
    calculate_trust_components,
    get_reputation_progression,
    recompute_user_trust_score,
)
from .publishing_service import (
    PublishingError,
    PublishingAuthorizationError,
    PublishingConflict,
    create_fact_check_draft,
    update_fact_check_draft,
    submit_fact_check_for_review,
    publish_fact_check,
)
from .verification_assignment_service import (
    VerificationAssignmentAuthorizationError,
    VerificationAssignmentConflict,
    VerificationAssignmentError,
    VerificationAssignmentReleaseBlocked,
    claim_verification_assignment,
    ensure_verification_assignment,
    get_available_verification_assignments,
    get_claim_verification_organization,
    get_organization_verification_workload,
    release_verification_assignment,
)
from .throttles import (
    FactCheckRateThrottle,
    PasswordResetRateThrottle,
    EmailVerificationRateThrottle,
)
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    PublicUserSearchSerializer,
    PublicIdentityProfileSerializer,
    CurrentUserSerializer,
    UserProfileSerializer,
    ClaimSerializer,
    ThreadSerializer,
    ThreadCommentSerializer,
    EvidenceSubmissionSerializer,
    PublicUserThreadSerializer,
    PublicUserEvidenceSerializer,
    PublicUserCommentSerializer,
    PublicModeratorVerdictSerializer,
    ThreadDetailSerializer,
    VoteSerializer,
    ThreadFlagSerializer,
    ModerationDecisionSerializer,
    ClaimMatchSerializer,
    UserWithTrustBreakdownSerializer,
    ClaimDeepAnalysisSerializer,
    AdjudicationDecisionSerializer,
    AdjudicationQueueCaseSerializer,
    FactCheckDraftCreateSerializer,
    FactCheckDraftUpdateSerializer,
    OfficialFactCheckSerializer,
    VerificationAssignmentClaimSerializer,
    VerificationAssignmentSerializer,
    OrganizationMembershipAdminSerializer,
)
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from .email_verification import send_email_verification


# GoogleLogin
class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    callback_url = "https://truthlens-dev.vercel.app/"  # TODO: update to production URL in env vars


# ── Pagination Configuration ──
class StandardCursorPagination(CursorPagination):
    """
    Cursor-based pagination for efficient infinite scrolling.
    More efficient than offset pagination for large datasets.
    """

    page_size = 20
    ordering = "-created_at"
    cursor_query_param = "cursor"
    template = None  # Disable HTML template

    def get_ordering(self, request, queryset, view):
        sort_order = request.query_params.get("sort", "newest")
        if sort_order == "oldest":
            return ("created_at",)
        return ("-created_at",)


class IsThreadOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.author == request.user


class IsEvidenceContributorOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        # Allow authenticated users to create evidence (POST)
        if request.method == "POST":
            return request.user.is_authenticated
        # Allow everyone to read
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.contributor == request.user


class IsCommenterOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.commenter == request.user


class IsVoterOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.voter == request.user


def _has_moderator_role(user):
    profile = getattr(user, "profile", None)
    if not profile:
        return False
    # Backward-compatible during migration from MODERATOR -> MOD.
    return profile.role in {UserProfile.Role.MOD, "MODERATOR"}


class IsModerator(BasePermission):
    """
    Legacy class name.

    MOD now represents the TruthLens Platform
    Safety Moderator role, not a factual verifier.
    """

    def has_permission(self, request, view):
        return has_capability(
            request.user,
            PartnerCapability.REVIEW_SAFETY,
        )


class CanReviewEvidence(BasePermission):
    def has_permission(
        self,
        request,
        view,
    ):
        return request.user and request.user.is_authenticated

    def has_object_permission(
        self,
        request,
        view,
        obj,
    ):
        # Nobody may issue an authoritative
        # review of their own evidence.
        if obj.contributor_id == request.user.id:
            return False

        case = get_latest_evidence_case(obj)

        if case is None:
            return False

        return has_case_capability(
            request.user,
            case,
            PartnerCapability.REVIEW_EVIDENCE,
        )


class IsNotModerator(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return not _has_moderator_role(request.user)


def _authenticated_user_or_none(request):
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user
    return None


def _record_authenticated_claim_check(user, claim):
    if not user:
        return

    ClaimCheckHistory.objects.create(user=user, claim=claim)

    profile = getattr(user, "profile", None)
    if profile:
        profile.fact_check_points += 1
        profile.save(update_fields=["fact_check_points"])


# Create your views here.
@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([FactCheckRateThrottle])
def receive_snippet(request):
    parsed_data = json.loads(request.body)
    base64_string = parsed_data.get("image_data")
    check_deepfake = parsed_data.get("check_deepfake", False)

    if not base64_string:
        return JsonResponse({"error": "No image data provided"}, status=400)

    if "," in base64_string:
        base64_string = base64_string.split(",")[1]

    # Decode the base64 string and save it as an image
    image_hash, _ = process_image(base64_string)

    # ── Claim Deduplication Pre-Check ──
    fingerprint = compute_fingerprint("IMAGE", image_hash)
    authenticated_user = _authenticated_user_or_none(request)

    if fingerprint:
        matched_claim = find_matching_claim(fingerprint, "IMAGE")
        if matched_claim:
            _record_authenticated_claim_check(authenticated_user, matched_claim)
            # A moderator has already resolved this claim — return cached verdict
            match_result = get_match_result(
                matched_claim,
                triggered_by=(authenticated_user),
                record_reuse=True,
            )
            return JsonResponse(
                {
                    "claim_id": str(matched_claim.id),
                    "cached": True,
                    "match": match_result,
                },
                status=200,
            )

    media_url = upload_image_to_database(base64_string)

    print("IMAGE HASH:", image_hash)
    print("DEEPFAKE CHECK ENABLED:", check_deepfake)

    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.IMAGE,
        media_hash=image_hash,
        media_url=media_url,
        claim_fingerprint=fingerprint,
        verified_via=Claim.VerificationSource.PENDING,
    )
    _record_authenticated_claim_check(authenticated_user, claim)
    claim_id = claim.id  # Get the ID of the saved claim

    snippet_fact_check_process.delay(
        image_hash, str(claim_id), check_deepfake, base64_string
    )

    return JsonResponse(
        {"claim_id": str(claim_id), "cached": False},
        status=200,
    )


@csrf_exempt
@api_view(["GET"])
@throttle_classes([])
def claim_polling_endpoint(request, claim_id):
    if not claim_id:
        return JsonResponse({"error": "Claim ID is required"}, status=400)

    try:
        claim = Claim.objects.get(id=claim_id)
    except Claim.DoesNotExist:
        return JsonResponse(
            {
                "verdict": "OUT_OF_SCOPE",
                "summary": "The content of the image is not a claim that can be fact-checked.",
                "confidence_score": 100,
                "source_type": "N/A",
            },
            status=200,
        )

    ai_verdict = claim.ai_verdict
    if ai_verdict is None:
        return JsonResponse({"verdict": "PENDING"}, status=200)
    else:
        match_result = get_match_result(claim)

        return JsonResponse(
            {
                "id": str(claim_id),
                "verdict": (match_result["verdict"]),
                "ai_verdict": (match_result["ai_verdict"]),
                "final_verdict": (match_result["final_verdict"]),
                "summary": (match_result["summary"]),
                "confidence_score": (match_result["confidence_score"]),
                "source_type": (match_result["source_type"]),
                "source_url": (match_result["source_url"]),
                "sources": (match_result["sources"]),
                "is_ai_generated": (match_result["is_ai_generated"]),
                "thread_id": (match_result["thread_id"]),
                # Temporary compatibility name.
                "has_community_verdict": (bool(claim.final_verdict)),
                "score_context": (match_result["score_context"]),
                "resolution_source": (match_result["resolution_source"]),
                "official_fact_check": (match_result["official_fact_check"]),
            },
            status=200,
        )


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([FactCheckRateThrottle])
def verify_url(request):
    # gets the data from fronted ('yung URL)
    url = request.data.get("url")
    print(f"Received URL: {url}")
    safe_url, url_error = validate_public_url(url)
    if url_error:
        return Response({"detail": url_error}, status=400)

    url_safety = check_url_threat_reputation(safe_url)
    if url_safety.get("status") == "UNSAFE":
        return Response(
            {
                "detail": "This URL is flagged as unsafe and cannot be analyzed.",
                "url_safety": url_safety,
            },
            status=400,
        )

    # ── Claim Deduplication Pre-Check ──
    fingerprint = compute_fingerprint("URL", safe_url)
    authenticated_user = _authenticated_user_or_none(request)

    if fingerprint:
        matched_claim = find_matching_claim(fingerprint, "URL")
        if matched_claim:
            _record_authenticated_claim_check(authenticated_user, matched_claim)
            match_result = get_match_result(
                matched_claim,
                triggered_by=(authenticated_user),
                record_reuse=True,
                query_text=safe_url,
            )
            return JsonResponse(
                {
                    "claim_id": str(matched_claim.id),
                    "url_safety": url_safety,
                    "cached": True,
                    "match": match_result,
                },
                status=200,
            )

    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.URL,
        url_link=safe_url,
        claim_fingerprint=fingerprint,
        verified_via=Claim.VerificationSource.PENDING,
    )
    _record_authenticated_claim_check(authenticated_user, claim)
    claim_id = claim.id

    url_fact_check_process.delay(safe_url, claim_id)

    return JsonResponse(
        {"claim_id": str(claim_id), "url_safety": url_safety, "cached": False},
        status=200,
    )


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


# User registration
@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def register_user(request):
    serializer = RegisterSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = serializer.save()

    verification_email_sent = False

    try:
        send_email_verification(user)
        verification_email_sent = True
    except Exception as error:
        print(
            "Failed to send verification email:",
            error,
        )

    tokens = get_tokens_for_user(user)

    return Response(
        {
            **tokens,
            "verification_email_sent": verification_email_sent,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    serializer = CurrentUserSerializer(request.user)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_claims(request):
    claims = (
        Claim.objects.filter(check_history__user=request.user)
        .annotate(last_checked_at=Max("check_history__checked_at"))
        .order_by("-last_checked_at", "-last_updated")
    )
    serializer = ClaimSerializer(claims, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_guest_scan(request):
    """Persist one extension guest scan to the authenticated user's private history."""
    scan = request.data.get("scan")
    if not isinstance(scan, dict):
        return Response({"detail": "scan payload is required."}, status=400)

    # If the scan already references a known claim, just link it to this user history.
    raw_claim_id = scan.get("claim_id")
    if raw_claim_id:
        try:
            claim_uuid = uuid.UUID(str(raw_claim_id))
            existing_claim = Claim.objects.filter(id=claim_uuid).first()
        except (ValueError, TypeError, AttributeError):
            existing_claim = None

        if existing_claim:
            _record_authenticated_claim_check(request.user, existing_claim)
            return Response(
                {"id": str(existing_claim.id), "mode": "linked"}, status=200
            )

    scan_type = str(scan.get("scan_type") or "SCAN").upper()
    verdict = str(scan.get("verdict") or "UNVERIFIED").upper()
    summary = str(scan.get("summary") or "").strip()
    source_type = str(scan.get("source_type") or "Extension Guest Sync").strip()[:50]
    source_url = str(scan.get("source_url") or "").strip()
    scanned_at = str(scan.get("scanned_at") or "").strip()

    allowed_verdicts = {
        "FACT",
        "FAKE",
        "MISLEADING",
        "SATIRE",
        "UNVERIFIED",
        "OUT_OF_SCOPE",
    }
    if verdict not in allowed_verdicts:
        verdict = "UNVERIFIED"

    try:
        consensus_score = float(scan.get("confidence_score", 0))
    except (TypeError, ValueError):
        consensus_score = 0.0
    consensus_score = max(0.0, min(consensus_score, 100.0))

    normalized_source_url = (
        source_url
        if source_url.startswith("http://") or source_url.startswith("https://")
        else None
    )

    if scan_type == "URL":
        claim_type = Claim.ClaimType.URL
    elif scan_type == "TEXT":
        claim_type = Claim.ClaimType.TEXT
    else:
        claim_type = Claim.ClaimType.IMAGE

    context_text = (
        f"Synced from extension guest scan ({scan_type}) at {scanned_at}"
        if scanned_at
        else f"Synced from extension guest scan ({scan_type})"
    )

    claim = Claim.objects.create(
        claim_type=claim_type,
        url_link=normalized_source_url if claim_type == Claim.ClaimType.URL else None,
        ai_summary=summary or "Synced from extension guest scan.",
        ai_verdict=verdict,
        consensus_score=consensus_score,
        context_text=context_text,
        source_type=source_type,
        source_link=normalized_source_url,
        top_verdict_source=normalized_source_url,
        verified_via=Claim.VerificationSource.AI_EXTENSION,
    )

    _record_authenticated_claim_check(request.user, claim)
    return Response({"id": str(claim.id), "mode": "created"}, status=201)


@api_view(["POST"])
def login_user(request):
    username = request.data.get("username")
    password = request.data.get("password")
    remember_me = request.data.get("remember_me")

    user = authenticate(request, username=username, password=password)

    if user is None:
        return Response(
            {"detail": "No active account found with the given credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    refresh = RefreshToken.for_user(user)

    if remember_me:
        refresh.set_exp(lifetime=timedelta(days=30))

    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([EmailVerificationRateThrottle])
def send_verification_email(request):
    profile = request.user.profile

    if profile.is_email_verified:
        return Response(
            {"detail": "Your email is already verified."},
            status=status.HTTP_200_OK,
        )

    if not request.user.email:
        return Response(
            {"detail": "No email address is associated " "with this account."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        send_email_verification(request.user)
    except Exception as error:
        print(
            "Failed to send verification email:",
            error,
        )

        return Response(
            {"detail": "Unable to send the verification " "email right now."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {"detail": "Verification email sent."},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email(request):
    token = request.query_params.get("token")

    if not token:
        return Response(
            {
                "status": "invalid",
                "detail": "Verification token is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        profile = UserProfile.objects.get(email_verification_token=token)
    except UserProfile.DoesNotExist:
        return Response(
            {
                "status": "invalid",
                "detail": "This verification link is invalid "
                "or has already been used.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if profile.is_email_verified:
        profile.email_verification_token = None
        profile.email_verification_sent_at = None

        profile.save(
            update_fields=[
                "email_verification_token",
                "email_verification_sent_at",
            ]
        )

        return Response(
            {
                "status": "verified",
                "detail": "Your email is already verified.",
            },
            status=status.HTTP_200_OK,
        )

    sent_at = profile.email_verification_sent_at

    if not sent_at:
        return Response(
            {
                "status": "expired",
                "detail": "This verification link has expired.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    expires_at = sent_at + timedelta(
        hours=settings.EMAIL_VERIFICATION_TOKEN_LIFETIME_HOURS
    )

    if timezone.now() > expires_at:
        profile.email_verification_token = None
        profile.email_verification_sent_at = None

        profile.save(
            update_fields=[
                "email_verification_token",
                "email_verification_sent_at",
            ]
        )

        return Response(
            {
                "status": "expired",
                "detail": "This verification link has expired.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile.is_email_verified = True
    profile.email_verification_token = None
    profile.email_verification_sent_at = None

    profile.save(
        update_fields=[
            "is_email_verified",
            "email_verification_token",
            "email_verification_sent_at",
        ]
    )

    return Response(
        {
            "status": "verified",
            "detail": "Email verified successfully.",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes(
    [
        IsAuthenticated,
        IsModerator,
    ]
)
def moderation_queue(request):
    """
    Return threads with active Safety moderation cases.
    """

    status_filter = request.query_params.get(
        "status",
        "ALL",
    )

    allowed = {
        "ALL",
        Thread.Status.PENDING,
        Thread.Status.OPEN,
        Thread.Status.CLOSED,
        Thread.Status.REJECTED,
    }

    if status_filter not in allowed:
        return Response(
            {"detail": "Invalid status filter."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = (
        Thread.objects.filter(
            moderation_cases__case_type=(ModerationCase.CaseType.SAFETY),
            moderation_cases__status__in=(ACTIVE_CASE_STATUSES),
        )
        .select_related(
            "claim",
            "author",
            "author__profile",
        )
        .distinct()
        .order_by("-created_at")
    )

    if status_filter != "ALL":
        queryset = queryset.filter(status=status_filter)

    serializer = ThreadSerializer(
        queryset,
        many=True,
    )

    return Response(
        serializer.data,
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def verdict_queue(request):
    reviewed_filter = (
        request.query_params.get(
            "reviewed",
            "pending",
        )
        .strip()
        .lower()
    )

    allowed = {
        "all",
        "pending",
        "resolved",
    }

    if reviewed_filter not in allowed:
        return Response(
            {"detail": "Invalid reviewed filter. " "Use all, pending, or " "resolved."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        limit = int(
            request.query_params.get(
                "limit",
                20,
            )
        )

        offset = int(
            request.query_params.get(
                "offset",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return Response(
            {"detail": "limit and offset must " "be integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if limit < 1 or limit > 100 or offset < 0:
        return Response(
            {
                "detail": "limit must be between "
                "1 and 100, and offset "
                "must be zero or greater."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    organization_id = request.query_params.get("organization_id")

    if not organization_id:
        return Response(
            {"detail": "organization_id is required " "for adjudication review."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    organization = get_object_or_404(
        Organization,
        id=organization_id,
    )

    if not has_capability(
        request.user,
        PartnerCapability.ADJUDICATE,
        organization=organization,
    ):
        return Response(
            {
                "detail": "You do not have permission "
                "to adjudicate for this "
                "organization."
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    queryset = ModerationCase.objects.filter(
        case_type=(ModerationCase.CaseType.ADJUDICATION)
    )

    if reviewed_filter == "pending":
        queryset = queryset.filter(status__in=ACTIVE_CASE_STATUSES)

    elif reviewed_filter == "resolved":
        queryset = queryset.filter(status=(ModerationCase.Status.RESOLVED))

    else:
        queryset = queryset.exclude(status=(ModerationCase.Status.CANCELLED))

    queryset = queryset.filter(organization=organization)

    queryset = (
        queryset.select_related(
            "claim",
            "organization",
            "assigned_to",
            "assigned_to__profile",
        )
        .annotate(
            total_evidence=Count(
                "claim__threads__evidence_submissions",
                distinct=True,
            ),
            verified_evidence=Count(
                "claim__threads__evidence_submissions",
                filter=Q(
                    claim__threads__evidence_submissions__evidence_status=(
                        EvidenceSubmission.EvidenceStatus.VERIFIED
                    )
                ),
                distinct=True,
            ),
            rejected_evidence=Count(
                "claim__threads__evidence_submissions",
                filter=Q(
                    claim__threads__evidence_submissions__evidence_status=(
                        EvidenceSubmission.EvidenceStatus.REJECTED
                    )
                ),
                distinct=True,
            ),
        )
        .order_by(
            "-priority",
            "-created_at",
        )
    )

    total_count = queryset.count()

    cases = queryset[offset : offset + limit]

    serializer = AdjudicationQueueCaseSerializer(
        cases,
        many=True,
        context={
            "request": request,
        },
    )

    return Response(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


def _publishing_error_response(
    error,
):
    if isinstance(
        error,
        PublishingAuthorizationError,
    ):
        response_status = status.HTTP_403_FORBIDDEN

    elif isinstance(
        error,
        PublishingConflict,
    ):
        response_status = status.HTTP_409_CONFLICT

    else:
        response_status = status.HTTP_400_BAD_REQUEST

    return Response(
        {
            "detail": str(error),
        },
        status=response_status,
    )


def _execute_claim_adjudication(
    request,
    claim,
):
    serializer = ModerationDecisionSerializer(data=request.data)

    serializer.is_valid(raise_exception=True)

    case = get_latest_adjudication_case(claim)

    if case is None:
        raise PermissionDenied("No adjudication case is available " "for this claim.")

    if not has_case_capability(
        request.user,
        case,
        PartnerCapability.ADJUDICATE,
    ):
        raise PermissionDenied(
            "You do not have permission " "to adjudicate this claim."
        )

    if has_adjudication_conflict(
        request.user,
        claim,
    ):
        raise PermissionDenied(
            "You cannot adjudicate a claim "
            "in which you have a direct "
            "contribution."
        )

    verification_run = None

    verification_run_id = serializer.validated_data.get("verification_run_id")

    if verification_run_id:
        verification_run = get_object_or_404(
            VerificationRun,
            id=verification_run_id,
            claim=claim,
        )

    contributor_ids = list(
        EvidenceSubmission.objects.filter(thread__claim=claim)
        .values_list(
            "contributor_id",
            flat=True,
        )
        .distinct()
    )

    try:
        result = issue_adjudication_decision(
            claim=claim,
            actor=request.user,
            verdict=(serializer.validated_data["moderator_verdict"]),
            canonical_claim=(serializer.validated_data["canonical_claim"]),
            rationale=(serializer.validated_data["moderator_notes"]),
            organization=case.organization,
            verification_run=verification_run,
            expected_revision=(serializer.validated_data.get("expected_revision")),
        )

    except AdjudicationAuthorizationError as error:
        raise PermissionDenied(str(error)) from error

    decision = result["decision"]

    # Compatibility mirror only.
    Thread.objects.filter(
        claim=claim,
    ).exclude(
        status=Thread.Status.REJECTED,
    ).update(
        moderator_verdict=decision.verdict,
        moderator_notes=decision.rationale,
        moderated_by=request.user,
        moderated_at=decision.decided_at,
    )

    for contributor_id in contributor_ids:
        transaction.on_commit(
            lambda user_id=contributor_id: (
                recompute_user_trust_score_task.delay(user_id)
            )
        )

    return decision


@api_view(["POST"])
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def moderation_resolve_thread(
    request,
    thread_id,
):
    """
    Legacy thread-addressed adjudication endpoint.

    The authoritative decision is Claim-centric.
    Thread moderation fields remain temporary
    compatibility mirrors only.

    Thread.status is intentionally not changed.
    Publication is intentionally not performed here.
    """

    thread = get_object_or_404(
        Thread.objects.select_related("claim"),
        id=thread_id,
    )

    claim = thread.claim

    try:
        with transaction.atomic():
            decision = _execute_claim_adjudication(
                request,
                claim,
            )

    except AdjudicationConflict as error:
        return Response(
            {
                "detail": str(error),
            },
            status=(status.HTTP_409_CONFLICT),
        )

    except (
        AdjudicationError,
        ModerationCaseError,
    ) as error:
        return Response(
            {
                "detail": str(error),
            },
            status=(status.HTTP_400_BAD_REQUEST),
        )

    thread.refresh_from_db()

    response_data = dict(
        ThreadDetailSerializer(
            thread,
            context={
                "request": request,
            },
        ).data
    )

    response_data["adjudication"] = AdjudicationDecisionSerializer(
        decision,
        context={
            "request": request,
        },
    ).data

    return Response(
        response_data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def adjudicate_claim(
    request,
    claim_id,
):
    claim = get_object_or_404(
        Claim,
        id=claim_id,
    )

    try:
        with transaction.atomic():
            decision = _execute_claim_adjudication(
                request,
                claim,
            )

    except AdjudicationConflict as error:
        return Response(
            {"detail": str(error)},
            status=status.HTTP_409_CONFLICT,
        )

    except (
        AdjudicationError,
        ModerationCaseError,
    ) as error:
        return Response(
            {"detail": str(error)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        AdjudicationDecisionSerializer(
            decision,
            context={
                "request": request,
            },
        ).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def fact_check_draft_create(
    request,
    claim_id,
):
    claim = get_object_or_404(
        Claim,
        id=claim_id,
    )

    serializer = FactCheckDraftCreateSerializer(data=request.data)

    serializer.is_valid(raise_exception=True)

    decision = (
        AdjudicationDecision.objects.filter(
            claim=claim,
            is_current=True,
        )
        .select_related(
            "organization",
        )
        .first()
    )

    if not decision:
        return Response(
            {
                "detail": "This claim does not "
                "have a current "
                "adjudication decision."
            },
            status=(status.HTTP_409_CONFLICT),
        )

    expected_revision = serializer.validated_data.get("expected_revision")

    if expected_revision is not None and (
        expected_revision != decision.revision_number
    ):
        return Response(
            {
                "detail": "The adjudication "
                "decision changed after "
                "the publishing workspace "
                "was opened. Refresh "
                "before creating a draft."
            },
            status=(status.HTTP_409_CONFLICT),
        )

    try:
        draft = create_fact_check_draft(
            decision=decision,
            actor=request.user,
            headline=(serializer.validated_data["headline"]),
            summary=(serializer.validated_data["summary"]),
            article_body=(
                serializer.validated_data.get(
                    "article_body",
                    "",
                )
            ),
            source_urls=(
                serializer.validated_data.get(
                    "source_urls",
                    [],
                )
            ),
        )

    except PublishingError as error:
        return _publishing_error_response(error)

    return Response(
        OfficialFactCheckSerializer(
            draft,
            context={
                "request": request,
            },
        ).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def fact_check_draft_update(
    request,
    fact_check_id,
):
    fact_check = get_object_or_404(
        OfficialFactCheck,
        id=fact_check_id,
    )

    serializer = FactCheckDraftUpdateSerializer(
        data=request.data,
        partial=True,
    )

    serializer.is_valid(raise_exception=True)

    data = serializer.validated_data

    try:
        updated = update_fact_check_draft(
            fact_check=fact_check,
            actor=request.user,
            headline=data.get("headline"),
            summary=data.get("summary"),
            article_body=data.get("article_body"),
            source_urls=(data["source_urls"] if "source_urls" in data else None),
        )

    except PublishingError as error:
        return _publishing_error_response(error)

    return Response(
        OfficialFactCheckSerializer(
            updated,
            context={
                "request": request,
            },
        ).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def fact_check_submit(
    request,
    fact_check_id,
):
    fact_check = get_object_or_404(
        OfficialFactCheck,
        id=fact_check_id,
    )

    try:
        submitted = submit_fact_check_for_review(
            fact_check=fact_check,
            actor=request.user,
        )

    except PublishingError as error:
        return _publishing_error_response(error)

    return Response(
        OfficialFactCheckSerializer(
            submitted,
            context={
                "request": request,
            },
        ).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def fact_check_publish(
    request,
    fact_check_id,
):
    fact_check = get_object_or_404(
        OfficialFactCheck,
        id=fact_check_id,
    )

    try:
        result = publish_fact_check(
            fact_check=fact_check,
            actor=request.user,
        )

    except PublishingError as error:
        return _publishing_error_response(error)

    published = result["fact_check"]

    return Response(
        OfficialFactCheckSerializer(
            published,
            context={
                "request": request,
            },
        ).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes(
    [
        IsAuthenticated,
        IsModerator,
    ]
)
def moderation_resolve_safety_thread(
    request,
    thread_id,
):
    thread = get_object_or_404(
        Thread,
        id=thread_id,
    )

    action = request.data.get("action", "").strip().upper()

    moderator_notes = request.data.get("moderator_notes", "").strip()

    allowed_actions = {
        "DISMISS",
        "REMOVE",
        "ESCALATE",
    }

    if action not in allowed_actions:
        return Response(
            {"detail": "Invalid action. Use DISMISS, " "REMOVE, or ESCALATE."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        if action == "ESCALATE":
            escalate_safety_case(
                thread=thread,
                actor=request.user,
                notes=moderator_notes,
            )

            thread.refresh_from_db()

            return Response(
                ThreadSerializer(
                    thread,
                    context={"request": request},
                ).data,
                status=status.HTTP_200_OK,
            )

        result = resolve_safety_case(
            thread=thread,
            actor=request.user,
            action=action,
            notes=moderator_notes,
        )

    except ModerationCaseError as error:
        return Response(
            {
                "detail": str(error),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    for reporter_id in result["reporter_ids"]:
        recompute_user_trust_score_task.delay(reporter_id)

    if action == "REMOVE":
        recompute_user_trust_score_task.delay(result["author_id"])

    for contributor_id in result["contributor_ids"]:
        recompute_user_trust_score_task.delay(contributor_id)

    return Response(
        ThreadSerializer(
            result["thread"],
            context={"request": request},
        ).data,
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def evidence_moderation_queue(request):
    """
    Evidence review queue.

    Professional evidence review is available only
    through an explicitly scoped verified partner
    organization with REVIEW_EVIDENCE capability.
    """

    evidence_status_filter = (
        request.query_params.get(
            "status",
            EvidenceSubmission.EvidenceStatus.UNVERIFIED,
        )
        .strip()
        .upper()
    )

    allowed_statuses = {
        value for value, _label in EvidenceSubmission.EvidenceStatus.choices
    }

    if evidence_status_filter not in allowed_statuses:
        return Response(
            {"detail": "Invalid evidence status."},
            status=(status.HTTP_400_BAD_REQUEST),
        )

    try:
        limit = int(
            request.query_params.get(
                "limit",
                20,
            )
        )

        offset = int(
            request.query_params.get(
                "offset",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return Response(
            {"detail": "limit and offset must " "be integers."},
            status=(status.HTTP_400_BAD_REQUEST),
        )

    if limit < 1 or limit > 100 or offset < 0:
        return Response(
            {
                "detail": "limit must be between "
                "1 and 100, and offset "
                "must be zero or greater."
            },
            status=(status.HTTP_400_BAD_REQUEST),
        )

    thread_id = request.query_params.get("thread_id")

    organization_id = request.query_params.get("organization_id")

    if not organization_id:
        return Response(
            {"detail": "organization_id is required " "for evidence review."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    organization = get_object_or_404(
        Organization,
        id=organization_id,
    )

    if not has_capability(
        request.user,
        PartnerCapability.REVIEW_EVIDENCE,
        organization=organization,
    ):
        return Response(
            {
                "detail": "You do not have permission "
                "to review evidence for this "
                "organization."
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    evidence_query = EvidenceSubmission.objects.filter(
        evidence_status=(evidence_status_filter)
    )

    # UNVERIFIED is an operational queue,
    # so it must correspond to an active
    # Evidence ModerationCase.
    if evidence_status_filter == EvidenceSubmission.EvidenceStatus.UNVERIFIED:
        evidence_query = evidence_query.filter(
            moderation_cases__case_type=(ModerationCase.CaseType.EVIDENCE),
            moderation_cases__status__in=(ACTIVE_CASE_STATUSES),
        )

    evidence_query = evidence_query.filter(
        moderation_cases__case_type=(ModerationCase.CaseType.EVIDENCE),
        moderation_cases__organization=organization,
    )

    if thread_id:
        evidence_query = evidence_query.filter(thread_id=thread_id)

    evidence_query = (
        evidence_query.select_related(
            "contributor",
            "contributor__profile",
            "thread",
            "thread__claim",
            "verified_by",
            "verified_by__profile",
        )
        .prefetch_related(
            "votes",
        )
        .distinct()
        .order_by("-submitted_at")
    )

    total_count = evidence_query.count()

    evidence = evidence_query[offset : offset + limit]

    serializer = EvidenceSubmissionSerializer(
        evidence,
        many=True,
        context={
            "request": request,
        },
    )

    return Response(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


VERIFICATION_WORKLOAD_CAPABILITIES = {
    PartnerCapability.CLAIM_VERIFICATION_WORK,
    PartnerCapability.REVIEW_EVIDENCE,
    PartnerCapability.ADJUDICATE,
    PartnerCapability.CREATE_FACT_CHECK_DRAFT,
    PartnerCapability.PUBLISH_FACT_CHECK,
    PartnerCapability.MANAGE_ORGANIZATION,
}


def _parse_verification_pagination(request):
    try:
        limit = int(
            request.query_params.get(
                "limit",
                20,
            )
        )

        offset = int(
            request.query_params.get(
                "offset",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError({"detail": "limit and offset must be integers."})

    if limit < 1 or limit > 100 or offset < 0:
        raise ValidationError(
            {
                "detail": "limit must be between 1 and 100, "
                "and offset must be zero or greater."
            }
        )

    return limit, offset


def _get_verification_organization(
    request,
    *,
    from_body=False,
):
    if from_body:
        serializer = VerificationAssignmentClaimSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        organization_id = serializer.validated_data["organization_id"]

    else:
        organization_id = request.query_params.get("organization_id")

        if not organization_id:
            raise ValidationError({"detail": "organization_id is required."})

    return get_object_or_404(
        Organization,
        id=organization_id,
    )


def _can_view_verification_workload(
    user,
    organization,
):
    return any(
        has_capability(
            user,
            capability,
            organization=organization,
        )
        for capability in VERIFICATION_WORKLOAD_CAPABILITIES
    )


def _verification_assignment_error_response(
    error,
):
    if isinstance(
        error,
        VerificationAssignmentAuthorizationError,
    ):
        response_status = status.HTTP_403_FORBIDDEN

    elif isinstance(
        error,
        (
            VerificationAssignmentConflict,
            VerificationAssignmentReleaseBlocked,
        ),
    ):
        response_status = status.HTTP_409_CONFLICT

    else:
        response_status = status.HTTP_400_BAD_REQUEST

    return Response(
        {
            "detail": str(error),
        },
        status=response_status,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def verification_intake(request):
    """
    Shared pool of AVAILABLE professional
    verification investigations.

    An organization_id is required so access is
    evaluated in the context of a specific verified
    partner organization.
    """

    organization = _get_verification_organization(
        request,
    )

    if not has_capability(
        request.user,
        PartnerCapability.CLAIM_VERIFICATION_WORK,
        organization=organization,
    ):
        return Response(
            {
                "detail": "You do not have permission to "
                "access verification intake for "
                "this organization."
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    limit, offset = _parse_verification_pagination(request)

    queryset = get_available_verification_assignments()

    total_count = queryset.count()

    assignments = queryset[offset : offset + limit]

    serializer = VerificationAssignmentSerializer(
        assignments,
        many=True,
        context={
            "request": request,
        },
    )

    return Response(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verification_assignment_claim(
    request,
    assignment_id,
):
    assignment = get_object_or_404(
        VerificationAssignment,
        id=assignment_id,
    )

    organization = _get_verification_organization(
        request,
        from_body=True,
    )

    try:
        claimed = claim_verification_assignment(
            assignment=assignment,
            organization=organization,
            actor=request.user,
        )

    except VerificationAssignmentError as error:
        return _verification_assignment_error_response(error)

    return Response(
        VerificationAssignmentSerializer(
            claimed,
            context={
                "request": request,
            },
        ).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verification_assignment_release(
    request,
    assignment_id,
):
    assignment = get_object_or_404(
        VerificationAssignment,
        id=assignment_id,
    )

    try:
        result = release_verification_assignment(
            assignment=assignment,
            actor=request.user,
        )

    except VerificationAssignmentError as error:
        return _verification_assignment_error_response(error)

    return Response(
        {
            "released_assignment": VerificationAssignmentSerializer(
                result["released_assignment"],
                context={
                    "request": request,
                },
            ).data,
            "available_assignment": VerificationAssignmentSerializer(
                result["available_assignment"],
                context={
                    "request": request,
                },
            ).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def verification_workload(request):
    """
    Return ACTIVE professional verification work
    belonging to one organization.
    """

    organization = _get_verification_organization(
        request,
    )

    if not _can_view_verification_workload(
        request.user,
        organization,
    ):
        return Response(
            {
                "detail": "You do not have permission to "
                "view verification work for this "
                "organization."
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    limit, offset = _parse_verification_pagination(request)

    queryset = get_organization_verification_workload(organization)

    total_count = queryset.count()

    assignments = queryset[offset : offset + limit]

    serializer = VerificationAssignmentSerializer(
        assignments,
        many=True,
        context={
            "request": request,
        },
    )

    return Response(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "organization": {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            },
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


# Viewsets
class ThreadViewSet(viewsets.ModelViewSet):
    serializer_class = ThreadSerializer
    permission_classes = [IsAuthenticated, IsThreadOwnerOrReadOnly]
    pagination_class = StandardCursorPagination

    def get_queryset(self):
        # Dynamic sorting based on parameter
        sort_order = self.request.query_params.get("sort", "newest")
        order_field = "created_at" if sort_order == "oldest" else "-created_at"

        queryset = (
            Thread.objects.exclude(status=Thread.Status.REJECTED)
            .select_related("claim", "author", "author__profile")
            .order_by(order_field)
        )

        search_query = self.request.query_params.get("search", "").strip()[:120]
        if search_query:
            queryset = queryset.filter(
                Q(caption__icontains=search_query)
                | Q(author__username__icontains=search_query)
                | Q(claim__context_text__icontains=search_query)
                | Q(claim__ai_summary__icontains=search_query)
                | Q(claim__source_link__icontains=search_query)
                | Q(claim__ai_verdict__icontains=search_query)
                | Q(claim__final_verdict__icontains=search_query)
            )

        claim_id = self.request.query_params.get("claim_id")
        if claim_id:
            queryset = queryset.filter(claim_id=claim_id)

        if getattr(self, "action", None) == "retrieve":
            queryset = queryset.prefetch_related(
                "flags",
                "evidence_submissions__votes",
                "evidence_submissions__contributor__profile",
                "evidence_submissions__verified_by__profile",
                "comments__commenter__profile",
            )
        else:
            queryset = queryset.prefetch_related("evidence_submissions")

        return queryset

    def perform_create(self, serializer):
        claim_id = serializer.validated_data.pop("claim_id")
        try:
            claim = Claim.objects.get(id=claim_id)
        except Claim.DoesNotExist:
            raise NotFound("Claim not found.")

        # ── Thread Deduplication: Block + Redirect ──
        # Check if this claim (or a matching claim) already has an active thread
        existing_thread = self._find_existing_thread(claim)
        if existing_thread:
            raise ValidationError(
                {
                    "detail": "A community discussion already exists for this claim.",
                    "existing_thread_id": str(existing_thread.id),
                    "redirect": True,
                }
            )

        with transaction.atomic():
            serializer.save(
                author=self.request.user,
                claim=claim,
            )

            ensure_verification_assignment(
                claim=claim,
            )

    def _find_existing_thread(self, claim):
        """
        Check if the claim (or a fingerprint-matched claim) already has an
        active thread. Returns the existing Thread or None.
        """
        # Direct check: does this exact claim already have a non-rejected thread?
        direct_thread = (
            Thread.objects.filter(claim=claim)
            .exclude(status=Thread.Status.REJECTED)
            .order_by("-created_at")
            .first()
        )
        if direct_thread:
            return direct_thread

        # Fingerprint check: does a matching claim have a thread?
        if claim.claim_fingerprint:
            matched_claim = find_matching_claim(
                claim.claim_fingerprint, claim.claim_type
            )
            if matched_claim and matched_claim.id != claim.id:
                matched_thread = (
                    Thread.objects.filter(claim=matched_claim)
                    .exclude(status=Thread.Status.REJECTED)
                    .order_by("-created_at")
                    .first()
                )
                if matched_thread:
                    return matched_thread

        return None

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ThreadDetailSerializer
        return ThreadSerializer


class ClaimViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ClaimSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Claim.objects.all()


class EvidenceSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = EvidenceSubmissionSerializer
    permission_classes = [
        IsAuthenticated,
        IsNotModerator,
        IsEvidenceContributorOrReadOnly,
    ]  # If moderator submits evidence, returns an error

    def get_queryset(self):
        return EvidenceSubmission.objects.all()

    def perform_create(self, serializer):
        thread_id = serializer.validated_data.pop("thread_id")

        try:
            thread = Thread.objects.select_related("claim").get(id=thread_id)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")

        with transaction.atomic():
            organization = get_claim_verification_organization(
                thread.claim,
                lock=True,
            )

            evidence = serializer.save(
                contributor=self.request.user,
                thread=thread,
                contributor_trust_snapshot=(self.request.user.profile.trust_score),
                evidence_status=(EvidenceSubmission.EvidenceStatus.UNVERIFIED),
            )

            ensure_evidence_case(
                evidence=evidence,
                actor=self.request.user,
                organization=organization,
            )

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[
            IsAuthenticated,
            CanReviewEvidence,
        ],
    )
    def verify(
        self,
        request,
        pk=None,
    ):
        evidence = self.get_object()

        evidence_status = request.data.get("evidence_status")

        notes = request.data.get(
            "moderator_notes",
            "",
        ).strip()

        rejection_reason = request.data.get("rejection_reason")

        expected_status = request.data.get(
            "expected_status",
            evidence.evidence_status,
        )

        try:
            result = review_evidence_submission(
                evidence=evidence,
                actor=request.user,
                evidence_status=evidence_status,
                moderator_notes=notes,
                rejection_reason=rejection_reason,
                expected_status=expected_status,
            )

        except EvidenceReviewConflict as error:
            return Response(
                {
                    "detail": str(error),
                },
                status=status.HTTP_409_CONFLICT,
            )

        except EvidenceReviewAuthorizationError as error:
            return Response(
                {
                    "detail": str(error),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        except (
            EvidenceReviewError,
            ModerationCaseError,
        ) as error:
            return Response(
                {
                    "detail": str(error),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        reviewed_evidence = result["evidence"]

        contributor_id = result["contributor_id"]

        # The review transaction has completed before
        # reputation is recomputed.
        recompute_user_trust_score(contributor_id)

        transaction.on_commit(
            lambda: (recompute_user_trust_score_task.delay(contributor_id))
        )

        serializer = EvidenceSubmissionSerializer(
            reviewed_evidence,
            context={
                "request": request,
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class ThreadCommentViewSet(viewsets.ModelViewSet):
    serializer_class = ThreadCommentSerializer
    permission_classes = [IsAuthenticated, IsCommenterOrReadOnly]

    def get_queryset(self):
        return ThreadComment.objects.all().order_by("-commented_at")

    def perform_create(self, serializer):
        thread_id = serializer.validated_data.pop("thread_id")
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")
        serializer.save(
            commenter=self.request.user,
            thread=thread,
        )


class ThreadFlagViewSet(viewsets.ModelViewSet):
    serializer_class = ThreadFlagSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if _has_moderator_role(self.request.user):
            return ThreadFlag.objects.select_related("thread", "flagged_by").order_by(
                "-flagged_at"
            )
        return (
            ThreadFlag.objects.filter(flagged_by=self.request.user)
            .select_related("thread", "flagged_by")
            .order_by("-flagged_at")
        )

    def perform_create(self, serializer):
        thread_id = serializer.validated_data.pop("thread_id")
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")

        try:
            with transaction.atomic():
                serializer.save(
                    flagged_by=self.request.user,
                    thread=thread,
                )

                ensure_safety_case(
                    thread=thread,
                    actor=self.request.user,
                )
        except IntegrityError:
            raise ValidationError({"detail": "You already flagged this thread."})


class VoteViewSet(viewsets.ModelViewSet):
    serializer_class = VoteSerializer
    permission_classes = [IsAuthenticated, IsVoterOrReadOnly]

    def get_queryset(self):
        return Vote.objects.select_related("evidence", "voter", "evidence__contributor")

    def perform_create(self, serializer):
        evidence = serializer.validated_data["evidence"]
        if evidence.contributor_id == self.request.user.id:
            raise ValidationError({"detail": "You cannot vote on your own evidence."})

        try:
            vote = serializer.save(
                voter=self.request.user,
                vote_trust_snapshot=self.request.user.profile.trust_score,
            )
        except IntegrityError:
            raise ValidationError({"detail": "You already voted on this evidence."})

        recompute_user_trust_score_task.delay(vote.evidence.contributor_id)

    def perform_update(self, serializer):
        vote = serializer.save()
        recompute_user_trust_score_task.delay(vote.evidence.contributor_id)

    def perform_destroy(self, instance):
        contributor_id = instance.evidence.contributor_id
        instance.delete()
        recompute_user_trust_score_task.delay(contributor_id)


# FOR AI-GENERATED IMAGE DETECTION
@csrf_exempt
@api_view(["POST"])
def test_deepfake(request):
    """Endpoint to test AI image detection with image standardization."""
    try:
        parsed_data = json.loads(request.body)
        base64_string = parsed_data.get("image_data")

        if not base64_string:
            return JsonResponse({"error": "No image data provided"}, status=400)

        if "," in base64_string:
            base64_string = base64_string.split(",")[1]

        # 1. Decode the raw bytes safely
        raw_image_bytes = base64.b64decode(base64_string)

        # 2. Standardize and optimize the image using Pillow
        img = Image.open(io.BytesIO(raw_image_bytes))

        # Strip alpha channels (transparency) which confuse AI models
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize down if the image is massive (keeps API fast and under limits)
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

        # Save to a new buffer as a clean JPEG
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=90)
        optimized_image_bytes = output_buffer.getvalue()
        # 3. Send the clean, optimized bytes to your model
        ai_data = detect_ai_image(optimized_image_bytes)

        if not ai_data:
            return JsonResponse({"error": "Detection API unavailable."}, status=503)

        ai_probability = ai_data["score"]
        fake_category = ai_data["category"]
        is_fake = ai_probability > 0.65

        # 4. Generate the dynamic explanation!
        summary_text = ""
        if is_fake:
            base64_for_groq = base64.b64encode(optimized_image_bytes).decode("utf-8")
            # Pass the category into the Groq function
            summary_text = generate_deepfake_explanation(base64_for_groq, fake_category)
        else:
            summary_text = "No significant indicators of AI generation were detected. The image appears to possess natural digital noise and structural consistency."

        return JsonResponse(
            {
                "ai_probability": ai_probability,
                "is_fake": is_fake,
                "summary": summary_text,  # <-- Pass this back to React!
            },
            status=200,
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)
    except Exception as e:
        print(f"Deepfake view error: {str(e)}")
        return JsonResponse({"error": "Failed to process image format."}, status=400)


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([FactCheckRateThrottle])
def verify_text(request):
    """Endpoint for pure text fact-checking."""
    text_content = request.data.get("text")

    if not text_content:
        return Response({"error": "Text is required"}, status=400)

    print(f"Received Text: {text_content[:100]}...")

    # ── Claim Deduplication Pre-Check ──
    fingerprint = compute_fingerprint("TEXT", text_content)
    # Even if fingerprint is None or exact match fails, we want semantic fallback!
    matched_claim = find_matching_claim(
        fingerprint,
        "TEXT",
        context_text=text_content,
        allow_semantic_fallback=False,
    )
    authenticated_user = _authenticated_user_or_none(request)

    if matched_claim:
        _record_authenticated_claim_check(authenticated_user, matched_claim)
        match_result = get_match_result(
            matched_claim,
            triggered_by=(authenticated_user),
            record_reuse=True,
            query_text=text_content,
        )
        return JsonResponse(
            {"claim_id": str(matched_claim.id), "cached": True, "match": match_result},
            status=200,
        )

    # TEMP HACK: Save as URL so we don't have to run migrations yet.
    # We set url_link to a short string so it doesn't crash the 500-character database limit!
    # Proper Implementation: Save as TEXT and store the content in context_text
    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.TEXT,
        context_text=text_content,
        claim_fingerprint=fingerprint,
        verified_via=Claim.VerificationSource.PENDING,
    )
    _record_authenticated_claim_check(authenticated_user, claim)
    claim_id = claim.id

    # Send the raw text to the Celery worker
    text_fact_check_process.delay(text_content, claim_id)

    return JsonResponse(
        {"claim_id": str(claim_id), "cached": False},
        status=200,
    )


@csrf_exempt
@api_view(["GET"])
def claim_match(request):
    """
    Pre-check endpoint for the extension to check if a claim already exists.
    Used to skip AI pipeline entirely when a resolved verdict is cached.

    Query params:
        fingerprint: the computed claim fingerprint
        claim_type: IMAGE, URL, or TEXT
        text: (optional) raw text for semantic matching fallback
    """
    fingerprint = request.query_params.get("fingerprint")
    claim_type = request.query_params.get("claim_type", "").upper()
    text = request.query_params.get("text")

    authenticated_user = _authenticated_user_or_none(request)

    if not fingerprint and not text:
        return Response({"match": None}, status=200)

    matched_claim = find_matching_claim(
        fingerprint,
        claim_type,
        context_text=text,
        allow_semantic_fallback=False,
    )
    if matched_claim:
        match_result = get_match_result(
            matched_claim,
            triggered_by=(authenticated_user),
            record_reuse=True,
            query_text=text,
        )
        serializer = ClaimMatchSerializer(data=match_result)
        serializer.is_valid(raise_exception=True)
        return Response({"match": serializer.validated_data}, status=200)

    return Response({"match": None}, status=200)


# for user view
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_users(request):
    """Return lightweight public user cards for global search."""
    query = (request.query_params.get("search") or "").strip()
    if not query:
        return Response([], status=200)

    try:
        limit = int(request.query_params.get("limit", 6))
    except (TypeError, ValueError):
        limit = 6

    limit = max(1, min(limit, 20))

    users = (
        User.objects.select_related("profile")
        .filter(Q(username__icontains=query) | Q(profile__bio__icontains=query))
        .exclude(id=request.user.id)
        .order_by("username")[:limit]
    )

    serializer = PublicUserSearchSerializer(
        users, many=True, context={"request": request}
    )
    return Response(serializer.data, status=200)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_public_user_profile(request, username):
    """Fetch read-only public identity fields for a user profile."""
    target_user = get_object_or_404(
        User.objects.select_related("profile"), username=username
    )

    serializer = PublicIdentityProfileSerializer(
        target_user, context={"request": request}
    )
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_user_threads(request, username):
    """Fetch public threads initiated by a specific user."""
    target_user = get_object_or_404(
        User.objects.select_related("profile"), username=username
    )

    threads = (
        Thread.objects.filter(author=target_user)
        .prefetch_related("evidence_submissions", "comments")
        .order_by("-created_at")
    )

    serializer = PublicUserThreadSerializer(
        threads, many=True, context={"request": request}
    )
    return Response(serializer.data, status=200)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_user_evidence(request, username):
    """Fetch public evidence and comments submitted by a specific user."""
    target_user = get_object_or_404(
        User.objects.select_related("profile"), username=username
    )

    evidence_items = list(
        EvidenceSubmission.objects.filter(contributor=target_user)
        .select_related("thread")
        .order_by("-submitted_at")
    )
    comment_items = list(
        ThreadComment.objects.filter(commenter=target_user)
        .select_related("thread")
        .order_by("-commented_at")
    )

    merged_activity = []
    for item in evidence_items:
        merged_activity.append((item.submitted_at, "EVIDENCE", item))
    for item in comment_items:
        merged_activity.append((item.commented_at, "COMMENT", item))

    merged_activity.sort(key=lambda row: row[0], reverse=True)

    payload = []
    for _, activity_type, item in merged_activity:
        if activity_type == "EVIDENCE":
            payload.append(
                PublicUserEvidenceSerializer(item, context={"request": request}).data
            )
        else:
            payload.append(
                PublicUserCommentSerializer(item, context={"request": request}).data
            )

    return Response(payload, status=200)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_user_verdicts(request, username):
    """Fetch public moderator verdict activity for a specific moderator user."""
    target_user = get_object_or_404(
        User.objects.select_related("profile"), username=username
    )

    if not _has_moderator_role(target_user):
        return Response([], status=200)

    verdict_threads = Thread.objects.filter(
        moderated_by=target_user,
        moderator_verdict__isnull=False,
        status=Thread.Status.CLOSED,
    ).order_by("-moderated_at", "-created_at")

    serializer = PublicModeratorVerdictSerializer(
        verdict_threads,
        many=True,
        context={"request": request},
    )
    return Response(serializer.data, status=200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def public_user_claims(request, username):
    """Fetch public claims submitted by a specific user."""
    target_user = get_object_or_404(User, username=username)
    claims = (
        Claim.objects.filter(check_history__user=target_user)
        .annotate(last_checked_at=Max("check_history__checked_at"))
        .order_by("-last_checked_at", "-last_updated")
    )

    serializer = ClaimSerializer(claims, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def moderator_transparency_stats(request, username):
    """Return moderator activity metrics for institutional transparency cards."""
    target_user = get_object_or_404(
        User.objects.select_related("profile"), username=username
    )

    if not _has_moderator_role(target_user):
        return Response({"detail": "This user is not a moderator."}, status=400)

    resolved_threads = Thread.objects.filter(
        moderated_by=target_user,
        moderator_verdict__isnull=False,
    )

    stats = {
        "total_claims_resolved": resolved_threads.count(),
        "fact_verdicts_issued": resolved_threads.filter(
            moderator_verdict="FACT"
        ).count(),
        "fake_verdicts_issued": resolved_threads.filter(
            moderator_verdict="FAKE"
        ).count(),
        "pending_moderator_review": Thread.objects.filter(
            status=Thread.Status.PENDING,
            moderator_verdict__isnull=True,
        ).count(),
    }

    return Response(stats, status=200)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_follow_user(request, username):
    """Toggle follow/unfollow for a specific user."""
    if request.user.username == username:
        return Response({"error": "You cannot follow yourself."}, status=400)

    target_user = get_object_or_404(User, username=username)
    profile = target_user.profile

    # If already following, UNFOLLOW
    if profile.followers.filter(id=request.user.id).exists():
        profile.followers.remove(request.user)
        is_following = False
    # If not following, FOLLOW
    else:
        profile.followers.add(request.user)
        is_following = True

    return Response(
        {"is_following": is_following, "followers_count": profile.followers.count()},
        status=200,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_followers(request, username):
    """Get a list of users who follow this profile."""
    target_user = get_object_or_404(User, username=username)
    # Get all User objects inside this profile's followers list
    followers = target_user.profile.followers.all()
    serializer = UserSerializer(followers, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_following(request, username):
    """Get a list of users this profile is following."""
    target_user = get_object_or_404(User, username=username)
    # Find all Users whose profiles include the target_user as a follower
    following = User.objects.filter(profile__followers=target_user)
    serializer = UserSerializer(following, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """Update user's profile info including bio, username, email, and avatar."""
    user = request.user
    profile = user.profile
    data = request.data

    # Update User model fields
    if "username" in data and data["username"]:
        user.username = data["username"]
    if "email" in data and data["email"]:
        user.email = data["email"]

    # Update Bio if provided
    if "bio" in data:
        profile.bio = data["bio"]

    # Update Avatar if base64 image is provided
    if "avatar_base64" in data and data["avatar_base64"]:
        base64_string = data["avatar_base64"]
        # Strip the data:image/png;base64, header if it exists
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]

        # Reuse your awesome existing upload service!
        avatar_url = upload_image_to_database(base64_string)
        if avatar_url:
            profile.avatar_url = avatar_url

    user.save()
    profile.save()

    # Return the updated user data
    serializer = UserWithTrustBreakdownSerializer(user, context={"request": request})
    return Response(serializer.data, status=200)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsModerator])
def moderation_stats_view(request):
    """
    Returns system-wide aggregates for the Moderation Page.
    """
    from django.db.models import Q

    flagged_threads = (
        ModerationCase.objects.filter(
            case_type=ModerationCase.CaseType.SAFETY,
            status__in=ACTIVE_CASE_STATUSES,
        )
        .exclude(thread__isnull=True)
        .values("thread_id")
        .distinct()
        .count()
    )
    closed_threads = Thread.objects.filter(status=Thread.Status.CLOSED).count()
    open_threads = Thread.objects.filter(
        Q(status=Thread.Status.OPEN) | Q(status=Thread.Status.PENDING)
    ).count()
    pending_verdicts = Thread.objects.filter(moderator_verdict__isnull=True).count()
    total_claims = Claim.objects.count()

    return Response(
        {
            "flagged_threads": flagged_threads,
            "closed_threads": closed_threads,
            "open_threads": open_threads,
            "pending_verdicts": pending_verdicts,
            "total_claims": total_claims,
        }
    )


class UserHubView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = user.profile

        # 1. Reputation & Progression
        components = calculate_trust_components(user)
        progression = get_reputation_progression(components)

        # 2. Personal Impact Metrics
        total_scans = Claim.objects.filter(check_history__user=user).distinct().count()

        evidence_submitted = EvidenceSubmission.objects.filter(contributor=user).count()
        votes_cast = Vote.objects.filter(voter=user).count()

        # Impact Ripple: How many votes did other people give to THIS user's evidence?
        impact_ripple = Vote.objects.filter(evidence__contributor=user).count()

        return Response(
            {
                "user_info": {
                    "username": user.username,
                    "avatar_url": (
                        profile.avatar_url
                        if hasattr(profile, "avatar_url") and profile.avatar_url
                        else None
                    ),
                },
                "reputation": {
                    "trust_score": components["trust_score"],
                    "status": progression["status"],
                    "current_rank": progression["current_rank"],
                    "next_rank": progression["next_rank"],
                    "score_to_next_rank": progression["score_to_next_rank"],
                    "actions_to_next_rank": progression["actions_to_next_rank"],
                    "progress_percent": progression["progress_percent"],
                    "resolved_actions": progression["resolved_actions"],
                    "confidence": progression["confidence"],
                    "breakdown": {
                        "base_score": components["base_score"],
                        "contribution_points": components["contribution_points"],
                        "community_points": components["community_points"],
                        "history_points": components["history_points"],
                        "moderation_penalty": components["moderation_penalty"],
                    },
                },
                "impact": {
                    "total_scans": total_scans,
                    "community_contributions": evidence_submitted + votes_cast,
                    "impact_ripple": impact_ripple,
                },
            }
        )


class UserFactCheckLibraryView(APIView):
    permission_classes = [IsAuthenticated]

    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 50

    VALID_VIEWS = {"history", "saved"}
    VALID_SORTS = {"newest", "oldest"}

    VALID_VERDICTS = {
        "FACT",
        "FAKE",
        "MISLEADING",
        "SATIRE",
        "UNVERIFIED",
        "OUT_OF_SCOPE",
    }

    VALID_TYPES = {
        Claim.ClaimType.TEXT,
        Claim.ClaimType.IMAGE,
        Claim.ClaimType.VIDEO,
        Claim.ClaimType.URL,
        Claim.ClaimType.FILE,
    }

    def get(self, request):
        user = request.user

        history_count = (
            Claim.objects.filter(check_history__user=user).distinct().count()
        )

        saved_count = user.profile.saved_claims.count()

        view_mode = request.query_params.get("view", "history").strip().lower()

        if view_mode not in self.VALID_VIEWS:
            return Response(
                {"detail": "Invalid view. Use 'history' or 'saved'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        search_query = request.query_params.get("search", "").strip()[:120]

        verdict = request.query_params.get("verdict", "").strip().upper()

        claim_type = request.query_params.get("type", "").strip().upper()

        sort_order = request.query_params.get("sort", "newest").strip().lower()

        if sort_order not in self.VALID_SORTS:
            sort_order = "newest"

        try:
            page_number = max(
                int(request.query_params.get("page", 1)),
                1,
            )
        except (TypeError, ValueError):
            page_number = 1

        try:
            page_size = int(
                request.query_params.get(
                    "page_size",
                    self.DEFAULT_PAGE_SIZE,
                )
            )
        except (TypeError, ValueError):
            page_size = self.DEFAULT_PAGE_SIZE

        page_size = max(
            1,
            min(page_size, self.MAX_PAGE_SIZE),
        )

        if view_mode == "history":
            queryset = Claim.objects.filter(check_history__user=user).annotate(
                activity_at=Max("check_history__checked_at")
            )

            ordering = (
                "activity_at",
                "id",
            )

            if sort_order == "newest":
                ordering = (
                    "-activity_at",
                    "-id",
                )

        else:
            queryset = user.profile.saved_claims.all().annotate(
                activity_at=F("last_updated")
            )

            ordering = (
                "activity_at",
                "id",
            )

            if sort_order == "newest":
                ordering = (
                    "-activity_at",
                    "-id",
                )

        if search_query:
            queryset = queryset.filter(
                Q(context_text__icontains=search_query)
                | Q(ai_summary__icontains=search_query)
                | Q(ai_verdict__icontains=search_query)
                | Q(final_verdict__icontains=search_query)
                | Q(source_link__icontains=search_query)
                | Q(top_verdict_source__icontains=search_query)
                | Q(url_link__icontains=search_query)
            )

        if verdict:
            if verdict not in self.VALID_VERDICTS:
                return Response(
                    {"detail": "Invalid verdict filter."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(
                Q(final_verdict=verdict)
                | Q(
                    final_verdict__isnull=True,
                    ai_verdict=verdict,
                )
                | Q(
                    final_verdict="",
                    ai_verdict=verdict,
                )
            )

        if claim_type:
            if claim_type not in self.VALID_TYPES:
                return Response(
                    {"detail": "Invalid claim type filter."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(claim_type=claim_type)

        queryset = queryset.order_by(*ordering)

        paginator = Paginator(
            queryset,
            page_size,
        )

        try:
            page_obj = paginator.page(page_number)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        page_claim_ids = [claim.id for claim in page_obj.object_list]

        saved_claim_ids = set(
            user.profile.saved_claims.filter(id__in=page_claim_ids).values_list(
                "id", flat=True
            )
        )

        serializer = ClaimSerializer(
            page_obj.object_list,
            many=True,
            context={
                "request": request,
                "saved_claim_ids": saved_claim_ids,
            },
        )

        return Response(
            {
                "view": view_mode,
                "counts": {
                    "history": history_count,
                    "saved": saved_count,
                },
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_save_claim(request, claim_id):
    """Allows a user to bookmark or un-bookmark a claim for their Personal Hub."""
    try:
        claim = Claim.objects.get(id=claim_id)
    except Claim.DoesNotExist:
        return Response({"error": "Claim not found."}, status=404)

    profile = request.user.profile

    if profile.saved_claims.filter(id=claim.id).exists():
        profile.saved_claims.remove(claim)
        is_saved = False
    else:
        profile.saved_claims.add(claim)
        is_saved = True

    return Response(
        {
            "is_saved": is_saved,
            "saved_count": profile.saved_claims.count(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_claim_analysis(request, claim_id):
    claim = get_object_or_404(Claim, id=claim_id)
    serializer = ClaimDeepAnalysisSerializer(claim, context={"request": request})
    return Response(serializer.data)


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([FactCheckRateThrottle])
def verify_file(request):
    base64_string = request.data.get("file_data")
    file_name = request.data.get("file_name", "")

    if not base64_string:
        return Response({"error": "No document data provided"}, status=400)

    if "," in base64_string:
        base64_string = base64_string.split(",")[1]

    try:
        # Decode base64 to raw bytes
        file_bytes = base64.b64decode(base64_string)
        file_obj = io.BytesIO(file_bytes)
        extracted_text = ""

        # Extract text based on file extension
        if file_name.lower().endswith(".pdf"):
            reader = PyPDF2.PdfReader(file_obj)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + "\n"

        elif file_name.lower().endswith(".docx") and docx:
            doc = docx.Document(file_obj)
            extracted_text = "\n".join([para.text for para in doc.paragraphs])

        elif file_name.lower().endswith(".txt"):
            extracted_text = file_bytes.decode("utf-8")

        else:
            return Response(
                {"error": "Unsupported file format. Please use PDF, DOCX, or TXT."},
                status=400,
            )

        # Limit text to 5000 characters to protect your Groq/Llama-3 context window
        extracted_text = extracted_text.strip()[:5000]

        if not extracted_text:
            return Response(
                {
                    "error": "Could not extract text. If this is a scanned image PDF, OCR is required."
                },
                status=400,
            )

        # ── Claim Deduplication Pre-Check ──
        fingerprint = compute_fingerprint("TEXT", extracted_text)
        matched_claim = find_matching_claim(
            fingerprint, "TEXT", context_text=extracted_text
        )
        authenticated_user = _authenticated_user_or_none(request)

        if matched_claim:
            _record_authenticated_claim_check(authenticated_user, matched_claim)
            match_result = get_match_result(matched_claim)
            return JsonResponse(
                {
                    "claim_id": str(matched_claim.id),
                    "cached": True,
                    "match": match_result,
                },
                status=200,
            )

        # Save as FILE claim type
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.FILE,
            url_link=f"Document Input: {file_name}",
            claim_fingerprint=fingerprint,
            verified_via=Claim.VerificationSource.PENDING,
        )
        _record_authenticated_claim_check(authenticated_user, claim)
        claim_id = claim.id

        # Send the extracted text to your existing Celery worker
        text_fact_check_process.delay(extracted_text, claim_id)

        return JsonResponse(
            {"claim_id": str(claim_id), "cached": False},
            status=200,
        )

    except Exception as e:
        return Response({"error": f"Failed to process document: {str(e)}"}, status=500)


# Password Reset Request Endpoint
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetRateThrottle])
def request_password_reset(request):
    email = str(request.data.get("email", "")).strip().lower()

    generic_message = (
        "If an account exists for this email, "
        "password reset instructions have been sent."
    )

    if not email:
        return Response(
            {"detail": "Email is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.filter(email__iexact=email).first()

    if user:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        frontend_url = os.getenv(
            "FRONTEND_URL",
            "http://localhost:5173",
        ).rstrip("/")

        reset_url = f"{frontend_url}/reset-password/{uid}/{token}"

        subject = "Reset your TruthLens password"

        text_body = (
            "We received a request to reset your TruthLens password.\n\n"
            f"Reset your password here:\n{reset_url}\n\n"
            "This link is single-use and will expire.\n\n"
            "If you did not request this, you can ignore this email."
        )

        html_body = render_to_string(
            "emails/password_reset.html",
            {
                "reset_url": reset_url,
            },
        )

        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )

        email_message.attach_alternative(
            html_body,
            "text/html",
        )

        try:
            email_message.send(fail_silently=False)

        except Exception as error:
            print(f"Password reset email failed: {error}")

    return Response(
        {"detail": generic_message},
        status=status.HTTP_200_OK,
    )


# Password Reset Confirmation Endpoint
@api_view(["POST"])
@permission_classes([AllowAny])
def confirm_password_reset(request):
    uid = request.data.get("uid")
    token = request.data.get("token")
    new_password = request.data.get("new_password")
    confirm_password = request.data.get("confirm_password")

    if not all([uid, token, new_password, confirm_password]):
        return Response(
            {"detail": "All fields are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if new_password != confirm_password:
        return Response(
            {"detail": "Passwords do not match."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)

    except (TypeError, ValueError, OverflowError, User.DoesNotExist) as error:
        print("RESET DEBUG uid decode/user lookup failed:", error)

        return Response(
            {"detail": "This password reset link is invalid or has expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    token_is_valid = default_token_generator.check_token(user, token)

    print("RESET DEBUG token valid:", token_is_valid)

    if not token_is_valid:
        return Response(
            {"detail": "This password reset link is invalid or has expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not default_token_generator.check_token(user, token):
        return Response(
            {"detail": "This password reset link is invalid or has expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as error:
        return Response(
            {"detail": error.messages},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    return Response(
        {"detail": "Your password has been reset successfully."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_onboarding(request):
    profile = request.user.profile

    if not profile.has_completed_onboarding:
        profile.has_completed_onboarding = True
        profile.save(update_fields=["has_completed_onboarding"])

    return Response(
        {
            "has_completed_onboarding": True,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def organization_members(
    request,
    organization_id,
):
    """
    Return the current administrative roster for
    one organization.

    Only users with MANAGE_ORGANIZATION for the
    requested organization may access the roster.

    LEFT memberships are historical relationships
    and are intentionally excluded from the current
    administrative roster.
    """

    organization = get_object_or_404(
        Organization,
        id=organization_id,
    )

    if not has_capability(
        request.user,
        PartnerCapability.MANAGE_ORGANIZATION,
        organization=organization,
    ):
        return Response(
            {
                "detail": (
                    "You do not have permission " "to manage this organization."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    memberships = (
        OrganizationMembership.objects.filter(
            organization=organization,
        )
        .exclude(
            status=(OrganizationMembership.Status.LEFT),
        )
        .select_related(
            "user",
            "approved_by",
        )
        .order_by(
            "user__username",
            "id",
        )
    )

    serializer = OrganizationMembershipAdminSerializer(
        memberships,
        many=True,
    )

    return Response(
        {
            "organization": {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            },
            "count": memberships.count(),
            "summary": {
                "active": memberships.filter(
                    status=(OrganizationMembership.Status.ACTIVE),
                ).count(),
                "pending": memberships.filter(
                    status=(OrganizationMembership.Status.PENDING),
                ).count(),
                "suspended": memberships.filter(
                    status=(OrganizationMembership.Status.SUSPENDED),
                ).count(),
            },
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )
