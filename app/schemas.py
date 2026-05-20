from enum import Enum
from typing import Any, Literal, Optional

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


class EstimationPhase(BaseModel):
    """Fase o hito del desglose mostrado en la UI."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    weeks: float = Field(ge=0)
    cost: float = Field(ge=0)


class EstimationTotals(BaseModel):
    duration_weeks: float = Field(ge=0)
    cost: float = Field(ge=0)
    confidence_pct: int = Field(ge=0, le=100)
    currency: str = Field(default="EUR", min_length=1)


def normalize_estimation_dict(data: Any) -> dict[str, Any]:
    """
    Adapta respuestas del esquema anterior (title, items, hours) al contrato actual.
    Útil para caché Redis antigua y para clientes que aún no se han reiniciado.
    """
    if not isinstance(data, dict):
        raise TypeError("La estimación debe ser un objeto JSON")

    d = dict(data)

    if "summary" not in d:
        if isinstance(d.get("title"), str):
            d["summary"] = d.pop("title")
        elif isinstance(d.get("executive_summary"), str):
            d["summary"] = d.pop("executive_summary")

    if "phases" not in d and isinstance(d.get("items"), list):
        phases: list[dict[str, Any]] = []
        for item in d["items"]:
            if not isinstance(item, dict):
                continue
            desc = item.get("description") or item.get("notes") or item.get("name") or ""
            weeks = item.get("weeks")
            if weeks is None and item.get("hours") is not None:
                weeks = max(0.5, float(item["hours"]) / 40.0)
            phases.append(
                {
                    "name": str(item.get("name") or "Phase"),
                    "description": str(desc),
                    "weeks": float(weeks if weeks is not None else 1),
                    "cost": float(item.get("cost") or 0),
                }
            )
        d["phases"] = phases
        d.pop("items", None)

    totals = d.get("totals")
    if isinstance(totals, dict):
        t = dict(totals)
        if "duration_weeks" not in t and t.get("hours") is not None:
            t["duration_weeks"] = max(1.0, float(t["hours"]) / 40.0)
        t.setdefault("cost", 0.0)
        t.setdefault("duration_weeks", 1.0)
        t.setdefault("confidence_pct", 50)
        t.setdefault("currency", d.get("currency") or "EUR")
        d["totals"] = t

    for key in (
        "title",
        "executive_summary",
        "items",
        "narrative_blocks",
        "recommended_team",
        "estimated_duration",
        "risks_and_assumptions",
        "currency",
    ):
        d.pop(key, None)

    return d


class StructuredEstimation(BaseModel):
    """Cuerpo estructurado de la estimación devuelto por el LLM y validado por la API."""

    summary: str = Field(min_length=1)
    phases: list[EstimationPhase] = Field(min_length=1)
    totals: EstimationTotals

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return normalize_estimation_dict(data)
        return data


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

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_estimation(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("estimation"), dict):
            payload = dict(data)
            payload["estimation"] = normalize_estimation_dict(payload["estimation"])
            return payload
        return data
