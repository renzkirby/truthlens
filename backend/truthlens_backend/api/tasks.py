from celery import shared_task
from tavily import TavilyClient
import os
import logging
import time
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
    search_official_vault,
)
from .models import Claim, UserProfile
from .trust_service import recompute_user_trust_score


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


DEFAULT_HTTP_TIMEOUT_SEC = _float_env("DEFAULT_HTTP_TIMEOUT_SEC", 12.0)
SUPABASE_MEDIA_FETCH_TIMEOUT_SEC = _float_env("SUPABASE_MEDIA_FETCH_TIMEOUT_SEC", 15.0)
GFC_HTTP_TIMEOUT_SEC = _float_env("GFC_HTTP_TIMEOUT_SEC", DEFAULT_HTTP_TIMEOUT_SEC)
TAVILY_EXTRACT_TIMEOUT_SEC = _float_env("TAVILY_EXTRACT_TIMEOUT_SEC", 20.0)


def _elapsed_ms(started_at):
    return int((time.perf_counter() - started_at) * 1000)


def _log_stage(claim_id, stage, started_at, **metadata):
    details = " ".join(
        f"{key}={value}" for key, value in metadata.items() if value is not None
    )
    message = f"PIPELINE_STAGE claim_id={claim_id} stage={stage} duration_ms={_elapsed_ms(started_at)}"
    if details:
        message = f"{message} {details}"
    logger.info(message)

# IMAGE PIPELINE
@shared_task
def snippet_fact_check_process(image_hash, claim_id, check_deepfake=False):
    task_started_at = time.perf_counter()
    outcome = "completed"

    # _, image_bytes = process_image(base64_string)

    try:
        claim = Claim.objects.get(id=claim_id)
    except Claim.DoesNotExist:
        outcome = "claim_missing"
        logger.warning("Claim %s not found.", claim_id)
        _log_stage(claim_id, "snippet_task_total", task_started_at, outcome=outcome)
        return

    media_fetch_started_at = time.perf_counter()
    try:
        logger.info("Downloading image from Supabase: %s", claim.media_url)
        response = requests.get(claim.media_url, timeout=SUPABASE_MEDIA_FETCH_TIMEOUT_SEC)
        response.raise_for_status()
        image_bytes = response.content
        _log_stage(
            claim_id,
            "fetch_media",
            media_fetch_started_at,
            status_code=response.status_code,
            bytes=len(image_bytes),
        )
    except requests.RequestException as exc:
        outcome = "media_fetch_failed"
        logger.error("Media download failed for claim %s: %s", claim_id, exc)
        _save_claim(
            claim_id,
            {
                "verdict": "UNVERIFIED",
                "summary": "Could not retrieve the submitted image for analysis.",
                "confidence_score": 0,
            },
            "System Error",
            "Image retrieval failed",
            "",
        )
        _log_stage(claim_id, "fetch_media_failed", media_fetch_started_at, error=str(exc)[:120])
        _log_stage(claim_id, "snippet_task_total", task_started_at, outcome=outcome)
        return

    is_deepfake = False
    ai_prob = 0.0

    # 1. PARALLEL CHECK: Deepfake Detection
    if check_deepfake:
        deepfake_started_at = time.perf_counter()
        logger.info("User requested deepfake check. Scanning image...")
        ai_prob = detect_ai_image(image_bytes)
        _log_stage(
            claim_id,
            "deepfake_detection",
            deepfake_started_at,
            ai_probability=round(ai_prob, 4),
        )
        
        if ai_prob > 0.65:
            logger.info("Deepfake detected for claim %s with confidence %.4f", claim_id, ai_prob)
            is_deepfake = True
            # Update the claim flag in the database, but DO NOT STOP.
            Claim.objects.filter(id=claim_id).update(is_ai_generated=True)
    else:
        logger.info("Skipping AI deepfake check based on user preference.")
        
    # 2. PARALLEL CHECK: OCR
    ocr_started_at = time.perf_counter()
    ocr_result = extract_text_from_image(image_bytes)
    _log_stage(claim_id, "ocr", ocr_started_at, text_length=len(ocr_result or ""))

    if not ocr_result:
        # If there is no text, BUT it is an AI image, give them a verdict!
        if is_deepfake:
            ai_verdict = {
                "verdict": "MISLEADING",
                "summary": f"This image contains no verifiable text, but forensic analysis indicates with {int(ai_prob * 100)}% confidence that the image itself is AI-generated.",
                "confidence_score": int(ai_prob * 100)
            }
            _save_claim(claim_id, ai_verdict, "AI Deepfake Detector", "AI Generated Image")
            outcome = "no_text_deepfake_verdict"
        else:
            # No text and not a deepfake = delete it.
            Claim.objects.filter(id=claim_id).delete()
            outcome = "no_text_deleted"

        _log_stage(claim_id, "ocr_no_text", ocr_started_at, outcome=outcome)
        _log_stage(claim_id, "snippet_task_total", task_started_at, outcome=outcome)
        return

    logger.info("Image processed successfully. Passing to Core Text Pipeline...")
    # 3. Hand off the text to the fact-checker!
    core_pipeline_started_at = time.perf_counter()
    execute_core_text_pipeline(ocr_result, claim_id)
    _log_stage(claim_id, "execute_core_text_pipeline", core_pipeline_started_at)
    _log_stage(claim_id, "snippet_task_total", task_started_at, outcome=outcome)

