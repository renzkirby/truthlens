from groq import Groq
import os
import json
import re
import logging
from urllib.parse import urlparse
import ipaddress
import imagehash
import uuid
import base64
import requests
from io import BytesIO
from PIL import Image
from supabase import create_client
 
logger = logging.getLogger(__name__)


def _float_env(name, default):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        logger.warning("Invalid %s value '%s'; using default %.2f", name, raw_value, default)
        return default


HF_DETECT_TIMEOUT_SEC = _float_env("HF_DETECT_TIMEOUT_SEC", 18.0)


groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


def _parse_groq_json(raw_content):
    """Strip markdown formatting and parse JSON from Groq responses."""
    cleaned = raw_content.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def validate_public_url(raw_url):
    """Allow only public http(s) URLs to reduce unsafe URL processing risk."""
    if not raw_url or not isinstance(raw_url, str):
        return None, "URL is required."

    candidate = raw_url.strip()
    if len(candidate) > 500:
        return None, "URL is too long."

    parsed = urlparse(candidate)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    if scheme not in {"http", "https"}:
        return None, "Only http/https URLs are allowed."
    if not host:
        return None, "Invalid URL format."

    if host in {"localhost", "127.0.0.1", "::1"}:
        return None, "Local URLs are not allowed."
    if host.endswith(".local") or host.endswith(".internal") or host.endswith(".localhost"):
        return None, "Private network URLs are not allowed."

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return None, "Private network URLs are not allowed."
    except ValueError:
        # Host is a domain name, which is allowed.
        pass

    sanitized = parsed._replace(fragment="").geturl()
    return sanitized, None


def check_url_threat_reputation(candidate_url):
    """
    Reputation-style URL threat check using Google Safe Browsing API.

    Returns a dict with status in: SAFE, UNSAFE, UNKNOWN.
    """
    api_key = os.environ.get("SAFE_BROWSING_API_KEY")
    if not api_key:
        return {
            "status": "UNKNOWN",
            "provider": "GOOGLE_SAFE_BROWSING",
            "reason": "SAFE_BROWSING_API_KEY not configured",
        }

    endpoint = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={api_key}"
    payload = {
        "client": {"clientId": "truthlens", "clientVersion": "1.0.0"},
        "threatInfo": {
            "threatTypes": [
                "MALWARE",
                "SOCIAL_ENGINEERING",
                "UNWANTED_SOFTWARE",
                "POTENTIALLY_HARMFUL_APPLICATION",
            ],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": candidate_url}],
        },
    }

    try:
        response = requests.post(endpoint, json=payload, timeout=6)
        if response.status_code != 200:
            return {
                "status": "UNKNOWN",
                "provider": "GOOGLE_SAFE_BROWSING",
                "reason": f"provider_error_{response.status_code}",
            }

        data = response.json() if response.content else {}
        matches = data.get("matches", [])
        if matches:
            threat_types = sorted(
                {
                    match.get("threatType")
                    for match in matches
                    if isinstance(match, dict) and match.get("threatType")
                }
            )
            return {
                "status": "UNSAFE",
                "provider": "GOOGLE_SAFE_BROWSING",
                "threat_types": threat_types,
            }

        return {
            "status": "SAFE",
            "provider": "GOOGLE_SAFE_BROWSING",
            "threat_types": [],
        }
    except requests.RequestException:
        return {
            "status": "UNKNOWN",
            "provider": "GOOGLE_SAFE_BROWSING",
            "reason": "provider_unreachable",
        }


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

                Task: Your job is to extract the core claim from the text by strictly following these steps:
                1. Identify the CENTRAL NARRATIVE of the provided text.
                2. Extract the primary verifiable claim. Translate any local slang or Taglish to English.
                3. UNDERLYING CLAIM EXTRACTION: If the text is actively debunking, fact-checking, or clarifying a rumor, your cleaned_claim MUST be the original fake rumor itself, NOT the fact-checker's conclusion.
                4. QUOTE CARDS & ATTRIBUTIONS (CRITICAL): If the text is a quote attributed to a specific person, journalist, or publication (e.g., a quote card), the `cleaned_claim` MUST explicitly state who said it (e.g., "Ogie Diaz stated that..."). Do not strip the speaker's name.
                5. CONTEXT RETENTION: You MUST include essential context in the cleaned_claim (e.g., specific names, dates, locations). Do not over-prune. 
                6. SEARCH QUERY OPTIMIZATION: Generate a highly optimized search query of exactly 6-10 keywords. You MUST prioritize proper nouns, the speaker's name, and unique identifiers to prevent ambiguous search results.
                7. Determine the article's own stance toward the extracted claim:
                    - DEBUNKING: The article is a fact-check disproving the extracted claim.
                    - REPORTING: The article neutrally reports the extracted claim as true.
                    - SATIRE: The text is from a parody source OR the text is deeply absurd/comedic.

                SPECIAL RULE — KNOWN SATIRE & MEME TROPES:
                1. If the text or Source URL originates from known satire (e.g., theonion.com, babylonbee), set "article_stance" to "SATIRE".
                2. MEME DETECTION: Be highly vigilant for misspelled news logos (e.g., "INQIURER" instead of "INQUIRER") or the use of fictional/pop-culture characters (e.g., TV doctors, actors, adult film stars) placed in real-world news contexts. If detected, you MUST set "article_stance" to "SATIRE".
                
                JSON Schema:
                You MUST output EXACTLY this JSON object with ALL THREE keys.
                {
                    "cleaned_claim": "A complete sentence detailing the core claim AND its specific context.",
                    "search_query": "Keyword1 Keyword2 Keyword3...",
                    "article_stance": "DEBUNKING, REPORTING, or SATIRE"
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
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict relevance checker for a fact-checking pipeline. "
                    "Two texts are relevant ONLY if they discuss the exact same real-world "
                    "event, person, and time period. "
                    "Output a JSON object with 'reasoning' (1 sentence of deduction) and 'is_relevant' (boolean true/false)."
                ),
            },
            {
                "role": "user",
                "content": f'Claim: "{original_text}"\n\nFact Check: "{fact_check_text}"',
            },
        ],
    )

    result = _parse_groq_json(response.choices[0].message.content)
    print("is_fact_check_relevant RESPONSE:", result)
    return result.get("is_relevant", False)

