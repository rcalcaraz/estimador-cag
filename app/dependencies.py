"""Dependencias FastAPI: caché y wrapper LLM (singletons)."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

import redis
import structlog
from openai import OpenAI

from app.cache.semantic import EstimationSemanticCache
from app.config import get_settings
from app.services.cache import EstimationCache
from app.services.llm_wrapper import LLMWrapper

log = structlog.get_logger()


@lru_cache
def get_cache() -> EstimationCache:
    settings = get_settings()
    return EstimationCache.from_url(settings.redis_url, ttl=settings.cache_ttl)


@lru_cache
def get_openai_client() -> Optional[OpenAI]:
    """Cliente OpenAI (moderación en ``check_input`` y embeddings de caché semántica)."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache
def get_semantic_cache() -> Optional[EstimationSemanticCache]:
    """Caché semántica; si Redis Stack o OpenAI no están disponibles, devuelve None."""
    settings = get_settings()
    if not settings.openai_api_key:
        log.warning("semantic_cache_disabled", reason="no_openai_key")
        return None

    try:
        from redisvl.utils.vectorize import OpenAITextVectorizer

        vectorizer = OpenAITextVectorizer(
            model=settings.embedding_model,
            api_config={"api_key": settings.openai_api_key},
        )
        redis_client = redis.from_url(settings.redis_url, decode_responses=False)
        return EstimationSemanticCache(
            redis_client=redis_client,
            vectorizer=vectorizer,
            threshold=settings.semantic_cache_threshold,
            ttl=settings.semantic_cache_ttl,
            log_only=settings.semantic_cache_log_only,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "semantic_cache_disabled",
            reason="setup_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )
        return None


@lru_cache
def get_llm_wrapper() -> LLMWrapper:
    settings = get_settings()
    return LLMWrapper(
        openai_api_key=settings.openai_api_key,
        anthropic_api_key=settings.anthropic_api_key,
        primary_model=settings.primary_model,
        fallback_model=settings.fallback_model,
        anthropic_first=(settings.llm_provider == "anthropic"),
        timeout=settings.llm_timeout,
        num_retries=settings.llm_retries,
        cache=get_cache(),
    )
