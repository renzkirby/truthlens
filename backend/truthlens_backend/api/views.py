from urllib import response

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
from groq import Groq


# Create your views here.
# Views Functions
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

        # Perform OCR using EasyOCR
        reader = easyocr.Reader(["en", "tl"])
        result = reader.readtext(image_file)

        if not result:
            return JsonResponse({"error": "No text detected in the image"}, status=400)

        extracted_text = " ".join([item[1] for item in result])

        # Clean the extracted text using Gemini-2.5-Flash to get a concise search query
        cleaned_text = clean_ocr_text(extracted_text).strip()

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
                context_data = fact_check_data.get("claims")
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


# Helper Functions
def clean_ocr_text(raw_text):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are a precise data extraction tool for a fact-checking pipeline. Your only job is to analyze messy OCR text, translate any local slang or Taglish to English, and extract the single most verifiable core claim. Extract a search query of exactly 10 words or less from this text. Output NOTHING else. No punctuation, no conversational filler.",
            },
            {
                "role": "user",
                "content": f"Text: {raw_text}",
            },
        ],
    )

    return response.choices[0].message.content


def evaluate_tavily_data(original_claim, tavily_data):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    evidence_text = ""
    for i, result in enumerate(tavily_data[:3]):
        evidence_text += (
            f"Source {i+1} ({result.get('url')}): {result.get('content')}\n\n"
        )

    print("EVIDENCE TEXT:", evidence_text)

    system_instructions = """
    Role: Act as the core fact-checking algorithmic engine for a misinformation filtering platform.
    Task: Analyze the provided social media claim against the retrieved live news evidence and classify it strictly into one of five predefined tiers.

    Evaluation Criteria (Follow this strict hierarchy):

    SATIRE: The claim explicitly contains markers like "satire" or "joke", OR the evidence confirms the source is a known satirical entity (e.g., The Onion). Summary requirement: State that the post originates from or is self-declared as satire.

    OUT_OF_SCOPE: The claim is a purely subjective opinion, a personal question, or lacks any falsifiable facts. Summary requirement: State that the content is an opinion or non-factual statement that cannot be fact-checked.

    UNVERIFIED: The evidence is completely unrelated to the entities/events in the claim, OR the evidence discusses the topic but lacks sufficient concrete data to definitively prove or debunk the claim. Summary requirement: State that current news sources do not contain enough verified information regarding this specific claim.

    FACT: The evidence directly, explicitly, and substantially confirms the core factual elements of the claim.

    FAKE: The evidence directly contradicts, debunks, or proves the core elements of the claim to be demonstrably false or altered.

    Output Constraints:
    Output ONLY a raw, valid JSON object. Absolutely NO markdown formatting (do not use ```json), NO conversational filler, and NO preambles.

    JSON Schema:
    {
    "reasoning": "Draft a 1-sentence internal logical deduction comparing the claim to the evidence. Do this BEFORE deciding the verdict.",
    "verdict": "MUST be exactly one of: [FACT, FAKE, UNVERIFIED, SATIRE, OUT_OF_SCOPE]",
    "summary": "A strict 1-2 sentence user-facing explanation following the rules above."
    }
    """

    user_data = f"""
    Inputs to Analyze:
    
    Claim: "{original_claim}"
    
    Evidence from Live News: 
    "{evidence_text}"
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": system_instructions,
            },
            {
                "role": "user",
                "content": user_data,
            },
        ],
    )

    try:
        raw_content = response.choices[0].message.content

        clean_json_string = (
            raw_content.strip().replace("```json", "").replace("```", "").strip()
        )

        print("JSON OUTPUT:", clean_json_string)

        return json.loads(clean_json_string)
    except json.JSONDecodeError:
        return {
            "verdict": "Unverified",
            "summary": "Could not definitively verify the claim from the live news.",
        }


def is_google_data_relevant(original_text, google_fact_check_text):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are an expert fact-checking journalist. Analyze this social media claim against the provided official fact check data. Determine if the fact check data is directly relevant and applicable for verifying the claim. Output ONLY 'Relevant' or 'Not Relevant'. Do not provide any explanation or additional text.",
            },
            {
                "role": "user",
                "content": f'Text 1 (From Claim): "{original_text}"\n Text 2 (From Fact Check Database): "{google_fact_check_text}"',
            },
        ],
    )

    print("RELEVANCE CHECK RESPONSE:", response.choices[0].message.content)
    clean_response = response.choices[0].message.content.strip().upper()

    if "NOT RELEVANT" in clean_response:
        return False
    return True
