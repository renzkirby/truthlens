from celery import shared_task
from tavily import TavilyClient
import os
import requests
from django.contrib.auth.models import User
from .ocr_service import extract_text_from_image
from .services import (
    process_image,
    clean_ocr_text,
    clean_extracted_text,
    extract_search_query,
    is_fact_check_relevant,
    evaluate_image_claim_with_gfc,
    evaluate_image_claim_with_tavily,
    evaluate_url_claim_with_gfc,
    evaluate_url_claim_with_tavily,
    detect_ai_image,
)
from .models import Claim, UserProfile
from .trust_service import recompute_user_trust_score

# IMAGE PIPELINE
@shared_task
def snippet_fact_check_process(image_hash, base64_string, claim_id, check_deepfake=False):
    _, image_bytes = process_image(base64_string)

    is_deepfake = False
    ai_prob = 0.0

    # 1. PARALLEL CHECK: Deepfake Detection
    if check_deepfake:
        print("User requested deepfake check. Scanning image...")
        ai_prob = detect_ai_image(image_bytes)
        
        if ai_prob > 0.65:
            print(f"Deepfake detected! Confidence: {ai_prob}")
            is_deepfake = True
            # Update the claim flag in the database, but DO NOT STOP.
            Claim.objects.filter(id=claim_id).update(is_ai_generated=True)
    else:
        print("Skipping AI deepfake check based on user preference.")
        
    # 2. PARALLEL CHECK: OCR
    ocr_result = extract_text_from_image(image_bytes)

    if not ocr_result:
        # If there is no text, BUT it is an AI image, give them a verdict!
        if is_deepfake:
            ai_verdict = {
                "verdict": "MISLEADING",
                "summary": f"This image contains no verifiable text, but forensic analysis indicates with {int(ai_prob * 100)}% confidence that the image itself is AI-generated.",
                "confidence_score": int(ai_prob * 100)
            }
            _save_claim(claim_id, ai_verdict, "AI Deepfake Detector", "AI Generated Image")
        else:
            # No text and not a deepfake = delete it.
            Claim.objects.filter(id=claim_id).delete()
        return

    print("Image processed successfully. Passing to Core Text Pipeline...")
    # 3. Hand off the text to the fact-checker!
    execute_core_text_pipeline(ocr_result, claim_id)

# TEXT PIPELINE
@shared_task
def text_fact_check_process(raw_text, claim_id):
    print(f"Received raw text. Passing to Core Text Pipeline...")
    
    execute_core_text_pipeline(raw_text, claim_id)
    
