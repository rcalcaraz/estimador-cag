from __future__ import annotations

import pytest

from app.schemas import (
    EstimationItem,
    EstimationTotals,
    StructuredEstimation,
)
from app.services.estimation_parser import parse_structured_estimation


def _sample_json() -> str:
    return """
{
  "title": "Estimación de prueba",
  "currency": "EUR",
  "items": [
    {"name": "Fase 1", "hours": 10, "cost": 800, "confidence_pct": 70}
  ],
  "totals": {"hours": 10, "cost": 800, "confidence_pct": 65},
  "risks_and_assumptions": ["Supuesto de prueba"]
}
"""


def test_parse_plain_json() -> None:
    est = parse_structured_estimation(_sample_json())
    assert est.title == "Estimación de prueba"
    assert len(est.items) == 1
    assert est.items[0].confidence_pct == 70


def test_parse_json_inside_markdown_fence() -> None:
    wrapped = f"```json\n{_sample_json().strip()}\n```"
    est = parse_structured_estimation(wrapped)
    assert est.totals.cost == 800
    assert est.totals.confidence_pct == 65


def test_parse_rejects_empty_body() -> None:
    with pytest.raises(ValueError, match="vacía"):
        parse_structured_estimation("   ")


def test_parse_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError, match="Esquema"):
        parse_structured_estimation('{"title": "x", "totals": {}}')


def test_structured_requires_items_or_narrative() -> None:
    with pytest.raises(ValueError):
        StructuredEstimation.model_validate(
            {
                "title": "Sin contenido",
                "totals": {"hours": 1},
                "items": [],
            }
        )


def test_narrative_only_valid() -> None:
    est = StructuredEstimation.model_validate(
        {
            "title": "Narrativa",
            "items": [],
            "totals": {"cost": 1000},
            "narrative_blocks": [{"title": "Alcance", "content": "Texto con cifras."}],
        }
    )
    assert est.narrative_blocks is not None
    assert len(est.narrative_blocks) == 1
