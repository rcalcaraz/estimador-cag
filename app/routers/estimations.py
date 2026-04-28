from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.llm_service import generate_estimation

router = APIRouter(tags=["estimaciones"])


class EstimateRequest(BaseModel):
    transcription: str = Field(
        ...,
        min_length=1,
        description="Texto de la transcripción de la reunión a estimar.",
        json_schema_extra={"example": "En la reunión con el cliente se discutió la necesidad de..."},
    )


class EstimateResponse(BaseModel):
    estimation: str = Field(..., description="Estimación generada por el modelo (markdown).")
    model: str = Field(..., description="Identificador del modelo usado.")
    provider: str = Field(..., description="Proveedor LLM: openai o anthropic.")
    generated_at: datetime = Field(..., description="Marca temporal UTC de la respuesta.")
    input_tokens: Optional[int] = Field(
        None, description="Tokens de entrada reportados por el proveedor."
    )
    output_tokens: Optional[int] = Field(
        None, description="Tokens de salida reportados por el proveedor."
    )
    total_tokens: Optional[int] = Field(
        None, description="Total de tokens si el proveedor lo expone."
    )


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
