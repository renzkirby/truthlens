import hashlib
import logging
import math
import re
from dataclasses import dataclass

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
)
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from pgvector.django import CosineDistance

from .embedding_service import (
    generate_embedding,
)
from .models import (
    Claim,
    ClaimFactCheckReference,
    KnowledgeReuseEvent,
    OfficialFactCheck,
)
from .organization_public_presence_service import is_public_partner_eligible
from .public_publication_query_service import (
    PublicPublicationNotFound,
    get_public_partner_fact_check_detail,
)

SEMANTIC_MATCH_THRESHOLD = 0.80
FULL_TEXT_RANK_THRESHOLD = 0.08
_UNSET = object()
logger = logging.getLogger(__name__)


class KnowledgeReuseError(Exception):
    pass


class InvalidKnowledgeReuse(KnowledgeReuseError):
    pass


@dataclass(frozen=True)
class PublishedFactCheckMatch:
    fact_check: OfficialFactCheck
    match_method: str
    similarity_score: float | None = None


def _published_fact_checks():
    """
    Return only currently published articles.

    Draft, in-review, and archived material must
    never become authoritative reusable knowledge.
    """
    return (
        OfficialFactCheck.objects.filter(
            publication_status=(OfficialFactCheck.PublicationStatus.PUBLISHED)
        )
        .select_related(
            "claim",
            "organization",
            "adjudication_decision",
        )
        .prefetch_related(
            "source_items",
        )
    )


def get_published_fact_check_for_claim(
    claim,
):
    """
    Return the current published knowledge
    record for a Claim, if one exists.
    """

    claim_id = getattr(
        claim,
        "pk",
        claim,
    )

    if not claim_id:
        return None

    return (
        _published_fact_checks()
        .filter(claim_id=claim_id)
        .order_by(
            "-version",
            "-published_at",
            "-created_at",
        )
        .first()
    )


def _normalize_query_text(
    text,
):
    if not isinstance(text, str):
        return ""

    return " ".join(text.strip().split())


def build_query_fingerprint(
    query_text,
):
    normalized = _normalize_query_text(query_text).casefold()

    if not normalized:
        return None

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def find_exact_canonical_published_fact_check(query_text):
    """Resolve only one unambiguous deterministic canonical equality match."""
    query_text = _normalize_query_text(query_text)
    if len(query_text) < 10:
        return None

    # Database case-insensitive equality is only the coarse candidate filter.
    # Authority transfer requires Python-level deterministic equality and a
    # single current PUBLISHED publication. If multiple institutions publish
    # the same canonical text, fail closed rather than choosing a winner.
    candidates = (
        _published_fact_checks()
        .filter(canonical_claim__iexact=query_text)
        .order_by("pk")
    )
    deterministic_matches = [
        candidate
        for candidate in candidates
        if (candidate.canonical_claim or "").casefold() == query_text.casefold()
    ]
    if len(deterministic_matches) != 1:
        if len(deterministic_matches) > 1:
            logger.info(
                "Exact canonical publication lookup is ambiguous; "
                "refusing authoritative resolution."
            )
        return None

    fact_check = deterministic_matches[0]
    return PublishedFactCheckMatch(
        fact_check=fact_check,
        match_method=ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL,
        similarity_score=1.0,
    )


