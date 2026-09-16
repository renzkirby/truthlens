from celery import shared_task
import math
import os
import logging
import time
import requests
import base64
from numbers import Number
from django.contrib.auth.models import User
from .ocr_service import extract_text_from_image
from .services import (
    ClaimGateError,
    LLMProviderUnavailableError,
    process_image,
    clean_ocr_text,
    clean_extracted_text,
    extract_search_query,
    is_fact_check_relevant,
    evaluate_claim_with_persisted_evidence,
    evaluate_image_claim_with_gfc,
    evaluate_image_claim_with_tavily,
    evaluate_url_claim_with_gfc,
    evaluate_url_claim_with_tavily,
    detect_ai_image,
    search_official_vault,
)
from .models import (
    Claim,
    OfficialFactCheck,
    UserProfile,
    VerificationEvidence,
)
from .trust_service import recompute_user_trust_score
from .verification.evidence_assessment import (
    assess_reasoning_evidence_batch_against_claim,
)
from .verification.evidence_dossier import (
    filter_reasoning_evidence_dossier_by_role,
    load_reasoning_evidence_dossier_for_run,
    render_reasoning_evidence_dossier,
)
from .verification.evidence_enrichment import persist_evidence_assessment
from .verification.ingestion import ingest_raw_evidence
from .verification.linking import link_evidence_sources_to_run
from .verification.providers.google_fact_check import (
    GoogleFactCheckProvider,
)
from .verification.providers.tavily import TavilyProvider
from .verification.runs import (
    abstain_verification_run,
    complete_verification_run,
    create_verification_run,
    fail_verification_run,
    start_verification_run,
)

logger = logging.getLogger(__name__)


class ClaimPersistenceError(RuntimeError):
    """Raised when automated analysis cannot be persisted to a Claim."""


def _float_env(name, default):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid %s value '%s'; using default %.2f", name, raw_value, default
        )
        return default


DEFAULT_HTTP_TIMEOUT_SEC = _float_env("DEFAULT_HTTP_TIMEOUT_SEC", 12.0)
SUPABASE_MEDIA_FETCH_TIMEOUT_SEC = _float_env("SUPABASE_MEDIA_FETCH_TIMEOUT_SEC", 15.0)
GFC_HTTP_TIMEOUT_SEC = _float_env("GFC_HTTP_TIMEOUT_SEC", DEFAULT_HTTP_TIMEOUT_SEC)
TAVILY_EXTRACT_TIMEOUT_SEC = _float_env("TAVILY_EXTRACT_TIMEOUT_SEC", 20.0)


def _retrieve_and_ingest_gfc(
    search_query,
    claim_id,
    *,
    stage_prefix="",
    verification_run=None,
):
    """
    Retrieve Google Fact Check data once and persist the parsed
    evidence without making a second provider request.

    Evidence persistence is best-effort during runtime wiring:
    a persistence failure must not discard otherwise usable GFC
    data or change the existing verdict path.
    """

    provider = GoogleFactCheckProvider(
        timeout=GFC_HTTP_TIMEOUT_SEC,
    )

    payload, raw_evidence_items = (
        provider.search_with_payload(
            search_query,
            limit=5,
        )
    )

    ingestion_started_at = time.perf_counter()
    stage_name = (
        f"{stage_prefix}gfc_evidence_ingestion"
    )

    try:
        evidence_sources = ingest_raw_evidence(
            raw_evidence_items
        )

        _log_stage(
            claim_id,
            stage_name,
            ingestion_started_at,
            evidence_sources=len(
                evidence_sources
            ),
        )

    except Exception as exc:
        _log_stage(
            claim_id,
            f"{stage_name}_failed",
            ingestion_started_at,
            error=str(exc)[:120],
        )

        logger.error(
            "GFC evidence ingestion failed "
            "for claim %s: %s",
            claim_id,
            exc,
        )
    else:
        if verification_run is not None:
            linking_started_at = time.perf_counter()
            linking_stage = f"{stage_prefix}gfc_evidence_linking"
            try:
                links = link_evidence_sources_to_run(
                    verification_run,
                    evidence_sources,
                    evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
                )
                _log_stage(
                    claim_id,
                    linking_stage,
                    linking_started_at,
                    verification_run_id=verification_run.pk,
                    evidence_links=len(links),
                )
            except Exception as exc:
                _log_stage(
                    claim_id,
                    f"{linking_stage}_failed",
                    linking_started_at,
                    verification_run_id=verification_run.pk,
                    error=str(exc)[:120],
                )
                logger.error(
                    "GFC evidence linking failed for claim %s, run %s: %s",
                    claim_id,
                    verification_run.pk,
                    exc,
                )

    return payload


def _retrieve_and_ingest_tavily(
    search_query, claim_id, *, stage_prefix="", verification_run=None,
):
    """Retrieve once, preserving usable payloads if evidence persistence fails."""
    provider = TavilyProvider(timeout=DEFAULT_HTTP_TIMEOUT_SEC)
    payload, raw_evidence_items = provider.search_with_payload(search_query, limit=5)

    ingestion_started_at = time.perf_counter()
    try:
        evidence_sources = ingest_raw_evidence(raw_evidence_items)
    except Exception as exc:
        _log_stage(
            claim_id,
            f"{stage_prefix}tavily_evidence_ingestion_failed",
            ingestion_started_at,
            error=str(exc)[:120],
        )
        logger.error(
            "Tavily evidence ingestion failed for claim %s: %s",
            claim_id,
            exc,
        )
    else:
        _log_stage(
            claim_id,
            f"{stage_prefix}tavily_evidence_ingestion",
            ingestion_started_at,
            evidence_sources=len(evidence_sources),
        )

        if verification_run is not None:
            linking_started_at = time.perf_counter()
            linking_stage = f"{stage_prefix}tavily_evidence_linking"
            try:
                links = link_evidence_sources_to_run(
                    verification_run,
                    evidence_sources,
                    evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
                )
                _log_stage(
                    claim_id,
                    linking_stage,
                    linking_started_at,
                    verification_run_id=verification_run.pk,
                    evidence_links=len(links),
                )
            except Exception as exc:
                _log_stage(
                    claim_id,
                    f"{linking_stage}_failed",
                    linking_started_at,
                    verification_run_id=verification_run.pk,
                    error=str(exc)[:120],
                )
                logger.error(
                    "Tavily evidence linking failed for claim %s, run %s: %s",
                    claim_id,
                    verification_run.pk,
                    exc,
                )

    return payload


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


