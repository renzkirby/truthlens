import hashlib
from dataclasses import dataclass

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
)
from django.db.models import F, Q
from pgvector.django import CosineDistance

from .embedding_service import (
    generate_embedding,
)
from .models import (
    KnowledgeReuseEvent,
    OfficialFactCheck,
)

SEMANTIC_MATCH_THRESHOLD = 0.80
FULL_TEXT_RANK_THRESHOLD = 0.08


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
        organization = {
            "id": str(fact_check.organization.id),
            "name": (fact_check.organization.name),
            "slug": (fact_check.organization.slug),
        }

    return {
        "fact_check_id": str(fact_check.id),
        "claim_id": (str(fact_check.claim_id) if fact_check.claim_id else None),
        "canonical_claim": (fact_check.canonical_claim),
        "headline": (fact_check.headline),
        "verdict": (fact_check.verdict),
        "summary": (fact_check.summary),
        "version": (fact_check.version),
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

    if fact_check.publication_status != (OfficialFactCheck.PublicationStatus.PUBLISHED):
        raise InvalidKnowledgeReuse(
            "Only published fact-checks " "may generate knowledge reuse " "events."
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
        triggered_by=triggered_by,
        reuse_type=reuse_type,
        match_method=match_method,
        similarity_score=(similarity_score),
        query_fingerprint=(build_query_fingerprint(query_text)),
        metadata=(metadata or {}),
    )
