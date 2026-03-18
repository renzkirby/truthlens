from celery import shared_task
from tavily import TavilyClient
import os
import requests

from .ocr_service import extract_text_from_image
from .services import (
    process_image,
    clean_ocr_text,
    clean_extracted_text,
    extract_search_query,
    is_fact_check_relevant,
    evaluate_image_claim_with_gfc,
    evaluate_image_claim_with_tavily,
    evaluate_url_claim_with_gfc,
    evaluate_url_claim_with_tavily,
)
from .models import Claim


# IMAGE PIPELINE
@shared_task
def snippet_fact_check_process(image_hash, base64_string, claim_id):
    _, image_bytes = process_image(base64_string)
    ocr_result = extract_text_from_image(image_bytes)

    if not ocr_result:
        Claim.objects.filter(id=claim_id).delete()
        return

    cleaned = clean_ocr_text(ocr_result)

    if cleaned.get("cleaned_claim") == "OUT_OF_SCOPE":
        Claim.objects.filter(id=claim_id).delete()
        return

    cleaned_claim = cleaned.get("cleaned_claim")
    search_query = cleaned.get("search_query")

    # Try GFC first — return early if relevant result found
    try:
        gfc_response = requests.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={
                "query": search_query,
                "key": os.environ.get("FACT_CHECK_API_KEY"),
            },
        )
        gfc_data = gfc_response.json()
        gfc_claims = gfc_data.get("claims", [])

        if gfc_claims:
            first_claim_text = gfc_claims[0].get("text", "")
            if is_fact_check_relevant(cleaned_claim, first_claim_text):
                ai_verdict = evaluate_image_claim_with_gfc(cleaned_claim, gfc_data)
                source_url = (
                    gfc_claims[0]
                    .get("claimReview", [{}])[0]
                    .get("url", "")
                )
                _save_claim(claim_id, ai_verdict, "Official Fact Check", cleaned_claim, source_url)
                return

    except Exception as e:
        print(f"GFC error: {str(e)}")

    # Fallback — Tavily web search
    try:
        tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
        tavily_response = tavily_client.search(
            query=search_query,
            search_depth="advanced",
            topic="news",
            days=3,
            include_answer=False,
        )
        tavily_results = tavily_response.get("results", [])
        ai_verdict = evaluate_image_claim_with_tavily(cleaned_claim, tavily_results)
        source_url = tavily_results[0].get("url", "") if tavily_results else ""
        _save_claim(claim_id, ai_verdict, "Live Web Search", cleaned_claim, source_url)

    except Exception as e:
        print(f"Tavily error: {str(e)}")
        _save_claim(claim_id, {
            "verdict": "UNVERIFIED",
            "summary": "Could not retrieve relevant information to verify the claim.",
            "confidence_score": 0,
        }, "Live Web Search", cleaned_claim, "")


# URL PIPELINE
@shared_task
def url_fact_check_process(url, claim_id):
    # Step 1 — Extract and clean text from URL
    try:
        response = requests.post(
            "https://api.tavily.com/extract",
            headers={"Authorization": f"Bearer {os.environ.get('TAVILY_API_KEY')}"},
            json={"urls": [url]},
        )
        tavily_data = response.json()

        if not tavily_data.get("results"):
            Claim.objects.filter(id=claim_id).delete()
            return

        raw_text = tavily_data["results"][0]["raw_content"]
        cleaned_text = clean_extracted_text(raw_text)
        result = extract_search_query(cleaned_text)

        cleaned_claim = result.get("cleaned_claim")
        search_query = result.get("search_query")

    except Exception as e:
        print(f"URL extraction error: {str(e)}")
        Claim.objects.filter(id=claim_id).delete()
        return

    # Step 2 — OUT_OF_SCOPE check
    if not cleaned_claim or cleaned_claim == "OUT_OF_SCOPE":
        Claim.objects.filter(id=claim_id).delete()
        return

    # Step 3 — Try GFC first, return early if relevant
    try:
        gfc_response = requests.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={
                "query": search_query[:200],
                "key": os.environ.get("FACT_CHECK_API_KEY"),
            },
        )
        gfc_data = gfc_response.json()
        gfc_claims = gfc_data.get("claims", [])

        if gfc_claims:
            first_claim_text = gfc_claims[0].get("text", "")
            if is_fact_check_relevant(cleaned_claim, first_claim_text):
                ai_verdict = evaluate_url_claim_with_gfc(cleaned_claim, gfc_data)
                _save_claim(claim_id, ai_verdict, "Official Fact Check", cleaned_text, url)
                return

    except Exception as e:
        print(f"GFC error: {str(e)}")

    # Step 4 — Fallback to Tavily web search
    try:
        tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
        search_response = tavily_client.search(
            query=search_query[:300],
            search_depth="advanced",
            topic="news",
            include_answer=True,
        )
        context = search_response.get("answer", "No additional context found")
        ai_verdict = evaluate_url_claim_with_tavily(cleaned_claim, context)
        _save_claim(claim_id, ai_verdict, "Live Web Search", cleaned_text, url)

    except Exception as e:
        print(f"Tavily search error: {str(e)}")
        _save_claim(claim_id, {
            "verdict": "UNVERIFIED",
            "summary": "Could not retrieve relevant information to verify the claim.",
            "confidence_score": 0,
        }, "Live Web Search", cleaned_text, url)


def _save_claim(claim_id, verdict, source_type, context_text, source_url=""):
    """Save the final verdict back to the Claim record."""
    try:
        claim = Claim.objects.get(id=claim_id)
        claim.verdict = verdict.get("verdict")
        claim.ai_summary = verdict.get("summary")
        claim.consensus_score = verdict.get("confidence_score")
        claim.source_type = source_type
        claim.context_text = context_text
        claim.source_link = source_url or None
        claim.verified_via = Claim.VerificationSource.AI_EXTENSION
        claim.save()
        print(f"Claim {claim_id} saved — verdict: {claim.verdict}")
    except Claim.DoesNotExist:
        print(f"Claim {claim_id} not found — skipping save")
    except Exception as e:
        print(f"Save failed for claim {claim_id}: {str(e)}")
        import traceback
        traceback.print_exc()