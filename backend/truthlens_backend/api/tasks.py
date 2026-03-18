from celery import shared_task
from .ocr_service import extract_text_from_image
from .services import *
from tavily import TavilyClient
from .models import Claim
import os
import requests


@shared_task
def snippet_fact_check_process(image_hash, base64_string, claim_id):
    # Decode the base64 string and convert it to bytes
    _, image_bytes = process_image(base64_string)
    ocr_result = extract_text_from_image(image_bytes)

    if not ocr_result:
        return {"error": "No text detected in the image"}

    cleaned_text = clean_ocr_text(ocr_result)

    if cleaned_text.get("cleaned_claim") == "OUT_OF_SCOPE":
        Claim.objects.filter(id=claim_id).delete()
        return

    else:

        # Try with Google's Fact Check Tools API first
        try:
            api_url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
            payload = {
                "query": cleaned_text.get("search_query"),
                "key": os.environ.get("FACT_CHECK_API_KEY"),
            }

            response = requests.get(api_url, params=payload)
            fact_check_data = response.json()

            print("Google's Response:", fact_check_data)
        except Exception as e:
            print("Error calling Google's Fact Check Tools API:", str(e))
            fact_check_data = {}

        if fact_check_data.get("claims"):
            first_claim_text = fact_check_data["claims"][0].get("text", "")

            if is_fact_check_relevant(
                cleaned_text.get("cleaned_claim"), first_claim_text
            ):
                ai_verdict = evaluate_image_claim_with_gfc(
                    cleaned_text.get("cleaned_claim"), fact_check_data
                )
                context_data = {
                    "summary": ai_verdict.get("summary"),
                    "verdict": ai_verdict.get("verdict"),
                    "confidence_score": ai_verdict.get("confidence_score"),
                    "source": fact_check_data.get("claims", [])
                    .get("claimReview", [{}])[0]
                    .get("url", "No source URL"),
                }
                source_type = "Official Fact Check"
            else:
                fact_check_data = {}

        # If Google's Fact Check Tools API doesn't return relevant results, try Tavily
        if not fact_check_data.get("claims"):
            try:
                tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
                tavily_response = tavily_client.search(
                    query=cleaned_text.get("search_query"),
                    search_depth="advanced",
                    topic="news",
                    days=3,
                    include_answer=False,
                )

                tavily_results = tavily_response.get("results", [])
                ai_verdict = evaluate_image_claim_with_tavily(
                    cleaned_text.get("cleaned_claim"), tavily_results
                )

                print(ai_verdict)

                context_data = {
                    "summary": ai_verdict.get("summary"),
                    "verdict": ai_verdict.get("verdict"),
                    "confidence_score": ai_verdict.get("confidence_score"),
                    "source": (
                        tavily_results[0].get("url")
                        if tavily_results
                        else "No source found"
                    ),
                }
                source_type = "Live Web Search"
            except Exception as e:
                print("Error calling Tavily API:", str(e))
                context_data = {
                    "summary": "Could not retrieve relevant information from the web to verify the claim.",
                    "verdict": "UNVERIFIED",
                    "confidence_score": 0,
                    "source": "N/A"
                }
                source_type = "Live Web Search"

        claim = Claim.objects.get(id=claim_id)
        claim.verdict = context_data.get("verdict")
        claim.ai_summary = context_data.get("summary")
        claim.consensus_score = context_data.get("confidence_score")
        claim.verified_via = Claim.VerificationSource.AI_EXTENSION
        claim.source_type = source_type
        claim.context_text = cleaned_text.get("cleaned_claim")
        claim.top_verdict_source = context_data.get("source")

        claim.save()

#URL FactCheck
@shared_task
def url_fact_check_process(url, claim_id):
    #extract content
    try:
        print("Starting Tavily extract...")  # tets
        response = requests.post(
            "https://api.tavily.com/extract",
            headers={"Authorization": f"Bearer {os.environ.get("TAVILY_API_KEY")}"},
            json={"urls": [url]},
        )

        print(f"Tavily response: {response.status_code}")  # test
        print(f"Tavily data: {response.json()}")  # test
        tavily_data = response.json()

        if not tavily_data.get("results"):
            return { "error": "Could not extract content from this URL. Try a news article instead." }
        
        raw_text = tavily_data["results"][0]["raw_content"]
        cleaned_text = clean_extracted_text(raw_text)      # regex cleaner first
        result = extract_search_query(cleaned_text)         # then AI extracts the claim
    
        cleaned_claim = result["cleaned_claim"]             # full sentence — for AI analysis
        search_query = result["search_query"]               # short query — for searching

        print(f"Raw Text Length: {len(raw_text)} characters")

        print(f"Cleaned claim text: {cleaned_claim}")

    except Exception as e:
        print(f"Tavily extract error: {str(e)}")  # test
        return {"error": f"Text extraction failed: {str(e)}"}
    
    #GFC
    if cleaned_claim == "OUT_OF_SCOPE":
        Claim.objects.filter(id=claim_id).delete()
        return
    else:
        try:
            fact_check_response = requests.get(
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
                params={
                    "query": search_query[:200],
                    "key": os.environ.get("FACT_CHECK_API_KEY"),
                },
            )

            gfc_data = fact_check_response.json()
            claims = gfc_data.get("claims", [])

            if claims:
                first_claim_text = claims[0].get("text", "")
                print(f"GFC Found a claim: {first_claim_text[:100]}...")

                if is_fact_check_relevant(cleaned_claim, first_claim_text):
                    print("GFC result is relevant, evaluating")

                    #AI Analysis
                    verdict = evaluate_url_claim_with_gfc(cleaned_claim, gfc_data)

                    context_data = {
                            "verdict": verdict.get("verdict"),
                            "summary": verdict.get("summary"),
                            "confidence_score": verdict.get("confidence_score"),
                            "source_type": "Official Fact Check",
                            "source_url": url,
                        }
                else:
                    print("GFC result not relevant, falling through to web search...")
            else:
                print("No claims found in GFC")

        except Exception as e:
            print(f"GFC error: {str(e)}")
            
        #Tavily
        try:
            print("Searching trough tavily....")

            tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

            search_response = tavily_client.search(
                query=search_query[:300],
                search_depth="advanced",
                topic="news",
                include_answer=True,
            )

            context = search_response.get("answer", "No additional context found")
            print(f"Tavily search context: {context[:200]}")

        except Exception as e:
            print(f"Search error: {str(e)}")
            context = "Could not retrieve additional context"

        #AI Analysis
        try:
            print("Running Groq Analysis...")

            verdict = evaluate_url_claim_with_tavily(cleaned_claim, context)
            print(f"AI verdict: {verdict}")

            context_data ={
                    "verdict": verdict.get("verdict"),
                    "summary": verdict.get("summary"),
                    "confidence_score": verdict.get("confidence_score"),
                    "source_type": "Live Web Search",
                    "source_url": url,
                }

        except Exception as e:
            print(f"Groq error: {str(e)}")
            return {"error": f"AI analysis failed: {str(e)}"}
        
        
        claim = Claim.objects.get(id=claim_id)
        claim.verdict = context_data.get("verdict")
        claim.ai_summary = context_data.get("summary")
        claim.consensus_score = context_data.get("confidence_score")
        claim.verified_via = Claim.VerificationSource.AI_EXTENSION
        claim.source_type = context_data.get("source_type")
        claim.context_text = cleaned_text
