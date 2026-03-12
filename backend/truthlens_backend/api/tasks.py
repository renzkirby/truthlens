from celery import shared_task
from .ocr_service import extract_text_from_image
from .services import *
from tavily import TavilyClient
from .models import Claim
import os
import requests


@shared_task
def snippet_fact_check_process(image_hash, base64_string, claim_id):
    # Decode the base64 string and convert it to bytes
    _, image_bytes = process_image(base64_string)
    ocr_result = extract_text_from_image(image_bytes)

    if not ocr_result:
        return {"error": "No text detected in the image"}

    cleaned_text = clean_ocr_text(ocr_result)

    if cleaned_text.get("cleaned_claim") == "OUT_OF_SCOPE":
        context_data = {
            "verdict": "OUT_OF_SCOPE",
            "summary": "The content of the image is not a claim that can be fact-checked.",
            "confidence_score": 100,
            "source_type": "N/A",
        }

    else:

        # Try with Google's Fact Check Tools API first
        try:
            api_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
            payload = {
                "query": cleaned_text.get("search_query"),
                "key": os.environ.get("FACT_CHECK_API_KEY"),
            }

            response = requests.get(api_url, params=payload)
            fact_check_data = response.json()

            print("Google's Response:", fact_check_data)
        except Exception as e:
            print("Error calling Google's Fact Check Tools API:", str(e))
            fact_check_data = {}

        if fact_check_data.get("claims"):
            first_claim_text = fact_check_data["claims"][0].get("text", "")

            if is_fact_check_relevant(
                cleaned_text.get("cleaned_claim"), first_claim_text
            ):
                ai_verdict = evaluate_image_claim_with_gfc(
                    cleaned_text.get("cleaned_claim"), fact_check_data
                )
                context_data = {
                    "summary": ai_verdict.get("summary"),
                    "verdict": ai_verdict.get("verdict"),
                    "confidence_score": ai_verdict.get("confidence_score"),
                    "source": fact_check_data.get("claims", [])
                    .get("claimReview", [{}])[0]
                    .get("url", "No source URL"),
                }
                source_type = "Official Fact Check"
            else:
                fact_check_data = {}

        # If Google's Fact Check Tools API doesn't return relevant results, try Tavily
        if not fact_check_data.get("claims"):
            try:
                tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
                tavily_response = tavily_client.search(
                    query=cleaned_text.get("search_query"),
                    search_depth="advanced",
                    topic="news",
                    days=3,
                    include_answer=False,
                )

                tavily_results = tavily_response.get("results", [])
                ai_verdict = evaluate_image_claim_with_tavily(
                    cleaned_text.get("cleaned_claim"), tavily_results
                )

                print(ai_verdict)

                context_data = {
                    "summary": ai_verdict.get("summary"),
                    "verdict": ai_verdict.get("verdict"),
                    "confidence_score": ai_verdict.get("confidence_score"),
                    "source": (
                        tavily_results[0].get("url")
                        if tavily_results
                        else "No source found"
                    ),
                }
                source_type = "Live Web Search"
            except Exception as e:
                print("Error calling Tavily API:", str(e))
                context_data = {
                    "summary": "Could not retrieve relevant information from the web to verify the claim.",
                    "verdict": "UNVERIFIED",
                    "confidence_score": 0,
                    "source": "N/A"
                }
                source_type = "Live Web Search"

    claim = Claim.objects.get(id=claim_id)
    claim.verdict = context_data.get("verdict")
    claim.ai_summary = context_data.get("summary")
    claim.consensus_score = context_data.get("confidence_score")
    claim.verified_via = Claim.VerificationSource.AI_EXTENSION
    claim.source_type = source_type
    claim.context_text = cleaned_text.get("cleaned_claim")
    claim.source_link = context_data.get("source")

    claim.save()