def _assess_and_persist_reasoning_evidence(
    claim_text,
    evidence_groups,
    claim_id,
    *,
    stage_prefix,
):
    stage_name = f"{stage_prefix}_evidence_assessment"
    eligible_items = []
    for evidence_group in evidence_groups:
        for evidence_item in evidence_group.evidence:
            if (
                evidence_item.stance != VerificationEvidence.Stance.UNKNOWN
                or evidence_item.relevance_score is not None
                or evidence_item.directness_score is not None
            ):
                continue
            eligible_items.append(evidence_item)

    if not eligible_items:
        return

    assessment_started_at = time.perf_counter()
    try:
        assessments = assess_reasoning_evidence_batch_against_claim(
            claim_text,
            eligible_items,
        )
    except Exception as exc:
        _log_stage(
            claim_id,
            f"{stage_prefix}_evidence_assessment_batch",
            assessment_started_at,
            eligible_items=len(eligible_items),
            outcome="assessment_failed",
            error=str(exc)[:120],
        )
        logger.error(
            "Evidence assessment failed for claim %s (batch): %s",
            claim_id,
            exc,
        )
        return

    _log_stage(
        claim_id,
        f"{stage_prefix}_evidence_assessment_batch",
        assessment_started_at,
        eligible_items=len(eligible_items),
    )

    for evidence_item, assessment in zip(eligible_items, assessments):
        persistence_started_at = time.perf_counter()
        try:
            persisted = persist_evidence_assessment(evidence_item, assessment)
        except Exception as exc:
            _log_stage(
                claim_id,
                stage_name,
                persistence_started_at,
                evidence_link_id=evidence_item.evidence_link_id,
                outcome="persistence_failed",
                error=str(exc)[:120],
            )
            logger.error(
                "Evidence assessment persistence failed for claim %s, "
                "link %s: %s",
                claim_id,
                evidence_item.evidence_link_id,
                exc,
            )
            continue

        _log_stage(
            claim_id,
            stage_name,
            persistence_started_at,
            evidence_link_id=evidence_item.evidence_link_id,
            persisted=persisted,
        )


# IMAGE PIPELINE
@shared_task
def snippet_fact_check_process(
    image_hash, claim_id, check_deepfake=False, base64_string=None
):
    task_started_at = time.perf_counter()
    outcome = "completed"

    try:
        claim = Claim.objects.get(id=claim_id)
    except Claim.DoesNotExist:
        outcome = "claim_missing"
        logger.warning("Claim %s not found.", claim_id)
        _log_stage(claim_id, "snippet_task_total", task_started_at, outcome=outcome)
        return

    media_fetch_started_at = time.perf_counter()
    image_bytes = None
    if base64_string:
        try:
            image_bytes = base64.b64decode(base64_string)
            _log_stage(
                claim_id,
                "fetch_media",
                media_fetch_started_at,
                status_code=200,
                bytes=len(image_bytes),
                source="base64_payload",
            )
        except Exception as exc:
            logger.error("Failed to decode provided base64 string: %s", exc)

    if not image_bytes:
        try:
            logger.info("Downloading image from Supabase: %s", claim.media_url)
            response = requests.get(
                claim.media_url, timeout=SUPABASE_MEDIA_FETCH_TIMEOUT_SEC
            )
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
            _log_stage(
                claim_id,
                "fetch_media_failed",
                media_fetch_started_at,
                error=str(exc)[:120],
            )
            _log_stage(claim_id, "snippet_task_total", task_started_at, outcome=outcome)
            return

    is_deepfake = False
    ai_prob = 0.0

    # 1. PARALLEL CHECK: Deepfake Detection
    if check_deepfake:
        deepfake_started_at = time.perf_counter()
        deepfake_result = detect_ai_image(image_bytes)
        ai_prob = deepfake_result.get("score", 0.0) if deepfake_result else 0.0
        fake_category = (
            deepfake_result.get("category", "Unknown") if deepfake_result else "Unknown"
        )
        _log_stage(
            claim_id,
            "deepfake_detection",
            deepfake_started_at,
            ai_probability=round(ai_prob, 4),
        )

        if ai_prob > 0.65:
            logger.info(
                "Deepfake detected for claim %s with confidence %.4f", claim_id, ai_prob
            )
            is_deepfake = True
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
                "summary": f"This image contains no verifiable text, but forensic analysis indicates with {int(ai_prob * 100)}% confidence that the image itself is AI-generated ({fake_category}).",
                "confidence_score": int(ai_prob * 100),
            }
            _save_claim(
                claim_id, ai_verdict, "AI Deepfake Detector", "AI Generated Image"
            )
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
    _log_stage(
        claim_id, "text_task_total", task_started_at, text_length=len(raw_text or "")
    )


