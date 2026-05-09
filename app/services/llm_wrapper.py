"""Wrapper LiteLLM con fallback entre proveedores, caché y coste estimado (patrón ai-engineering)."""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator

import litellm
from litellm import Router

from app.services.cache import EstimationCache

log = logging.getLogger(__name__)

MODEL_COSTS: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
}


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    base = _normalise_model_name(model)
    costs = MODEL_COSTS.get(base) or MODEL_COSTS.get(model) or {"input": 0.0, "output": 0.0}
    return round((tokens_in * costs["input"] + tokens_out * costs["output"]) / 1_000_000, 6)


def _normalise_model_name(model: str) -> str:
    return model.split("/", 1)[1] if "/" in model else model


def _provider_from_model(model: str) -> str:
    name = _normalise_model_name(model).lower()
    if name.startswith("claude"):
        return "anthropic"
    if name.startswith("gpt") or name.startswith("o1") or name.startswith("o3"):
        return "openai"
    return "unknown"


def _extract_delta(chunk: Any) -> str:
    try:
        delta = chunk.choices[0].delta
    except (AttributeError, IndexError):
        return ""
    content = getattr(delta, "content", None)
    return content or ""


class LLMWrapper:
    """Cliente unificado con Router LiteLLM (fallback), caché y tracking de coste."""

    ROUTER_MODEL_GROUP = "estimator"

    def __init__(
        self,
        *,
        openai_api_key: str | None,
        anthropic_api_key: str | None,
        primary_model: str,
        fallback_model: str,
        anthropic_first: bool,
        timeout: int,
        num_retries: int,
        cache: EstimationCache,
    ):
        self.openai_api_key = openai_api_key
        self.anthropic_api_key = anthropic_api_key
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.anthropic_first = anthropic_first
        self.timeout = timeout
        self.num_retries = num_retries
        self.cache = cache

        openai_dep = {
            "model_name": self.ROUTER_MODEL_GROUP,
            "litellm_params": {
                "model": primary_model,
                "api_key": openai_api_key,
                "timeout": timeout,
            },
        }
        anthropic_dep = {
            "model_name": self.ROUTER_MODEL_GROUP,
            "litellm_params": {
                "model": fallback_model,
                "api_key": anthropic_api_key,
                "timeout": timeout,
            },
        }
        model_list = [anthropic_dep, openai_dep] if anthropic_first else [openai_dep, anthropic_dep]

        self.router = Router(
            model_list=model_list,
            fallbacks=[{self.ROUTER_MODEL_GROUP: [self.ROUTER_MODEL_GROUP]}],
            num_retries=num_retries,
        )

    async def acomplete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        model_override: str | None = None,
        max_tokens: int = 8192,
        thinking_budget: int | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        cache_key_model = model_override or self.primary_model
        cache_key = EstimationCache.make_key(
            system_prompt=system_prompt,
            user_message=user_message,
            model=cache_key_model,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
        )
        cached = self.cache.get(cache_key)
        if cached:
            return {**cached, "cache_hit": True}

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        kwargs = self._build_call_kwargs(
            messages=messages,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            model_override=model_override,
            temperature=temperature,
            stream=False,
        )

        log.info(
            "llm_call_started model=%s thinking=%s",
            model_override or self.primary_model,
            thinking_budget is not None,
        )
        t0 = time.perf_counter()
        try:
            response = await self._adispatch(model_override=model_override, **kwargs)
        except Exception:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.exception("llm_call_failed latency_ms=%s", latency_ms)
            raise

        latency_ms = int((time.perf_counter() - t0) * 1000)
        result = self._normalise_response(response, latency_ms=latency_ms)
        log.info(
            "llm_call_completed model=%s provider=%s in=%s out=%s cost_usd=%s",
            result["model"],
            result["provider"],
            result["usage"]["input_tokens"],
            result["usage"]["output_tokens"],
            result["cost_usd"],
        )
        self.cache.set(cache_key, result)
        return {**result, "cache_hit": False}

    async def acomplete_stream(
        self,
        *,
        system_prompt: str,
        user_message: str,
        model_override: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        cache_key_model = model_override or self.primary_model
        cache_key = EstimationCache.make_key(
            system_prompt=system_prompt,
            user_message=user_message,
            model=cache_key_model,
            max_tokens=max_tokens,
            thinking_budget=None,
        )
        cached = self.cache.get(cache_key)
        if cached:
            log.info("stream_cache_hit chars=%s", len(cached.get("estimation", "")))
            yield cached.get("estimation", "")
            return

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        kwargs = self._build_call_kwargs(
            messages=messages,
            max_tokens=max_tokens,
            thinking_budget=None,
            model_override=model_override,
            temperature=temperature,
            stream=True,
        )

        log.info("llm_stream_started model=%s", model_override or self.primary_model)
        t0 = time.perf_counter()
        full_text: list[str] = []
        try:
            response = await self._adispatch(model_override=model_override, **kwargs)
            async for chunk in response:
                delta = _extract_delta(chunk)
                if delta:
                    full_text.append(delta)
                    yield delta
        except Exception:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.exception("llm_stream_failed latency_ms=%s", latency_ms)
            raise

        latency_ms = int((time.perf_counter() - t0) * 1000)
        rendered = "".join(full_text)
        log.info("llm_stream_completed latency_ms=%s chars=%s", latency_ms, len(rendered))

        self.cache.set(
            cache_key,
            {
                "estimation": rendered,
                "model": model_override or self.primary_model,
                "provider": _provider_from_model(model_override or self.primary_model),
                "finish_reason": "stop",
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "latency_ms": latency_ms,
                "cost_usd": 0.0,
            },
        )

    def _build_call_kwargs(
        self,
        *,
        messages: list[dict],
        max_tokens: int,
        thinking_budget: int | None,
        model_override: str | None,
        temperature: float,
        stream: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stream:
            kwargs["stream"] = True

        if thinking_budget is not None:
            target_model = model_override or self.primary_model
            if _provider_from_model(target_model) == "anthropic":
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
                kwargs["max_tokens"] = max(max_tokens, thinking_budget + 1024)
            else:
                log.warning(
                    "thinking_budget ignorado para proveedor=%s model=%s",
                    _provider_from_model(target_model),
                    target_model,
                )
        return kwargs

    async def _adispatch(self, *, model_override: str | None, **kwargs: Any) -> Any:
        if model_override:
            api_key = (
                self.anthropic_api_key
                if _provider_from_model(model_override) == "anthropic"
                else self.openai_api_key
            )
            return await litellm.acompletion(
                model=model_override,
                api_key=api_key,
                timeout=self.timeout,
                num_retries=self.num_retries,
                **kwargs,
            )
        return await self.router.acompletion(model=self.ROUTER_MODEL_GROUP, **kwargs)

    @staticmethod
    def _normalise_response(response: Any, *, latency_ms: int) -> dict[str, Any]:
        choice = response.choices[0]
        finish_reason = (choice.finish_reason or "stop").lower()
        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", input_tokens + output_tokens) or (
            input_tokens + output_tokens
        )

        model = _normalise_model_name(response.model)
        return {
            "estimation": choice.message.content or "",
            "model": model,
            "provider": _provider_from_model(model),
            "finish_reason": finish_reason,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "latency_ms": latency_ms,
            "cost_usd": _estimate_cost(model, input_tokens, output_tokens),
        }
