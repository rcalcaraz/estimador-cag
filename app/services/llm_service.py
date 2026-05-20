"""Llamadas al LLM para generar estimaciones (CAG: contexto en el system prompt).

Las llamadas pasan por :mod:`app.services.llm_wrapper` (LiteLLM + fallback + caché Redis),
igual que en ai-engineering.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Literal, Optional

from app.context.examples import ESTIMATION_EXAMPLES
from app.dependencies import get_llm_wrapper
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

DEFAULT_MAX_TOKENS = 8192

# Versión de las plantillas Jinja en ``app/prompts/<version>/`` (expuesta en la API).
ESTIMATION_PROMPT_VERSION = "v1"

_SYSTEM_ROLE = """Eres un estimador de software experto. Tu tarea es producir estimaciones de esfuerzo, coste y planificación basándote en:

1. Los ejemplos de estimaciones previas que recibes a continuación (son tu referencia de tono, granularidad y formato).
2. La transcripción de una nueva reunión con el cliente, que el usuario te enviará en el siguiente mensaje.

Debes imitar la estructura y el nivel de detalle de los ejemplos: desglose de tareas con horas y costes cuando aplique, totales, equipo recomendado, duración y riesgos o supuestos claros. Si la transcripción es incompleta, indica supuestos explícitos antes de cifrar.

Responde únicamente con la estimación (cuerpo del documento), en el mismo idioma que la transcripción salvo que el cliente pida otro idioma explícitamente."""


@dataclass(frozen=True)
class EstimationOutcome:
    """Resultado de una llamada al LLM para estimar."""

    estimation: str
    model: str
    provider: Literal["openai", "anthropic"]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    response_time_seconds: Optional[float] = None
    cost_usd: Optional[float] = None
    cache_hit: bool = False


def get_system_role_prompt() -> str:
    """Texto de instrucciones de rol enviado al inicio del mensaje *system* (sin ejemplos CAG)."""
    return _SYSTEM_ROLE.strip()


def format_cag_examples_block() -> str:
    """Bloque de ejemplos de estimación inyectados como contexto CAG (mismo formato que en el *system*)."""
    parts: List[str] = []
    for i, ex in enumerate(ESTIMATION_EXAMPLES, start=1):
        parts.append(
            f"### Ejemplo {i}\n"
            f"**Resumen de la reunión original:**\n{ex['meeting_summary'].strip()}\n\n"
            f"**Estimación generada entonces:**\n{ex['estimation'].strip()}"
        )
    return "\n\n".join(parts)


def build_system_prompt() -> str:
    """Instrucciones de rol + ejemplos históricos inyectados (mensaje *system*)."""
    return "\n\n".join(
        [
            get_system_role_prompt(),
            "## Estimaciones de referencia (contexto CAG)",
            format_cag_examples_block(),
        ]
    )


_PROJECT_TYPE_LABEL: dict[ProjectType, str] = {
    ProjectType.MOBILE_APP: "aplicación móvil",
    ProjectType.WEB_SAAS: "SaaS / producto web",
    ProjectType.INTERNAL_TOOL: "herramienta interna",
    ProjectType.DATA_PIPELINE: "pipeline de datos / ETL",
}

_DETAIL_LEVEL_HINT: dict[DetailLevel, str] = {
    DetailLevel.SUMMARY: "Respuesta breve: visionado general, totales aproximados y riesgos clave.",
    DetailLevel.MEDIUM: "Equilibrio entre síntesis y desglose: fases o áreas con orden de magnitud.",
    DetailLevel.DETAILED: "Muy detallado: desglose fino, supuestos explícitos, riesgos y dependencias.",
}

_OUTPUT_FORMAT_HINT: dict[OutputFormat, str] = {
    OutputFormat.PHASES_TABLE: "Prioriza una tabla por fases (o hitos) con esfuerzo y notas.",
    OutputFormat.LINE_ITEMS: "Prioriza lista de partidas / ítems numerados con estimación por ítem.",
    OutputFormat.NARRATIVE: "Prioriza narrativa continua (párrafos) manteniendo cifras donde aplique.",
}


def build_estimation_user_message(req: EstimationRequest) -> str:
    """Construye el mensaje de usuario a partir del contrato :class:`EstimationRequest`."""
    desc = req.description.strip()
    pt = _PROJECT_TYPE_LABEL[req.project_type]
    dl = _DETAIL_LEVEL_HINT[req.detail_level]
    fmt = _OUTPUT_FORMAT_HINT[req.output_format]
    return (
        "## Parámetros del encargo\n"
        f"- **Tipo de proyecto:** {pt} (`{req.project_type.value}`)\n"
        f"- **Nivel de detalle:** {dl}\n"
        f"- **Formato de salida deseado:** {fmt}\n\n"
        "## Descripción del alcance / contexto\n"
        f"{desc}"
    )


def _coerce_provider(raw: str, model: str) -> Literal["openai", "anthropic"]:
    if raw in ("openai", "anthropic"):
        return raw  # type: ignore[return-value]
    m = model.lower()
    if "claude" in m:
        return "anthropic"
    return "openai"


def _wrapper_result_to_outcome(result: dict, *, elapsed_s: float) -> EstimationOutcome:
    usage = result.get("usage") or {}
    return EstimationOutcome(
        estimation=(result.get("estimation") or "").strip(),
        model=result.get("model") or "",
        provider=_coerce_provider(result.get("provider") or "", result.get("model") or ""),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
        response_time_seconds=elapsed_s,
        cost_usd=result.get("cost_usd"),
        cache_hit=bool(result.get("cache_hit")),
    )


async def complete_estimation(system_prompt: str, user_message: str) -> EstimationOutcome:
    """
    Llama al wrapper LiteLLM con ``role=system`` y ``role=user`` como mensajes separados
    (no concatenados).

    El router LiteLLM usa ``PRIMARY_MODEL`` (OpenAI) y ``FALLBACK_MODEL`` (Anthropic);
    el orden depende de ``LLM_PROVIDER``. Se requiere al menos una API key (fallback opcional).
    """
    wrapper = get_llm_wrapper()

    t0 = time.perf_counter()
    result = await wrapper.acomplete(
        system_prompt=system_prompt,
        user_message=user_message,
        model_override=None,
        max_tokens=DEFAULT_MAX_TOKENS,
        thinking_budget=None,
        temperature=0.3,
    )
    wall_s = time.perf_counter() - t0
    latency_ms = result.get("latency_ms")
    elapsed_s = (latency_ms / 1000.0) if isinstance(latency_ms, int) else wall_s

    rendered = (result.get("estimation") or "").strip()
    if not rendered:
        raise RuntimeError("El proveedor devolvió contenido vacío")

    return _wrapper_result_to_outcome({**result, "estimation": rendered}, elapsed_s=elapsed_s)