def record_authoritative_claim_fact_check_reference(
    *,
    target_claim,
    fact_check,
    query_text,
):
    """Revalidate under locks; write resolution without copying any verdict state."""
    query_text = _normalize_query_text(query_text)
    if len(query_text) < 10:
        raise InvalidKnowledgeReuse("An adequate canonical query is required.")
    if (
        not isinstance(target_claim, Claim)
        or target_claim._state.adding
        or not isinstance(fact_check, OfficialFactCheck)
        or fact_check._state.adding
    ):
        raise InvalidKnowledgeReuse("Persisted target and publication are required.")

    fingerprint = build_query_fingerprint(query_text)
    with transaction.atomic():
        target_claim = Claim.objects.select_for_update(of=("self",)).get(
            pk=target_claim.pk
        )
        # Revalidate the full exact-canonical candidate set while holding
        # locks on the currently matching publication rows. Authority transfer
        # is permitted only when the supplied publication is the sole current
        # PUBLISHED deterministic match.
        publication_candidates = list(
            OfficialFactCheck.objects.select_for_update(of=("self",))
            .filter(
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
                canonical_claim__iexact=query_text,
            )
            .order_by("pk")
        )
        deterministic_matches = [
            candidate
            for candidate in publication_candidates
            if (candidate.canonical_claim or "").casefold() == query_text.casefold()
        ]
        if len(deterministic_matches) != 1:
            return None

        publication = deterministic_matches[0]
        if publication.pk != fact_check.pk:
            return None

        reference, created = ClaimFactCheckReference.objects.get_or_create(
            target_claim=target_claim,
            relationship_kind=ClaimFactCheckReference.RelationshipKind.AUTHORITATIVE,
            defaults={
                "fact_check": publication,
                "match_method": ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL,
                "similarity_score": 1.0,
                "query_fingerprint": fingerprint,
            },
        )
        if (
            reference.fact_check_id != publication.pk
            or reference.match_method
            != ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL
            or reference.query_fingerprint != fingerprint
        ):
            raise InvalidKnowledgeReuse(
                "Target already has a different authoritative resolution."
            )

    if created:
        try:
            # A savepoint also isolates database analytics errors from caller transactions.
            with transaction.atomic():
                record_knowledge_reuse(
                    fact_check=publication,
                    target_claim=target_claim,
                    reuse_type=KnowledgeReuseEvent.ReuseType.VERIFICATION_CONTEXT,
                    match_method=KnowledgeReuseEvent.MatchMethod.EXACT_TEXT,
                    similarity_score=1.0,
                    query_text=query_text,
                    metadata={"source": "EXACT_CANONICAL_RESOLUTION"},
                )
        except Exception:
            logger.warning("Failed to record exact canonical reuse analytics.")
    return reference


def record_equivalent_claim_fact_check_reference(
    *,
    target_claim,
    query_text,
    fact_check=None,
    published_canonical_claim=None,
    similarity_score=_UNSET,
):
    """
    Resolve and persist one unambiguous equivalent publication without copying
    any factual verdict into the target Claim.

    ``fact_check`` and ``published_canonical_claim`` remain optional compatibility
    assertions for internal/test callers; they never select the authoritative
    publication. The publication is selected only by the bounded multi-candidate
    equivalence assessment above.
    """
    query_text = _normalize_query_text(query_text)
    if len(query_text) < 10:
        raise InvalidKnowledgeReuse("An adequate incoming claim is required.")
    if not isinstance(target_claim, Claim) or target_claim._state.adding:
        raise InvalidKnowledgeReuse("A persisted target claim is required.")
    if target_claim.claim_type not in (Claim.ClaimType.IMAGE, Claim.ClaimType.URL):
        return None

    if fact_check is not None and (
        not isinstance(fact_check, OfficialFactCheck) or fact_check._state.adding
    ):
        raise InvalidKnowledgeReuse("A persisted publication is required.")
    if published_canonical_claim is not None and not isinstance(
        published_canonical_claim, str
    ):
        raise InvalidKnowledgeReuse("Published canonical claim must be text.")

    if similarity_score is not _UNSET and similarity_score is not None:
        similarity_score = float(similarity_score)
        if not math.isfinite(similarity_score) or not 0 <= similarity_score <= 1:
            raise InvalidKnowledgeReuse("similarity_score must be between 0 and 1.")

    unique_match = find_unique_equivalent_published_fact_check_match(query_text)
    if unique_match is None:
        return None

    selected = unique_match.fact_check
    assessed_canonical = selected.canonical_claim

    # Compatibility assertions may reject a stale/caller-selected publication,
    # but they can never choose which publication receives authority.
    if fact_check is not None and selected.pk != fact_check.pk:
        return None
    if (
        published_canonical_claim is not None
        and assessed_canonical != published_canonical_claim
    ):
        return None

    resolved_similarity = (
        unique_match.similarity_score
        if similarity_score is _UNSET
        else similarity_score
    )
    fingerprint = build_query_fingerprint(query_text)

    with transaction.atomic():
        target_claim = Claim.objects.select_for_update(of=("self",)).get(
            pk=target_claim.pk
        )
        if target_claim.claim_type not in (Claim.ClaimType.IMAGE, Claim.ClaimType.URL):
            return None

        publication = (
            OfficialFactCheck.objects.select_for_update(of=("self",))
            .filter(
                pk=selected.pk,
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            )
            .first()
        )
        # The selected publication must still represent the exact canonical
        # proposition that was assessed before the reference is written.
        if publication is None or publication.canonical_claim != assessed_canonical:
            return None

        reference, _created = ClaimFactCheckReference.objects.get_or_create(
            target_claim=target_claim,
            relationship_kind=ClaimFactCheckReference.RelationshipKind.AUTHORITATIVE,
            defaults={
                "fact_check": publication,
                "match_method": ClaimFactCheckReference.MatchMethod.EQUIVALENT_CLAIM,
                "similarity_score": resolved_similarity,
                "query_fingerprint": fingerprint,
            },
        )
        if (
            reference.fact_check_id != publication.pk
            or reference.match_method
            != ClaimFactCheckReference.MatchMethod.EQUIVALENT_CLAIM
            or reference.query_fingerprint != fingerprint
        ):
            raise InvalidKnowledgeReuse(
                "Target already has a different authoritative resolution."
            )

    return reference


