from groq import Groq
from dotenv import load_dotenv
import os
import json
import re
import imagehash
import base64
from io import BytesIO
from PIL import Image


# Clean the OCR text to extract a concise search query or determine if it's out of scope
def clean_ocr_text(raw_text):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: You are a precise data extraction tool for a fact-checking pipeline. 
                Task: Your only job is to analyze messy OCR text, if the text contains factual, verifiable claim, translate any local slang or Taglish to English, and extract the single most verifiable core claim. Extract a search query of exactly 10 words or less from this text. Aside from this, clean the ocr text to something much readable to the human reader. If the text is purely subjective, an opinion, a question, or does not contain any factual claim that can be verified, respond with the exact phrase "OUT_OF_SCOPE". 
                
                Output Constraints:
                Do not output anything other than the clean claim or "OUT_OF_SCOPE". Do not provide any explanation or additional text. Output NOTHING else. No punctuation, no conversational filler. The output format should be in a json object with two fields: "cleaned_claim" and "search_query". If the text is out of scope, both fields should be "OUT_OF_SCOPE".
                
                JSON Schema:
                If the text contains a verifiable claim:
                {
                "cleaned_claim": "A concise, cleaned version of the core claim extracted from the OCR text, translated to English if necessary.",
                "search_query": "A concise search query derived from the cleaned claim."
                }
                If the text is out of scope:
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

    cleaned_ocr_text = (
        raw_response.strip().replace("```json", "").replace("```", "").strip()
    )

    print("JSON OUTPUT:", cleaned_ocr_text)

    return json.loads(cleaned_ocr_text)


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


# URL VERIFIER******************************************************************************************************************


def clean_extracted_text(text):
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"http\S+", "", text)
    lines = text.split("\n")
    lines = [line.strip() for line in lines if len(line.strip()) > 40]
    text = "\n".join(lines)
    return text[:3000]

# cleans the text for a much more efficient querying
def extract_search_query(text):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
                Role: You are a precise data extraction tool for a fact-checking pipeline. 
                Task: Your only job is to analyze the extracted text from a website, if the text contains factual, verifiable claim, translate any local slang or Taglish to English, and extract the single most verifiable core claim. Extract a search query of exactly 10 words or less from this text. The output of the cleaned ocr text should be the original extracted text but cleaned. If the text is purely subjective, an opinion, a question, or does not contain any factual claim that can be verified, respond with the exact phrase "OUT_OF_SCOPE". 
                
                Output Constraints:
                Do not output anything other than the clean claim or "OUT_OF_SCOPE". Do not provide any explanation or additional text. Output NOTHING else. No punctuation, no conversational filler. The output format should be in a json object with two fields: "cleaned_claim" and "search_query". If the text is out of scope, both fields should be "OUT_OF_SCOPE".
                
                JSON Schema:
                If the text contains a verifiable claim:
                {
                "cleaned_claim": "A concise, cleaned version of the core claim extracted from the OCR text, translated to English if necessary.",
                "search_query": "A concise search query derived from the cleaned claim."
                }
                If the text is out of scope:
                {
                "cleaned_claim": "OUT_OF_SCOPE",
                "search_query": "OUT_OF_SCOPE"
                }
                """,
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


def is_gfc_relevant(extracted_text, gfc_claim_text):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a relevance checker for a fact-checking pipeline. "
                    "Compare the two texts below and determine if the fact check "
                    "result is directly relevant to verifying the article claim. "
                    "Output ONLY 'Relevant' or 'Not Relevant'. No explanation."
                ),
            },
            {
                "role": "user",
                "content": (
                    f'Article text: "{extracted_text[:300]}"\n\n'
                    f'Fact check claim: "{gfc_claim_text}"'
                ),
            },
        ],
    )

    result = response.choices[0].message.content.strip().upper()

    if "NOT RELEVANT" in result:
        return False
    return True


def evaluate_with_gfc(extracted_text, gfc_data):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    gfc_claim_text = gfc_data.get("claims", [{}])[0].get("text", "")
    gfc_rating = (
        gfc_data.get("claims", [{}])[0]
        .get("claimReview", [{}])[0]
        .get("textualRating", "")
    )
    gfc_source = (
        gfc_data.get("claims", [{}])[0].get("claimReview", [{}])[0].get("url", "")
    )

    response = client.chat.completions.create(
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
                    f'Official Fact Check Claim: "{gfc_claim_text}"\n'
                    f'Official Rating: "{gfc_rating}"'
                ),
            },
        ],
    )

    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {
            "verdict": "UNVERIFIED",
            "summary": "Could not analyze the official fact check data.",
            "confidence_score": 0,
        }


def evaluate_with_tavily(extracted_text, context):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    response = client.chat.completions.create(
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
                    f'Evidence from Live News Search: "{context}"'
                ),
            },
        ],
    )

    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {
            "verdict": "UNVERIFIED",
            "summary": "Could not analyze the evidence from the web search.",
            "confidence_score": 0,
        }


def process_image(raw_base64):
    image_bytes = base64.b64decode(raw_base64)
    pil_img = Image.open(BytesIO(image_bytes))
    image_hash = str(imagehash.phash(pil_img))

    return image_hash, image_bytes