def execute_core_text_pipeline(raw_text, claim_id):
    """The shared brain for both Snippets and pure Text claims."""

    # --- 1. SECOND CHANCE TEXT DEDUPLICATION ---

    pipeline_started_at = time.perf_counter()

    # Missing claims retain the existing runtime path without a lifecycle record.
    run_claim = Claim.objects.filter(id=claim_id).first()
    run = None
    if run_claim is not None:
        run = create_verification_run(run_claim)
        run = start_verification_run(run)

    selected_verdict = None
    pipeline_error = None
    runtime_error_propagating = False
    try:
        from .claim_matching import compute_fingerprint, find_matching_claim

        text_fingerprint = compute_fingerprint("TEXT", raw_text)
        matched_claim = find_matching_claim(
            text_fingerprint,
            "TEXT",
            context_text=raw_text,
            allow_semantic_fallback=False,
        )

        if matched_claim and str(matched_claim.id) != str(claim_id):
            logger.info(
                "Second-chance deduplication hit! OCR text matches existing claim %s ",
                matched_claim.id,
            )

            try:
                current_claim = Claim.objects.get(id=claim_id)
                # Reuse prior automated analysis without copying an
                # authoritative human decision onto a distinct Claim.
                current_claim.ai_verdict = matched_claim.ai_verdict
                current_claim.ai_summary = matched_claim.ai_summary
                current_claim.consensus_score = matched_claim.consensus_score
                current_claim.source_type = matched_claim.source_type
                current_claim.source_link = matched_claim.source_link
                current_claim.top_verdict_source = matched_claim.top_verdict_source
                current_claim.ai_sources = matched_claim.ai_sources
                current_claim.is_ai_generated = matched_claim.is_ai_generated
                current_claim.score_context = (
                    "This result was matched from a prior analysis of the same claim."
                )
                current_claim.save(
                    update_fields=[
                        "ai_verdict",
                        "ai_summary",
                        "consensus_score",
                        "source_type",
                        "source_link",
                        "top_verdict_source",
                        "ai_sources",
                        "is_ai_generated",
                        "score_context",
                        "last_updated",
                    ]
                )
            except Claim.DoesNotExist:
                pass

            selected_verdict = matched_claim.ai_verdict

            # ABORT the pipeline so we don't waste LLM/Tavily API calls!
            return
        # -------------------------------------------

        outcome = "completed"

        try:
            clean_started_at = time.perf_counter()
            cleaned = clean_ocr_text(raw_text)
            _log_stage(
                claim_id,
                "clean_ocr_text",
                clean_started_at,
                text_length=len(raw_text or ""),
            )

            cleaned_claim = cleaned.get("cleaned_claim")
            search_query = cleaned.get("search_query")
            article_stance = cleaned.get("article_stance", "NEUTRAL")

            if cleaned_claim == "OUT_OF_SCOPE":
                logger.info("Claim %s was gated as out of scope.", claim_id)
                outcome = "abstained_out_of_scope"
                selected_verdict = "OUT_OF_SCOPE"
                _log_stage(
                    claim_id,
                    "core_text_pipeline_total",
                    pipeline_started_at,
                    outcome=outcome,
                )
                return

            if article_stance == "SATIRE":
                _save_claim(
                    claim_id,
                    {
                        "verdict": "SATIRE",
                        "summary": "This content originates from a known satire or parody publication and is not intended to be factual.",
                        "confidence_score": 99,
                    },
                    "Satire Detection",
                    cleaned_claim,
                    [],
                )
                outcome = "satire_stance_shortcut"
                selected_verdict = "SATIRE"
                _log_stage(
                    claim_id,
                    "core_text_pipeline_total",
                    pipeline_started_at,
                    outcome=outcome,
                )
                return

            vault_started_at = time.perf_counter()
            target_claim = Claim.objects.filter(id=claim_id).first()

            vault_match = search_official_vault(
                cleaned_claim,
                target_claim=target_claim,
            )

            if vault_match:
                logger.info("Vault match found for claim %s!", claim_id)

                # We found a highly similar past rumor. Now we ask Gemini to evaluate the NEW claim
                # against the VERIFIED vault context to avoid the "Negation Trap".
                vault_eval_started_at = time.perf_counter()
                ai_verdict = evaluate_image_claim_with_gfc(
                    cleaned_claim,
                    {
                        "claims": [
                            {
                                "text": vault_match["canonical_claim"],
                                "claimReview": [
                                    {
                                        "textualRating": vault_match["verdict"],
                                        "publisher": {"name": "TruthLens Official Vault"},
                                    }
                                ],
                            }
                        ]
                    },
                    article_stance,
                )

                _save_claim(
                    claim_id,
                    ai_verdict,
                    "TruthLens Verified Vault",
                    vault_match["summary"],
                    vault_match.get("sources", []),
                )

                _log_stage(claim_id, "vault_search_success", vault_started_at)
                outcome = "completed_vault"
                selected_verdict = (
                    ai_verdict.get("verdict") if isinstance(ai_verdict, dict) else None
                )
                return

            # Try GFC first — return early if relevant result found
            gfc_started_at = time.perf_counter()
            gfc_claims = []
            is_relevant = False

            try:
                gfc_data = _retrieve_and_ingest_gfc(
                    search_query,
                    claim_id,
                    verification_run=run,
                )

                gfc_claims = gfc_data.get(
                    "claims",
                    [],
                )
                _log_stage(
                    claim_id,
                    "gfc_search",
                    gfc_started_at,
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
            except Exception as e:
                _log_stage(
                    claim_id, "gfc_search_failed", gfc_started_at, error=str(e)[:120]
                )
                logger.error("GFC error for claim %s: %s", claim_id, e)

            if gfc_claims and is_relevant:
                gfc_eval_started_at = time.perf_counter()
                if run is None:
                    ai_verdict = evaluate_image_claim_with_gfc(
                        cleaned_claim,
                        gfc_data,
                        article_stance,
                    )
                    has_persisted_evidence = True
                else:
                    evidence_dossier = load_reasoning_evidence_dossier_for_run(run)
                    fact_check_groups = filter_reasoning_evidence_dossier_by_role(
                        evidence_dossier,
                        VerificationEvidence.EvidenceRole.FACT_CHECK,
                    )
                    if fact_check_groups:
                        _assess_and_persist_reasoning_evidence(
                            cleaned_claim,
                            fact_check_groups,
                            claim_id,
                            stage_prefix="gfc",
                        )
                        evidence_dossier = load_reasoning_evidence_dossier_for_run(
                            run
                        )
                        fact_check_groups = (
                            filter_reasoning_evidence_dossier_by_role(
                                evidence_dossier,
                                VerificationEvidence.EvidenceRole.FACT_CHECK,
                            )
                        )
                    evidence_context = render_reasoning_evidence_dossier(
                        fact_check_groups
                    )
                    has_persisted_evidence = bool(evidence_context)
                    if has_persisted_evidence:
                        try:
                            ai_verdict = evaluate_claim_with_persisted_evidence(
                                cleaned_claim,
                                evidence_context,
                                article_stance,
                            )
                        except LLMProviderUnavailableError:
                            raise
                        except Exception as exc:
                            has_persisted_evidence = False
                            _log_stage(
                                claim_id,
                                "gfc_llm_evaluation_failed",
                                gfc_eval_started_at,
                                error=str(exc)[:120],
                            )
                            logger.error(
                                "GFC persisted-evidence evaluation failed "
                                "for claim %s: %s",
                                claim_id,
                                exc,
                            )
                    else:
                        _log_stage(
                            claim_id,
                            "gfc_persisted_evidence_unavailable",
                            gfc_eval_started_at,
                            verification_run_id=run.pk,
                        )

                if has_persisted_evidence:
                    _log_stage(
                        claim_id,
                        "gfc_llm_evaluation",
                        gfc_eval_started_at,
                        verdict=ai_verdict.get("verdict"),
                    )
                    source_urls = []
                    for claim_data in gfc_claims[:3]:
                        review_url = claim_data.get("claimReview", [{}])[0].get(
                            "url", ""
                        )
                        if review_url:
                            source_urls.append(review_url)

                    save_started_at = time.perf_counter()
                    _save_claim(
                        claim_id,
                        ai_verdict,
                        "Official Fact Check",
                        cleaned_claim,
                        source_urls,
                    )
                    _log_stage(
                        claim_id,
                        "save_claim",
                        save_started_at,
                        source_type="Official Fact Check",
                    )
                    outcome = "completed_gfc"
                    selected_verdict = (
                        ai_verdict.get("verdict")
                        if isinstance(ai_verdict, dict)
                        else None
                    )
                    return

            # Fallback — Tavily web search
            tavily_started_at = time.perf_counter()
            try:
                tavily_response = _retrieve_and_ingest_tavily(
                    search_query, claim_id, verification_run=run,
                )
            except Exception as e:
                _log_stage(
                    claim_id, "tavily_search_failed", tavily_started_at, error=str(e)[:120]
                )
                logger.error("Tavily error for claim %s: %s", claim_id, e)
                _save_claim(
                    claim_id,
                    {
                        "verdict": "UNVERIFIED",
                        "summary": "Could not retrieve relevant information to verify the claim.",
                        "confidence_score": 0,
                    },
                    "Live Web Search",
                    cleaned_claim,
                    [],
                )
                outcome = "completed_tavily_fallback_unverified"
                selected_verdict = "UNVERIFIED"
            else:
                tavily_results = tavily_response.get("results", [])
                _log_stage(
                    claim_id,
                    "tavily_search",
                    tavily_started_at,
                    results=len(tavily_results),
                )

                source_urls = [
                    {
                        "url": result.get("url"),
                        "title": result.get("title", "External Source"),
                        "snippet": result.get("content", "")[:250] + "...",
                    }
                    for result in tavily_results[:3]
                    if result.get("url")
                ]

                tavily_eval_started_at = time.perf_counter()
                evaluator_invoked = False
                if run is None:
                    tavily_answer = tavily_response.get(
                        "answer", "No additional web context found."
                    )
                    results_context = ""
                    for index, result in enumerate(tavily_results[:3]):
                        results_context += (
                            f"Source {index + 1}: "
                            f"{result.get('title', 'No Title')}\n"
                            f"URL: {result.get('url', '')}\n"
                            f"Content: {result.get('content', '')}\n\n"
                        )
                    combined_context = (
                        "Text Extracted From Image "
                        "(Do NOT use this as evidence to prove itself):\n"
                        f"{raw_text}\n\nWeb Search Answer:\n{tavily_answer}\n\n"
                        f"Top Search Results:\n{results_context}"
                    )
                    evaluator_invoked = True
                    ai_verdict = evaluate_image_claim_with_tavily(
                        cleaned_claim,
                        combined_context,
                        article_stance,
                    )
                else:
                    evidence_dossier = load_reasoning_evidence_dossier_for_run(run)
                    secondary_groups = filter_reasoning_evidence_dossier_by_role(
                        evidence_dossier,
                        VerificationEvidence.EvidenceRole.SECONDARY,
                    )
                    if secondary_groups:
                        _assess_and_persist_reasoning_evidence(
                            cleaned_claim,
                            secondary_groups,
                            claim_id,
                            stage_prefix="tavily",
                        )
                        evidence_dossier = load_reasoning_evidence_dossier_for_run(
                            run
                        )
                        secondary_groups = (
                            filter_reasoning_evidence_dossier_by_role(
                                evidence_dossier,
                                VerificationEvidence.EvidenceRole.SECONDARY,
                            )
                        )
                    evidence_context = render_reasoning_evidence_dossier(
                        secondary_groups
                    )
                    if evidence_context:
                        evaluator_invoked = True
                        ai_verdict = evaluate_claim_with_persisted_evidence(
                            cleaned_claim,
                            evidence_context,
                            article_stance,
                        )
                    else:
                        _log_stage(
                            claim_id,
                            "tavily_persisted_evidence_unavailable",
                            tavily_eval_started_at,
                            verification_run_id=run.pk,
                        )
                        ai_verdict = {
                            "reasoning": (
                                "No persisted Tavily evidence was available for evaluation."
                            ),
                            "verdict": "UNVERIFIED",
                            "summary": (
                                "Could not retrieve persisted evidence to verify the claim."
                            ),
                            "confidence_score": 0,
                            "score_context": (
                                "No persisted secondary evidence was available for verification."
                            ),
                        }

                if evaluator_invoked:
                    _log_stage(
                        claim_id,
                        "tavily_llm_evaluation",
                        tavily_eval_started_at,
                        verdict=ai_verdict.get("verdict"),
                    )
                save_started_at = time.perf_counter()
                _save_claim(
                    claim_id,
                    ai_verdict,
                    "Live Web Search",
                    cleaned_claim,
                    source_urls,
                )
                _log_stage(
                    claim_id,
                    "save_claim",
                    save_started_at,
                    source_type="Live Web Search",
                )
                outcome = "completed_tavily"
                selected_verdict = (
                    ai_verdict.get("verdict")
                    if isinstance(ai_verdict, dict)
                    else None
                )

        except ClaimGateError as e:
            pipeline_error = e
            outcome = "claim_gate_failed"
            logger.error("ClaimGate processing failed for claim %s.", claim_id)
            raise

        except ClaimPersistenceError as e:
            pipeline_error = e
            outcome = "claim_persistence_failed"
            logger.error("Claim persistence failed for claim %s.", claim_id)
            raise

        except LLMProviderUnavailableError as e:
            pipeline_error = e
            outcome = "final_evaluator_unavailable"
            logger.error(
                "Final evaluator unavailable for claim %s.",
                claim_id,
            )
            raise

        # This catches other catastrophic errors.
        except Exception as e:
            pipeline_error = e
            outcome = "fatal_error"
            logger.error("Core Fact Check Fatal Error for claim %s: %s", claim_id, e)
            try:
                claim = Claim.objects.get(id=claim_id)
                claim.ai_verdict = "UNVERIFIED"
                claim.ai_summary = "An error occurred during analysis."
                claim.save(
                    update_fields=[
                        "ai_verdict",
                        "ai_summary",
                        "last_updated",
                    ]
                )
            except Claim.DoesNotExist:
                pass
        finally:
            _log_stage(
                claim_id, "core_text_pipeline_total", pipeline_started_at, outcome=outcome
            )
    except BaseException as exc:
        # Dedup errors historically propagate; retain that behavior and their cause.
        if pipeline_error is None:
            pipeline_error = exc
        runtime_error_propagating = True
        raise
    finally:
        # Keep lifecycle storage errors outside all provider fallback handlers.
        # This is the only terminal dispatch, including for early cache returns.
        if run is not None:
            try:
                if pipeline_error is not None:
                    if isinstance(pipeline_error, ClaimGateError):
                        fail_verification_run(
                            run,
                            failure_stage="claim_gate",
                            failure_code="CLAIM_GATE_FAILED",
                            failure_message=(
                                f"ClaimGate processing failed for claim {claim_id}."
                            ),
                        )
                    elif isinstance(pipeline_error, ClaimPersistenceError):
                        fail_verification_run(
                            run,
                            failure_stage="claim_persistence",
                            failure_code="CLAIM_SAVE_FAILED",
                            failure_message=(
                                f"Claim persistence failed for claim {claim_id}."
                            ),
                        )
                    elif isinstance(pipeline_error, LLMProviderUnavailableError):
                        fail_verification_run(
                            run,
                            failure_stage="final_evaluator",
                            failure_code="LLM_UNAVAILABLE",
                            failure_message=str(pipeline_error),
                        )
                    else:
                        fail_verification_run(
                            run,
                            failure_stage="core_text_pipeline",
                            failure_code="UNHANDLED_EXCEPTION",
                            failure_message=str(pipeline_error),
                        )
                elif selected_verdict in ("FACT", "FAKE", "MISLEADING", "SATIRE"):
                    complete_verification_run(run)
                else:
                    abstain_verification_run(run)
            except Exception:
                if not runtime_error_propagating:
                    raise
                logger.exception(
                    "VerificationRun finalization failed for claim %s; "
                    "preserving the original runtime exception",
                    claim_id,
                )


# URL PIPELINE
@shared_task
def url_fact_check_process(url, claim_id):
    pipeline_started_at = time.perf_counter()
    outcome = "completed"

    # Step 1 — Extract and clean text from URL

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

    except Exception as e:
        logger.error("URL extraction error for claim %s: %s", claim_id, e)
        _log_stage(
            claim_id, "url_extract_failed", url_extract_started_at, error=str(e)[:120]
        )
        Claim.objects.filter(id=claim_id).delete()
        outcome = "url_extraction_failed_deleted"
        _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
        return

    # Extraction failures above delete the claim and must not create a run.
    run_claim = Claim.objects.filter(id=claim_id).first()
    run = None
    if run_claim is not None:
        run = create_verification_run(run_claim)
        run = start_verification_run(run)

    selected_verdict = None
    pipeline_error = None
    runtime_error_propagating = False
    try:
        query_extract_started_at = time.perf_counter()
        result = extract_search_query(cleaned_text, url)
        _log_stage(claim_id, "extract_search_query", query_extract_started_at)

        cleaned_claim = result.get("cleaned_claim")
        search_query = result.get("search_query")
        article_stance = result.get("article_stance", "NEUTRAL")

        # Step 2 — OUT_OF_SCOPE check
        if cleaned_claim == "OUT_OF_SCOPE":
            logger.info("Claim %s was gated as out of scope.", claim_id)
            outcome = "abstained_out_of_scope"
            selected_verdict = "OUT_OF_SCOPE"
            _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
            return

        if article_stance == "SATIRE":
            _save_claim(
                claim_id,
                {
                    "verdict": "SATIRE",
                    "summary": "This content originates from a known satire or parody publication and is not intended to be factual.",
                    "confidence_score": 99,
                },
                "Satire Detection",
                cleaned_claim,
                url,
            )
            outcome = "satire_stance_shortcut"
            selected_verdict = "SATIRE"
            _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
            return

        vault_started_at = time.perf_counter()
        target_claim = Claim.objects.filter(id=claim_id).first()

        vault_match = search_official_vault(
            cleaned_claim,
            target_claim=target_claim,
        )

        if vault_match:
            logger.info("Vault match found for URL claim %s!", claim_id)

            # We inject the vault data into the Gemini prompt to avoid the Negation Trap
            vault_eval_started_at = time.perf_counter()
            ai_verdict = evaluate_url_claim_with_gfc(
                cleaned_claim,
                {
                    "claims": [
                        {
                            "text": vault_match["canonical_claim"],
                            "claimReview": [
                                {
                                    "textualRating": vault_match["verdict"],
                                    "publisher": {"name": "TruthLens Official Vault"},
                                }
                            ],
                        }
                    ]
                },
                article_stance,
            )

            _save_claim(
                claim_id,
                ai_verdict,
                "TruthLens Verified Vault",
                vault_match["summary"],
                vault_match.get("sources", []),
            )

            _log_stage(claim_id, "url_vault_search_success", vault_started_at)
            outcome = "completed_vault"
            selected_verdict = (
                ai_verdict.get("verdict") if isinstance(ai_verdict, dict) else None
            )
            _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
            return

        # Step 3 — Try GFC first, return early if relevant
        gfc_started_at = time.perf_counter()
        gfc_claims = []
        is_relevant = False

        try:
            gfc_data = _retrieve_and_ingest_gfc(
                search_query,
                claim_id,
                stage_prefix="url_",
                verification_run=run,
            )

            gfc_claims = gfc_data.get(
                "claims",
                [],
            )
            _log_stage(
                claim_id,
                "url_gfc_search",
                gfc_started_at,
                claims=len(gfc_claims),
            )

            if gfc_claims:
                first_claim_text = gfc_claims[0].get("text", "")
                relevance_started_at = time.perf_counter()
                is_relevant = is_fact_check_relevant(cleaned_claim, first_claim_text)
                _log_stage(
                    claim_id,
                    "url_gfc_relevance_check",
                    relevance_started_at,
                    relevant=is_relevant,
                )
        except Exception as e:
            _log_stage(claim_id, "url_gfc_failed", gfc_started_at, error=str(e)[:120])
            logger.error("GFC error for claim %s: %s", claim_id, e)

        if gfc_claims and is_relevant:
            gfc_eval_started_at = time.perf_counter()
            evaluation_completed = False
            if run is None:
                try:
                    ai_verdict = evaluate_url_claim_with_gfc(
                        cleaned_claim,
                        gfc_data,
                        article_stance,
                    )
                except Exception as e:
                    _log_stage(
                        claim_id,
                        "url_gfc_failed",
                        gfc_started_at,
                        error=str(e)[:120],
                    )
                    logger.error("GFC error for claim %s: %s", claim_id, e)
                else:
                    evaluation_completed = True
            else:
                evidence_dossier = load_reasoning_evidence_dossier_for_run(run)
                fact_check_groups = filter_reasoning_evidence_dossier_by_role(
                    evidence_dossier,
                    VerificationEvidence.EvidenceRole.FACT_CHECK,
                )
                if fact_check_groups:
                    _assess_and_persist_reasoning_evidence(
                        cleaned_claim,
                        fact_check_groups,
                        claim_id,
                        stage_prefix="url_gfc",
                    )
                    evidence_dossier = load_reasoning_evidence_dossier_for_run(
                        run
                    )
                    fact_check_groups = (
                        filter_reasoning_evidence_dossier_by_role(
                            evidence_dossier,
                            VerificationEvidence.EvidenceRole.FACT_CHECK,
                        )
                    )
                evidence_context = render_reasoning_evidence_dossier(
                    fact_check_groups
                )
                if evidence_context:
                    try:
                        ai_verdict = evaluate_claim_with_persisted_evidence(
                            cleaned_claim,
                            evidence_context,
                            article_stance,
                        )
                    except LLMProviderUnavailableError:
                        raise
                    except Exception as e:
                        _log_stage(
                            claim_id,
                            "url_gfc_llm_evaluation_failed",
                            gfc_eval_started_at,
                            error=str(e)[:120],
                        )
                        logger.error(
                            "URL GFC persisted-evidence evaluation failed "
                            "for claim %s: %s",
                            claim_id,
                            e,
                        )
                    else:
                        evaluation_completed = True
                else:
                    _log_stage(
                        claim_id,
                        "url_gfc_persisted_evidence_unavailable",
                        gfc_eval_started_at,
                        verification_run_id=run.pk,
                    )

            if evaluation_completed:
                _log_stage(
                    claim_id,
                    "url_gfc_llm_evaluation",
                    gfc_eval_started_at,
                    verdict=ai_verdict.get("verdict"),
                )

                source_urls = []
                for claim_data in gfc_claims[:3]:
                    review_url = claim_data.get("claimReview", [{}])[0].get(
                        "url", ""
                    )
                    if review_url:
                        source_urls.append(review_url)

                save_started_at = time.perf_counter()
                _save_claim(
                    claim_id,
                    ai_verdict,
                    "Official Fact Check",
                    cleaned_text,
                    source_urls,
                )
                _log_stage(
                    claim_id,
                    "save_claim",
                    save_started_at,
                    source_type="Official Fact Check",
                )
                outcome = "completed_gfc"
                selected_verdict = (
                    ai_verdict.get("verdict")
                    if isinstance(ai_verdict, dict)
                    else None
                )
                _log_stage(
                    claim_id, "url_task_total", pipeline_started_at, outcome=outcome
                )
                return

        # Step 4 — Fallback to Tavily web search
        tavily_search_started_at = time.perf_counter()
        try:
            search_response = _retrieve_and_ingest_tavily(
                search_query[:300],
                claim_id,
                stage_prefix="url_",
                verification_run=run,
            )
        except Exception as e:
            _log_stage(
                claim_id, "url_tavily_failed", tavily_search_started_at, error=str(e)[:120]
            )
            logger.error("Tavily search error for claim %s: %s", claim_id, e)
            _save_claim(
                claim_id,
                {
                    "verdict": "UNVERIFIED",
                    "summary": "Could not retrieve relevant information to verify the claim.",
                    "confidence_score": 0,
                },
                "Live Web Search",
                cleaned_text,
                [],
            )
            outcome = "completed_tavily_fallback_unverified"
            selected_verdict = "UNVERIFIED"
        else:
            tavily_results = search_response.get("results", [])
            _log_stage(
                claim_id,
                "url_tavily_search",
                tavily_search_started_at,
                results=len(tavily_results),
            )

            source_urls = [
                {
                    "url": result.get("url"),
                    "title": result.get("title", "External Source"),
                    "snippet": result.get("content", "")[:250] + "...",
                }
                for result in tavily_results[:3]
                if result.get("url")
            ]

            tavily_eval_started_at = time.perf_counter()
            evaluator_invoked = False
            if run is None:
                tavily_answer = search_response.get(
                    "answer", "No additional web context found."
                )
                results_context = ""
                for index, result in enumerate(tavily_results[:3]):
                    results_context += (
                        f"Source {index + 1}: "
                        f"{result.get('title', 'No Title')}\n"
                        f"URL: {result.get('url', '')}\n"
                        f"Content: {result.get('content', '')}\n\n"
                    )
                combined_context = (
                    "Original URL Content to Verify "
                    "(Do NOT use this as evidence to prove itself):\n"
                    f"{cleaned_text[:1500]}\n\nWeb Search Answer:\n{tavily_answer}\n\n"
                    f"Top Search Results:\n{results_context}"
                )
                evaluator_invoked = True
                try:
                    ai_verdict = evaluate_url_claim_with_tavily(
                        cleaned_claim,
                        combined_context,
                        article_stance,
                    )
                except Exception as e:
                    _log_stage(
                        claim_id,
                        "url_tavily_failed",
                        tavily_search_started_at,
                        error=str(e)[:120],
                    )
                    logger.error("Tavily search error for claim %s: %s", claim_id, e)
                    _save_claim(
                        claim_id,
                        {
                            "verdict": "UNVERIFIED",
                            "summary": (
                                "Could not retrieve relevant information "
                                "to verify the claim."
                            ),
                            "confidence_score": 0,
                        },
                        "Live Web Search",
                        cleaned_text,
                        [],
                    )
                    outcome = "completed_tavily_fallback_unverified"
                    selected_verdict = "UNVERIFIED"
                    return
            else:
                evidence_dossier = load_reasoning_evidence_dossier_for_run(run)
                secondary_groups = filter_reasoning_evidence_dossier_by_role(
                    evidence_dossier,
                    VerificationEvidence.EvidenceRole.SECONDARY,
                )
                if secondary_groups:
                    _assess_and_persist_reasoning_evidence(
                        cleaned_claim,
                        secondary_groups,
                        claim_id,
                        stage_prefix="url_tavily",
                    )
                    evidence_dossier = load_reasoning_evidence_dossier_for_run(
                        run
                    )
                    secondary_groups = (
                        filter_reasoning_evidence_dossier_by_role(
                            evidence_dossier,
                            VerificationEvidence.EvidenceRole.SECONDARY,
                        )
                    )
                evidence_context = render_reasoning_evidence_dossier(
                    secondary_groups
                )
                if evidence_context:
                    evaluator_invoked = True
                    ai_verdict = evaluate_claim_with_persisted_evidence(
                        cleaned_claim,
                        evidence_context,
                        article_stance,
                    )
                else:
                    _log_stage(
                        claim_id,
                        "url_tavily_persisted_evidence_unavailable",
                        tavily_eval_started_at,
                        verification_run_id=run.pk,
                    )
                    ai_verdict = {
                        "reasoning": (
                            "No persisted Tavily evidence was available for evaluation."
                        ),
                        "verdict": "UNVERIFIED",
                        "summary": (
                            "Could not retrieve persisted evidence to verify the claim."
                        ),
                        "confidence_score": 0,
                        "score_context": (
                            "No persisted secondary evidence was available for verification."
                        ),
                    }

            if evaluator_invoked:
                _log_stage(
                    claim_id,
                    "url_tavily_llm_evaluation",
                    tavily_eval_started_at,
                    verdict=ai_verdict.get("verdict"),
                )
            save_started_at = time.perf_counter()
            _save_claim(claim_id, ai_verdict, "Live Web Search", cleaned_text, source_urls)
            _log_stage(
                claim_id, "save_claim", save_started_at, source_type="Live Web Search"
            )
            outcome = "completed_tavily"
            selected_verdict = (
                ai_verdict.get("verdict") if isinstance(ai_verdict, dict) else None
            )
        finally:
            _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)

    except ClaimGateError as exc:
        pipeline_error = exc
        outcome = "claim_gate_failed"
        runtime_error_propagating = True
        logger.error("ClaimGate processing failed for claim %s.", claim_id)
        _log_stage(claim_id, "url_task_total", pipeline_started_at, outcome=outcome)
        raise
    except BaseException as exc:
        pipeline_error = exc
        runtime_error_propagating = True
        raise
    finally:
        # Finalize once, outside provider fallback handlers and across early returns.
        if run is not None:
            try:
                if pipeline_error is not None:
                    if isinstance(pipeline_error, ClaimGateError):
                        fail_verification_run(
                            run,
                            failure_stage="claim_gate",
                            failure_code="CLAIM_GATE_FAILED",
                            failure_message=(
                                f"ClaimGate processing failed for claim {claim_id}."
                            ),
                        )
                    elif isinstance(pipeline_error, ClaimPersistenceError):
                        fail_verification_run(
                            run,
                            failure_stage="claim_persistence",
                            failure_code="CLAIM_SAVE_FAILED",
                            failure_message=(
                                f"Claim persistence failed for claim {claim_id}."
                            ),
                        )
                    elif isinstance(pipeline_error, LLMProviderUnavailableError):
                        fail_verification_run(
                            run,
                            failure_stage="final_evaluator",
                            failure_code="LLM_UNAVAILABLE",
                            failure_message=str(pipeline_error),
                        )
                    else:
                        fail_verification_run(
                            run,
                            failure_stage="url_fact_check_pipeline",
                            failure_code="UNHANDLED_EXCEPTION",
                            failure_message=str(pipeline_error),
                        )
                elif selected_verdict in ("FACT", "FAKE", "MISLEADING", "SATIRE"):
                    complete_verification_run(run)
                else:
                    abstain_verification_run(run)
            except Exception:
                if not runtime_error_propagating:
                    raise
                logger.exception(
                    "VerificationRun finalization failed for URL claim %s; "
                    "preserving the original runtime exception",
                    claim_id,
                )


