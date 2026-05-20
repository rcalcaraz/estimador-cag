"""Tests de la caché semántica (índice y vectorizer simulados)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.schemas import (
    DetailLevel,
    EstimationPhase,
    EstimationRequest,
    EstimationTotals,
    OutputFormat,
    ProjectType,
    StructuredEstimation,
)


def _valid_request() -> EstimationRequest:
    return EstimationRequest(
        description=(
            "Mobile app for booking medical appointments with login dashboard and calendar."
        ),
        project_type=ProjectType.MOBILE_APP,
        detail_level=DetailLevel.SUMMARY,
        output_format=OutputFormat.NARRATIVE,
    )


def _canned_result() -> StructuredEstimation:
    return StructuredEstimation(
        summary="Standard mobile app for appointment management.",
        phases=[
            EstimationPhase(
                name="Discovery",
                description="Scoping and tech spike.",
                weeks=1,
                cost=5000,
            ),
            EstimationPhase(
                name="Build",
                description="Core feature implementation.",
                weeks=6,
                cost=20000,
            ),
        ],
        totals=EstimationTotals(
            duration_weeks=7,
            cost=25000,
            confidence_pct=70,
            currency="EUR",
        ),
    )


def _build_cache(*, threshold: float = 0.92, log_only: bool = False, hits=None):
    from app.cache.semantic import EstimationSemanticCache

    fake_index = MagicMock()
    fake_index.create.return_value = None
    fake_index.set_client.return_value = None
    fake_index.query.return_value = hits or []
    fake_index.load.return_value = None
    fake_vectorizer = SimpleNamespace(embed=lambda text: [0.1] * 1536)

    cache = EstimationSemanticCache.__new__(EstimationSemanticCache)
    cache.redis_client = MagicMock()
    cache.vectorizer = fake_vectorizer
    cache.threshold = threshold
    cache.ttl = 60
    cache.log_only = log_only
    cache.index = fake_index
    return cache, fake_index, fake_vectorizer


def test_bucket_includes_all_form_options() -> None:
    from app.cache.semantic import EstimationSemanticCache

    request = _valid_request()
    bucket = EstimationSemanticCache.bucket_for(request, prompt_version="v1")
    assert bucket == "v1:mobile_app:summary:narrative"


def test_bucket_changes_when_any_option_changes() -> None:
    from app.cache.semantic import EstimationSemanticCache

    base = _valid_request()
    other = EstimationRequest.model_validate(
        {**base.model_dump(), "output_format": OutputFormat.PHASES_TABLE}
    )
    assert EstimationSemanticCache.bucket_for(
        base, prompt_version="v1"
    ) != EstimationSemanticCache.bucket_for(other, prompt_version="v1")


def test_bucket_changes_when_prompt_version_changes() -> None:
    from app.cache.semantic import EstimationSemanticCache

    request = _valid_request()
    assert EstimationSemanticCache.bucket_for(
        request, prompt_version="v1"
    ) != EstimationSemanticCache.bucket_for(request, prompt_version="v2")


def test_lookup_returns_none_when_index_is_empty() -> None:
    cache, _, _ = _build_cache(hits=[])
    assert cache.lookup(_valid_request(), prompt_version="v1") is None


def test_lookup_returns_none_when_similarity_below_threshold() -> None:
    cache, _, _ = _build_cache(
        threshold=0.92,
        hits=[{"result_json": _canned_result().model_dump_json(), "vector_distance": 0.5}],
    )
    assert cache.lookup(_valid_request(), prompt_version="v1") is None


def test_lookup_returns_result_when_similarity_above_threshold() -> None:
    cache, _, _ = _build_cache(
        threshold=0.92,
        hits=[{"result_json": _canned_result().model_dump_json(), "vector_distance": 0.05}],
    )
    hit = cache.lookup(_valid_request(), prompt_version="v1")
    assert hit is not None
    assert hit.estimation.totals.cost == 25000


def test_lookup_log_only_never_serves_even_on_hit() -> None:
    cache, _, _ = _build_cache(
        threshold=0.92,
        log_only=True,
        hits=[{"result_json": _canned_result().model_dump_json(), "vector_distance": 0.01}],
    )
    assert cache.lookup(_valid_request(), prompt_version="v1") is None


def test_store_writes_to_index_with_ttl() -> None:
    cache, fake_index, _ = _build_cache()
    cache.store(
        _valid_request(),
        _canned_result(),
        prompt_version="v1",
        model="gpt-4o-mini",
        provider="openai",
    )
    assert fake_index.load.called
    args, kwargs = fake_index.load.call_args
    payload = args[0][0]
    assert payload["bucket"] == "v1:mobile_app:summary:narrative"
    assert "Standard mobile app" in payload["result_json"]
    assert payload["model"] == "gpt-4o-mini"
    assert payload["provider"] == "openai"
    assert kwargs.get("ttl") == 60


def test_lookup_returns_stored_model_and_provider() -> None:
    cache, _, _ = _build_cache(
        threshold=0.92,
        hits=[
            {
                "result_json": _canned_result().model_dump_json(),
                "vector_distance": 0.05,
                "model": "claude-haiku-4-5",
                "provider": "anthropic",
            }
        ],
    )
    hit = cache.lookup(_valid_request(), prompt_version="v1")
    assert hit is not None
    assert hit.model == "claude-haiku-4-5"
    assert hit.provider == "anthropic"


def test_store_swallows_index_errors() -> None:
    cache, fake_index, _ = _build_cache()
    fake_index.load.side_effect = RuntimeError("redis unreachable")
    cache.store(_valid_request(), _canned_result(), prompt_version="v1")