# TEXT PIPELINE
@shared_task
def text_fact_check_process(raw_text, claim_id):
    task_started_at = time.perf_counter()
    logger.info("Received raw text. Passing to Core Text Pipeline...")
    
    execute_core_text_pipeline(raw_text, claim_id)
    _log_stage(claim_id, "text_task_total", task_started_at, text_length=len(raw_text or ""))
    
def execute_core_text_pipeline(raw_text, claim_id):
    """The shared brain for both Snippets and pure Text claims."""
    pipeline_started_at = time.perf_counter()
    outcome = "completed"

    try:
        clean_started_at = time.perf_counter()
        cleaned = clean_ocr_text(raw_text)
        _log_stage(claim_id, "clean_ocr_text", clean_started_at, text_length=len(raw_text or ""))

        if cleaned.get("cleaned_claim") == "OUT_OF_SCOPE":
            Claim.objects.filter(id=claim_id).delete()
            outcome = "out_of_scope_deleted"
            return

        cleaned_claim = cleaned.get("cleaned_claim")
        search_query = cleaned.get("search_query")
        article_stance = cleaned.get("article_stance", "NEUTRAL")

        vault_started_at = time.perf_counter()
        vault_match = search_official_vault(cleaned_claim)

        if vault_match:
            logger.info(f"Vault match found for claim {claim_id}!")
            
            # We found a highly similar past rumor. Now we ask Gemini to evaluate the NEW claim 
            # against the VERIFIED vault context to avoid the "Negation Trap".
            vault_eval_started_at = time.perf_counter()
            ai_verdict = evaluate_image_claim_with_gfc(
                cleaned_claim, 
                {
                    "claims": [{
                        "text": vault_match["canonical_claim"],
                        "claimReview": [{
                            "textualRating": vault_match["verdict"],
                            "publisher": {"name": "TruthLens Official Vault"}
                        }]
                    }]
                }, 
                article_stance
            )
            
            _save_claim(
                claim_id, 
                ai_verdict, 
                "TruthLens Verified Vault", 
                vault_match["summary"], 
                vault_match.get("sources", [])
            )
            
            _log_stage(claim_id, "vault_search_success", vault_started_at)
            outcome = "completed_vault"
            return

        # Try GFC first — return early if relevant result found
        gfc_started_at = time.perf_counter()
        try:
            gfc_response = requests.get(
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
                params={
                    "query": search_query,
                    "key": os.environ.get("FACT_CHECK_API_KEY"),
                },
                timeout=GFC_HTTP_TIMEOUT_SEC,
            )
            gfc_data = gfc_response.json()
            gfc_claims = gfc_data.get("claims", [])
            _log_stage(
                claim_id,
                "gfc_search",
                gfc_started_at,
                status_code=gfc_response.status_code,
                claims=len(gfc_claims),
            )

            if gfc_claims:
                first_claim_text = gfc_claims[0].get("text", "")
                relevance_started_at = time.perf_counter()
                is_relevant = is_fact_check_relevant(cleaned_claim, first_claim_text)
                _log_stage(
                    claim_id,
                    "gfc_relevance_check",
                    relevance_started_at,
                    relevant=is_relevant,
                )
                if is_relevant:
                    gfc_eval_started_at = time.perf_counter()
                    ai_verdict = evaluate_image_claim_with_gfc(cleaned_claim, gfc_data, article_stance)
                    _log_stage(
                        claim_id,
                        "gfc_llm_evaluation",
                        gfc_eval_started_at,
                        verdict=ai_verdict.get("verdict"),
                    )
                    source_urls = []
                    for c in gfc_claims[:3]:
                        review_url = c.get("claimReview", [{}])[0].get("url", "")
                        if review_url:
                            source_urls.append(review_url)

                    save_started_at = time.perf_counter()
                    _save_claim(claim_id, ai_verdict, "Official Fact Check", cleaned_claim, source_urls)
                    _log_stage(claim_id, "save_claim", save_started_at, source_type="Official Fact Check")
                    outcome = "completed_gfc"
                    return

        except Exception as e:
            _log_stage(claim_id, "gfc_search_failed", gfc_started_at, error=str(e)[:120])
            print(f"GFC error: {str(e)}")

        # Fallback — Tavily web search
        tavily_started_at = time.perf_counter()
        try:
            tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
            tavily_response = tavily_client.search(
                query=search_query,
                search_depth="advanced",
                topic="general",
                include_answer=True,
                include_domains=[
                    # Philippine News & Fact Checkers
                    "gmanetwork.com", "rappler.com", "philstar.com", 
                    "inquirer.net", "news.abs-cbn.com", "manilabulletin.com",
                    "bworldonline.com", "pna.gov.ph", "verafiles.org",
                    
                    # International News & Wires
                    "reuters.com", "apnews.com", "bbc.com", "cnn.com", 
                    "aljazeera.com", "nytimes.com", "theguardian.com",
                    
                    # Global Fact-Checkers
                    "snopes.com", "politifact.com", "factcheck.org", "afp.com"
                ]
            )
            tavily_results = tavily_response.get("results", [])
            tavily_answer = tavily_response.get("answer", "No additional web context found.")
            _log_stage(claim_id, "tavily_search", tavily_started_at, results=len(tavily_results))
            
            # BUILD RICHER CONTEXT: Give the AI the top 3 actual articles to read
            results_context = ""
            for i, res in enumerate(tavily_results[:3]):
                results_context += f"Source {i+1}: {res.get('title', 'No Title')}\nURL: {res.get('url', '')}\nContent: {res.get('content', '')}\n\n"

            # FIXED: Renamed the label to prevent circular reasoning
            combined_context = f"Text Extracted From Image (Do NOT use this as evidence to prove itself):\n{raw_text}\n\nWeb Search Answer:\n{tavily_answer}\n\nTop Search Results:\n{results_context}"

            tavily_eval_started_at = time.perf_counter()
            ai_verdict = evaluate_image_claim_with_tavily(cleaned_claim, combined_context, article_stance)
            _log_stage(
                claim_id,
                "tavily_llm_evaluation",
                tavily_eval_started_at,
                verdict=ai_verdict.get("verdict"),
            )

            source_urls = [
                {
                    "url": res.get("url"),
                    "title": res.get("title", "External Source"),
                    "snippet": res.get("content", "")[:250] + "..." # Grab the first 250 characters
                }
                for res in tavily_results[:3] if res.get("url")
            ]

            save_started_at = time.perf_counter()
            _save_claim(claim_id, ai_verdict, "Live Web Search", cleaned_claim, source_urls)
            _log_stage(claim_id, "save_claim", save_started_at, source_type="Live Web Search")
            outcome = "completed_tavily"

        except Exception as e:
            _log_stage(claim_id, "tavily_search_failed", tavily_started_at, error=str(e)[:120])
            print(f"Tavily error: {str(e)}")
            _save_claim(claim_id, {
                "verdict": "UNVERIFIED",
                "summary": "Could not retrieve relevant information to verify the claim.",
                "confidence_score": 0,
            }, "Live Web Search", cleaned_claim, [])
            outcome = "completed_tavily_fallback_unverified"

    # This catches catastrophic errors (like Groq going down completely)
    except Exception as e:
        outcome = "fatal_error"
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
    finally:
        _log_stage(claim_id, "core_text_pipeline_total", pipeline_started_at, outcome=outcome)

