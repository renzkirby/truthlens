"""
Claim Matching & Resolution Cache Service
══════════════════════════════════════════
Provides fingerprint computation and claim deduplication logic.

Exact-Match Fingerprinting
  - IMAGE claims: perceptual hash (pHash) with Hamming distance tolerance
  - URL claims: normalized URL → SHA-256
  - TEXT claims: normalized text → SHA-256

When a new claim arrives, we compute its fingerprint and check the database
for existing claims with the same (or near-matching) fingerprint. If a match
is found that has been resolved by a moderator, we return the cached verdict
immediately — saving AI/API costs and giving the user an instant answer.
"""

import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from django.db.models import Q
from pgvector.django import CosineDistance

from .embedding_service import generate_embedding


def compute_fingerprint(claim_type, data):
    """
    Compute a canonical fingerprint for a claim based on its type.

    Args:
        claim_type: One of "IMAGE", "URL", "TEXT"
        data: The raw data to fingerprint:
              - IMAGE: the media_hash (pHash hex string)
              - URL: the raw URL string
              - TEXT: the raw claim text

    Returns:
        str: A fingerprint string, or None if data is insufficient.
    """
    if not data:
        return None

    if claim_type == "IMAGE":
        return _fingerprint_image(data)
    elif claim_type == "URL":
        return _fingerprint_url(data)
    elif claim_type == "TEXT":
        return _fingerprint_text(data)
    return None


def _fingerprint_image(media_hash):
    """
    For images, the pHash IS the fingerprint.
    We store it directly so we can do Hamming distance comparisons later.
    """
    if not media_hash or len(media_hash) < 4:
        return None
    return f"img:{media_hash}"


def _fingerprint_url(raw_url):
    """
    Normalize a URL to a canonical form, then hash it.
    Strips: fragments, tracking params (utm_*, fbclid, etc.), trailing slashes.
    Lowercases scheme and host.
    """
    if not raw_url:
        return None

    TRACKING_PARAMS = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "source", "ref_src", "ref_url",
    }

    parsed = urlparse(raw_url.strip())
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/") or "/"

    # Filter out tracking query params
    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {
        k: v for k, v in sorted(query_params.items())
        if k.lower() not in TRACKING_PARAMS
    }
    clean_query = urlencode(filtered, doseq=True)

    normalized = urlunparse((scheme, host, path, "", clean_query, ""))
    url_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"url:{url_hash}"


def _fingerprint_text(raw_text):
    """
    Normalize text and hash it for exact-match deduplication.
    Normalization: lowercase, collapse whitespace, strip punctuation.
    """
    if not raw_text or len(raw_text.strip()) < 10:
        return None

    normalized = raw_text.lower().strip()
    # Collapse all whitespace to single spaces
    normalized = re.sub(r"\s+", " ", normalized)
    # Remove common punctuation that varies across copies
    normalized = re.sub(r"[^\w\s]", "", normalized)

    text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"txt:{text_hash}"


def _hamming_distance(hash1, hash2):
    """
    Compute the Hamming distance between two hex-encoded pHash strings.
    Each hex char = 4 bits, so we convert to integers and count differing bits.
    """
    try:
        int1 = int(hash1, 16)
        int2 = int(hash2, 16)
        return bin(int1 ^ int2).count("1")
    except (ValueError, TypeError):
        return 999  # Return large distance on error


def find_semantic_match(embedding, claim_type="TEXT", threshold=0.85):
    """
    Search for a semantically similar claim using cosine distance.
    Returns the best match that has a cosine similarity > threshold.
    Similarity = 1 - CosineDistance. So we look for distance < (1 - threshold).
    """
    from .models import Claim

    if not embedding:
        return None

    max_distance = 1.0 - threshold

    candidates = (
        Claim.objects
        .exclude(claim_embedding__isnull=True)
        .filter(claim_type=claim_type)
        .annotate(distance=CosineDistance("claim_embedding", embedding))
        .filter(distance__lt=max_distance)
        .prefetch_related("threads")
        .order_by("distance", "-last_updated")
    )

    # Prioritization: resolved -> thread -> any match
    resolved = candidates.filter(final_verdict__isnull=False).first()
    if resolved:
        return resolved

    with_thread = candidates.filter(threads__isnull=False).distinct().first()
    if with_thread:
        return with_thread

    # Just return whatever is closest
    return candidates.first()


