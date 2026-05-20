from __future__ import annotations

from typing import NoReturn

import pytest
from fastapi.testclient import TestClient

from app.routers import estimations as estimations_router
from app.services.llm_service import ESTIMATION_PROMPT_VERSION, EstimationOutcome


def _valid_payload() -> dict:
    return {
        "description": (
            "El cliente necesita un panel web para gestionar pedidos, "
            "con login y notificaciones por email."
        ),
        "project_type": "web_saas",
        "detail_level": "medium",
        "output_format": "phases_table",
    }


@pytest.fixture
def sample_outcome() -> EstimationOutcome:
    return EstimationOutcome(
        estimation="## Estimación\n\nTotal orientativo: 40 h.",
        model="gpt-4o-mini",
        provider="openai",
        input_tokens=1234,
        output_tokens=567,
        total_tokens=1801,
        response_time_seconds=0.42,
        cost_usd=0.001234,
        cache_hit=False,
    )


@pytest.fixture
def patch_generate(
    monkeypatch: pytest.MonkeyPatch,
    sample_outcome: EstimationOutcome,
) -> None:
    async def fake_complete(_system: str, _user: str) -> EstimationOutcome:
        return sample_outcome

    monkeypatch.setattr(estimations_router, "complete_estimation", fake_complete)


def test_estimate_returns_200_and_matches_schema(
    client: TestClient,
    patch_generate: None,
    sample_outcome: EstimationOutcome,
) -> None:
    response = client.post("/api/v1/estimate", json=_valid_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == sample_outcome.estimation
    assert body["prompt_version"] == ESTIMATION_PROMPT_VERSION
    assert body["model"] == sample_outcome.model
    assert body["provider"] == sample_outcome.provider
    assert body["cache_hit"] is False
    assert body["cost_usd"] == pytest.approx(0.001234)
    assert body["total_tokens"] == 1801


def test_estimate_value_error_returns_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def bad(_system: str, _user: str) -> NoReturn:
        raise ValueError("entrada inválida")

    monkeypatch.setattr(estimations_router, "complete_estimation", bad)
    response = client.post("/api/v1/estimate", json=_valid_payload())
    assert response.status_code == 400
    assert "entrada inválida" in response.json()["detail"]


def test_estimate_validation_error_short_description(client: TestClient) -> None:
    payload = {
        "description": "corta",
        "project_type": "web_saas",
        "detail_level": "medium",
        "output_format": "phases_table",
    }
    response = client.post("/api/v1/estimate", json=payload)
    assert response.status_code == 422
