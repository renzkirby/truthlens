from django.http import JsonResponse
from django.core.mail import send_mail
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db import IntegrityError, transaction
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound
from rest_framework.pagination import CursorPagination
from datetime import timedelta
from django.shortcuts import get_object_or_404
import json
import secrets
import base64
from .services import detect_ai_image
from .services import process_image, upload_image_to_database
from .services import validate_public_url, check_url_threat_reputation
from .claim_matching import compute_fingerprint, find_matching_claim, get_match_result
from .tasks import (
    snippet_fact_check_process,
    url_fact_check_process,
    update_contributor_trust_score,
    text_fact_check_process,
    recompute_user_trust_score_task,
)
from .models import (
    Claim,
    Thread,
    UserProfile,
    EvidenceSubmission,
    ThreadComment,
    ThreadFlag,
    FlagResolutionLog,
    Vote,
)
from .trust_service import recompute_user_trust_score
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    CurrentUserSerializer,
    UserProfileSerializer,
    ClaimSerializer,
    ThreadSerializer,
    ThreadCommentSerializer,
    EvidenceSubmissionSerializer,
    ThreadDetailSerializer,
    VoteSerializer,
    ThreadFlagSerializer,
    ModerationDecisionSerializer,
    ClaimMatchSerializer,
    UserWithTrustBreakdownSerializer,
)

# ── Pagination Configuration ──
class StandardCursorPagination(CursorPagination):
    """
    Cursor-based pagination for efficient infinite scrolling.
    More efficient than offset pagination for large datasets.
    """
    page_size = 20
    ordering = '-created_at'
    cursor_query_param = 'cursor'
    template = None  # Disable HTML template

ALLOWED_MODERATION_TRANSITIONS = {
    "PENDING": {"OPEN", "CLOSED", "REJECTED"},
    "OPEN": {"CLOSED", "REJECTED"},
    "CLOSED": {"OPEN"},
    "REJECTED": set(),
}

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

class IsModerator(BasePermission):
    def has_permission(self, request, view):
        return (request.user.is_authenticated and request.user.profile.role == UserProfile.Role.MODERATOR)

class IsNotModerator(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.profile.role != UserProfile.Role.MODERATOR

# Create your views here.
@csrf_exempt
@api_view(["POST"])
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
    if fingerprint:
        matched_claim = find_matching_claim(fingerprint, "IMAGE")
        if matched_claim and matched_claim.final_verdict:
            # A moderator has already resolved this claim — return cached verdict
            match_result = get_match_result(matched_claim)
            return JsonResponse(
                {"claim_id": str(matched_claim.id), "cached": True, "match": match_result},
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
        verdict=None,
        verified_via=Claim.VerificationSource.PENDING,
    )
    claim_id = claim.id  # Get the ID of the saved claim

    snippet_fact_check_process.delay(image_hash, str(claim_id), check_deepfake)

    return JsonResponse(
        {"claim_id": str(claim_id), "cached": False},
        status=200,
    )



@csrf_exempt
@api_view(["GET"])
def claim_polling_endpoint(request, claim_id):
    if not claim_id:
        return JsonResponse({"error": "Claim ID is required"}, status=400)

    try:
        claim = Claim.objects.get(id=claim_id)
    except Claim.DoesNotExist:
        return JsonResponse({
            "verdict": "OUT_OF_SCOPE",
            "summary": "The content of the image is not a claim that can be fact-checked.",
            "confidence_score": 100,
            "source_type": "N/A",
            }, status=200)

    ai_verdict = claim.ai_verdict or claim.verdict
    if ai_verdict is None:
        return JsonResponse({"verdict": "PENDING"}, status=200)
    else:
        # Include community verdict info when available
        effective_verdict = claim.final_verdict or ai_verdict
        active_thread = claim.threads.exclude(status="REJECTED").order_by("-created_at").first()
        moderator_notes = None
        if claim.final_verdict:
            resolved_thread = claim.threads.filter(
                moderator_verdict__isnull=False
            ).order_by("-moderated_at").first()
            if resolved_thread:
                moderator_notes = resolved_thread.moderator_notes

        return JsonResponse(
            {
                "id": claim_id,
                "verdict": effective_verdict,
                "ai_verdict": ai_verdict,
                "final_verdict": claim.final_verdict,
                "summary": moderator_notes or claim.ai_summary,
                "confidence_score": claim.consensus_score,
                "source_type": claim.source_type,
                "source_url": claim.top_verdict_source,
                "is_ai_generated": claim.is_ai_generated,
                "thread_id": str(active_thread.id) if active_thread else None,
                "has_community_verdict": bool(claim.final_verdict),
                "score_context": claim.score_context,
            },
            status=200,
        )


@csrf_exempt
@api_view(["POST"])
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
    if fingerprint:
        matched_claim = find_matching_claim(fingerprint, "URL")
        if matched_claim and matched_claim.final_verdict:
            match_result = get_match_result(matched_claim)
            return JsonResponse(
                {"claim_id": str(matched_claim.id), "url_safety": url_safety, "cached": True, "match": match_result},
                status=200,
            )

    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.URL,
        url_link=safe_url,
        claim_fingerprint=fingerprint,
        verdict=None,
        verified_via=Claim.VerificationSource.PENDING,
    )
    claim_id = claim.id
    
    url_fact_check_process.delay(safe_url, claim_id)
    
    return JsonResponse(
        {"claim_id": str(claim_id), "url_safety": url_safety, "cached": False},
        status=200,
    )