# Evaluate Google's Fact Check Tools data against the original claim using Groq
def evaluate_image_claim_with_gfc(original_claim, google_fact_check_data, article_stance="NEUTRAL"):

    # 1. Safely extract the data blocks
    claim_data = google_fact_check_data.get("claims", [{}])[0]
    review_data = claim_data.get("claimReview", [{}])[0]

    # 2. Extract the rumor AND the official rating
    fact_check_text = claim_data.get("text", "Unknown claim")
    gfc_rating = review_data.get("textualRating", "UNKNOWN")
    publisher = review_data.get("publisher", {}).get("name", "Official Fact Checker")

    system_instructions = """
        Role: You are the TruthLens Core Logic Engine, an expert automated fact-checking AI, forensic linguist, and misinformation analyst. 
        Task: Your sole function is to evaluate a specific social media claim strictly against a provided dossier of evidence, and output a structured JSON analysis.

        CRITICAL DIRECTIVES & HALLUCINATION PREVENTION:
        1. STRICT EVIDENCE BINDING: You are a forensic reading comprehension engine, NOT an omniscient knowledge base. You must evaluate the claim EXCLUSIVELY based on the facts explicitly provided in the evidence block.
        2. NO PRE-TRAINED KNOWLEDGE: Do not use your internal weights to verify the claim. 
        EXCEPTION: You MAY use your pre-trained world knowledge to identify if the claim relies on obviously fictional characters (e.g., TV/movie characters), well-known internet memes, or sheer physical impossibilities. If the claim relies on a fictional character performing a real-world action, immediately classify it as SATIRE or FAKE, overriding the provided evidence if the evidence is gullible.
        3. ANTI-ECHO CHAMBER RULE: Ignore the confidence, emotional tone, or viral popularity of the claim. Judge only the objective factual alignment between the claim's core assertions and the provided evidence.
        4. XML ATTENTION FOCUSING: Treat the user's input wrapped in <claim> tags as the premise, and data wrapped in <evidence> tags as the absolute truth.
        5. ARTICLE STANCE AWARENESS: You will be given the stance of the source text toward the claim.
                    - If DEBUNKING: The source is actively disproving the claim. Treat the claim as the original fake rumor being debunked — it is likely FAKE or MISLEADING.
                    - If REPORTING: The source is a primary news report confirming the claim. You must evaluate if the broader evidence aligns with or contradicts this reporting. If the evidence generally supports the narrative or is from the same original source, the verdict is FACT.
                    - If NEUTRAL: Evaluate purely from the evidence.

        CLASSIFICATION TIERS & EVALUATION LOGIC:
        You must map your evaluation to EXACTLY ONE of the following 5 tiers. 

        1. FACT: The core subjects, actions, statistical figures, and temporal context of the claim are completely supported by the evidence. Minor semantic variations that do not alter the fundamental truth are acceptable.

        2. FAKE: The claim is entirely fabricated or explicitly contradicted by the evidence.

        3. MISLEADING: The claim contains a mix of truth and falsehoods. 
        - THE "MISSING CONTEXT" RULE: If the evidence states the claim uses genuine media (real photos/videos/quotes) but places them in a false context (e.g., wrong date, wrong location, unrelated event), the claim is MISLEADING. 
        - THE CHERRY-PICKING RULE: If true statistics or partial facts are intentionally cherry-picked to construct a mathematically or logically false overall narrative, it is MISLEADING.

        4. SATIRE: The claim is a joke, parody, or humorous critique.
        - DETECTION PROTOCOL: Look beyond explicit labels. Satire is present if the text exhibits extreme hyperbole, semantic dissonance (mixing formal institutional language with sheer absurdity), or echoic mention (mocking repetition). Be highly alert for "dry sarcasm," exaggerated "pavictim" (playing victim) narratives, or claims originating from known parody sources. If a claim is so absurd that it breaches the threshold of reality without malicious deception, it is SATIRE.

        5. UNVERIFIED: The provided evidence is irrelevant, inconclusive, or completely absent. Or, the claim is a subjective opinion, political prediction, or emotional expression that cannot be objectively proven true or false. 
        - AUTHORIZED ABSTENTION: If you do not know the answer based strictly on the evidence, you must choose UNVERIFIED.

        6. STRICT ENTITY MATCHING (THE 'KEYWORD SALAD' TRAP): Do not stamp 'FACT' just because keywords match. You must verify EXACT identities. If the claim is about a specific public figure and the evidence discusses a different person or entity that merely shares the same name, they are NOT the same. In these cases, you must classify it as UNVERIFIED or FAKE.
                
        7. GRAMMAR & ATTRIBUTION ACCURACY: Pay strict grammatical attention to WHO is doing WHAT. The roles in the claim (subject, object, action) must perfectly align with the evidence. (e.g., If the claim says Person A committed an action against Person B, evidence showing Person B did it to Person A means the claim is FAKE). Furthermore, if the claim attributes a quote or statement to a specific individual, journalist, or organization, the evidence MUST explicitly confirm that the specific entity actually made that statement.

        PHILIPPINE MISINFORMATION TROPES:
        - "CTTO" (Credit to the Owner): Treat claims containing "CTTO" with extreme skepticism; it is predominantly used to strip original provenance and launder decontextualized media.
        - Clickbait Markers: Phrases like "Look at this," excessive capitalization, or extreme punctuation (!!!) often accompany Missing Context memes. Evaluate the core assertion against the evidence rigorously.

        JSON OUTPUT SCHEMA & ENFORCEMENT:
        You must output ONLY a raw, valid JSON object. 
        DO NOT wrap the JSON in markdown formatting (e.g., no ```json blocks).
        DO NOT include conversational filler, preambles, or explanations outside the JSON object.

        Your JSON must exactly match this structure:
        {
        "reasoning": "Think step-by-step here. 1) Analyze the core assertion of the claim. 2) Summarize the provided evidence. 3) Compare the two for alignment, contradictions, or missing context. 4) Evaluate for satire or absurdity. Do this logical deduction BEFORE stating the verdict.",
        "verdict": "Must be exactly one of: 'FACT', 'FAKE', 'MISLEADING', 'UNVERIFIED', 'SATIRE'",
        "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language.",
        "confidence_score": 95,
        "score_context": "A strict 10-15 word one-liner explaining WHY you gave this specific confidence score. (e.g., 'Strong consensus across multiple reputable news outlets.')"
        }
        """
    user_data = (
            f"<claim>{original_claim}</claim>\n\n"
            f"<stance>{article_stance}</stance>\n\n"
            f"<evidence>The claim '{fact_check_text}' was reviewed by {publisher} and received an Official Rating of: {gfc_rating.upper()}</evidence>\n\n"
            "CRITICAL OVERRIDE: If the <stance> is SATIRE, you MUST bypass evidence checking and immediately output a verdict of SATIRE."
        )
    
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


