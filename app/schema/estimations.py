from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