def record_related_claim_fact_check_reference(
    *,
    target_claim,
    fact_check,
    query_text,
    match_method,
    similarity_score=None,
):
    """Persist context provenance only; never transfer a publication's verdict."""
    query_text = _normalize_query_text(query_text)
    if len(query_text) < 10:
        raise InvalidKnowledgeReuse("An adequate incoming query is required.")
    if (
        not isinstance(target_claim, Claim)
        or target_claim.pk is None
        or target_claim._state.adding
        or not isinstance(fact_check, OfficialFactCheck)
        or fact_check.pk is None
        or fact_check._state.adding
    ):
        raise InvalidKnowledgeReuse("Persisted target and publication are required.")
    if target_claim.claim_type not in (Claim.ClaimType.IMAGE, Claim.ClaimType.URL):
        return None
    if match_method not in (
        ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL,
        ClaimFactCheckReference.MatchMethod.EXACT_HEADLINE,
        ClaimFactCheckReference.MatchMethod.SEMANTIC,
        ClaimFactCheckReference.MatchMethod.FULL_TEXT,
    ):
        raise InvalidKnowledgeReuse("Invalid related match method.")
    if similarity_score is not None:
        similarity_score = float(similarity_score)
        if not math.isfinite(similarity_score) or not 0 <= similarity_score <= 1:
            raise InvalidKnowledgeReuse("similarity_score must be between 0 and 1.")

    with transaction.atomic():
        target_claim = Claim.objects.select_for_update(of=("self",)).get(
            pk=target_claim.pk
        )
        if target_claim.claim_type not in (Claim.ClaimType.IMAGE, Claim.ClaimType.URL):
            return None
        publication = (
            OfficialFactCheck.objects.select_for_update(of=("self",))
            .filter(
                pk=fact_check.pk,
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            )
            .first()
        )
        if publication is None:
            return None

        # Revalidate exact labels against the current locked publication. Generic
        # Vault EXACT_TEXT is not itself a durable match method or authority.
        canonical_matches = (
            _normalize_query_text(publication.canonical_claim).casefold()
            == query_text.casefold()
        )
        if match_method == ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL:
            if not canonical_matches:
                return None
        elif match_method == ClaimFactCheckReference.MatchMethod.EXACT_HEADLINE:
            if canonical_matches or (
                _normalize_query_text(publication.headline).casefold()
                != query_text.casefold()
            ):
                return None

        reference, _created = ClaimFactCheckReference.objects.get_or_create(
            target_claim=target_claim,
            fact_check=publication,
            relationship_kind=ClaimFactCheckReference.RelationshipKind.RELATED,
            defaults={
                "match_method": match_method,
                "similarity_score": similarity_score,
                "query_fingerprint": build_query_fingerprint(query_text),
            },
        )
    return reference


