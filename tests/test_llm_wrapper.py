from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import fakeredis
import pytest

from app.services.cache import EstimationCache
from app.services.llm_wrapper import LLMWrapper, _estimate_cost, _normalise_model_name


def _fake_completion(
    model: str,
    content: str = "the answer",
    input_tokens: int = 100,
    output_tokens: int = 50,
):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
    )


@pytest.fixture
def wrapper() -> LLMWrapper:
    cache = EstimationCache(fakeredis.FakeRedis(decode_responses=True), ttl=60)
    return LLMWrapper(
        openai_api_key="fake-openai",
        anthropic_api_key="fake-anthropic",
        primary_model="gpt-4o-mini",
        fallback_model="claude-haiku-4-5-20251001",
        anthropic_first=False,
        timeout=30,
        num_retries=2,
        cache=cache,
    )


def test_estimate_cost_uses_pricing_table() -> None:
    cost = _estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.75)


def test_estimate_cost_unknown_dated_model_via_litellm() -> None:
    cost = _estimate_cost("gpt-4o-mini-2024-07-18", 2337, 369)
    assert cost > 0


def test_resolve_billing_model_from_router_group_name(wrapper: LLMWrapper) -> None:
    fake = _fake_completion(model="estimator", content="ok", input_tokens=2337, output_tokens=369)
    fake._hidden_params = {"litellm_model_name": "gpt-4o-mini"}
    billing = wrapper._resolve_billing_model(fake, model_override=None)
    assert billing == "gpt-4o-mini"
    assert _normalise_model_name("estimator") == wrapper.ROUTER_MODEL_GROUP


@pytest.mark.asyncio
async def test_acomplete_router_group_name_nonzero_cost(wrapper: LLMWrapper) -> None:
    fake = _fake_completion(model="estimator", content="priced", input_tokens=2337, output_tokens=369)
    fake._hidden_params = {"litellm_model_name": "gpt-4o-mini"}
    with patch.object(wrapper.router, "acompletion", return_value=fake):
        result = await wrapper.acomplete(
            system_prompt="sys",
            user_message="usr",
            model_override=None,
            max_tokens=4000,
            thinking_budget=None,
            temperature=0.3,
        )
    assert result["model"] == "gpt-4o-mini"
    assert result["cost_usd"] > 0


@pytest.mark.asyncio
async def test_acomplete_returns_normalised_dict_and_caches(wrapper: LLMWrapper) -> None:
    fake = _fake_completion(model="gpt-4o-mini", content="hello world")
    with patch.object(wrapper.router, "acompletion", return_value=fake) as mocked:
        result = await wrapper.acomplete(
            system_prompt="sys",
            user_message="usr",
            model_override=None,
            max_tokens=4000,
            thinking_budget=None,
            temperature=0.3,
        )
    assert mocked.call_count == 1
    assert result["estimation"] == "hello world"
    assert result["model"] == "gpt-4o-mini"
    assert result["provider"] == "openai"
    assert result["finish_reason"] == "stop"
    assert result["usage"]["input_tokens"] == 100
    assert result["usage"]["output_tokens"] == 50
    assert result["cache_hit"] is False
    assert result["cost_usd"] > 0

    with patch.object(wrapper.router, "acompletion") as mocked_again:
        cached = await wrapper.acomplete(
            system_prompt="sys",
            user_message="usr",
            model_override=None,
            max_tokens=4000,
            thinking_budget=None,
            temperature=0.3,
        )
    assert mocked_again.call_count == 0
    assert cached["cache_hit"] is True
    assert cached["estimation"] == "hello world"


@pytest.mark.asyncio
async def test_acomplete_with_model_override_bypasses_router(wrapper: LLMWrapper) -> None:
    fake = _fake_completion(model="gpt-4o", content="overridden")
    with patch("app.services.llm_wrapper.litellm.acompletion", return_value=fake) as direct, patch.object(
        wrapper.router, "acompletion"
    ) as router_call:
        result = await wrapper.acomplete(
            system_prompt="sys",
            user_message="usr",
            model_override="gpt-4o",
            max_tokens=4000,
            thinking_budget=None,
            temperature=0.3,
        )
    assert direct.call_count == 1
    assert router_call.call_count == 0
    assert direct.call_args.kwargs["model"] == "gpt-4o"
    assert result["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_thinking_budget_passed_for_anthropic_override(wrapper: LLMWrapper) -> None:
    fake = _fake_completion(model="claude-haiku-4-5-20251001", content="ok")
    with patch("app.services.llm_wrapper.litellm.acompletion", return_value=fake) as direct:
        await wrapper.acomplete(
            system_prompt="sys",
            user_message="usr",
            model_override="claude-haiku-4-5-20251001",
            max_tokens=1000,
            thinking_budget=4096,
            temperature=0.3,
        )
    kwargs = direct.call_args.kwargs
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 4096}
    assert kwargs["max_tokens"] == 4096 + 1024

