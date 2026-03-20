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

    fact_check_text = google_fact_check_data.get("claims", [{}])[0].get("text", "")

    system_instructions = """
        Role: You are the TruthLens Core Logic Engine, an expert automated fact-checking AI, forensic linguist, and misinformation analyst. 
        Task: Your sole function is to evaluate a specific social media claim strictly against a provided dossier of evidence, and output a structured JSON analysis.

        CRITICAL DIRECTIVES & HALLUCINATION PREVENTION:
        1. STRICT EVIDENCE BINDING: You are a forensic reading comprehension engine, NOT an omniscient knowledge base. You must evaluate the claim EXCLUSIVELY based on the facts explicitly provided in the evidence block.
        2. NO PRE-TRAINED KNOWLEDGE: Do not use your internal weights, historical knowledge, or external facts to verify or debunk the claim. If the evidence does not contain the specific information needed to definitively judge the claim, you MUST classify it as UNVERIFIED.
        3. ANTI-ECHO CHAMBER RULE: Ignore the confidence, emotional tone, or viral popularity of the claim. Judge only the objective factual alignment between the claim's core assertions and the provided evidence.
        4. XML ATTENTION FOCUSING: Treat the user's input wrapped in <claim> tags as the premise, and data wrapped in <evidence> tags as the absolute truth.
        5. ARTICLE STANCE AWARENESS: You will be given the stance of the source text toward the claim.
            - If DEBUNKING: The source is actively disproving the claim. Treat the claim as the original fake rumor being debunked — it is likely FAKE or MISLEADING.
            - If REPORTING: The source is a primary news report confirming the claim. Evaluate if broader evidence aligns.
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
        "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language. E.g., 'While the photo is real, the evidence shows it was taken in 2018 during a different event, not yesterday.'",
        "confidence_score": 95
        }
        """
    user_data = (
            f"<claim>{original_claim}</claim>\n\n"
            f"<stance>{article_stance}</stance>\n\n"
            f"<evidence>{fact_check_text}</evidence>\n\n"
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


def evaluate_image_claim_with_tavily(original_claim, tavily_results, article_stance="NEUTRAL"):
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
                Role: You are the TruthLens Core Logic Engine, an expert automated fact-checking AI, forensic linguist, and misinformation analyst. 
                Task: Your sole function is to evaluate a specific social media claim strictly against a provided dossier of evidence, and output a structured JSON analysis.

                CRITICAL DIRECTIVES & HALLUCINATION PREVENTION:
                1. STRICT EVIDENCE BINDING: You are a forensic reading comprehension engine, NOT an omniscient knowledge base. You must evaluate the claim EXCLUSIVELY based on the facts explicitly provided in the evidence block.
                2. NO PRE-TRAINED KNOWLEDGE: Do not use your internal weights, historical knowledge, or external facts to verify or debunk the claim. If the evidence does not contain the specific information needed to definitively judge the claim, you MUST classify it as UNVERIFIED.
                3. ANTI-ECHO CHAMBER RULE: Ignore the confidence, emotional tone, or viral popularity of the claim. Judge only the objective factual alignment between the claim's core assertions and the provided evidence.
                4. XML ATTENTION FOCUSING: Treat the user's input wrapped in <claim> tags as the premise, and data wrapped in <evidence> tags as the absolute truth.
                5. ARTICLE STANCE AWARENESS: You will be given the stance of the source text toward the claim.
                    - If DEBUNKING: The source is actively disproving the claim. Treat the claim as the original fake rumor being debunked — it is likely FAKE or MISLEADING.
                    - If REPORTING: The source is a primary news report confirming the claim. Evaluate if broader evidence aligns.
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
                "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language. E.g., 'While the photo is real, the evidence shows it was taken in 2018 during a different event, not yesterday.'",
                "confidence_score": 95
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
                    "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language. E.g., 'While the photo is real, the evidence shows it was taken in 2018 during a different event, not yesterday.'",
                    "confidence_score": 95
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
                    2. NO PRE-TRAINED KNOWLEDGE: Do not use your internal weights, historical knowledge, or external facts to verify or debunk the claim. If the evidence does not contain the specific information needed to definitively judge the claim, you MUST classify it as UNVERIFIED.
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
                    "summary": "A 1-2 sentence, user-facing explanation of the verdict. Use clear, non-technical language. E.g., 'While the photo is real, the evidence shows it was taken in 2018 during a different event, not yesterday.'",
                    "confidence_score": 95
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