def get_published_fact_check_resolution_for_claim(claim):
    """Direct publication retains priority; only valid authoritative methods resolve."""
    publication = get_published_fact_check_for_claim(claim)
    if publication is not None:
        return PublishedFactCheckMatch(
            fact_check=publication,
            match_method=KnowledgeReuseEvent.MatchMethod.CLAIM_CACHE,
        )

    reference = (
        ClaimFactCheckReference.objects.filter(
            target_claim=claim,
            relationship_kind=ClaimFactCheckReference.RelationshipKind.AUTHORITATIVE,
            match_method__in=(
                ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL,
                ClaimFactCheckReference.MatchMethod.EQUIVALENT_CLAIM,
            ),
            fact_check__publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        .select_related(
            "fact_check__claim",
            "fact_check__organization",
            "fact_check__adjudication_decision",
        )
        .prefetch_related("fact_check__source_items")
        .first()
    )
    if reference is None:
        return None
    publication = reference.fact_check
    if re.fullmatch(r"[0-9a-f]{64}", reference.query_fingerprint or "") is None:
        return None
    if reference.match_method == ClaimFactCheckReference.MatchMethod.EQUIVALENT_CLAIM:
        return PublishedFactCheckMatch(
            fact_check=publication,
            match_method=reference.match_method,
            similarity_score=reference.similarity_score,
        )
    canonical = _normalize_query_text(publication.canonical_claim)
    if len(canonical) < 10 or reference.query_fingerprint != build_query_fingerprint(
        canonical
    ):
        return None

    # A durable reference must also remain unambiguous at response time. If a
    # second current PUBLISHED publication later appears with the same exact
    # canonical text, stop transferring institutional authority through the
    # reference until the ambiguity is resolved.
    unique_match = find_exact_canonical_published_fact_check(canonical)
    if unique_match is None or unique_match.fact_check.pk != publication.pk:
        return None

    return PublishedFactCheckMatch(
        fact_check=publication,
        match_method=reference.match_method,
        similarity_score=reference.similarity_score,
    )


def build_related_published_fact_check_payload(reference):
    """Public reading context only; never expose the publication's verdict."""
    if (
        reference is None
        or reference.relationship_kind
        != ClaimFactCheckReference.RelationshipKind.RELATED
        or reference.match_method
        not in (
            ClaimFactCheckReference.MatchMethod.SEMANTIC,
            ClaimFactCheckReference.MatchMethod.FULL_TEXT,
            ClaimFactCheckReference.MatchMethod.EXACT_HEADLINE,
            ClaimFactCheckReference.MatchMethod.EXACT_CANONICAL,
        )
    ):
        return None

    fact_check = reference.fact_check
    partner = fact_check.organization
    if (
        fact_check.publication_status != OfficialFactCheck.PublicationStatus.PUBLISHED
        or partner is None
        or not is_public_partner_eligible(partner)
        or not (partner.slug or "").strip()
    ):
        return None

    # A RELATED reference is surfaceable only when the existing anonymous
    # publication-detail contract can actually resolve the article. This keeps
    # extension links aligned with sealed public lineage instead of treating a
    # live PUBLISHED row as sufficient public reachability.
    try:
        public_detail = get_public_partner_fact_check_detail(
            organization=partner,
            publication_id=fact_check.id,
        )
    except PublicPublicationNotFound:
        return None

    public_organization = public_detail["organization"]
    return {
        "fact_check_id": str(public_detail["selected_publication_id"]),
        "headline": public_detail["article"]["headline"],
        "published_at": public_detail["published_at"],
        "match_method": reference.match_method,
        "organization": {
            "name": public_organization["name"],
            "slug": public_organization["slug"],
            "public_profile_available": True,
            "logo_url": public_organization.get("logo_url"),
        },
    }


def get_related_published_fact_check_payloads(claim, *, limit=3):
    """Read durable IMAGE/URL provenance in chronology, without reuse or search."""
    if not isinstance(limit, int) or limit < 1:
        return []
    if isinstance(claim, Claim) and claim._state.adding:
        return []
    claim_id = getattr(claim, "pk", claim)
    if not claim_id:
        return []
    try:
        target_exists = Claim.objects.filter(
            pk=claim_id, claim_type__in=(Claim.ClaimType.IMAGE, Claim.ClaimType.URL)
        ).exists()
    except (ValidationError, ValueError, TypeError):
        return []
    if not target_exists:
        return []

    references = (
        ClaimFactCheckReference.objects.filter(
            target_claim_id=claim_id,
            relationship_kind=ClaimFactCheckReference.RelationshipKind.RELATED,
            fact_check__publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        .select_related("fact_check", "fact_check__organization")
        .order_by("-created_at", "fact_check_id")
    )
    payloads = []
    for reference in references:
        payload = build_related_published_fact_check_payload(reference)
        if payload is not None:
            payloads.append(payload)
            if len(payloads) >= min(limit, 3):
                break
    return payloads


def index_published_fact_check(
    fact_check,
):
    """
    Build the searchable representation of a
    published OfficialFactCheck.

    Embedding generation may be expensive, so
    callers should normally execute this outside
    the publication transaction.
    """

    if not isinstance(
        fact_check,
        OfficialFactCheck,
    ):
        fact_check = OfficialFactCheck.objects.get(pk=fact_check)

    if fact_check.publication_status != (OfficialFactCheck.PublicationStatus.PUBLISHED):
        return False

    canonical_claim = (fact_check.canonical_claim or "").strip()

    if not canonical_claim:
        return False

    try:
        embedding = generate_embedding(canonical_claim)

    except Exception:
        embedding = None

    update_values = {
        "search_vector": (
            SearchVector(
                "canonical_claim",
                weight="A",
            )
            + SearchVector(
                "headline",
                weight="A",
            )
            + SearchVector(
                "summary",
                weight="B",
            )
            + SearchVector(
                "article_body",
                weight="C",
            )
        ),
    }

    if embedding:
        update_values["embedding"] = embedding

    (OfficialFactCheck.objects.filter(pk=fact_check.pk).update(**update_values))

    return True


def find_published_fact_check_candidates(
    query_text,
    *,
    semantic_threshold=SEMANTIC_MATCH_THRESHOLD,
    full_text_rank_threshold=FULL_TEXT_RANK_THRESHOLD,
    max_candidates=5,
):
    """
    Return a bounded set of plausible PUBLISHED publication candidates.

    This reuses the same exact/semantic/full-text retrieval semantics as the
    ordinary Knowledge Vault, but never ranks one institution into authority.
    If more than ``max_candidates`` distinct plausible publications are found,
    fail closed by returning an empty list rather than silently truncating the
    authority-assessment set.
    """
    query_text = _normalize_query_text(query_text)
    if len(query_text) < 10 or max_candidates < 1:
        return []

    queryset = _published_fact_checks()
    matches = []
    seen = set()

    def add_match(match):
        fact_check_id = match.fact_check.pk
        if fact_check_id in seen:
            return True
        seen.add(fact_check_id)
        matches.append(match)
        return len(matches) <= max_candidates

    # Exact canonical/headline candidates use the same generic Vault semantics.
    exact_candidates = list(
        queryset.filter(
            Q(canonical_claim__iexact=query_text) | Q(headline__iexact=query_text)
        ).order_by("-published_at", "-created_at", "pk")[: max_candidates + 1]
    )
    for fact_check in exact_candidates:
        if not add_match(
            PublishedFactCheckMatch(
                fact_check=fact_check,
                match_method=KnowledgeReuseEvent.MatchMethod.EXACT_TEXT,
                similarity_score=1.0,
            )
        ):
            logger.info(
                "Published equivalence candidate set exceeded the bounded limit; "
                "refusing authoritative resolution."
            )
            return []

    try:
        query_embedding = generate_embedding(query_text)
    except Exception:
        query_embedding = None

    if query_embedding:
        max_distance = 1.0 - semantic_threshold
        semantic_candidates = list(
            queryset.exclude(embedding__isnull=True)
            .annotate(
                distance=CosineDistance(
                    "embedding",
                    query_embedding,
                )
            )
            .filter(distance__lte=max_distance)
            .order_by("distance", "-published_at", "-created_at", "pk")[
                : max_candidates + 1
            ]
        )
        for fact_check in semantic_candidates:
            similarity = max(0.0, min(1.0, 1.0 - float(fact_check.distance)))
            if not add_match(
                PublishedFactCheckMatch(
                    fact_check=fact_check,
                    match_method=KnowledgeReuseEvent.MatchMethod.SEMANTIC,
                    similarity_score=similarity,
                )
            ):
                logger.info(
                    "Published equivalence candidate set exceeded the bounded limit; "
                    "refusing authoritative resolution."
                )
                return []

    search_query = SearchQuery(query_text, search_type="plain")
    full_text_candidates = list(
        queryset.exclude(search_vector__isnull=True)
        .annotate(
            search_rank=SearchRank(
                F("search_vector"),
                search_query,
            )
        )
        .filter(search_rank__gte=full_text_rank_threshold)
        .order_by("-search_rank", "-published_at", "-created_at", "pk")[
            : max_candidates + 1
        ]
    )
    for fact_check in full_text_candidates:
        if not add_match(
            PublishedFactCheckMatch(
                fact_check=fact_check,
                match_method=KnowledgeReuseEvent.MatchMethod.FULL_TEXT,
                similarity_score=None,
            )
        ):
            logger.info(
                "Published equivalence candidate set exceeded the bounded limit; "
                "refusing authoritative resolution."
            )
            return []

    return matches


def find_unique_equivalent_published_fact_check_match(
    query_text,
    *,
    semantic_threshold=SEMANTIC_MATCH_THRESHOLD,
    full_text_rank_threshold=FULL_TEXT_RANK_THRESHOLD,
    max_candidates=5,
):
    """
    Return one publication only when exactly one plausible candidate expresses
    the same factual proposition.

    Candidate retrieval never confers authority. Every plausible candidate is
    evaluated through the strict claim-equivalence classifier. Two or more
    equivalent publications are ambiguous and therefore produce no authority.
    Provider exhaustion propagates so callers cannot fabricate an institutional
    result when equivalence could not be assessed.
    """
    from .services import assess_claim_equivalence

    query_text = _normalize_query_text(query_text)
    if len(query_text) < 10:
        return None

    candidates = find_published_fact_check_candidates(
        query_text,
        semantic_threshold=semantic_threshold,
        full_text_rank_threshold=full_text_rank_threshold,
        max_candidates=max_candidates,
    )
    if not candidates:
        return None

    equivalent_matches = []
    for candidate in candidates:
        canonical_claim = candidate.fact_check.canonical_claim
        assessment = assess_claim_equivalence(query_text, canonical_claim)
        if assessment["equivalent"] is True:
            equivalent_matches.append(candidate)
            if len(equivalent_matches) > 1:
                logger.info(
                    "Published claim equivalence is ambiguous across multiple "
                    "publications; refusing authoritative resolution."
                )
                return None

    if len(equivalent_matches) != 1:
        return None

    candidate = equivalent_matches[0]
    return PublishedFactCheckMatch(
        fact_check=candidate.fact_check,
        match_method=ClaimFactCheckReference.MatchMethod.EQUIVALENT_CLAIM,
        similarity_score=candidate.similarity_score,
    )


def find_published_fact_check_match(
    query_text,
    *,
    semantic_threshold=(SEMANTIC_MATCH_THRESHOLD),
    full_text_rank_threshold=(FULL_TEXT_RANK_THRESHOLD),
):
    """
    Search only PUBLISHED OfficialFactCheck rows.

    Search order:

        1. Exact canonical/headline match
        2. Semantic vector match
        3. PostgreSQL full-text fallback

    Returning a match does NOT mean that its verdict
    automatically applies to a new claim.
    """

    query_text = _normalize_query_text(query_text)

    if len(query_text) < 10:
        return None

    queryset = _published_fact_checks()

    # ---------------------------------
    # 1. Exact authoritative text match
    # ---------------------------------

    exact_match = (
        queryset.filter(
            Q(canonical_claim__iexact=(query_text)) | Q(headline__iexact=(query_text))
        )
        .order_by(
            "-published_at",
            "-created_at",
        )
        .first()
    )

    if exact_match:
        return PublishedFactCheckMatch(
            fact_check=exact_match,
            match_method=(KnowledgeReuseEvent.MatchMethod.EXACT_TEXT),
            similarity_score=1.0,
        )

    # ---------------------------------
    # 2. Semantic similarity
    # ---------------------------------

    try:
        query_embedding = generate_embedding(query_text)

    except Exception:
        query_embedding = None

    if query_embedding:
        max_distance = 1.0 - semantic_threshold

        semantic_match = (
            queryset.exclude(embedding__isnull=True)
            .annotate(
                distance=CosineDistance(
                    "embedding",
                    query_embedding,
                )
            )
            .filter(distance__lte=max_distance)
            .order_by(
                "distance",
                "-published_at",
                "-created_at",
            )
            .first()
        )

        if semantic_match:
            similarity = 1.0 - float(semantic_match.distance)

            similarity = max(
                0.0,
                min(
                    similarity,
                    1.0,
                ),
            )

            return PublishedFactCheckMatch(
                fact_check=semantic_match,
                match_method=(KnowledgeReuseEvent.MatchMethod.SEMANTIC),
                similarity_score=(similarity),
            )

    # ---------------------------------
    # 3. PostgreSQL full-text fallback
    # ---------------------------------

    search_query = SearchQuery(
        query_text,
        search_type="plain",
    )

    full_text_match = (
        queryset.exclude(search_vector__isnull=True)
        .annotate(
            search_rank=SearchRank(
                F("search_vector"),
                search_query,
            )
        )
        .filter(search_rank__gte=(full_text_rank_threshold))
        .order_by(
            "-search_rank",
            "-published_at",
            "-created_at",
        )
        .first()
    )

    if full_text_match:
        return PublishedFactCheckMatch(
            fact_check=full_text_match,
            match_method=(KnowledgeReuseEvent.MatchMethod.FULL_TEXT),
            # PostgreSQL SearchRank is not a
            # cosine similarity score and should
            # not be represented as one.
            similarity_score=None,
        )

    return None


def build_published_fact_check_payload(
    match,
):
    """
    Build reusable verification context from a
    published fact-check.

    This is intentionally distinct from an
    adjudication response.
    """

    if match is None:
        return None

    fact_check = match.fact_check

    if fact_check.publication_status != (OfficialFactCheck.PublicationStatus.PUBLISHED):
        raise InvalidKnowledgeReuse("Only published fact-checks " "may be reused.")

    source_items = list(fact_check.source_items.all())

    if source_items:
        sources = [
            {
                "url": source.url,
                "title": source.title,
                "source_type": (source.source_type),
            }
            for source in source_items
        ]

    else:
        # Temporary compatibility for old
        # publications not yet normalized.
        sources = []

        for raw_source in fact_check.sources or []:
            if isinstance(
                raw_source,
                str,
            ):
                sources.append(
                    {
                        "url": raw_source,
                        "title": None,
                        "source_type": ("LEGACY_IMPORT"),
                    }
                )

            elif isinstance(
                raw_source,
                dict,
            ):
                url = raw_source.get("url")

                if url:
                    sources.append(
                        {
                            "url": url,
                            "title": (raw_source.get("title")),
                            "source_type": ("LEGACY_IMPORT"),
                        }
                    )

    organization = None

    if fact_check.organization:
        partner = fact_check.organization
        public_profile_available = is_public_partner_eligible(partner)
        organization = {
            "id": str(partner.id),
            "name": partner.name,
            "slug": partner.slug,
            "public_profile_available": public_profile_available,
            "logo_url": (
                partner.logo_url
                if public_profile_available and partner.public_logo_enabled
                else None
            ),
        }

    return {
        "fact_check_id": str(fact_check.id),
        "claim_id": (str(fact_check.claim_id) if fact_check.claim_id else None),
        "canonical_claim": (fact_check.canonical_claim),
        "headline": (fact_check.headline),
        "verdict": (fact_check.verdict),
        "summary": (fact_check.summary),
        "version": (fact_check.version),
        "revision_kind": fact_check.revision_kind,
        "organization": organization,
        "published_at": (
            fact_check.published_at.isoformat() if fact_check.published_at else None
        ),
        "sources": sources,
        "match_method": (match.match_method),
        "similarity_score": (match.similarity_score),
    }


def record_knowledge_reuse(
    *,
    fact_check,
    reuse_type,
    match_method,
    target_claim=None,
    triggered_by=None,
    similarity_score=None,
    query_text=None,
    metadata=None,
):
    """
    Record a material reuse of an authoritative
    published fact-check.

    Do not call this for ordinary page views.
    """

    if fact_check is None or fact_check.pk is None or fact_check._state.adding:
        raise InvalidKnowledgeReuse("Knowledge reuse requires a persisted fact-check.")

    if fact_check.publication_status != (OfficialFactCheck.PublicationStatus.PUBLISHED):
        raise InvalidKnowledgeReuse(
            "Only published fact-checks " "may generate knowledge reuse " "events."
        )

    if fact_check.organization_id is None:
        raise InvalidKnowledgeReuse("Knowledge reuse requires a source organization.")
    source_organization_id_snapshot = str(fact_check.organization_id).strip()
    if not source_organization_id_snapshot:
        raise InvalidKnowledgeReuse(
            "Knowledge reuse requires a nonblank source organization ID."
        )

    target_claim_id_snapshot = ""
    if target_claim is not None:
        if target_claim.pk is None or target_claim._state.adding:
            raise InvalidKnowledgeReuse(
                "Knowledge reuse requires a persisted target claim."
            )
        target_claim_id_snapshot = str(target_claim.pk).strip()
        if not target_claim_id_snapshot:
            raise InvalidKnowledgeReuse(
                "Knowledge reuse requires a nonblank target claim ID."
            )

    valid_reuse_types = {
        value for value, _label in (KnowledgeReuseEvent.ReuseType.choices)
    }

    if reuse_type not in valid_reuse_types:
        raise InvalidKnowledgeReuse("Invalid knowledge reuse type.")

    valid_match_methods = {
        value for value, _label in (KnowledgeReuseEvent.MatchMethod.choices)
    }

    if match_method not in valid_match_methods:
        raise InvalidKnowledgeReuse("Invalid knowledge match method.")

    if similarity_score is not None:
        similarity_score = float(similarity_score)

        if similarity_score < 0 or similarity_score > 1:
            raise InvalidKnowledgeReuse("similarity_score must be " "between 0 and 1.")

    return KnowledgeReuseEvent.objects.create(
        fact_check=fact_check,
        target_claim=target_claim,
        source_organization_id_snapshot=source_organization_id_snapshot,
        target_claim_id_snapshot=target_claim_id_snapshot,
        triggered_by=triggered_by,
        reuse_type=reuse_type,
        match_method=match_method,
        similarity_score=(similarity_score),
        query_fingerprint=(build_query_fingerprint(query_text)),
        metadata=(metadata or {}),
    )
