from groq import Groq
import os
import json
import re
import imagehash
import base64
from io import BytesIO
from PIL import Image

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


def _parse_groq_json(raw_content):
    """Strip markdown formatting and parse JSON from Groq responses."""
    cleaned = raw_content.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


# ──────────────────────────────────────────────
# IMAGE PIPELINE
# ──────────────────────────────────────────────

def clean_ocr_text(raw_text):
    """Extract a verifiable core claim and search query from raw OCR text."""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: You are a precise data extraction tool for a fact-checking pipeline.
                Task: Analyze messy OCR text. If it contains a factual, verifiable claim,
                translate any local slang or Taglish to English and extract the single most
                verifiable core claim as a search query of 10 words or less. Also clean the
                OCR text into something readable. If the text is purely subjective, an opinion,
                a question, or unverifiable, respond with OUT_OF_SCOPE for both fields.

                Output ONLY a raw JSON object with no explanation or filler.

                JSON Schema:
                {
                    "cleaned_claim": "Cleaned, readable version of the core claim in English.",
                    "search_query": "Concise search query derived from the cleaned claim."
                }
                If out of scope:
                {
                    "cleaned_claim": "OUT_OF_SCOPE",
                    "search_query": "OUT_OF_SCOPE"
                }
                """,
            },
            {
                "role": "user",
                "content": f"Text: {raw_text}",
            },
        ],
    )

    raw_response = response.choices[0].message.content
    print("clean_ocr_text OUTPUT:", raw_response)
    return _parse_groq_json(raw_response)


def is_fact_check_relevant(original_text, fact_check_text):
    """Check if a fact check result is relevant to the original claim or article."""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a relevance checker for a fact-checking pipeline. "
                    "Compare the two texts and determine if the fact check result is "
                    "directly relevant to verifying the claim. "
                    "Output ONLY 'Relevant' or 'Not Relevant'. No explanation."
                ),
            },
            {
                "role": "user",
                "content": f'Claim: "{original_text}"\n\nFact Check: "{fact_check_text}"',
            },
        ],
    )

    result = response.choices[0].message.content.strip().upper()
    print("is_fact_check_relevant RESPONSE:", result)
    return "NOT RELEVANT" not in result


def evaluate_image_claim_with_gfc(original_claim, gfc_data):
    """Evaluate an image claim against Google Fact Check data."""
    fact_check_text = gfc_data.get("claims", [{}])[0].get("text", "")

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: Act as the core fact-checking engine for a misinformation filtering platform.
                Task: Analyze the social media claim against official fact check data.

                Evaluation Criteria:
                FACT: The fact check directly confirms the core factual elements of the claim.
                FAKE: The fact check directly contradicts or debunks the claim.
                UNVERIFIED: The fact check lacks sufficient data to decide.

                Output ONLY a raw valid JSON object. No markdown. No backticks.

                JSON Schema:
                {
                    "reasoning": "1-sentence deduction comparing the claim to the fact check.",
                    "verdict": "MUST be exactly one of: [FACT, FAKE, UNVERIFIED]",
                    "summary": "1-2 sentence user-facing explanation.",
                    "confidence_score": "Integer from 1 to 100."
                }
                """,
            },
            {
                "role": "user",
                "content": f'Claim: "{original_claim}"\n\nFact Check Data: "{fact_check_text}"',
            },
        ],
    )

    try:
        print("evaluate_image_claim_with_gfc OUTPUT:", response.choices[0].message.content)
        return _parse_groq_json(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {
            "verdict": "UNVERIFIED",
            "summary": "Could not definitively verify the claim from the official fact check data.",
            "confidence_score": 0,
        }


def evaluate_image_claim_with_tavily(original_claim, tavily_results):
    """Evaluate an image claim against Tavily live news results."""
    evidence_text = ""
    for i, result in enumerate(tavily_results[:3]):
        evidence_text += f"Source {i+1} ({result.get('url')}): {result.get('content')}\n\n"

    print("EVIDENCE TEXT:", evidence_text)

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: Act as the core fact-checking engine for a misinformation filtering platform.
                Task: Analyze the social media claim against retrieved live news evidence.

                Evaluation Criteria (strict hierarchy):
                SATIRE: Claim contains satire markers OR evidence confirms a satirical source.
                UNVERIFIED: Evidence is unrelated OR lacks sufficient data to decide.
                FACT: Evidence directly and substantially confirms the claim.
                FAKE: Evidence directly contradicts or debunks the claim.

                Summary rules: For UNVERIFIED, state that current sources lack enough verified
                information. For FACT/FAKE, do not mention evidence sufficiency.

                Output ONLY a raw valid JSON object. No markdown. No backticks.

                JSON Schema:
                {
                    "reasoning": "1-sentence deduction comparing the claim to the evidence.",
                    "verdict": "MUST be exactly one of: [FACT, FAKE, UNVERIFIED, SATIRE]",
                    "summary": "1-2 sentence user-facing explanation.",
                    "confidence_score": "Integer from 1 to 100. Not 100 unless indisputable."
                }
                """,
            },
            {
                "role": "user",
                "content": f'Claim: "{original_claim}"\n\nEvidence: "{evidence_text}"',
            },
        ],
    )

    try:
        print("evaluate_image_claim_with_tavily OUTPUT:", response.choices[0].message.content)
        return _parse_groq_json(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {
            "verdict": "UNVERIFIED",
            "summary": "Could not definitively verify the claim from the live news.",
            "confidence_score": 0,
        }


# ──────────────────────────────────────────────
# URL PIPELINE
# ──────────────────────────────────────────────

def clean_extracted_text(text):
    """Strip markdown, links, and short lines from URL-extracted text."""
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"http\S+", "", text)
    lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 40]
    return "\n".join(lines)[:3000]


def evaluate_url_claim_with_gfc(extracted_text, gfc_data):
    """Evaluate a URL article claim against Google Fact Check data."""
    gfc_claim_text = gfc_data.get("claims", [{}])[0].get("text", "")
    gfc_rating = (
        gfc_data.get("claims", [{}])[0]
        .get("claimReview", [{}])[0]
        .get("textualRating", "")
    )

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: Act as the core fact-checking engine for a misinformation filtering platform.
                Task: Analyze the article against the official fact check data and classify it.

                Evaluation Criteria:
                SATIRE: Claim contains satire markers OR evidence confirms a satirical source.
                FACT: The fact check directly confirms the claim OR source is a known reliable outlet.
                FAKE: The fact check directly contradicts or debunks the claim.
                UNVERIFIED: The fact check lacks sufficient data to decide.

                Output ONLY a raw valid JSON object. No markdown. No backticks.

                JSON Schema:
                {
                    "reasoning": "1-sentence deduction comparing the article to the fact check.",
                    "verdict": "MUST be exactly one of: [FACT, FAKE, UNVERIFIED, SATIRE]",
                    "summary": "TWO PARTS: Part 1 - what the article is about. Part 2 - why this verdict. 2 sentences max.",
                    "confidence_score": "Integer from 1 to 100."
                }
                """,
            },
            {
                "role": "user",
                "content": (
                    f'Article: "{extracted_text[:500]}"\n\n'
                    f'Official Fact Check: "{gfc_claim_text}"\n'
                    f'Official Rating: "{gfc_rating}"'
                ),
            },
        ],
    )

    try:
        return _parse_groq_json(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {
            "verdict": "UNVERIFIED",
            "summary": "Could not analyze the official fact check data.",
            "confidence_score": 0,
        }


def evaluate_url_claim_with_tavily(extracted_text, context):
    """Evaluate a URL article claim against Tavily web search context."""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: Act as the core fact-checking engine for a misinformation filtering platform.
                Task: Analyze the article claim against live news evidence.

                Evaluation Criteria (strict hierarchy):
                SATIRE: Claim contains satire markers OR evidence confirms a satirical source.
                UNVERIFIED: Evidence is unrelated OR lacks sufficient data to decide.
                FACT: Evidence directly confirms the claim OR source is a known reliable outlet.
                FAKE: Evidence directly contradicts or debunks the claim.

                Output ONLY a raw valid JSON object. No markdown. No backticks.
                Do not output a confidence score of 100 unless the evidence is indisputable.

                JSON Schema:
                {
                    "reasoning": "1-sentence deduction comparing the claim to the evidence.",
                    "verdict": "MUST be exactly one of: [FACT, FAKE, UNVERIFIED, SATIRE]",
                    "summary": "TWO PARTS: Part 1 - what the article is about. Part 2 - reason for verdict. 2 sentences max.",
                    "confidence_score": "Integer from 1 to 100."
                }
                """,
            },
            {
                "role": "user",
                "content": (
                    f'Article Claim: "{extracted_text[:500]}"\n\n'
                    f'Evidence from Live News: "{context}"'
                ),
            },
        ],
    )

    try:
        return _parse_groq_json(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {
            "verdict": "UNVERIFIED",
            "summary": "Could not analyze the evidence from the web search.",
            "confidence_score": 0,
        }


# ──────────────────────────────────────────────
# SHARED UTILITIES
# ──────────────────────────────────────────────

def process_image(raw_base64):
    """Decode a base64 image and compute its perceptual hash."""
    image_bytes = base64.b64decode(raw_base64)
    pil_img = Image.open(BytesIO(image_bytes))
    image_hash = str(imagehash.phash(pil_img))
    return image_hash, image_bytes