# URL PIPELINE
@shared_task
def url_fact_check_process(url, claim_id):
    pipeline_started_at = time.perf_counter()
    outcome = "completed"

    # Step 1 — Extract and clean text from URL
    if article_stance == "SATIRE":
        _save_claim(claim_id, {
            "verdict": "SATIRE",
            "summary": "This content originates from a known satire publication and is not intended to be factual.",
            "confidence_score": 99,
        }, "Satire Detection", cleaned_claim, url)
        outcome = "satire_stance_shortcut"
        _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
        return

    url_extract_started_at = time.perf_counter()
    try:
        response = requests.post(
            "https://api.tavily.com/extract",
            headers={"Authorization": f"Bearer {os.environ.get('TAVILY_API_KEY')}"},
            json={"urls": [url]},
            timeout=TAVILY_EXTRACT_TIMEOUT_SEC,
        )
        tavily_data = response.json()
        _log_stage(
            claim_id,
            "tavily_extract",
            url_extract_started_at,
            status_code=response.status_code,
            has_results=bool(tavily_data.get("results")),
        )

        if not tavily_data.get("results"):
            Claim.objects.filter(id=claim_id).delete()
            outcome = "url_extract_empty_deleted"
            _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
            return

        raw_text = tavily_data["results"][0]["raw_content"]
        cleaned_text = clean_extracted_text(raw_text)

        query_extract_started_at = time.perf_counter()
        result = extract_search_query(cleaned_text, url)
        _log_stage(claim_id, "extract_search_query", query_extract_started_at)

        cleaned_claim = result.get("cleaned_claim")
        search_query = result.get("search_query")
        article_stance = result.get("article_stance", "NEUTRAL")

    except Exception as e:
        print(f"URL extraction error: {str(e)}")
        _log_stage(claim_id, "url_extract_failed", url_extract_started_at, error=str(e)[:120])
        Claim.objects.filter(id=claim_id).delete()
        outcome = "url_extraction_failed_deleted"
        _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
        return

    # Step 2 — OUT_OF_SCOPE check
    if cleaned.get("cleaned_claim") == "OUT_OF_SCOPE":
            logger.info("Claim is out of scope. Saving rejection verdict.")
            _save_claim(
                claim_id,
                {
                    "verdict": "OUT_OF_SCOPE",
                    "summary": "This content appears to be a personal statement, opinion, greeting, or non-factual text. TruthLens can only verify objective claims, news, and rumors.",
                    "confidence_score": 0,
                    "score_context": "No verifiable factual claim detected."
                },
                "System Filter",
                raw_text,
                []
            )
            outcome = "completed_out_of_scope"
            return
    if article_stance == "SATIRE":
        _save_claim(claim_id, {
            "verdict": "SATIRE",
            "summary": "This content originates from a known satire or parody publication and is not intended to be factual.",
            "confidence_score": 99,
        }, "Satire Detection", cleaned_claim, url)
        outcome = "satire_stance_shortcut"
        _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
        return

    vault_started_at = time.perf_counter()
    vault_match = search_official_vault(cleaned_claim)
    
    if vault_match:
        logger.info(f"Vault match found for URL claim {claim_id}!")
        
        # We inject the vault data into the Gemini prompt to avoid the Negation Trap
        vault_eval_started_at = time.perf_counter()
        ai_verdict = evaluate_url_claim_with_gfc(
            cleaned_claim, 
            {
                "claims": [{
                    "text": vault_match["canonical_claim"],
                    "claimReview": [{
                        "textualRating": vault_match["verdict"],
                        "publisher": {"name": "TruthLens Official Vault"}
                    }]
                }]
            }, 
            article_stance
        )
        
        _save_claim(
            claim_id, 
            ai_verdict, 
            "TruthLens Verified Vault", 
            vault_match["summary"], 
            vault_match.get("sources", [])
        )
        
        _log_stage(claim_id, "url_vault_search_success", vault_started_at)
        outcome = "completed_vault"
        _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
        return

    # Step 3 — Try GFC first, return early if relevant
    gfc_started_at = time.perf_counter()
    try:
        gfc_response = requests.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={
                "query": search_query[:200],
                "key": os.environ.get("FACT_CHECK_API_KEY"),
            },
            timeout=GFC_HTTP_TIMEOUT_SEC,
        )
        gfc_data = gfc_response.json()
        gfc_claims = gfc_data.get("claims", [])
        _log_stage(
            claim_id,
            "url_gfc_search",
            gfc_started_at,
            status_code=gfc_response.status_code,
            claims=len(gfc_claims),
        )

        if gfc_claims:
            first_claim_text = gfc_claims[0].get("text", "")
            relevance_started_at = time.perf_counter()
            is_relevant = is_fact_check_relevant(cleaned_claim, first_claim_text)
            _log_stage(claim_id, "url_gfc_relevance_check", relevance_started_at, relevant=is_relevant)
            if is_relevant:
                gfc_eval_started_at = time.perf_counter()
                ai_verdict = evaluate_url_claim_with_gfc(cleaned_claim, gfc_data, article_stance)
                _log_stage(
                    claim_id,
                    "url_gfc_llm_evaluation",
                    gfc_eval_started_at,
                    verdict=ai_verdict.get("verdict"),
                )

                source_urls = []
                for c in gfc_claims[:3]:
                    review_url = c.get("claimReview", [{}])[0].get("url", "")
                    if review_url:
                        source_urls.append(review_url)

                save_started_at = time.perf_counter()
                _save_claim(claim_id, ai_verdict, "Official Fact Check", cleaned_text, source_urls)
                _log_stage(claim_id, "save_claim", save_started_at, source_type="Official Fact Check")
                outcome = "completed_gfc"
                _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
                return

    except Exception as e:
        _log_stage(claim_id, "url_gfc_failed", gfc_started_at, error=str(e)[:120])
        print(f"GFC error: {str(e)}")

    # Step 4 — Fallback to Tavily web search
    tavily_search_started_at = time.perf_counter()
    try:
        tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
        search_response = tavily_client.search(
            query=search_query[:300],
            search_depth="advanced",
            topic="general",
            include_answer=True,
            include_domains=[
                    "gmanetwork.com", "rappler.com", "philstar.com", 
                    "inquirer.net", "news.abs-cbn.com", "manilabulletin.com",
                    "bworldonline.com", "pna.gov.ph"
                ]
        )

        tavily_results = search_response.get("results", [])
        tavily_answer = search_response.get("answer", "No additional web context found.")
        _log_stage(claim_id, "url_tavily_search", tavily_search_started_at, results=len(tavily_results))

        # BUILD RICHER CONTEXT: Give the AI the top 3 actual articles to read
        results_context = ""
        for i, res in enumerate(tavily_results[:3]):
            results_context += f"Source {i+1}: {res.get('title', 'No Title')}\nURL: {res.get('url', '')}\nContent: {res.get('content', '')}\n\n"

        # FIXED: Renamed the label to prevent circular reasoning
        combined_context = f"Original URL Content to Verify (Do NOT use this as evidence to prove itself):\n{cleaned_text[:1500]}\n\nWeb Search Answer:\n{tavily_answer}\n\nTop Search Results:\n{results_context}"
        tavily_eval_started_at = time.perf_counter()
        ai_verdict = evaluate_url_claim_with_tavily(cleaned_claim, combined_context, article_stance)
        _log_stage(
            claim_id,
            "url_tavily_llm_evaluation",
            tavily_eval_started_at,
            verdict=ai_verdict.get("verdict"),
        )
        
        source_urls = [
            {
                "url": res.get("url"),
                "title": res.get("title", "External Source"),
                "snippet": res.get("content", "")[:250] + "..." 
            }
            for res in tavily_results[:3] if res.get("url")
        ]

        save_started_at = time.perf_counter()
        _save_claim(claim_id, ai_verdict, "Live Web Search", cleaned_text, source_urls)
        _log_stage(claim_id, "save_claim", save_started_at, source_type="Live Web Search")
        outcome = "completed_tavily"

    except Exception as e:
        _log_stage(claim_id, "url_tavily_failed", tavily_search_started_at, error=str(e)[:120])
        print(f"Tavily search error: {str(e)}")
        _save_claim(claim_id, {
            "verdict": "UNVERIFIED",
            "summary": "Could not retrieve relevant information to verify the claim.",
            "confidence_score": 0,
        }, "Live Web Search", cleaned_text, [])
        outcome = "completed_tavily_fallback_unverified"
    finally:
        _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)


def _save_claim(claim_id, verdict, source_type, context_text, source_urls=None):
    """Save AI analysis output to the Claim record without setting final moderator verdict."""
    from .claim_matching import compute_fingerprint

    if source_urls is None:
        source_urls = []
    elif isinstance(source_urls, str):
        source_urls = [source_urls]

    top_url = source_urls[0] if source_urls else (verdict.get("source_url") or "")

    try:
        claim = Claim.objects.get(id=claim_id)
        ai_verdict_value = verdict.get("verdict")
        claim.ai_verdict = ai_verdict_value
        # Keep final_verdict reserved for moderator or verified-evidence consensus decisions.
        claim.verdict = ai_verdict_value
        claim.ai_summary = verdict.get("summary")
        claim.ai_reasoning = verdict.get("reasoning")
        claim.score_context = verdict.get("score_context")
        
        confidence = verdict.get("confidence_score", 0)
        if ai_verdict_value == "UNVERIFIED" and (confidence == 0 or confidence is None):
            confidence = 40
        claim.consensus_score = confidence
        claim.source_type = source_type
        claim.context_text = context_text
        claim.source_link = top_url or None
        claim.top_verdict_source = top_url or None
        claim.ai_sources = source_urls
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