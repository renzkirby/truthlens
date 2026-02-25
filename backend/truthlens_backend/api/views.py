from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from io import BytesIO
from PIL import Image
import os
import json
import base64
import easyocr
import cv2
import requests
from dotenv import load_dotenv
from tavily import TavilyClient
from google import genai


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

        bytes_decoded = base64.b64decode(base64_string)
        img = Image.open(BytesIO(bytes_decoded))
        out_jpg = img.convert("RGB")
        os.makedirs("./api/img/", exist_ok=True)
        out_jpg.save("./api/img/snippet.jpg")

        image_file = "./api/img/snippet.jpg"

        # ACCURACY PROBLEM WITH OPENCV
        # image_cv = cv2.imread(image_file)

        # # converts image's color to gray
        # gray_image = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)

        # # reduce image noise
        # thresh_img = cv2.adaptiveThreshold(
        #     gray_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        # )

        # cv2.imwrite("./api/img/processed_snippet.jpg", thresh_img)

        reader = easyocr.Reader(["en", "tl"])
        result = reader.readtext(image_file)

        if not result:
            return JsonResponse({"error": "No text detected in the image"}, status=400)

        extracted_text = " ".join([item[1] for item in result])

        cleaned_text = clean_ocr_text(extracted_text)

        api_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
        payload = {
            "query": cleaned_text,
            "key": os.environ.get("GOOGLE_API_KEY"),
        }

        response = requests.get(api_url, params=payload)
        fact_check_data = response.json()

        if fact_check_data.get("claims"):
            context_data = fact_check_data.get("claims")
            source_type = "Official Fact Check"
        else:
            tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
            tavily_response = tavily_client.search(
                query=cleaned_text,
                search_depth="advanced",
                include_answer=True,
            )

            context_data = {
                "summary": tavily_response.get("answer"),
                "sources": tavily_response.get("results"),
            }
            source_type = "Live Web Search"

        return JsonResponse(
            {
                "message": "Image saved successfully!",
                "extracted_text": extracted_text,
                "result": context_data,
                "source_type": source_type,
            },
            status=200,
        )


def clean_ocr_text(raw_text):
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"You are a precise data extraction tool for a fact-checking pipeline. Your only job is to analyze messy OCR text, translate any local slang or Taglish to English, and extract the single most verifiable core claim. Extract a search query of exactly 6 words or less from this text. Output NOTHING else. No punctuation, no conversational filler. Text: {raw_text}",
    )

    return response.text