#User registration
@csrf_exempt
@api_view(["POST"])
def register_user(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        token = secrets.token_urlsafe(32)
        user.profile.email_verification_token = token
        user.profile.save()

        verification_link = f"http://localhost:5174/verify-email?token={token}"
        send_mail(
            subject="Verify your TruthLens email",
            message=f"Click the link to verify your email: {verification_link}",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=True,  # don't crash registration if email fails
        )

        return Response(get_tokens_for_user(user), status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    serializer = CurrentUserSerializer(request.user)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_claims(request):
    claims = Claim.objects.filter(
        threads__author=request.user 
    ).distinct().order_by("-last_updated")
    serializer = ClaimSerializer(claims, many=True)
    return Response(serializer.data)

@api_view(["POST"])
def login_user(request):
    username = request.data.get("username")
    password = request.data.get("password")
    remember_me = request.data.get("remember_me")

    user = authenticate(request, username=username, password=password)

    if user is None:
        return Response(
            {"detail": "No active account found with the given credentials"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    refresh = RefreshToken.for_user(user)

    if remember_me:
        refresh.set_exp(lifetime=timedelta(days=30))

    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_verification_email(request):
    token = secrets.token_urlsafe(32)
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        return Response({ "error": "User does not exist."}, status=404)
    
    user_profile.email_verification_token = token
    user_profile.save()
    
    verification_link = f"http://localhost:5174/verify-email?token={token}"
    
    send_mail(
        subject="Verify your TruthLens email",
        message=f"Click the link to verify your email: {verification_link}",
        from_email=None,
        recipient_list=[request.user.email],
    )
    
    return Response({"message": "Verification email sent."}, status=200) 

@api_view(["GET"])
def verify_email(request):
    token = request.query_params.get("token")

    if not token:
        return Response({"error": "Token is required."}, status=400)

    try:
        user_profile = UserProfile.objects.get(email_verification_token=token)
    except UserProfile.DoesNotExist:
        return Response({"error": "Invalid or expired token"}, status=400)
    
    user_profile.is_email_verified = True
    user_profile.email_verification_token = None
    user_profile.save()
    
    return Response({"message": "Email verified successfully."}, status=200)
    

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsModerator])
def moderation_queue(request):
    # Safety queue: reported/flagged threads requiring moderator review for conduct issues.
    status_filter = request.query_params.get("status", Thread.Status.PENDING)
    allowed = {"ALL", Thread.Status.PENDING, Thread.Status.OPEN, Thread.Status.CLOSED, Thread.Status.REJECTED}
    if status_filter not in allowed:
        return Response(
            {"detail": "Invalid status filter."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = (
        Thread.objects.filter(flags__isnull=False)
        .select_related("claim", "author", "author__profile")
        .distinct()
        .order_by("-created_at")
    )
    if status_filter != "ALL":
        queryset = queryset.filter(status=status_filter)

    serializer = ThreadSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsModerator])
def verdict_queue(request):
    # Verdict queue: claim adjudication workflow, independent of report/flag status.
    reviewed_filter = request.query_params.get("reviewed", "pending")
    allowed = {"all", "pending", "resolved"}
    if reviewed_filter not in allowed:
        return Response(
            {"detail": "Invalid reviewed filter. Use all, pending, or resolved."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = (
        Thread.objects.select_related(
            "claim", "author", "author__profile", "moderated_by", "moderated_by__profile"
        )
        .order_by("-created_at")
    )
    if reviewed_filter == "pending":
        queryset = queryset.filter(moderator_verdict__isnull=True)
    elif reviewed_filter == "resolved":
        queryset = queryset.filter(moderator_verdict__isnull=False)

    serializer = ThreadSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsModerator])
def moderation_resolve_thread(request, thread_id):
    try:
        thread = Thread.objects.get(id=thread_id)
    except Thread.DoesNotExist:
        raise NotFound("Thread not found.")

    serializer = ModerationDecisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    moderator_verdict = serializer.validated_data["moderator_verdict"]
    moderator_notes = serializer.validated_data.get("moderator_notes", "")
    next_status = serializer.validated_data.get("status", Thread.Status.CLOSED)

    current_status = thread.status or Thread.Status.OPEN
    if next_status not in ALLOWED_MODERATION_TRANSITIONS.get(current_status, set()):
        return Response(
            {"detail": f"Invalid status transition from {current_status} to {next_status}."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    contributor_ids = set(
        thread.evidence_submissions.values_list("contributor_id", flat=True).distinct()
    )

    with transaction.atomic():
        thread.moderator_verdict = moderator_verdict
        thread.moderator_notes = moderator_notes
        thread.status = next_status
        thread.moderated_by = request.user
        thread.moderated_at = timezone.now()
        thread.save(
            update_fields=[
                "moderator_verdict",
                "moderator_notes",
                "status",
                "moderated_by",
                "moderated_at",
            ]
        )

        # Keep AI verdict immutable and write moderator decision to final verdict.
        thread.claim.final_verdict = moderator_verdict
        # Backward compatibility for existing consumers still reading claim.verdict.
        thread.claim.verdict = moderator_verdict
        thread.claim.last_updated = timezone.now()
        thread.claim.save(update_fields=["final_verdict", "verdict", "last_updated"])

    for contributor_id in contributor_ids:
        recompute_user_trust_score_task.delay(contributor_id)

    return Response(ThreadDetailSerializer(thread).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsModerator])
def moderation_resolve_safety_thread(request, thread_id):
    """Resolve a reported thread directly from the safety queue."""
    try:
        thread = Thread.objects.get(id=thread_id)
    except Thread.DoesNotExist:
        raise NotFound("Thread not found.")

    action = (request.data.get("action") or "").strip().upper()
    moderator_notes = (request.data.get("moderator_notes") or "").strip()
    allowed_actions = {"DISMISS", "REMOVE", "ESCALATE"}
    if action not in allowed_actions:
        return Response(
            {"detail": "Invalid action. Use DISMISS, REMOVE, or ESCALATE."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    contributor_ids = set(
        thread.evidence_submissions.values_list("contributor_id", flat=True).distinct()
    )

    with transaction.atomic():
        if action == "DISMISS":
            thread.status = Thread.Status.OPEN
        elif action == "REMOVE":
            thread.status = Thread.Status.REJECTED
        else:
            thread.status = Thread.Status.CLOSED

        thread.moderated_by = request.user
        thread.moderated_at = timezone.now()
        if moderator_notes:
            thread.moderator_notes = moderator_notes

        update_fields = ["status", "moderated_by", "moderated_at"]
        if moderator_notes:
            update_fields.append("moderator_notes")
        thread.save(update_fields=update_fields)

        # Persist resolved report history for trust-score accuracy metrics.
        current_flags = list(thread.flags.select_related("flagged_by"))
        resolved_logs = []
        reporter_ids = set()
        for flag in current_flags:
            reporter_ids.add(flag.flagged_by_id)
            resolved_logs.append(
                FlagResolutionLog(
                    thread=thread,
                    flagged_by=flag.flagged_by,
                    reason=flag.reason,
                    notes=flag.notes,
                    flagged_at=flag.flagged_at,
                    resolved_action=action,
                    is_valid_report=(action == "REMOVE"),
                    resolved_by=request.user,
                )
            )

        if resolved_logs:
            FlagResolutionLog.objects.bulk_create(resolved_logs)

        # Keep active queue clean after archiving resolved entries.
        thread.flags.all().delete()

    # Recompute trust for all reporters involved in the resolved moderation event.
    for reporter_id in reporter_ids:
        recompute_user_trust_score_task.delay(reporter_id)

    # Conduct penalties apply to the thread author when a thread is removed.
    if action == "REMOVE":
        recompute_user_trust_score_task.delay(thread.author_id)

    for contributor_id in contributor_ids:
        recompute_user_trust_score_task.delay(contributor_id)

    return Response(ThreadSerializer(thread).data, status=status.HTTP_200_OK)

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsModerator])
def evidence_moderation_queue(request):
    """
    Returns unverified evidence submissions for review. Moderators only.
    
    Query params:
    - status: filter by status (UNVERIFIED, VERIFIED, REJECTED)
    - thread_id: filter by thread
    - limit: number of items per page (default 20)
    - offset: number of items to skip (default 0)
    """
    
    status = request.query_params.get("status", "UNVERIFIED")
    thread_id = request.query_params.get("thread_id")
    limit = int(request.query_params.get("limit", 20))
    offset = int(request.query_params.get("offset", 0))

    evidence_query = EvidenceSubmission.objects.filter(evidence_status=status).select_related("contributor", "thread__claim").order_by("-submitted_at")
    
    if thread_id:
        evidence_query = evidence_query.filter(thread_id=thread_id)
    
    # Get total count for pagination info
    total_count = evidence_query.count()
    
    # Apply pagination
    evidence = evidence_query[offset:offset + limit]
        
    serializer = EvidenceSubmissionSerializer(evidence, many=True, context={"request": request})
    
    return Response({
        "count": total_count,
        "limit": limit,
        "offset": offset,
        "results": serializer.data
    }, status=200)

#Viewsets
class ThreadViewSet(viewsets.ModelViewSet):
    serializer_class = ThreadSerializer
    permission_classes = [IsAuthenticated, IsThreadOwnerOrReadOnly]
    pagination_class = StandardCursorPagination

    def get_queryset(self):
        queryset = (
            Thread.objects.exclude(status=Thread.Status.REJECTED)
            .select_related("claim", "author", "author__profile")
            .order_by("-created_at")
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
            raise NotFound('Claim not found.')

        # ── Thread Deduplication: Block + Redirect ──
        # Check if this claim (or a matching claim) already has an active thread
        existing_thread = self._find_existing_thread(claim)
        if existing_thread:
            raise ValidationError({
                "detail": "A community discussion already exists for this claim.",
                "existing_thread_id": str(existing_thread.id),
                "redirect": True,
            })

        serializer.save(author=self.request.user, claim=claim)

    def _find_existing_thread(self, claim):
        """
        Check if the claim (or a fingerprint-matched claim) already has an
        active thread. Returns the existing Thread or None.
        """
        # Direct check: does this exact claim already have a non-rejected thread?
        direct_thread = (
            Thread.objects
            .filter(claim=claim)
            .exclude(status=Thread.Status.REJECTED)
            .order_by("-created_at")
            .first()
        )
        if direct_thread:
            return direct_thread

        # Fingerprint check: does a matching claim have a thread?
        if claim.claim_fingerprint:
            matched_claim = find_matching_claim(claim.claim_fingerprint, claim.claim_type)
            if matched_claim and matched_claim.id != claim.id:
                matched_thread = (
                    Thread.objects
                    .filter(claim=matched_claim)
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
    permission_classes = [IsAuthenticated, IsNotModerator, IsEvidenceContributorOrReadOnly] #If moderator submits evidence, returns an error

    def get_queryset(self):
        return EvidenceSubmission.objects.all()
    
    def perform_create(self, serializer):
        thread_id = serializer.validated_data.pop("thread_id")
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")
        serializer.save(
            contributor=self.request.user,
            thread=thread,
            contributor_trust_snapshot=self.request.user.profile.trust_score,
        )
        
    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated, IsModerator])
    def verify(self, request, pk=None):
        """
        Verify or reject an evidence. Moderators only.
        Request body:
        {
            "evidence_status": "VERIFIED" or "REJECTED",
            "moderator_notes": "Optional notes",
        }
        """
        
        evidence = self.get_object()

        status = request.data.get("evidence_status")
        notes = request.data.get("moderator_notes", "")

        if status not in ["VERIFIED", "REJECTED"]:
            return Response({
                "detail": "Invalid evidence_status. Must be VERIFIED or REJECTED."
            }, status=status.HTTP_400_BAD_REQUEST)

        evidence.evidence_status = status
        evidence.verified_by = request.user
        evidence.verified_at = timezone.now()
        evidence.moderator_notes = notes
        evidence.save(update_fields=["evidence_status", "verified_by", "verified_at", "moderator_notes"])
        
        # Auto-compute final verdict for the claim based on verified evidence
        claim = evidence.thread.claim
        final_verdict = claim.compute_final_verdict()
        if final_verdict:
            claim.final_verdict = final_verdict
            claim.save(update_fields=["final_verdict"])
        
        # Persist trust immediately so UI does not show stale overall score after moderation.
        recompute_user_trust_score(evidence.contributor.id)
        # Keep async recompute as a safety net for eventual consistency.
        update_contributor_trust_score.delay(evidence.contributor.id, status)
        
        serializer = EvidenceSubmissionSerializer(evidence, context={"request": request})
        return Response(serializer.data, status=200)
        
        
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
        if self.request.user.profile.role == UserProfile.Role.MODERATOR:
            return ThreadFlag.objects.select_related("thread", "flagged_by").order_by("-flagged_at")
        return ThreadFlag.objects.filter(flagged_by=self.request.user).select_related(
            "thread", "flagged_by"
        ).order_by("-flagged_at")

    def perform_create(self, serializer):
        thread_id = serializer.validated_data.pop("thread_id")
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")

        try:
            serializer.save(flagged_by=self.request.user, thread=thread)
        except IntegrityError:
            raise ValidationError({"detail": "You already flagged this thread."})

        # Flagged threads are routed into moderation review without blocking all new threads.
        if thread.status == Thread.Status.OPEN:
            thread.status = Thread.Status.PENDING
            thread.save(update_fields=["status"])

        # Reporting activity affects contribution denominator immediately.
        recompute_user_trust_score_task.delay(self.request.user.id)


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
    """Temporary endpoint to test AI image detection."""
    parsed_data = json.loads(request.body)
    base64_string = parsed_data.get("image_data")

    if not base64_string:
        return JsonResponse({"error": "No image data provided"}, status=400)

    if "," in base64_string:
        base64_string = base64_string.split(",")[1]

    image_bytes = base64.b64decode(base64_string)
    
    # Call the API directly (No Celery needed for this quick test)
    ai_probability = detect_ai_image(image_bytes)
    
    return JsonResponse({
        "ai_probability": ai_probability,
        "is_fake": ai_probability > 0.65
    }, status=200)

@csrf_exempt
@api_view(["POST"])
def verify_text(request):
    """Endpoint for pure text fact-checking."""
    text_content = request.data.get("text")
    
    if not text_content:
        return Response({"error": "Text is required"}, status=400)
        
    print(f"Received Text: {text_content[:100]}...")

    # ── Claim Deduplication Pre-Check ──
    fingerprint = compute_fingerprint("TEXT", text_content)
    # Even if fingerprint is None or exact match fails, we want semantic fallback!
    matched_claim = find_matching_claim(fingerprint, "TEXT", context_text=text_content)
    
    if matched_claim and matched_claim.final_verdict:
        match_result = get_match_result(matched_claim)
        return JsonResponse(
            {"claim_id": str(matched_claim.id), "cached": True, "match": match_result},
            status=200,
        )

    # TEMP HACK: Save as URL so we don't have to run migrations yet.
    # We set url_link to a short string so it doesn't crash the 500-character database limit!
    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.URL, 
        url_link="Text Claim Input",
        claim_fingerprint=fingerprint,
        verdict=None,
        verified_via=Claim.VerificationSource.PENDING,
    )
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

    if not fingerprint and not text:
        return Response({"match": None}, status=200)

    matched_claim = find_matching_claim(fingerprint, claim_type, context_text=text)
    if matched_claim:
        match_result = get_match_result(matched_claim)
        serializer = ClaimMatchSerializer(data=match_result)
        serializer.is_valid(raise_exception=True)
        return Response({"match": serializer.validated_data}, status=200)

    return Response({"match": None}, status=200)

# for user view
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_public_user_profile(request, username):
    """Fetch public profile data for any user by their username."""
    # Look up the user, return 404 if they don't exist
    target_user = get_object_or_404(User, username=username)
    
    # We can reuse your existing serializer that includes the trust breakdown!
    serializer = UserWithTrustBreakdownSerializer(target_user, context={"request": request})
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def public_user_claims(request, username):
    """Fetch public claims submitted by a specific user."""
    target_user = get_object_or_404(User, username=username)
    claims = Claim.objects.filter(
        threads__author=target_user
    ).distinct().order_by("-last_updated")
    
    serializer = ClaimSerializer(claims, many=True)
    return Response(serializer.data)

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
        
    return Response({
        "is_following": is_following,
        "followers_count": profile.followers.count()
    }, status=200)

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