def execute_core_text_pipeline(raw_text, claim_id):
    """The shared brain for both Snippets and pure Text claims."""
    try:
        cleaned = clean_ocr_text(raw_text)

        if cleaned.get("cleaned_claim") == "OUT_OF_SCOPE":
            Claim.objects.filter(id=claim_id).delete()
            return

        cleaned_claim = cleaned.get("cleaned_claim")
        search_query = cleaned.get("search_query")
        article_stance = cleaned.get("article_stance", "NEUTRAL")

        # Try GFC first — return early if relevant result found
        try:
            gfc_response = requests.get(
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
                params={
                    "query": search_query,
                    "key": os.environ.get("FACT_CHECK_API_KEY"),
                },
            )
            gfc_data = gfc_response.json()
            gfc_claims = gfc_data.get("claims", [])

            if gfc_claims:
                first_claim_text = gfc_claims[0].get("text", "")
                if is_fact_check_relevant(cleaned_claim, first_claim_text):
                    ai_verdict = evaluate_image_claim_with_gfc(cleaned_claim, gfc_data, article_stance)
                    source_url = (
                        gfc_claims[0]
                        .get("claimReview", [{}])[0]
                        .get("url", "")
                    )
                    _save_claim(claim_id, ai_verdict, "Official Fact Check", cleaned_claim, source_url)
                    return

        except Exception as e:
            print(f"GFC error: {str(e)}")

        # Fallback — Tavily web search
        try:
            tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
            tavily_response = tavily_client.search(
                query=search_query,
                search_depth="advanced",
                topic="general",
                include_answer=True,
            )
            tavily_results = tavily_response.get("results", [])
            tavily_answer = tavily_response.get("answer", "No additional web context found.")
            
            # FIXED: Changed ocr_result to raw_text
            combined_context = f"Original Source Text:\n{raw_text}\n\nWeb Search Context:\n{tavily_answer}"
            
            ai_verdict = evaluate_image_claim_with_tavily(cleaned_claim, combined_context, article_stance)
            source_url = tavily_results[0].get("url", "") if tavily_results else ""
            _save_claim(claim_id, ai_verdict, "Live Web Search", cleaned_claim, source_url)

        except Exception as e:
            print(f"Tavily error: {str(e)}")
            _save_claim(claim_id, {
                "verdict": "UNVERIFIED",
                "summary": "Could not retrieve relevant information to verify the claim.",
                "confidence_score": 0,
            }, "Live Web Search", cleaned_claim, "")

    # This catches catastrophic errors (like Groq going down completely)
    except Exception as e:
        print(f"Core Fact Check Error (Fatal): {e}")
        try:
            claim = Claim.objects.get(id=claim_id)
            claim.verdict = "UNVERIFIED"
            claim.ai_verdict = "UNVERIFIED"
            # Keep moderator verdict channel empty until moderator or consensus sets it.
            claim.final_verdict = None
            claim.ai_summary = "An error occurred during analysis."
            claim.save()
        except Claim.DoesNotExist:
            pass

# URL PIPELINE
@shared_task
def url_fact_check_process(url, claim_id):
    # Step 1 — Extract and clean text from URL
    SATIRE_DOMAINS = ["theonion.com", "babylonbee.com", "adobochronicles.com"]
        
    print(f"URL received: {url}")
    print(f"Satire check: {any(domain in url.lower() for domain in SATIRE_DOMAINS)}")


    if any(domain in url.lower() for domain in SATIRE_DOMAINS):
        _save_claim(claim_id, {
                "verdict": "SATIRE",
                "summary": "This content originates from a known satire or parody publication and is not intended to be factual.",
                "confidence_score": 99,
            }, "Satire Detection", url, url)
        return
    try:
        response = requests.post(
            "https://api.tavily.com/extract",
            headers={"Authorization": f"Bearer {os.environ.get('TAVILY_API_KEY')}"},
            json={"urls": [url]},
        )
        tavily_data = response.json()

        if not tavily_data.get("results"):
            Claim.objects.filter(id=claim_id).delete()
            return

        raw_text = tavily_data["results"][0]["raw_content"]
        cleaned_text = clean_extracted_text(raw_text)

        

        result = extract_search_query(cleaned_text, url)

        cleaned_claim = result.get("cleaned_claim")
        search_query = result.get("search_query")
        article_stance = result.get("article_stance", "NEUTRAL")

    except Exception as e:
        print(f"URL extraction error: {str(e)}")
        Claim.objects.filter(id=claim_id).delete()
        return

    # Step 2 — OUT_OF_SCOPE check
    if not cleaned_claim or cleaned_claim == "OUT_OF_SCOPE":
        Claim.objects.filter(id=claim_id).delete()
        return
    if article_stance == "SATIRE":
        _save_claim(claim_id, {
            "verdict": "SATIRE",
            "summary": "This content originates from a known satire or parody publication and is not intended to be factual.",
            "confidence_score": 99,
        }, "Satire Detection", cleaned_claim, url)
        return

    # Step 3 — Try GFC first, return early if relevant
    try:
        gfc_response = requests.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={
                "query": search_query[:200],
                "key": os.environ.get("FACT_CHECK_API_KEY"),
            },
        )
        gfc_data = gfc_response.json()
        gfc_claims = gfc_data.get("claims", [])

        if gfc_claims:
            first_claim_text = gfc_claims[0].get("text", "")
            if is_fact_check_relevant(cleaned_claim, first_claim_text):
                ai_verdict = evaluate_url_claim_with_gfc(cleaned_claim, gfc_data, article_stance)
                _save_claim(claim_id, ai_verdict, "Official Fact Check", cleaned_text, url)
                return

    except Exception as e:
        print(f"GFC error: {str(e)}")

    # Step 4 — Fallback to Tavily web search
    try:
        tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
        search_response = tavily_client.search(
            query=search_query[:300],
            search_depth="advanced",
            topic="general",
            include_answer=True,
        )
        tavily_answer = search_response.get("answer", "No additional web context found.")
        combined_context = f"Original Article Content:\n{cleaned_text[:1500]}\n\nWeb Search Context:\n{tavily_answer}"
        ai_verdict = evaluate_url_claim_with_tavily(cleaned_claim, combined_context, article_stance)
        _save_claim(claim_id, ai_verdict, "Live Web Search", cleaned_text, url)

    except Exception as e:
        print(f"Tavily search error: {str(e)}")
        _save_claim(claim_id, {
            "verdict": "UNVERIFIED",
            "summary": "Could not retrieve relevant information to verify the claim.",
            "confidence_score": 0,
        }, "Live Web Search", cleaned_text, url)


