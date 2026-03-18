from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound
from tavily import TavilyClient
import os
import json
import requests
from .services import *
from .tasks import snippet_fact_check_process, url_fact_check_process
from .models import *
from .serializers import *


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
    print("IMAGE HASH:", image_hash)

    claim = Claim.objects.create(
        claim_type=Claim.ClaimType.IMAGE,
        media_hash=image_hash,
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

    if claim.verdict is None:
        return JsonResponse({"verdict": "PENDING"}, status=200)
    else:
        return JsonResponse(
            {
                "id": claim_id,
                "verdict": claim.verdict,
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

#Threads viewset
class ThreadViewSet(viewsets.ModelViewSet):
    serializer_class = ThreadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Thread.objects.all().order_by("-created_at")

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
    permission_classes = [IsAuthenticated]
    
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

class ThreadCommentViewSet(viewsets.ModelViewSet):
    serializer_class = ThreadCommentSerializer
    permission_classes = [IsAuthenticated]
    
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