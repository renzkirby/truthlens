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


# IMAGE PIPELINE
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

                Task: Your job is to analyze messy, raw OCR text, reconstruct the meaning, and extract the core claim by strictly following these steps:
                1. RECONSTRUCTION: Mentally clean and piece together the fragmented OCR text to identify its CENTRAL NARRATIVE.
                2. Extract the primary verifiable claim that directly drives this central narrative. Translate any local slang or Taglish to English.
                3. NEGATIVE CONSTRAINT: You MUST completely ignore background context, biographical trivia, or secondary historical facts (e.g., ages, family ties), regardless of how verifiable they are.
                4. Generate a concise search query of exactly 10 words or less based ONLY on the primary claim.
                5. If the central narrative is purely subjective, a personal lifestyle update, a meme/joke, an opinion, a question, or lacks a hard factual claim to verify, respond with the exact phrase "OUT_OF_SCOPE".

                Output Constraints:
                Do not output anything other than the JSON object. Do not provide any explanation or conversational filler. If the text is out of scope, both fields should be "OUT_OF_SCOPE".

                JSON Schema:
                {
                    "cleaned_claim": "A readable, grammatically clean version of the core claim central to the main narrative.",
                    "search_query": "A concise search query derived from the cleaned claim."
                }
                """
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

# Evaluate Google's Fact Check Tools data against the original claim using Groq
def evaluate_image_claim_with_gfc(original_claim, google_fact_check_data):

    fact_check_text = google_fact_check_data.get("claims", [{}])[0].get("text", "")

    system_instructions = """
        Role: You are the TruthLens Core Logic Engine, an expert automated fact-checking AI, forensic linguist, and misinformation analyst. 
        Task: Your sole function is to evaluate a specific social media claim strictly against a provided dossier of evidence, and output a structured JSON analysis.

        CRITICAL DIRECTIVES & HALLUCINATION PREVENTION:
        1. STRICT EVIDENCE BINDING: You are a forensic reading comprehension engine, NOT an omniscient knowledge base. You must evaluate the claim EXCLUSIVELY based on the facts explicitly provided in the evidence block.
        2. NO PRE-TRAINED KNOWLEDGE: Do not use your internal weights, historical knowledge, or external facts to verify or debunk the claim. If the evidence does not contain the specific information needed to definitively judge the claim, you MUST classify it as UNVERIFIED.
        3. ANTI-ECHO CHAMBER RULE: Ignore the confidence, emotional tone, or viral popularity of the claim. Judge only the objective factual alignment between the claim's core assertions and the provided evidence.

        CLASSIFICATION TIERS & EVALUATION LOGIC:
        You must map your evaluation to EXACTLY ONE of the following 4 tiers. Pay close attention to the epistemological rules regarding "Missing Context" and "Satire".

        1. FACT: The core subjects, actions, statistical figures, and temporal context of the claim are completely supported by the evidence. Minor semantic variations that do not alter the fundamental truth are acceptable.

        2. FAKE: The claim is explicitly contradicted by the evidence. 
        - THE "MISSING CONTEXT" RULE: If the evidence states the claim uses genuine media (real photos/videos/quotes) but places them in a false context (e.g., wrong date, wrong location, unrelated event), the claim is FAKE. The intent is to deceive via recontextualization.
        - THE "MISLEADING" RULE: If true statistics or facts are cherry-picked to construct a mathematically or logically false narrative, it maps to FAKE.

        3. SATIRE: The claim is a joke, parody, or humorous critique.
        - DETECTION PROTOCOL: Look beyond explicit labels. Satire is present if the text exhibits extreme hyperbole, semantic dissonance (mixing formal institutional language with sheer absurdity), or echoic mention (mocking repetition). Be highly alert for "dry sarcasm," exaggerated "pavictim" (playing victim) narratives, or claims originating from known parody sources. If a claim is so absurd that it breaches the threshold of reality without malicious deception, it is SATIRE.

        4. UNVERIFIED: The provided evidence is irrelevant, inconclusive, or completely absent. Or, the claim is a subjective opinion, political prediction, or emotional expression that cannot be objectively proven true or false. 
        - AUTHORIZED ABSTENTION: If you do not know the answer based strictly on the evidence, you must choose UNVERIFIED.

        PHILIPPINE MISINFORMATION TROPES:
        - "CTTO" (Credit to the Owner): Treat claims containing "CTTO" with extreme skepticism; it is predominantly used to strip original provenance and launder decontextualized media.
        - Clickbait Markers: Phrases like "Look at this," excessive capitalization, or extreme punctuation (!!!) often accompany Missing Context memes. Evaluate the core assertion against the evidence rigorously.

        JSON OUTPUT SCHEMA & ENFORCEMENT:
        You must output ONLY a raw, valid JSON object. 
        DO NOT wrap the JSON in markdown formatting. Do not use the word json and backticks.
        DO NOT include conversational filler, preambles, or explanations outside the JSON object.

        Your JSON must exactly match this structure:
        {
        "reasoning": "Think step-by-step here. 1) Analyze the core assertion of the claim. 2) Summarize the provided evidence. 3) Compare the two for alignment, contradictions, or missing context. 4) Evaluate for satire or absurdity. Do this logical deduction BEFORE stating the verdict.",
        "verdict": "Must be exactly one of: 'FACT', 'FAKE', 'UNVERIFIED', 'SATIRE'",
        "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language. E.g., 'While the photo is real, the evidence shows it was taken in 2018 during a different event, not yesterday.'",
        "confidence_score": 95
        }
        """
    user_data = f"""
    Inputs to Analyze:
    
    Claim: "{original_claim}"
    
    Official Fact Check Data: 
    "{fact_check_text}"
    """
    
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
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


# URL PIPELINE
def clean_extracted_text(text):
    """Strip markdown, links, and short lines from URL-extracted text."""
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"http\S+", "", text)
    lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 40]
    return "\n".join(lines)[:3000]

def extract_search_query(text):
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: You are a precise data extraction tool for a fact-checking pipeline. 

                Task: Your job is to extract the core claim from the text by strictly following these steps:
                1. Identify the CENTRAL NARRATIVE or main subject of the provided text.
                2. Extract the primary verifiable claim that directly drives this central narrative. Translate any local slang or Taglish to English.
                3. NEGATIVE CONSTRAINT: You MUST completely ignore background context, biographical trivia, or secondary historical facts (e.g., family relationships, past careers, ages), regardless of how verifiable they are.
                4. Generate a search query of exactly 10 words or less based ONLY on the primary claim.
                5. If the central narrative is purely subjective, a personal lifestyle update, an opinion, a question, or lacks a hard factual claim to verify, you must respond with the exact phrase "OUT_OF_SCOPE".

                Output Constraints:
                Do not output anything other than the JSON object. Do not provide any explanation or conversational filler. If the text is out of scope, both fields should be "OUT_OF_SCOPE".

                JSON Schema:
                {
                    "cleaned_claim": "A concise, cleaned version of the core claim central to the main narrative.",
                    "search_query": "A concise search query derived from the cleaned claim."
                }
                """
            },
            {
                "role": "user",
                "content": f"Text: {text}",
            },
        ],
    )

    extracted_search_query = response.choices[0].message.content

    print("JSON OUTPUT:", extracted_search_query)

    return json.loads(extracted_search_query)


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
                    Role: You are the TruthLens Core Logic Engine, an expert automated fact-checking AI, forensic linguist, and misinformation analyst. 
                    Task: Your sole function is to evaluate a specific social media claim strictly against a provided dossier of evidence, and output a structured JSON analysis.

                    CRITICAL DIRECTIVES & HALLUCINATION PREVENTION:
                    1. STRICT EVIDENCE BINDING: You are a forensic reading comprehension engine, NOT an omniscient knowledge base. You must evaluate the claim EXCLUSIVELY based on the facts explicitly provided in the evidence block.
                    2. NO PRE-TRAINED KNOWLEDGE: Do not use your internal weights, historical knowledge, or external facts to verify or debunk the claim. If the evidence does not contain the specific information needed to definitively judge the claim, you MUST classify it as UNVERIFIED.
                    3. ANTI-ECHO CHAMBER RULE: Ignore the confidence, emotional tone, or viral popularity of the claim. Judge only the objective factual alignment between the claim's core assertions and the provided evidence.

                    CLASSIFICATION TIERS & EVALUATION LOGIC:
                    You must map your evaluation to EXACTLY ONE of the following 4 tiers. Pay close attention to the epistemological rules regarding "Missing Context" and "Satire".

                    1. FACT: The core subjects, actions, statistical figures, and temporal context of the claim are completely supported by the evidence. Minor semantic variations that do not alter the fundamental truth are acceptable.

                    2. FAKE: The claim is explicitly contradicted by the evidence. 
                    - THE "MISSING CONTEXT" RULE: If the evidence states the claim uses genuine media (real photos/videos/quotes) but places them in a false context (e.g., wrong date, wrong location, unrelated event), the claim is FAKE. The intent is to deceive via recontextualization.
                    - THE "MISLEADING" RULE: If true statistics or facts are cherry-picked to construct a mathematically or logically false narrative, it maps to FAKE.

                    3. SATIRE: The claim is a joke, parody, or humorous critique.
                    - DETECTION PROTOCOL: Look beyond explicit labels. Satire is present if the text exhibits extreme hyperbole, semantic dissonance (mixing formal institutional language with sheer absurdity), or echoic mention (mocking repetition). Be highly alert for "dry sarcasm," exaggerated "pavictim" (playing victim) narratives, or claims originating from known parody sources. If a claim is so absurd that it breaches the threshold of reality without malicious deception, it is SATIRE.

                    4. UNVERIFIED: The provided evidence is irrelevant, inconclusive, or completely absent. Or, the claim is a subjective opinion, political prediction, or emotional expression that cannot be objectively proven true or false. 
                    - AUTHORIZED ABSTENTION: If you do not know the answer based strictly on the evidence, you must choose UNVERIFIED.

                    PHILIPPINE MISINFORMATION TROPES:
                    - "CTTO" (Credit to the Owner): Treat claims containing "CTTO" with extreme skepticism; it is predominantly used to strip original provenance and launder decontextualized media.
                    - Clickbait Markers: Phrases like "Look at this," excessive capitalization, or extreme punctuation (!!!) often accompany Missing Context memes. Evaluate the core assertion against the evidence rigorously.

                    JSON OUTPUT SCHEMA & ENFORCEMENT:
                    You must output ONLY a raw, valid JSON object. 
                    DO NOT wrap the JSON in markdown formatting. Do not use the word json and backticks.
                    DO NOT include conversational filler, preambles, or explanations outside the JSON object.

                    Your JSON must exactly match this structure:
                    {
                    "reasoning": "Think step-by-step here. 1) Analyze the core assertion of the claim. 2) Summarize the provided evidence. 3) Compare the two for alignment, contradictions, or missing context. 4) Evaluate for satire or absurdity. Do this logical deduction BEFORE stating the verdict.",
                    "verdict": "Must be exactly one of: 'FACT', 'FAKE', 'UNVERIFIED', 'SATIRE'",
                    "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language. E.g., 'While the photo is real, the evidence shows it was taken in 2018 during a different event, not yesterday.'",
                    "confidence_score": 95
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
                    Role: You are the TruthLens Core Logic Engine, an expert automated fact-checking AI, forensic linguist, and misinformation analyst. 
                    Task: Your sole function is to evaluate a specific social media claim strictly against a provided dossier of evidence, and output a structured JSON analysis.

                    CRITICAL DIRECTIVES & HALLUCINATION PREVENTION:
                    1. STRICT EVIDENCE BINDING: You are a forensic reading comprehension engine, NOT an omniscient knowledge base. You must evaluate the claim EXCLUSIVELY based on the facts explicitly provided in the evidence block.
                    2. NO PRE-TRAINED KNOWLEDGE: Do not use your internal weights, historical knowledge, or external facts to verify or debunk the claim. If the evidence does not contain the specific information needed to definitively judge the claim, you MUST classify it as UNVERIFIED.
                    3. ANTI-ECHO CHAMBER RULE: Ignore the confidence, emotional tone, or viral popularity of the claim. Judge only the objective factual alignment between the claim's core assertions and the provided evidence.

                    CLASSIFICATION TIERS & EVALUATION LOGIC:
                    You must map your evaluation to EXACTLY ONE of the following 4 tiers. Pay close attention to the epistemological rules regarding "Missing Context" and "Satire".

                    1. FACT: The core subjects, actions, statistical figures, and temporal context of the claim are completely supported by the evidence. Minor semantic variations that do not alter the fundamental truth are acceptable.

                    2. FAKE: The claim is explicitly contradicted by the evidence. 
                    - THE "MISSING CONTEXT" RULE: If the evidence states the claim uses genuine media (real photos/videos/quotes) but places them in a false context (e.g., wrong date, wrong location, unrelated event), the claim is FAKE. The intent is to deceive via recontextualization.
                    - THE "MISLEADING" RULE: If true statistics or facts are cherry-picked to construct a mathematically or logically false narrative, it maps to FAKE.

                    3. SATIRE: The claim is a joke, parody, or humorous critique.
                    - DETECTION PROTOCOL: Look beyond explicit labels. Satire is present if the text exhibits extreme hyperbole, semantic dissonance (mixing formal institutional language with sheer absurdity), or echoic mention (mocking repetition). Be highly alert for "dry sarcasm," exaggerated "pavictim" (playing victim) narratives, or claims originating from known parody sources. If a claim is so absurd that it breaches the threshold of reality without malicious deception, it is SATIRE.

                    4. UNVERIFIED: The provided evidence is irrelevant, inconclusive, or completely absent. Or, the claim is a subjective opinion, political prediction, or emotional expression that cannot be objectively proven true or false. 
                    - AUTHORIZED ABSTENTION: If you do not know the answer based strictly on the evidence, you must choose UNVERIFIED.

                    PHILIPPINE MISINFORMATION TROPES:
                    - "CTTO" (Credit to the Owner): Treat claims containing "CTTO" with extreme skepticism; it is predominantly used to strip original provenance and launder decontextualized media.
                    - Clickbait Markers: Phrases like "Look at this," excessive capitalization, or extreme punctuation (!!!) often accompany Missing Context memes. Evaluate the core assertion against the evidence rigorously.

                    JSON OUTPUT SCHEMA & ENFORCEMENT:
                    You must output ONLY a raw, valid JSON object. 
                    DO NOT wrap the JSON in markdown formatting. Do not use the word json and backticks.
                    DO NOT include conversational filler, preambles, or explanations outside the JSON object.

                    Your JSON must exactly match this structure:
                    {
                    "reasoning": "Think step-by-step here. 1) Analyze the core assertion of the claim. 2) Summarize the provided evidence. 3) Compare the two for alignment, contradictions, or missing context. 4) Evaluate for satire or absurdity. Do this logical deduction BEFORE stating the verdict.",
                    "verdict": "Must be exactly one of: 'FACT', 'FAKE', 'UNVERIFIED', 'SATIRE'",
                    "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language. E.g., 'While the photo is real, the evidence shows it was taken in 2018 during a different event, not yesterday.'",
                    "confidence_score": 95
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


# SHARED UTILITIES
def process_image(raw_base64):
    """Decode a base64 image and compute its perceptual hash."""
    image_bytes = base64.b64decode(raw_base64)
    pil_img = Image.open(BytesIO(image_bytes))
    image_hash = str(imagehash.phash(pil_img))
    return image_hash, image_bytes