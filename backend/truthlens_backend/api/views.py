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
from .tasks import snippet_fact_check_process
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
        return JsonResponse({"error": "Claim not found"}, status=404)

    if claim.verdict is None:
        return JsonResponse({"verdict": "PENDING"}, status=200)
    else:
        return JsonResponse(
            {
                "verdict": claim.verdict,
                "summary": claim.ai_summary,
                "confidence_score": claim.consensus_score,
                "source_type": claim.source_type,
                "source_url": claim.source_link,
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

    # extract
    try:
        print("Starting Tavily extract...")  # tets
        response = requests.post(
            "https://api.tavily.com/extract",
            headers={"Authorization": f"Bearer {os.environ.get("TAVILY_API_KEY")}"},
            json={"urls": [url]},
        )

        print(f"Tavily response: {response.status_code}")  # test
        print(f"Tavily data: {response.json()}")  # test
        tavily_data = response.json()

        if not tavily_data.get("results"):
            return Response(
                {
                    "error": "Could not extract content from this URL. Try a news article instead."
                },
                status=400,
            )
        
        raw_text = tavily_data["results"][0]["raw_content"]
        cleaned_text = clean_extracted_text(raw_text)      # regex cleaner first
        result = extract_search_query(cleaned_text)         # then AI extracts the claim

        cleaned_claim = result["cleaned_claim"]             # full sentence — for AI analysis
        search_query = result["search_query"]               # short query — for searching

        print(f"Raw Text Length: {len(raw_text)} characters")

        print(f"Cleaned claim text: {cleaned_claim}")

    except Exception as e:
        print(f"Tavily extract error: {str(e)}")  # test
        return Response({"error": f"Text extraction failed: {str(e)}"}, status=500)

    # GFC
    try:
        fact_check_response = requests.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={
                "query": search_query[:200],
                "key": os.environ.get("FACT_CHECK_API_KEY"),
            },
        )

        gfc_data = fact_check_response.json()
        claims = gfc_data.get("claims", [])

        if claims:
            first_claim_text = claims[0].get("text", "")
            print(f"GFC Found a claim: {first_claim_text[:100]}...")

            if is_fact_check_relevant(cleaned_claim, first_claim_text):
                print("GFC result is relevant, evaluating")

                verdict = evaluate_url_claim_with_gfc(cleaned_claim, gfc_data)

                return Response(
                    {
                        "verdict": verdict.get("verdict"),
                        "summary": verdict.get("summary"),
                        "confidence_score": verdict.get("confidence_score"),
                        "source_type": "Official Fact Check",
                        "source_url": url,
                    }
                )
            else:
                print("GFC result not relevant, falling through to web search...")
        else:
            print("No claims found in GFC")

    except Exception as e:
        print(f"GFC error: {str(e)}")

    # tavily search
    try:
        print("Searching trough tavily....")

        tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

        search_response = tavily_client.search(
            query=search_query[:300],
            search_depth="advanced",
            topic="news",
            include_answer=True,
        )

        context = search_response.get("answer", "No additional context found")
        print(f"Tavily search context: {context[:200]}")

    except Exception as e:
        print(f"Search error: {str(e)}")
        context = "Could not retrieve additional context"

    # AI analysis
    try:
        print("Running Groq Analysis...")

        verdict = evaluate_url_claim_with_tavily(cleaned_claim, context)
        print(f"AI verdict: {verdict}")

        return Response(
            {
                "verdict": verdict.get("verdict"),
                "summary": verdict.get("summary"),
                "confidence_score": verdict.get("confidence_score"),
                "source_type": "Live Web Search",
                "source_url": url,
            }
        )

    except Exception as e:
        print(f"Groq error: {str(e)}")
        return Response({"error": f"AI analysis failed: {str(e)}"}, status=500)


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
    queryset = Claim.objects.all()



