from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from tavily import TavilyClient
import os
import json
import requests
from .services import *
from .tasks import snippet_fact_check_process
from .models import Claim


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

            if is_fact_check_relevant(extracted_text, first_claim_text):
                print("GFC result is relevant, evaluating")

                verdict = evaluate_url_claim_with_gfc(extracted_text, gfc_data)

                return Response(
                    {
                        "status": verdict.get("verdict"),
                        "explanation": verdict.get("summary"),
                        "confidence": verdict.get("confidence_score"),
                        "source_type": "Official Fact Check",
                        "original_url": url,
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

        verdict = evaluate_url_claim_with_tavily(extracted_text, context)
        print(f"AI verdict: {verdict}")

        return Response(
            {
                "status": verdict.get("verdict"),
                "explanation": verdict.get("summary"),
                "confidence": verdict.get("confidence_score"),
                "source_type": "Live Web Search",
                "original_url": url,
            }
        )

    except Exception as e:
        print(f"Groq error: {str(e)}")
        return Response({"error": f"AI analysis failed: {str(e)}"}, status=500)
