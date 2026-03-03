from urllib import response
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
from tavily import TavilyClient
from google import genai
import imagehash
import os
import json
import base64
import easyocr
import cv2
import requests
from .services import (
    clean_ocr_text,
    evaluate_google_data,
    evaluate_tavily_data,
    is_google_data_relevant,
)


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
        bytes_decoded = base64.b64decode(base64_string)
        img = Image.open(BytesIO(bytes_decoded))
        out_jpg = img.convert("RGB")
        os.makedirs("./api/img/", exist_ok=True)
        out_jpg.save("./api/img/snippet.jpg")

        image_file = "./api/img/snippet.jpg"

        image = Image.open(image_file)
        image_hash = str(imagehash.phash(image))

        print("IMAGE HASH:", image_hash)

        # Perform OCR using EasyOCR
        reader = easyocr.Reader(["en", "tl"])
        result = reader.readtext(image_file)

        if not result:
            return JsonResponse({"error": "No text detected in the image"}, status=400)

        extracted_text = " ".join([item[1] for item in result])

        # Clean the extracted text using Gemini-2.5-Flash to get a concise search query
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
        api_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
        payload = {
            "query": cleaned_text,
            "key": os.environ.get("FACT_CHECK_API_KEY"),
        }

        response = requests.get(api_url, params=payload)
        fact_check_data = response.json()

        print("GOOGLE'S RESPONSE:", fact_check_data)

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