def _save_claim(claim_id, verdict, source_type, context_text, source_urls=None):
    """Save AI analysis output to the Claim record without setting final moderator verdict."""
    from .claim_matching import compute_fingerprint

    try:
        if not isinstance(verdict, dict):
            raise TypeError("verdict must be a dictionary")

        if source_urls is None:
            source_urls = []
        elif isinstance(source_urls, str):
            source_urls = [source_urls]

        first = source_urls[0] if source_urls else None
        if isinstance(first, dict):
            top_url = first.get("url", "")
        elif isinstance(first, str):
            top_url = first
        else:
            top_url = verdict.get("source_url") or ""

        ai_verdict_value = verdict.get("verdict")
        if "verdict" in verdict:
            ai_verdict_max_length = Claim._meta.get_field("ai_verdict").max_length
            if ai_verdict_value is not None:
                if not isinstance(ai_verdict_value, str):
                    raise TypeError("verdict value must be a string or None")
                if len(ai_verdict_value) > ai_verdict_max_length:
                    raise ValueError("verdict value exceeds the model field length")

        confidence = verdict.get("confidence_score", 0)
        if isinstance(confidence, bool):
            raise TypeError("confidence score must not be boolean")
        if confidence is None:
            if ai_verdict_value == "UNVERIFIED":
                confidence = 40
        else:
            if not isinstance(confidence, Number):
                raise TypeError("confidence score must be numeric")
            try:
                normalized_confidence = float(confidence)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("confidence score cannot be stored") from exc
            if not math.isfinite(normalized_confidence):
                raise ValueError("confidence score must be finite")
            confidence = normalized_confidence
            if ai_verdict_value == "UNVERIFIED" and confidence == 0:
                confidence = 40

        score_context = verdict.get("score_context")
        if score_context is not None:
            score_context = str(score_context)
            score_context_max_length = Claim._meta.get_field(
                "score_context"
            ).max_length
            original_score_context_length = len(score_context)
            if original_score_context_length > score_context_max_length:
                logger.warning(
                    "Truncating score_context for claim %s from %s to %s characters.",
                    claim_id,
                    original_score_context_length,
                    score_context_max_length,
                )
                score_context = score_context[:score_context_max_length]

        claim = Claim.objects.get(id=claim_id)
        claim.ai_verdict = ai_verdict_value
        # Keep final_verdict reserved for the authoritative adjudication service.
        claim.ai_summary = verdict.get("summary")
        claim.ai_reasoning = verdict.get("reasoning")
        claim.score_context = score_context
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
            except Exception:
                logger.warning(
                    "Failed to generate embedding during _save_claim for claim %s.",
                    claim_id,
                )

        claim.save(
            update_fields=[
                "ai_verdict",
                "ai_summary",
                "ai_reasoning",
                "score_context",
                "consensus_score",
                "source_type",
                "context_text",
                "source_link",
                "top_verdict_source",
                "ai_sources",
                "verified_via",
                "claim_fingerprint",
                "claim_embedding",
                "last_updated",
            ]
        )
        logger.info(
            "Claim %s AI analysis saved — ai_verdict: %s, fingerprint: %s",
            claim_id,
            claim.ai_verdict,
            claim.claim_fingerprint,
        )
        return claim
    except ClaimPersistenceError:
        raise
    except Exception as exc:
        logger.error("Claim persistence failed for claim %s.", claim_id)
        raise ClaimPersistenceError(
            f"Claim persistence failed for claim {claim_id}."
        ) from exc


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


@shared_task
def index_official_fact_check_task(
    fact_check_id,
):
    """
    Generate/update search indexes for a
    published OfficialFactCheck.
    """

    from .knowledge_reuse_service import (
        index_published_fact_check,
    )

    try:
        fact_check = OfficialFactCheck.objects.get(id=fact_check_id)

    except OfficialFactCheck.DoesNotExist:
        logger.warning(
            "OfficialFactCheck %s not found " "during indexing.",
            fact_check_id,
        )

        return False

    try:
        return index_published_fact_check(fact_check)

    except Exception as error:
        logger.exception(
            "Failed to index " "OfficialFactCheck %s: %s",
            fact_check_id,
            error,
        )

        return False
