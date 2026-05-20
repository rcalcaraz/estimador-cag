import structlog
from fastapi import APIRouter, HTTPException

from app.prompts.loader import render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResponse
from app.services.llm_service import (
    ESTIMATION_PROMPT_VERSION,
    EstimationOutcome,
    complete_estimation,
)

log = structlog.get_logger()
router = APIRouter(tags=["estimaciones"])


def _estimation_response_from_outcome(outcome: EstimationOutcome) -> EstimationResponse:
    return EstimationResponse(
        text=outcome.estimation,
        prompt_version=ESTIMATION_PROMPT_VERSION,
        model=outcome.model,
        provider=outcome.provider,
        cache_hit=outcome.cache_hit,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        total_tokens=outcome.total_tokens,
        response_time_seconds=outcome.response_time_seconds,
        cost_usd=outcome.cost_usd,
    )


@router.post("/estimate", response_model=EstimationResponse)
async def estimate(body: EstimationRequest) -> EstimationResponse:
    """
    Genera una estimación de software a partir del cuerpo tipado (:class:`EstimationRequest`),
    usando plantillas Jinja (system + user) y contexto CAG en el system prompt.
    """
    system_prompt, user_message = render_estimation_prompt(body)
    try:
        outcome = await complete_estimation(system_prompt, user_message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.error("estimation_endpoint_error", error=str(e))
        raise HTTPException(
            status_code=502,
            detail=f"Error al llamar al proveedor LLM: {e!s}",
        ) from e

    return _estimation_response_from_outcome(outcome)