def evaluate_image_claim_with_tavily(original_claim, combined_context, article_stance="NEUTRAL"):
    """Evaluate an image claim against Tavily live news results."""
    evidence_text = combined_context

    print("EVIDENCE TEXT:", evidence_text)

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
                4. XML ATTENTION FOCUSING: Treat the user's input wrapped in <claim> tags as the premise, and data wrapped in <evidence> tags as the absolute truth.
                5. ARTICLE STANCE AWARENESS: You will be given the stance of the source text toward the claim.
                    - If DEBUNKING: The source is actively disproving the claim. Treat the claim as the original fake rumor being debunked — it is likely FAKE or MISLEADING.
                    - If REPORTING: The source is a primary news report confirming the claim. You must evaluate if the broader evidence aligns with or contradicts this reporting. If the evidence generally supports the narrative or is from the same original source, the verdict is FACT.
                    - If NEUTRAL: Evaluate purely from the evidence.

                CLASSIFICATION TIERS & EVALUATION LOGIC:
                You must map your evaluation to EXACTLY ONE of the following 5 tiers. 

                1. FACT: The core subjects, actions, statistical figures, and temporal context of the claim are completely supported by the evidence. Minor semantic variations that do not alter the fundamental truth are acceptable.

                2. FAKE: The claim is entirely fabricated or explicitly contradicted by the evidence.

                3. MISLEADING: The claim contains a mix of truth and falsehoods. 
                - THE "MISSING CONTEXT" RULE: If the evidence states the claim uses genuine media (real photos/videos/quotes) but places them in a false context (e.g., wrong date, wrong location, unrelated event), the claim is MISLEADING. 
                - THE CHERRY-PICKING RULE: If true statistics or partial facts are intentionally cherry-picked to construct a mathematically or logically false overall narrative, it is MISLEADING.

                4. SATIRE: The claim is a joke, parody, or humorous critique.
                - DETECTION PROTOCOL: Look beyond explicit labels. Satire is present if the text exhibits extreme hyperbole, semantic dissonance (mixing formal institutional language with sheer absurdity), or echoic mention (mocking repetition). Be highly alert for "dry sarcasm," exaggerated "pavictim" (playing victim) narratives, or claims originating from known parody sources. If a claim is so absurd that it breaches the threshold of reality without malicious deception, it is SATIRE.

                5. UNVERIFIED: The provided evidence is irrelevant, inconclusive, or completely absent. Or, the claim is a subjective opinion, political prediction, or emotional expression that cannot be objectively proven true or false. 
                    - AUTHORIZED ABSTENTION: If you do not know the answer based strictly on the evidence, you must choose UNVERIFIED.
                    - THE GOSSIP RULE: If the claim is based on a "blind item," an unverified statement by a showbiz vlogger/insider (e.g., "Ogie Diaz revealed..."), or an anonymous source, AND the evidence does not contain official statements from the actual people involved confirming it, you MUST classify it as UNVERIFIED. The fact that a vlogger said a rumor exists does not make the rumor a FACT.
                
                6. STRICT ENTITY MATCHING (THE 'KEYWORD SALAD' TRAP): Do not stamp 'FACT' just because keywords match. You must verify EXACT identities. If the claim is about a specific public figure and the evidence discusses a different person or entity that merely shares the same name, they are NOT the same. In these cases, you must classify it as UNVERIFIED or FAKE.
                        
                7. GRAMMAR & ATTRIBUTION ACCURACY: Pay strict grammatical attention to WHO is doing WHAT. The roles in the claim (subject, object, action) must perfectly align with the evidence. (e.g., If the claim says Person A committed an action against Person B, evidence showing Person B did it to Person A means the claim is FAKE). Furthermore, if the claim attributes a quote or statement to a specific individual, journalist, or organization, the evidence MUST explicitly confirm that the specific entity actually made that statement.


                PHILIPPINE MISINFORMATION TROPES:
                - "CTTO" (Credit to the Owner): Treat claims containing "CTTO" with extreme skepticism; it is predominantly used to strip original provenance and launder decontextualized media.
                - Clickbait Markers: Phrases like "Look at this," excessive capitalization, or extreme punctuation (!!!) often accompany Missing Context memes. Evaluate the core assertion against the evidence rigorously.

                JSON OUTPUT SCHEMA & ENFORCEMENT:
                You must output ONLY a raw, valid JSON object. 
                DO NOT wrap the JSON in markdown formatting (e.g., no ```json blocks).
                DO NOT include conversational filler, preambles, or explanations outside the JSON object.

                Your JSON must exactly match this structure:
                {
                "reasoning": "Think step-by-step here. 1) Analyze the core assertion of the claim. 2) Summarize the provided evidence. 3) Compare the two for alignment, contradictions, or missing context. 4) Evaluate for satire or absurdity. Do this logical deduction BEFORE stating the verdict.",
                "verdict": "Must be exactly one of: 'FACT', 'FAKE', 'MISLEADING', 'UNVERIFIED', 'SATIRE'",
                "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language.",
                "confidence_score": 95,
                "score_context": "A strict 10-15 word one-liner explaining WHY you gave this specific confidence score. (e.g., 'Strong consensus across multiple reputable news outlets.')",
                "source_url": "The exact URL from the evidence block. If no explicit URL is provided in the evidence text, you MUST return null. DO NOT make up or hallucinate a URL like example.com."
                }
                """,
            },
            {
                "role": "user",
                "content": (
                    f"<claim>{original_claim}</claim>\n\n"
                    f"<stance>{article_stance}</stance>\n\n"
                    f"<evidence>{evidence_text}</evidence>\n\n"
                    "CRITICAL OVERRIDE: If the <stance> is SATIRE, you MUST bypass evidence checking and immediately output a verdict of SATIRE."
                ),
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

def extract_search_query(text, source_url=""):
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: You are a precise data extraction tool for a fact-checking pipeline.

                Task: Your job is to extract the core claim from the text by strictly following these steps:
                1. Identify the CENTRAL NARRATIVE of the provided text.
                2. Extract the primary verifiable claim. Translate any local slang or Taglish to English.
                3. UNDERLYING CLAIM EXTRACTION: If the text is actively debunking, fact-checking, or clarifying a rumor, your cleaned_claim MUST be the original fake rumor itself, NOT the fact-checker's conclusion.
                - Example: If text says "Fake News: Pope did not wear a puffer jacket", you extract "The Pope wore a white puffer jacket."
                4. CONTEXT RETENTION: You MUST include essential context in the cleaned_claim (e.g., specific names, dates, locations, and the specific event being alleged). Do not over-prune.
                5. Generate a highly optimized search query of exactly 6-10 keywords. Use distinct nouns and entities that a search engine can easily find.
                6. Determine the article's own stance toward the extracted claim:
                    - DEBUNKING: The article is a fact-check disproving the extracted claim.
                    - REPORTING: The article neutrally reports the extracted claim as true.
                    - SATIRE: The text is from a parody source OR the text is deeply absurd/comedic.

                SPECIAL RULE — KNOWN SATIRE SOURCES:
                If the text or Source URL originates from known satire (e.g., theonion.com, babylonbee), MUST set "article_stance" to "SATIRE".

                JSON Schema:
                You MUST output EXACTLY this JSON object with ALL THREE keys.
                {
                    "cleaned_claim": "A complete sentence detailing the core claim AND its specific context.",
                    "search_query": "Keyword1 Keyword2 Keyword3...",
                    "article_stance": "DEBUNKING, REPORTING, or SATIRE"
                }
                """
            },
            {
                "role": "user",
                "content": f"Source URL: {source_url}\n\nText: {text}",
            },
        ],
    )

    extracted_search_query = response.choices[0].message.content

    print("JSON OUTPUT:", extracted_search_query)
 
    return json.loads(extracted_search_query)


def evaluate_url_claim_with_gfc(extracted_text, gfc_data, article_stance="NEUTRAL"):
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
                    4. XML ATTENTION FOCUSING: Treat the user's input wrapped in <claim> tags as the premise, and data wrapped in <evidence> tags as the absolute truth.

                    CLASSIFICATION TIERS & EVALUATION LOGIC:
                    You must map your evaluation to EXACTLY ONE of the following 5 tiers. 

                    1. FACT: The core subjects, actions, statistical figures, and temporal context of the claim are completely supported by the evidence. Minor semantic variations that do not alter the fundamental truth are acceptable.

                    2. FAKE: The claim is entirely fabricated or explicitly contradicted by the evidence.

                    3. MISLEADING: The claim contains a mix of truth and falsehoods. 
                    - THE "MISSING CONTEXT" RULE: If the evidence states the claim uses genuine media (real photos/videos/quotes) but places them in a false context (e.g., wrong date, wrong location, unrelated event), the claim is MISLEADING. 
                    - THE CHERRY-PICKING RULE: If true statistics or partial facts are intentionally cherry-picked to construct a mathematically or logically false overall narrative, it is MISLEADING.

                    4. SATIRE: The claim is a joke, parody, or humorous critique.
                    - DETECTION PROTOCOL: Look beyond explicit labels. Satire is present if the text exhibits extreme hyperbole, semantic dissonance (mixing formal institutional language with sheer absurdity), or echoic mention (mocking repetition). Be highly alert for "dry sarcasm," exaggerated "pavictim" (playing victim) narratives, or claims originating from known parody sources. If a claim is so absurd that it breaches the threshold of reality without malicious deception, it is SATIRE.

                    5. UNVERIFIED: The provided evidence is irrelevant, inconclusive, or completely absent. Or, the claim is a subjective opinion, political prediction, or emotional expression that cannot be objectively proven true or false. 
                    - AUTHORIZED ABSTENTION: If you do not know the answer based strictly on the evidence, you must choose UNVERIFIED.
                  
                    6. STRICT ENTITY MATCHING (THE 'KEYWORD SALAD' TRAP): Do not stamp 'FACT' just because keywords match. You must verify EXACT identities. If the claim is about a specific public figure and the evidence discusses a different person or entity that merely shares the same name, they are NOT the same. In these cases, you must classify it as UNVERIFIED or FAKE.
                            
                    7. GRAMMAR & ATTRIBUTION ACCURACY: Pay strict grammatical attention to WHO is doing WHAT. The roles in the claim (subject, object, action) must perfectly align with the evidence. (e.g., If the claim says Person A committed an action against Person B, evidence showing Person B did it to Person A means the claim is FAKE). Furthermore, if the claim attributes a quote or statement to a specific individual, journalist, or organization, the evidence MUST explicitly confirm that the specific entity actually made that statement.
                

                    PHILIPPINE MISINFORMATION TROPES:
                    - "CTTO" (Credit to the Owner): Treat claims containing "CTTO" with extreme skepticism; it is predominantly used to strip original provenance and launder decontextualized media.
                    - Clickbait Markers: Phrases like "Look at this," excessive capitalization, or extreme punctuation (!!!) often accompany Missing Context memes. Evaluate the core assertion against the evidence rigorously.

                    JSON OUTPUT SCHEMA & ENFORCEMENT:
                    You must output ONLY a raw, valid JSON object. 
                    DO NOT wrap the JSON in markdown formatting (e.g., no ```json blocks).
                    DO NOT include conversational filler, preambles, or explanations outside the JSON object.

                    Your JSON must exactly match this structure:
                    {
                    "reasoning": "Think step-by-step here. 1) Analyze the core assertion of the claim. 2) Summarize the provided evidence. 3) Compare the two for alignment, contradictions, or missing context. 4) Evaluate for satire or absurdity. Do this logical deduction BEFORE stating the verdict.",
                    "verdict": "Must be exactly one of: 'FACT', 'FAKE', 'MISLEADING', 'UNVERIFIED', 'SATIRE'",
                    "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language.",
                    "confidence_score": 95,
                    "score_context": "A strict 10-15 word one-liner explaining WHY you gave this specific confidence score. (e.g., 'Strong consensus across multiple reputable news outlets.')"
                    }
                    """,
            },
            {
                "role": "user",
                "content": (
                    f"<claim>{extracted_text}</claim>\n\n"
                    f"<stance>{article_stance}</stance>\n\n"
                    f"<evidence>{gfc_claim_text} (Official Rating: {gfc_rating})</evidence>\n\n"
                    "CRITICAL OVERRIDE: If the <stance> is SATIRE, you MUST bypass evidence checking and immediately output a verdict of SATIRE."
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


def evaluate_url_claim_with_tavily(extracted_text, context, article_stance="NEUTRAL"):
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
                    2. NO PRE-TRAINED KNOWLEDGE: Do not use your internal weights to verify the claim. 
                    EXCEPTION: You MAY use your pre-trained world knowledge to identify if the claim relies on obviously fictional characters (e.g., TV/movie characters), well-known internet memes, or sheer physical impossibilities. If the claim relies on a fictional character performing a real-world action, immediately classify it as SATIRE or FAKE, overriding the provided evidence if the evidence is gullible.
                    3. ANTI-ECHO CHAMBER RULE: Ignore the confidence, emotional tone, or viral popularity of the claim. Judge only the objective factual alignment between the claim's core assertions and the provided evidence.
                    4. XML ATTENTION FOCUSING: Treat the user's input wrapped in <claim> tags as the premise, and data wrapped in <evidence> tags as the absolute truth.
                    5. ARTICLE STANCE AWARENESS: You will be given the stance of the source article toward the claim.
                    - If DEBUNKING: The article is actively disproving the claim. Treat the claim as something being debunked.
                    - If REPORTING: The article is a primary news source confirming the claim. You must evaluate if the broader evidence aligns with or contradicts this reporting. If the evidence generally supports the narrative or is from the same original source, the verdict is FACT.
                    - If NEUTRAL: Evaluate purely from the evidence.

                    CLASSIFICATION TIERS & EVALUATION LOGIC:
                    You must map your evaluation to EXACTLY ONE of the following 5 tiers. 

                    1. FACT: The core subjects, actions, statistical figures, and temporal context of the claim are completely supported by the evidence. Minor semantic variations that do not alter the fundamental truth are acceptable.

                    2. FAKE: The claim is entirely fabricated or explicitly contradicted by the evidence.

                    3. MISLEADING: The claim contains a mix of truth and falsehoods. 
                    - THE "MISSING CONTEXT" RULE: If the evidence states the claim uses genuine media (real photos/videos/quotes) but places them in a false context (e.g., wrong date, wrong location, unrelated event), the claim is MISLEADING. 
                    - THE CHERRY-PICKING RULE: If true statistics or partial facts are intentionally cherry-picked to construct a mathematically or logically false overall narrative, it is MISLEADING.

                    4. SATIRE: The claim is a joke, parody, or humorous critique.
                    - DETECTION PROTOCOL: Look beyond explicit labels. Satire is present if the text exhibits extreme hyperbole, semantic dissonance (mixing formal institutional language with sheer absurdity), or echoic mention (mocking repetition). Be highly alert for "dry sarcasm," exaggerated "pavictim" (playing victim) narratives, or claims originating from known parody sources. If a claim is so absurd that it breaches the threshold of reality without malicious deception, it is SATIRE.

                    5. UNVERIFIED: The provided evidence is irrelevant, inconclusive, or completely absent. Or, the claim is a subjective opinion, political prediction, or emotional expression that cannot be objectively proven true or false. 
                    - AUTHORIZED ABSTENTION: If you do not know the answer based strictly on the evidence, you must choose UNVERIFIED.
                    - THE GOSSIP RULE: If the claim is based on a "blind item," an unverified statement by a showbiz vlogger/insider (e.g., "Ogie Diaz revealed..."), or an anonymous source, AND the evidence does not contain official statements from the actual people involved confirming it, you MUST classify it as UNVERIFIED. The fact that a vlogger said a rumor exists does not make the rumor a FACT.
                    
                    6. STRICT ENTITY MATCHING (THE 'KEYWORD SALAD' TRAP): Do not stamp 'FACT' just because keywords match. You must verify EXACT identities. If the claim is about a specific public figure and the evidence discusses a different person or entity that merely shares the same name, they are NOT the same. In these cases, you must classify it as UNVERIFIED or FAKE.
                            
                    7. GRAMMAR & ATTRIBUTION ACCURACY: Pay strict grammatical attention to WHO is doing WHAT. The roles in the claim (subject, object, action) must perfectly align with the evidence. (e.g., If the claim says Person A committed an action against Person B, evidence showing Person B did it to Person A means the claim is FAKE). Furthermore, if the claim attributes a quote or statement to a specific individual, journalist, or organization, the evidence MUST explicitly confirm that the specific entity actually made that statement.

                    PHILIPPINE MISINFORMATION TROPES:
                    - "CTTO" (Credit to the Owner): Treat claims containing "CTTO" with extreme skepticism; it is predominantly used to strip original provenance and launder decontextualized media.
                    - Clickbait Markers: Phrases like "Look at this," excessive capitalization, or extreme punctuation (!!!) often accompany Missing Context memes. Evaluate the core assertion against the evidence rigorously.

                    JSON OUTPUT SCHEMA & ENFORCEMENT:
                    You must output ONLY a raw, valid JSON object. 
                    DO NOT wrap the JSON in markdown formatting (e.g., no ```json blocks).
                    DO NOT include conversational filler, preambles, or explanations outside the JSON object.

                    Your JSON must exactly match this structure:
                    {
                    "reasoning": "Think step-by-step here. 1) Analyze the core assertion of the claim. 2) Summarize the provided evidence. 3) Compare the two for alignment, contradictions, or missing context. 4) Evaluate for satire or absurdity. Do this logical deduction BEFORE stating the verdict.",
                    "verdict": "Must be exactly one of: 'FACT', 'FAKE', 'MISLEADING', 'UNVERIFIED', 'SATIRE'",
                    "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language.",
                    "confidence_score": 95,
                    "score_context": "A strict 10-15 word one-liner explaining WHY you gave this specific confidence score. (e.g., 'Strong consensus across multiple reputable news outlets.')",
                    "source_url": "The exact URL from the evidence block. If no explicit URL is provided in the evidence text, you MUST return null. DO NOT make up or hallucinate a URL like example.com."
                    }
                    """,
            },
            {
                "role": "user",
                "content": (
                    f"<claim>{extracted_text}</claim>\n\n"
                    f"<stance>{article_stance}</stance>\n\n"
                    f"<evidence>{context}</evidence>\n\n"
                    "CRITICAL OVERRIDE: If the <stance> is SATIRE, you MUST bypass evidence checking and immediately output a verdict of SATIRE."
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

def upload_image_to_database(base64_string):
    supabase = create_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_SERVICE_KEY"),
    )
    
    image_bytes = base64.b64decode(base64_string)
    file_name = f"{uuid.uuid4()}.png"

    supabase.storage.from_("claim-images").upload(
        file_name,
        image_bytes,
        {"content-type": "image/png"},
    )
    
    public_url = supabase.storage.from_("claim-images").get_public_url(file_name)
    print("PUBLIC URL TYPE:", type(public_url))
    print("PUBLIC URL VALUE:", public_url)
    return public_url
    

# AI DEEPFAKE/AI GENERATED IMAGE PIPELINE
def detect_ai_image(image_bytes):
    """Sends image to Hugging Face's inference API to detect AI generation."""
    API_URL = "https://router.huggingface.co/hf-inference/models/dima806/deepfake_vs_real_image_detection"
    headers = {
            "Authorization": f"Bearer {os.environ.get('HUGGINGFACE_API_KEY')}",
            "Content-Type": "application/octet-stream"
        }
    
    try:
        response = requests.post(
            API_URL,
            headers=headers,
            data=image_bytes,
            timeout=HF_DETECT_TIMEOUT_SEC,
        )
        
        if response.status_code != 200:
            print(f"API Error: {response.text}")
            return 0.0 
            
        result = response.json()
        print("Deepfake Detection Result:", result)
        
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
            result = result[0]

        for label_data in result:
            if label_data.get('label', '').lower() in ['artificial', 'fake', 'ai-generated']:
                return float(label_data.get('score', 0.0))
                
        return 0.0
    except Exception as e:
        print(f"Detection Error: {str(e)}")
        return 0.0

def generate_deepfake_explanation(base64_string):
    """Uses Groq Vision to write an explanation of AI artifacts in the image."""
    try:
        # Initialize Groq client (ensure GROQ_API_KEY is in your environment)
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        # Ensure the base64 string has the correct data URI prefix for Groq
        image_url = f"data:image/jpeg;base64,{base64_string}"

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert digital forensics AI. The user will provide an image that has already been mathematically flagged as AI-generated. Write a concise, 2-sentence summary describing what is in the photo, and pointing out 1 or 2 common AI artifacts visible in the image (e.g., anatomical errors, lighting inconsistencies, blurry background details). Keep it brief and objective."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this AI-generated image and explain the artifacts."},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            model="llama-3.2-11b-vision-preview", # Groq's vision model
            temperature=0.3,
            max_tokens=150
        )
        
        return chat_completion.choices[0].message.content
        
    except Exception as e:
        print(f"Vision AI Error: {str(e)}")
        return "Our forensic model detected strong indicators of digital manipulation or AI generation, but a detailed visual summary could not be generated."
