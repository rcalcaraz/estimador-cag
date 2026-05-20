"""Dependencias FastAPI: caché y wrapper LLM (singletons)."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from openai import OpenAI

from app.config import get_settings
from app.services.cache import EstimationCache
from app.services.llm_wrapper import LLMWrapper


@lru_cache
def get_cache() -> EstimationCache:
    settings = get_settings()
    return EstimationCache.from_url(settings.redis_url, ttl=settings.cache_ttl)


@lru_cache
def get_openai_client() -> Optional[OpenAI]:
    """Cliente OpenAI para la API de moderación en ``check_input``."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


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
