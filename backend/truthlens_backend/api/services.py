from groq import Groq
from dotenv import load_dotenv
import os
import json
import imagehash
import base64
from io import BytesIO
from PIL import Image


# Clean the OCR text to extract a concise search query or determine if it's out of scope
def clean_ocr_text(raw_text):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """
                Role: You are a precise data extraction tool for a fact-checking pipeline. 
                Task: Your only job is to analyze messy OCR text, if the text contains factual, verifiable claim, translate any local slang or Taglish to English, and extract the single most verifiable core claim. Extract a search query of exactly 10 words or less from this text. If the text is purely subjective, an opinion, a question, or does not contain any factual claim that can be verified, respond with the exact phrase "OUT_OF_SCOPE". 
                
                Output Constraints:
                Do not output anything other than the clean claim or "OUT_OF_SCOPE". Do not provide any explanation or additional text. Output NOTHING else. No punctuation, no conversational filler.""",
            },
            {
                "role": "user",
                "content": f"Text: {raw_text}",
            },
        ],
    )

    return response.choices[0].message.content


# Evaluate Tavily data against the original claim using Groq
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
    
    UNVERIFIED: The evidence is completely unrelated to the entities/events in the claim, OR the evidence discusses the topic but lacks sufficient concrete data to definitively prove or debunk the claim. Summary requirement: State that current news sources do not contain enough verified information regarding this specific claim.

    FACT: The evidence directly, explicitly, and substantially confirms the core factual elements of the claim.

    FAKE: The evidence directly contradicts, debunks, or proves the core elements of the claim to be demonstrably false or altered.

    Output Constraints:
    Output ONLY a raw, valid JSON object. Absolutely NO markdown formatting (do not use ```json), NO conversational filler, and NO preambles.
    You must calculate a confidence score. Do not output a score of 100 unless the evidence is indisputable. The summary must strictly follow the requirements outlined in the criteria above for each tier. DO NOT mention the presence or absence of evidence in the summary unless it is required by the criteria. For example, if the claim is classified as FACT or FAKE, do not mention the sufficiency of evidence in the summary. If the claim is classified as UNVERIFIED, do not mention any confirming or contradicting evidence in the summary. The summary should be concise and directly address the claim's classification based on the evidence.

    JSON Schema:
    {
    "reasoning": "Draft a 1-sentence internal logical deduction comparing the claim to the evidence. Do this BEFORE deciding the verdict.",
    "verdict": "MUST be exactly one of: [FACT, FAKE, UNVERIFIED, SATIRE]",
    "summary": "A strict 1-2 sentence user-facing explanation following the rules above.",
    "confidence_score": "An integer from 1 to 100 representing your certainty in the chosen verdict based on the quality of the evidence."
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
            "verdict": "UNVERIFIED",
            "summary": "Could not definitively verify the claim from the live news.",
            "confidence_score": 0,
        }


# Evaluate the relevance of Google's Fact Check Tools data against the original claim using Groq
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


# Evaluate Google's Fact Check Tools data against the original claim using Groq
def evaluate_google_data(original_claim, google_fact_check_data):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    fact_check_text = google_fact_check_data.get("claims", [{}])[0].get("text", "")

    system_instructions = """
    Role: Act as the core fact-checking algorithmic engine for a misinformation filtering platform.
    Task: Analyze the provided social media claim against the retrieved official fact check data and classify it strictly into one of three predefined tiers.

    Evaluation Criteria (Follow this strict hierarchy):

    FACT: The official fact check directly, explicitly, and substantially confirms the core factual elements of the claim.

    FAKE: The official fact check directly contradicts, debunks, or proves the core elements of the claim to be demonstrably false or altered.

    UNVERIFIED: The official fact check discusses the topic but lacks sufficient concrete data to definitively prove or debunk the claim.

    Output Constraints:
    Output ONLY a raw, valid JSON object. Absolutely NO markdown formatting (do not use ```json), NO conversational filler, and NO preambles.
    You must calculate a confidence score. Do not output a score of 100 unless the evidence is indisputable.

    JSON Schema:
    {
    "reasoning": "Draft a 1-sentence internal logical deduction comparing the claim to the official fact check data. Do this BEFORE deciding the verdict.",
    "verdict": "MUST be exactly one of: [FACT, FAKE, UNVERIFIED]",
    "summary": "A strict 1-2 sentence user-facing explanation following the rules above.",
    "confidence_score": "An integer from 1 to 100 representing your certainty in the chosen verdict based on the quality of the evidence."
    }
    """

    user_data = f"""
    Inputs to Analyze:
    
    Claim: "{original_claim}"
    
    Official Fact Check Data: 
    "{fact_check_text}"
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

        print("GOOGLE EVALUATION JSON OUTPUT:", clean_json_string)
        return json.loads(clean_json_string)
    except json.JSONDecodeError:
        return {
            "verdict": "UNVERIFIED",
            "summary": "Could not definitively verify the claim from the official fact check data.",
            "confidence_score": 0,
        }


def process_image(raw_base64):
    image_bytes = base64.b64decode(raw_base64)
    pil_img = Image.open(BytesIO(image_bytes))
    image_hash = str(imagehash.phash(pil_img))

    return image_hash, image_bytes
