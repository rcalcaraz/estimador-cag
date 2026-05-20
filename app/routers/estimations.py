from dataclasses import replace

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_openai_client, get_semantic_cache
from app.guardrails.input import InputGuardrailViolation, check_input
from app.guardrails.output import enforce_scope_response
from app.prompts.loader import render_estimation_prompt
from app.schemas import CacheKind, EstimationRequest, EstimationResponse
from app.services.llm_service import (
    ESTIMATION_PROMPT_VERSION,
    EstimationOutcome,
    complete_estimation,
    try_exact_cache_lookup,
)

log = structlog.get_logger()
router = APIRouter(tags=["estimaciones"])


def _estimation_response_from_outcome(outcome: EstimationOutcome) -> EstimationResponse:
    return EstimationResponse(
        estimation=outcome.estimation,
        prompt_version=ESTIMATION_PROMPT_VERSION,
        model=outcome.model,
        provider=outcome.provider,
        cache_hit=outcome.cache_kind != CacheKind.NONE,
        cache_kind=outcome.cache_kind,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        total_tokens=outcome.total_tokens,
        response_time_seconds=outcome.response_time_seconds,
        cost_usd=outcome.cost_usd,
    )


@router.post("/estimate", response_model=EstimationResponse)
async def estimate(
    body: EstimationRequest,
    openai_client=Depends(get_openai_client),
) -> EstimationResponse:
    """
    Genera una estimación de software a partir del cuerpo tipado (:class:`EstimationRequest`),
    usando plantillas Jinja (system + user) y contexto CAG en el system prompt.
    """
    log.info(
        "estimation_request_received",
        project_type=body.project_type.value,
        detail_level=body.detail_level.value,
        output_format=body.output_format.value,
        description_chars=len(body.description),
    )

    try:
        check_input(body.description, openai_client=openai_client)
    except InputGuardrailViolation as exc:
        log.info(
            "estimation_blocked_by_input_guardrail",
            reason=exc.reason,
            message=exc.message,
        )
        raise HTTPException(
            status_code=400,
            detail={"reason": exc.reason, "message": exc.message},
        ) from exc

    system_prompt, user_message = render_estimation_prompt(body)

    exact_outcome = try_exact_cache_lookup(system_prompt, user_message)
    if exact_outcome is not None:
        log.info("estimation_cache_hit", kind="exact")
        outcome = replace(
            exact_outcome,
            estimation=enforce_scope_response(exact_outcome.estimation),
        )
        return _estimation_response_from_outcome(outcome)

    semantic_cache = get_semantic_cache()
    if semantic_cache is not None:
        semantic_hit = semantic_cache.lookup(body, ESTIMATION_PROMPT_VERSION)
        if semantic_hit is not None:
            log.info("estimation_cache_hit", kind="semantic")
            outcome = EstimationOutcome(
                estimation=enforce_scope_response(semantic_hit.estimation),
                model=semantic_hit.model,
                provider=semantic_hit.provider,
                cache_kind=CacheKind.SEMANTIC,
            )
            return _estimation_response_from_outcome(outcome)

    try:
        outcome = await complete_estimation(system_prompt, user_message)
        outcome = replace(
            outcome,
            estimation=enforce_scope_response(outcome.estimation),
        )
        if semantic_cache is not None:
            semantic_cache.store(
                body,
                outcome.estimation,
                ESTIMATION_PROMPT_VERSION,
                model=outcome.model,
                provider=outcome.provider,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.error("estimation_endpoint_error", error=str(e))
        raise HTTPException(
            status_code=502,
            detail=f"Error al llamar al proveedor LLM: {e!s}",
        ) from e

    return _estimation_response_from_outcome(outcome)
