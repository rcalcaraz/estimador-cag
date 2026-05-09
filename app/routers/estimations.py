from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException

from app.schema.estimations import EstimateRequest, EstimateResponse
from app.services.llm_service import generate_estimation

log = structlog.get_logger()
router = APIRouter(tags=["estimaciones"])


@router.post("/estimate", response_model=EstimateResponse)
async def estimate(body: EstimateRequest) -> EstimateResponse:
    """
    Genera una estimación de software a partir de la transcripción, usando el contexto CAG
    (ejemplos históricos en el system prompt).
    """
    try:
        outcome = await generate_estimation(body.transcription)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.error("estimation_endpoint_error", error=str(e))
        raise HTTPException(
            status_code=502,
            detail=f"Error al llamar al proveedor LLM: {e!s}",
        ) from e

    return EstimateResponse(
        estimation=outcome.estimation,
        model=outcome.model,
        provider=outcome.provider,
        generated_at=datetime.now(timezone.utc),
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        total_tokens=outcome.total_tokens,
    )