def find_matching_claim(fingerprint, claim_type, hamming_threshold=5, context_text=None, semantic_threshold=0.80):
    """
    Search the database for an existing claim that matches the given fingerprint or text.

    Matching logic:
      - For IMAGE claims: exact fingerprint match OR Hamming distance ≤ threshold
      - For URL claims: exact fingerprint match only
      - For TEXT claims: exact fingerprint match OR semantic similarity > threshold

    Returns the best matching Claim object, prioritizing:
      1. Claims with a final_verdict (moderator-resolved) — most recent first
      2. Claims with an active community thread — most recent first
      3. Claims with an AI verdict — most recent first

    Returns None if no match found.
    """
    from .models import Claim  # Local import to avoid circular dependency

    # --- 1. Exact fingerprint match (all types) ---
    if fingerprint:
        exact_matches = (
            Claim.objects
            .filter(claim_fingerprint=fingerprint)
            .select_related()
            .prefetch_related("threads")
            .order_by("-last_updated")
        )

        # Prioritize: resolved claims first, then claims with threads, then any
        resolved = exact_matches.filter(final_verdict__isnull=False).first()
        if resolved:
            return resolved

        with_thread = exact_matches.filter(threads__isnull=False).distinct().first()
        if with_thread:
            return with_thread

        any_match = exact_matches.first()
        if any_match:
            return any_match

    # --- 2. Near-match for IMAGE claims (Hamming distance) ---
    if claim_type == "IMAGE" and fingerprint and fingerprint.startswith("img:"):
        incoming_hash = fingerprint[4:]  # Strip "img:" prefix
        image_candidates = (
            Claim.objects
            .filter(
                claim_type="IMAGE",
                claim_fingerprint__startswith="img:",
            )
            .exclude(claim_fingerprint=fingerprint)
            .prefetch_related("threads")
            .order_by("-last_updated")
        )

        best_match = None
        best_distance = hamming_threshold + 1

        for candidate in image_candidates[:200]:
            candidate_hash = candidate.claim_fingerprint[4:]
            distance = _hamming_distance(incoming_hash, candidate_hash)
            if distance <= hamming_threshold and distance < best_distance:
                best_distance = distance
                best_match = candidate

        if best_match:
            return best_match

    # --- 3. Semantic similarity match for TEXT/URL claims (Phase 2 Fallback) ---
    # Only applies if we have context_text and didn't find an exact match above
    if claim_type in ["TEXT", "URL"] and context_text:
        print(f"No exact match found for {claim_type}. Generating embedding for semantic check...")
        embedding = generate_embedding(context_text)
        if embedding:
            semantic_match = find_semantic_match(embedding, claim_type, semantic_threshold)
            if semantic_match:
                print(f"Semantic match found! (Threshold {semantic_threshold}) -> Claim ID: {semantic_match.id}")
                return semantic_match
            else:
                print("No semantic match found above threshold.")

    return None


def get_match_result(matched_claim):
    """
    Format the match result for API response.

    Returns a dict with:
      - match_type: "resolved", "has_thread", or "has_verdict"
      - claim_id: matched claim UUID
      - verdict: the effective verdict
      - summary: AI or moderator summary
      - thread_id: first active thread ID (if any)
      - moderator_notes: notes from moderator (if resolved)
    """
    if not matched_claim:
        return None

    threads = list(matched_claim.threads.exclude(status="REJECTED").order_by("-created_at"))
    active_thread = threads[0] if threads else None

    # Determine the effective verdict
    effective_verdict = matched_claim.final_verdict or matched_claim.ai_verdict or matched_claim.verdict

    result = {
        "match_type": "no_verdict",
        "claim_id": str(matched_claim.id),
        "claim_type": matched_claim.claim_type,
        "verdict": effective_verdict,
        "ai_verdict": matched_claim.ai_verdict,
        "final_verdict": matched_claim.final_verdict,
        "summary": matched_claim.ai_summary,
        "confidence_score": matched_claim.consensus_score,
        "source_type": matched_claim.source_type,
        "source_url": matched_claim.top_verdict_source or matched_claim.source_link,
        "is_ai_generated": matched_claim.is_ai_generated,
        "thread_id": str(active_thread.id) if active_thread else None,
        "thread_status": active_thread.status if active_thread else None,
        "moderator_notes": None,
    }

    if matched_claim.final_verdict:
        result["match_type"] = "resolved"
        # Get moderator notes from the resolved thread
        resolved_thread = matched_claim.threads.filter(
            moderator_verdict__isnull=False
        ).order_by("-moderated_at").first()
        if resolved_thread:
            result["moderator_notes"] = resolved_thread.moderator_notes
            result["summary"] = resolved_thread.moderator_notes or matched_claim.ai_summary
    elif active_thread:
        result["match_type"] = "has_thread"
    elif effective_verdict:
        result["match_type"] = "has_verdict"

    return result
