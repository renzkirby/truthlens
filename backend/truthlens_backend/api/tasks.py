from celery import shared_task
from .ocr_service import extract_text_from_image
from .services import (
    clean_ocr_text,
    evaluate_google_data,
    evaluate_tavily_data,
    is_google_data_relevant,
    process_image,
)
from tavily import TavilyClient
import os
import requests


@shared_task
def snippet_fact_check_process(image_hash, base64_string, claim_id):
    # Decode the base64 string and convert it to bytes
    _, image_bytes = process_image(base64_string)
    ocr_result = extract_text_from_image(image_bytes)

    if not ocr_result:
        return {"error": "No text detected in the image"}

    cleaned_text = clean_ocr_text(ocr_result).strip()

    if cleaned_text == "OUT_OF_SCOPE":
        return {
            "message": "Image processed successfully!",
            "extracted_text": ocr_result,
            "cleaned_text": cleaned_text,
            "result": {
                "verdict": "OUT_OF_SCOPE",
                "summary": "The content of the image is not a claim that can be fact-checked.",
                "confidence_score": 100,
            },
            "source_type": "N/A",
        }

    # Try with Google's Fact Check Tools API first
    try:
        api_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
        payload = {
            "query": cleaned_text,
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

        if is_google_data_relevant(ocr_result, first_claim_text):
            ai_verdict = evaluate_google_data(ocr_result, fact_check_data)
            context_data = {
                "summary": ai_verdict.get("summary"),
                "verdict": ai_verdict.get("verdict"),
                "confidence_score": ai_verdict.get("confidence_score"),
                "sources": fact_check_data.get("claims", []),
            }
            source_type = "Official Fact Check"
        else:
            fact_check_data = {}

    if not fact_check_data.get("claims"):
        try:
            tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
            tavily_response = tavily_client.search(
                query=cleaned_text,
                search_depth="advanced",
                topic="news",
                days=3,
                include_answer=False,
            )

            tavily_results = tavily_response.get("results", [])
            ai_verdict = evaluate_tavily_data(ocr_result, tavily_results)

            print(ai_verdict)

            context_data = {
                "summary": ai_verdict.get("summary"),
                "verdict": ai_verdict.get("verdict"),
                "confidence_score": ai_verdict.get("confidence_score"),
                "sources": tavily_results,
            }
            source_type = "Live Web Search"
        except Exception as e:
            print("Error calling Tavily API:", str(e))
            context_data = {
                "summary": "Could not retrieve relevant information from the web to verify the claim.",
                "verdict": "UNVERIFIED",
                "confidence_score": 0,
            }
            source_type = "Live Web Search"


# TO DO: Save the fact-checking results and context data to the database associated with the claim_id for later retrieval when users view the claim details.
