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
from datetime import timedelta
import json
import secrets
import base64
from .services import detect_ai_image
from .services import process_image, upload_image_to_database
from .tasks import snippet_fact_check_process, url_fact_check_process, update_contributor_trust_score, text_fact_check_process
from .models import Claim, Thread, UserProfile, EvidenceSubmission, ThreadComment, ThreadFlag
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    UserProfileSerializer,
    ClaimSerializer,
    ThreadSerializer,
    ThreadCommentSerializer,
    EvidenceSubmissionSerializer,
    ThreadDetailSerializer,
    VoteSerializer,
    ThreadFlagSerializer,
    ModerationDecisionSerializer,
)

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
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.contributor == request.user

class IsCommenterOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.commenter == request.user

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

    if not base64_string:
        return JsonResponse({"error": "No image data provided"}, status=400)

    if "," in base64_string:
        base64_string = base64_string.split(",")[1]

    # Decode the base64 string and save it as an image
    image_hash, _ = process_image(base64_string)
    
    media_url = upload_image_to_database(base64_string)
    
    print("IMAGE HASH:", image_hash)

    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.IMAGE,
        media_hash=image_hash,
        media_url=media_url,
        verdict=None,
        verified_via=Claim.VerificationSource.PENDING,
    )
    claim_id = claim.id  # Get the ID of the saved claim

    snippet_fact_check_process.delay(image_hash, base64_string, str(claim_id))

    return JsonResponse(
        {"claim_id": str(claim_id)},
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
        return JsonResponse(
            {
                "id": claim_id,
                "verdict": ai_verdict,
                "ai_verdict": ai_verdict,
                "final_verdict": claim.final_verdict,
                "summary": claim.ai_summary,
                "confidence_score": claim.consensus_score,
                "source_type": claim.source_type,
                "source_url": claim.top_verdict_source,
            },
            status=200,
        )


@csrf_exempt
@api_view(["POST"])
def verify_url(request):
    # gets the data from fronted ('yung URL)
    url = request.data.get("url")
    print(f"Received URL: {url}")
    if not url:
        return Response({"error": "URL is required"}, status=400)

    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.URL,
        url_link=url,
        verdict=None,
        verified_via=Claim.VerificationSource.PENDING,
    )
    claim_id = claim.id
    
    url_fact_check_process.delay(url, claim_id)
    
    return JsonResponse(
        {"claim_id": str(claim_id)},
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
    serializer = UserSerializer(request.user)
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

    queryset = Thread.objects.filter(flags__isnull=False).distinct().order_by("-created_at")
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

    queryset = Thread.objects.select_related("claim", "author", "moderated_by").order_by("-created_at")
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

    return Response(ThreadDetailSerializer(thread).data, status=status.HTTP_200_OK)

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsModerator])
def evidence_moderation_queue(request):
    """
    Returns unverified evidence submissions for review. Moderators only.
    
    Query params:
    - status: filter by status (UNVERIFIED, VERIFIED, REJECTED)
    - thread_id: filter by thread
    """
    
    status = request.query_params.get("status", "UNVERIFIED")
    thread_id = request.query_params.get("thread_id")

    evidence = EvidenceSubmission.objects.filter(evidence_status=status).select_related("contributor", "thread__claim").order_by("-submitted_at")
    
    if thread_id:
        evidence = evidence.filter(thread_id=thread_id)
        
    serializer = EvidenceSubmissionSerializer(evidence, many=True)
    return Response(serializer.data, status=200)

#Viewsets
class ThreadViewSet(viewsets.ModelViewSet):
    serializer_class = ThreadSerializer
    permission_classes = [IsAuthenticated, IsThreadOwnerOrReadOnly]

    def get_queryset(self):
        return Thread.objects.exclude(status=Thread.Status.REJECTED).order_by("-created_at")

    def perform_create(self, serializer):
        claim_id = serializer.validated_data.pop("claim_id")
        try:
            claim = Claim.objects.get(id=claim_id)
        except Claim.DoesNotExist:
            raise NotFound('Claim not found.')
        serializer.save(author=self.request.user, claim=claim)

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
        
        update_contributor_trust_score.delay(evidence.contributor.id, status) # Update trust score asynchronously after moderation decision
        
        serializer = EvidenceSubmissionSerializer(evidence)
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

    # TEMP HACK: Save as URL so we don't have to run migrations yet.
    # We set url_link to a short string so it doesn't crash the 500-character database limit!
    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.URL, 
        url_link="Text Claim Input", 
        verdict=None,
        verified_via=Claim.VerificationSource.PENDING,
    )
    claim_id = claim.id
    
    # Send the raw text to the Celery worker
    text_fact_check_process.delay(text_content, claim_id)
    
    return JsonResponse(
        {"claim_id": str(claim_id)},
        status=200,
    )