"""Tests for ``enforce_scope_response`` (output filter policy)."""

from __future__ import annotations

from app.guardrails.output import enforce_scope_response
from app.schemas import (
    OUT_OF_SCOPE_PREFIX,
    EstimationPhase,
    EstimationTotals,
    StructuredEstimation,
)


def _build(*, confidence_pct: int, summary: str) -> StructuredEstimation:
    return StructuredEstimation.model_construct(
        summary=summary,
        phases=[
            EstimationPhase.model_construct(
                name="Discovery",
                description="Workshop and scoping.",
                weeks=2,
                cost=2500,
            )
        ],
        totals=EstimationTotals.model_construct(
            duration_weeks=2,
            cost=2500,
            confidence_pct=confidence_pct,
            currency="EUR",
        ),
    )


def test_high_confidence_passes_through_untouched() -> None:
    original = _build(confidence_pct=80, summary="Solid mid-size SaaS build.")
    out = enforce_scope_response(original)
    assert out is original


def test_low_confidence_with_correct_prefix_passes_through() -> None:
    original = _build(
        confidence_pct=15,
        summary=f"{OUT_OF_SCOPE_PREFIX} the description is too vague.",
    )
    out = enforce_scope_response(original)
    assert out is original


def test_low_confidence_without_prefix_gets_rewritten() -> None:
    original = _build(
        confidence_pct=10,
        summary="A standard SaaS project around 30k.",
    )
    out = enforce_scope_response(original)
    assert out is not original
    assert out.summary.startswith(OUT_OF_SCOPE_PREFIX)
    assert out.totals.confidence_pct == 10
    assert out.totals.cost == 0
    assert out.totals.duration_weeks == 1
    assert len(out.phases) == 1
    assert out.phases[0].name == "Not estimated"
    assert "A standard SaaS project around 30k." in out.summary


def test_filter_never_raises_even_with_pathological_input() -> None:
    original = _build(confidence_pct=0, summary="x" * 1000)
    out = enforce_scope_response(original)
    StructuredEstimation.model_validate(out.model_dump())
