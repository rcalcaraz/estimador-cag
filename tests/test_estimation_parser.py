from __future__ import annotations

import pytest

from app.schemas import StructuredEstimation
from app.services.estimation_parser import parse_structured_estimation


def _sample_json() -> str:
    return """
{
  "summary": "Estimación orientativa para un panel web con integración ERP.",
  "phases": [
    {
      "name": "Discovery & Requirements",
      "description": "Entrevistas y definición de alcance.",
      "weeks": 2,
      "cost": 2500
    }
  ],
  "totals": {
    "duration_weeks": 2,
    "cost": 2500,
    "confidence_pct": 65,
    "currency": "EUR"
  }
}
"""


def test_parse_plain_json() -> None:
    est = parse_structured_estimation(_sample_json())
    assert est.summary.startswith("Estimación")
    assert len(est.phases) == 1
    assert est.phases[0].name == "Discovery & Requirements"
    assert est.totals.confidence_pct == 65


def test_parse_json_inside_markdown_fence() -> None:
    wrapped = f"```json\n{_sample_json().strip()}\n```"
    est = parse_structured_estimation(wrapped)
    assert est.totals.cost == 2500


def test_parse_rejects_empty_body() -> None:
    with pytest.raises(ValueError, match="vacía"):
        parse_structured_estimation("   ")


def test_parse_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError, match="Esquema"):
        parse_structured_estimation(
            '{"summary": "x", "phases": [], "totals": {"duration_weeks": 1, "cost": 1, "confidence_pct": 50}}'
        )


def test_normalize_legacy_title_and_items() -> None:
    legacy = {
        "title": "Admin portal",
        "items": [
            {
                "name": "Discovery",
                "hours": 80,
                "cost": 2500,
                "notes": "Stakeholder interviews",
            }
        ],
        "totals": {"hours": 80, "cost": 2500, "confidence_pct": 72},
        "currency": "EUR",
    }
    est = StructuredEstimation.model_validate(legacy)
    assert est.summary == "Admin portal"
    assert len(est.phases) == 1
    assert est.phases[0].weeks == 2.0
    assert est.totals.confidence_pct == 72


def test_structured_requires_at_least_one_phase() -> None:
    with pytest.raises(Exception):
        StructuredEstimation.model_validate(
            {
                "summary": "Sin fases",
                "phases": [],
                "totals": {"duration_weeks": 1, "cost": 100, "confidence_pct": 50},
            }
        )
