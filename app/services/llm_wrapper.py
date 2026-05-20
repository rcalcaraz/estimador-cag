"""Wrapper LiteLLM con fallback entre proveedores, caché y coste estimado (patrón ai-engineering)."""

from __future__ import annotations

import time
from typing import Any

import litellm
import structlog
from litellm import Router

from app.services.cache import EstimationCache

log = structlog.get_logger()

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


def _usage_dict_from_litellm(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if input_tokens is None and output_tokens is None:
        return None
    in_t = int(input_tokens or 0)
    out_t = int(output_tokens or 0)
    total = getattr(usage, "total_tokens", None)
    total_t = int(total) if total is not None else in_t + out_t
    return {
        "input_tokens": in_t,
        "output_tokens": out_t,
        "total_tokens": total_t,
    }


def _provider_from_model(model: str) -> str:
    name = _normalise_model_name(model).lower()
    if name.startswith("claude"):
        return "anthropic"
    if name.startswith("gpt") or name.startswith("o1") or name.startswith("o3"):
        return "openai"
    return "unknown"


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
        )

        log.info(
            "llm_call_started",
            model=model_override or self.primary_model,
            thinking=thinking_budget is not None,
        )
        t0 = time.perf_counter()
        try:
            response = await self._adispatch(model_override=model_override, **kwargs)
        except Exception:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.exception("llm_call_failed", latency_ms=latency_ms)
            raise

        latency_ms = int((time.perf_counter() - t0) * 1000)
        result = self._normalise_response(response, latency_ms=latency_ms)
        log.info(
            "llm_call_completed",
            model=result["model"],
            provider=result["provider"],
            input_tokens=result["usage"]["input_tokens"],
            output_tokens=result["usage"]["output_tokens"],
            cost_usd=result["cost_usd"],
        )
        self.cache.set(cache_key, result)
        return {**result, "cache_hit": False}

    def _build_call_kwargs(
        self,
        *,
        messages: list[dict],
        max_tokens: int,
        thinking_budget: int | None,
        model_override: str | None,
        temperature: float,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if thinking_budget is not None:
            target_model = model_override or self.primary_model
            if _provider_from_model(target_model) == "anthropic":
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
                kwargs["max_tokens"] = max(max_tokens, thinking_budget + 1024)
            else:
                log.warning(
                    "thinking_budget_ignored",
                    provider=_provider_from_model(target_model),
                    model=target_model,
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
        usage_norm = _usage_dict_from_litellm(response.usage)
        if usage_norm is None:
            usage_norm = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        model = _normalise_model_name(response.model)
        return {
            "estimation": choice.message.content or "",
            "model": model,
            "provider": _provider_from_model(model),
            "finish_reason": finish_reason,
            "usage": usage_norm,
            "latency_ms": latency_ms,
            "cost_usd": _estimate_cost(
                model, usage_norm["input_tokens"], usage_norm["output_tokens"]
            ),
        }
