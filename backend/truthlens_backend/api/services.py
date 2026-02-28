from groq import Groq
from dotenv import load_dotenv
import os
import json


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
