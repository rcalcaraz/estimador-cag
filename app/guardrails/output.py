"""Output guardrails: belt-and-suspenders on top of schema validation.

``enforce_scope_response`` is a *filter* (not an *exception*): it rewrites the
``summary`` when the LLM produced a low-confidence answer without the
``Out of scope:`` prefix. In practice the prompt should steer the model, but this
filter handles edge cases at the boundary (``confidence_pct == 30`` exactly, or
future loosening of the threshold).
"""

from __future__ import annotations

import structlog

from app.schemas import (
    LOW_CONFIDENCE_THRESHOLD,
    OUT_OF_SCOPE_PREFIX,
    EstimationPhase,
    EstimationTotals,
    StructuredEstimation,
)

log = structlog.get_logger()


_NOT_ESTIMATED_PHASE = EstimationPhase(
    name="Not estimated",
    description="Cannot be sized without more information about scope, integrations and team.",
    weeks=1,
    cost=0,
)


def enforce_scope_response(estimation: StructuredEstimation) -> StructuredEstimation:
    """Rewrite the result if confidence is low and the summary does not declare it.

    Policy: ``filter`` — never raises, always returns a well-formed
    ``StructuredEstimation``. The user gets a clear message instead of an error.
    """
    is_low_confidence = estimation.totals.confidence_pct < LOW_CONFIDENCE_THRESHOLD
    already_marked = estimation.summary.startswith(OUT_OF_SCOPE_PREFIX)

    if not is_low_confidence or already_marked:
        return estimation

    log.info(
        "enforce_scope_response_filtering",
        confidence_pct=estimation.totals.confidence_pct,
        original_summary_chars=len(estimation.summary),
    )
    new_summary = (
        f"{OUT_OF_SCOPE_PREFIX} not enough information to estimate confidently. "
        f"Original model rationale: {estimation.summary[:400]}"
    )
    return StructuredEstimation(
        summary=new_summary[:1200],
        phases=[_NOT_ESTIMATED_PHASE],
        totals=EstimationTotals(
            duration_weeks=1,
            cost=0,
            confidence_pct=estimation.totals.confidence_pct,
            currency=estimation.totals.currency,
        ),
    )