def _save_claim(claim_id, verdict, source_type, context_text, source_url=""):
    """Save AI analysis output to the Claim record without setting final moderator verdict."""
    from .claim_matching import compute_fingerprint

    try:
        claim = Claim.objects.get(id=claim_id)
        ai_verdict_value = verdict.get("verdict")
        claim.ai_verdict = ai_verdict_value
        # Keep final_verdict reserved for moderator or verified-evidence consensus decisions.
        claim.verdict = ai_verdict_value
        claim.ai_summary = verdict.get("summary")
        claim.score_context = verdict.get("score_context")
        
        confidence = verdict.get("confidence_score", 0)
        if ai_verdict_value == "UNVERIFIED" and (confidence == 0 or confidence is None):
            confidence = 40
        claim.consensus_score = confidence
        claim.source_type = source_type
        claim.context_text = context_text
        claim.source_link = source_url or None
        claim.verified_via = Claim.VerificationSource.AI_EXTENSION

        # Compute fingerprint if not already set (e.g., text claims where
        # context_text is only available after OCR/extraction)
        if not claim.claim_fingerprint:
            if claim.claim_type == "IMAGE" and claim.media_hash:
                claim.claim_fingerprint = compute_fingerprint("IMAGE", claim.media_hash)
            elif claim.claim_type == "URL" and claim.url_link:
                claim.claim_fingerprint = compute_fingerprint("URL", claim.url_link)
            elif context_text:
                claim.claim_fingerprint = compute_fingerprint("TEXT", context_text)

        # Compute semantic embedding if context_text exists and not already set
        if context_text and not claim.claim_embedding:
            from .embedding_service import generate_embedding
            try:
                embedding = generate_embedding(context_text)
                if embedding:
                    claim.claim_embedding = embedding
            except Exception as e:
                print(f"Failed to generate embedding during _save_claim: {e}")

        claim.save()
        print(
            f"Claim {claim_id} saved — ai_verdict: {claim.ai_verdict}, final_verdict: {claim.final_verdict}, fingerprint: {claim.claim_fingerprint}"
        )
    except Claim.DoesNotExist:
        print(f"Claim {claim_id} not found — skipping save")
    except Exception as e:
        print(f"Save failed for claim {claim_id}: {str(e)}")
        import traceback
        traceback.print_exc()

@shared_task
def update_contributor_trust_score(contributor_id, evidence_status=None):
    """Backward-compatible task entrypoint; now recalculates trust from the full formula."""
    try:
        recompute_user_trust_score(contributor_id)
    except User.DoesNotExist:
        return


@shared_task
def recompute_user_trust_score_task(user_id):
    try:
        recompute_user_trust_score(user_id)
    except User.DoesNotExist:
        return