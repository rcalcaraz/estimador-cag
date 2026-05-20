from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ProjectType(str, Enum):
    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"


class DetailLevel(str, Enum):
    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"


class OutputFormat(str, Enum):
    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"


class EstimationRequest(BaseModel):
    description: str = Field(min_length=20, max_length=2000)
    project_type: ProjectType
    detail_level: DetailLevel
    output_format: OutputFormat


class EstimationItem(BaseModel):
    """Fase, hito o partida del desglose."""

    name: str = Field(min_length=1)
    hours: Optional[float] = Field(default=None, ge=0)
    cost: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    confidence_pct: Optional[int] = Field(default=None, ge=0, le=100)


class EstimationTotals(BaseModel):
    hours: Optional[float] = Field(default=None, ge=0)
    cost: Optional[float] = Field(default=None, ge=0)
    hourly_rate_note: Optional[str] = None
    confidence_pct: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Confianza global (0–100) en los totales agregados de la estimación.",
    )


class NarrativeBlock(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


class StructuredEstimation(BaseModel):
    """Cuerpo estructurado de la estimación devuelto por el LLM y validado por la API."""

    title: str = Field(min_length=1)
    currency: str = Field(default="EUR", min_length=1)
    executive_summary: Optional[str] = None
    items: list[EstimationItem] = Field(default_factory=list)
    totals: EstimationTotals
    recommended_team: Optional[str] = None
    estimated_duration: Optional[str] = None
    risks_and_assumptions: list[str] = Field(default_factory=list)
    narrative_blocks: Optional[list[NarrativeBlock]] = None

    @model_validator(mode="after")
    def _has_content(self) -> "StructuredEstimation":
        has_items = len(self.items) > 0
        has_narrative = bool(self.narrative_blocks)
        if not has_items and not has_narrative:
            raise ValueError(
                "La estimación debe incluir al menos un ítem en 'items' o un bloque en 'narrative_blocks'"
            )
        return self


class EstimationResponse(BaseModel):
    estimation: StructuredEstimation
    prompt_version: str
    model: str
    provider: Literal["openai", "anthropic"]
    cache_hit: bool
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    response_time_seconds: Optional[float] = None
    cost_usd: Optional[float] = None
