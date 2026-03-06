from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from io import BytesIO
from PIL import Image
from tavily import TavilyClient
import imagehash
import os
import json
import base64
import easyocr
import requests
from .services import (
    clean_ocr_text,
    evaluate_google_data,
    evaluate_tavily_data,
    is_google_data_relevant,
)
from .ocr_service import extract_text_from_image


# Create your views here.
@csrf_exempt
def receive_snippet(request):
    if request.method == "POST":
        parsed_data = json.loads(request.body)
        base64_string = parsed_data.get("image_data")

        if not base64_string:
            return JsonResponse({"error": "No image data provided"}, status=400)

        if "," in base64_string:
            base64_string = base64_string.split(",")[1]

        # Decode the base64 string and save it as an image
        image_bytes = base64.b64decode(base64_string)
        pil_img = Image.open(BytesIO(image_bytes))
        image_hash = str(imagehash.phash(pil_img))
        print("IMAGE HASH:", image_hash)

        # Perform OCR using EasyOCR
        ocr_result = extract_text_from_image(image_bytes)

        if not ocr_result:
            return JsonResponse({"error": "No text detected in the image"}, status=400)

        extracted_text = " ".join(ocr_result)

        # Clean the extracted text using Groq to get a concise search query
        cleaned_text = clean_ocr_text(extracted_text).strip()

        if cleaned_text == "OUT_OF_SCOPE":
            return JsonResponse(
                {
                    "message": "Image processed successfully!",
                    "extracted_text": extracted_text,
                    "cleaned_text": cleaned_text,
                    "result": {
                        "verdict": "OUT_OF_SCOPE",
                        "summary": "The content of the image is not a claim that can be fact-checked.",
                        "confidence_score": 100,
                    },
                    "source_type": "N/A",
                },
                status=200,
            )

        # Use the cleaned text to query Google's Fact Check Tools API
        try:
            api_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
            payload = {
                "query": cleaned_text,
                "key": os.environ.get("FACT_CHECK_API_KEY"),
            }

            response = requests.get(api_url, params=payload)
            fact_check_data = response.json()

            print("GOOGLE'S RESPONSE:", fact_check_data)
        except Exception as e:
            print("Error calling Google's Fact Check Tools API:", str(e))
            fact_check_data = {}

        # Check if the API returned any claims and prepare the context data accordingly
        if fact_check_data.get("claims"):
            first_claim_text = fact_check_data["claims"][0].get("text", "")

            if is_google_data_relevant(extracted_text, first_claim_text):
                ai_verdict = evaluate_google_data(extracted_text, fact_check_data)
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
                ai_verdict = evaluate_tavily_data(extracted_text, tavily_results)

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

        return JsonResponse(
            {
                "message": "Image saved successfully!",
                "extracted_text": extracted_text,
                "cleaned_text": cleaned_text,
                "result": context_data,
                "source_type": source_type,
            },
            status=200,
        )
