import hashlib
import json
import logging
import uuid
from collections.abc import Mapping
from copy import deepcopy

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)

_DIRECTORY_GENERATION_KEY = "public-partner-directory:generation:v1"
_PUBLICATION_GENERATION_PREFIX = "public-fact-checks:generation:v1"


def _safe_cache_get(key):
    try:
        return cache.get(key)
    except Exception:
        logger.exception("Cache read failed for key %s.", key)
        return None


def _safe_cache_set(key, value, *, timeout):
    try:
        cache.set(key, value, timeout=timeout)
        return True
    except Exception:
        logger.exception("Cache write failed for key %s.", key)
        return False


def _safe_cache_add(key, value, *, timeout):
    try:
        return cache.add(key, value, timeout=timeout)
    except Exception:
        logger.exception("Cache add failed for key %s.", key)
        return False


def _generation(key):
    value = _safe_cache_get(key)
    if isinstance(value, str) and value:
        return value

    candidate = uuid.uuid4().hex
    if _safe_cache_add(key, candidate, timeout=None):
        return candidate

    value = _safe_cache_get(key)
    if isinstance(value, str) and value:
        return value

    # If the backend is unavailable, use a one-off generation so application
    # requests continue through the authoritative database path without
    # accidentally reusing an old cache generation.
    return uuid.uuid4().hex


def _rotate_generation(key):
    return _safe_cache_set(
        key,
        uuid.uuid4().hex,
        timeout=None,
    )


def _digest(values):
    encoded = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _publication_generation_key(organization_id):
    return f"{_PUBLICATION_GENERATION_PREFIX}:{organization_id}"


def _plain_payload(value):
    if isinstance(value, Mapping):
        return {
            str(key): _plain_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_plain_payload(item) for item in value]
    return deepcopy(value)


def _copy_cached_payload(value):
    if value is None:
        return None
    return _plain_payload(value)


def get_public_partner_directory_payload(*, search, organization_type):
    generation = _generation(_DIRECTORY_GENERATION_KEY)
    key = (
        "public-partner-directory:v1:"
        f"{generation}:{_digest({'search': search, 'type': organization_type})}"
    )
    return _copy_cached_payload(_safe_cache_get(key))


def set_public_partner_directory_payload(
    payload,
    *,
    search,
    organization_type,
):
    generation = _generation(_DIRECTORY_GENERATION_KEY)
    key = (
        "public-partner-directory:v1:"
        f"{generation}:{_digest({'search': search, 'type': organization_type})}"
    )
    return _safe_cache_set(
        key,
        _plain_payload(payload),
        timeout=settings.PUBLIC_PARTNER_DIRECTORY_CACHE_SECONDS,
    )


def invalidate_public_partner_directory_cache():
    return _rotate_generation(_DIRECTORY_GENERATION_KEY)


def get_public_fact_check_collection_payload(
    *,
    organization_id,
    limit,
    offset,
):
    generation = _generation(_publication_generation_key(organization_id))
    key = (
        "public-fact-check-collection:v1:"
        f"{organization_id}:{generation}:{limit}:{offset}"
    )
    return _copy_cached_payload(_safe_cache_get(key))


def set_public_fact_check_collection_payload(
    payload,
    *,
    organization_id,
    limit,
    offset,
):
    generation = _generation(_publication_generation_key(organization_id))
    key = (
        "public-fact-check-collection:v1:"
        f"{organization_id}:{generation}:{limit}:{offset}"
    )
    return _safe_cache_set(
        key,
        deepcopy(payload),
        timeout=settings.PUBLIC_FACT_CHECK_COLLECTION_CACHE_SECONDS,
    )


def get_public_fact_check_detail_payload(
    *,
    organization_id,
    publication_id,
):
    generation = _generation(_publication_generation_key(organization_id))
    key = (
        "public-fact-check-detail:v1:"
        f"{organization_id}:{generation}:{publication_id}"
    )
    return _copy_cached_payload(_safe_cache_get(key))


def set_public_fact_check_detail_payload(
    payload,
    *,
    organization_id,
    publication_id,
):
    generation = _generation(_publication_generation_key(organization_id))
    key = (
        "public-fact-check-detail:v1:"
        f"{organization_id}:{generation}:{publication_id}"
    )
    return _safe_cache_set(
        key,
        deepcopy(payload),
        timeout=settings.PUBLIC_FACT_CHECK_DETAIL_CACHE_SECONDS,
    )


def invalidate_public_fact_check_cache(organization_id):
    return _rotate_generation(_publication_generation_key(organization_id))


def invalidate_public_organization_read_cache(organization_id):
    directory_invalidated = invalidate_public_partner_directory_cache()
    publications_invalidated = invalidate_public_fact_check_cache(organization_id)
    return directory_invalidated and publications_invalidated
