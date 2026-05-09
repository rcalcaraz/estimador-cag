"""Llamadas al LLM para generar estimaciones (CAG: contexto en el system prompt).

Las llamadas pasan por :mod:`app.services.llm_wrapper` (LiteLLM + fallback + caché Redis),
igual que en ai-engineering.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import AsyncIterator, List, Literal, Optional

from app.config import Settings, get_settings
from app.dependencies import get_llm_wrapper
from app.context.examples import ESTIMATION_EXAMPLES

DEFAULT_MAX_TOKENS = 8192

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


async def stream_estimation_text(
    meeting_transcript: str,
    *,
    cfg: Settings | None = None,
    outcome_holder: List[EstimationOutcome],
) -> AsyncIterator[str]:
    """
    Igual que `generate_estimation`, pero emite la estimación por fragmentos (streaming).

    Tras consumir el iterador, el resultado completo y metadatos quedan en *outcome_holder*.
    Los tokens pueden ser ``None`` si el proveedor no los reporta en modo streaming.
    """
    text = (meeting_transcript or "").strip()
    if not text:
        raise ValueError("La transcripción de la reunión no puede estar vacía")

    settings = cfg or get_settings()
    system_prompt = build_system_prompt()
    wrapper = get_llm_wrapper()

    t0 = time.perf_counter()
    parts: List[str] = []

    async for piece in wrapper.acomplete_stream(
        system_prompt=system_prompt,
        user_message=text,
        model_override=None,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=0.3,
    ):
        parts.append(piece)
        yield piece

    elapsed = time.perf_counter() - t0
    rendered = "".join(parts).strip()
    if not rendered:
        raise RuntimeError("El proveedor devolvió contenido vacío")

    outcome_holder.clear()
    outcome_holder.append(
        EstimationOutcome(
            estimation=rendered,
            model=settings.primary_model,
            provider="anthropic" if settings.llm_provider == "anthropic" else "openai",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            response_time_seconds=elapsed,
            cost_usd=None,
            cache_hit=False,
        )
    )


async def generate_estimation(
    meeting_transcript: str,
    *,
    cfg: Settings | None = None,
) -> EstimationOutcome:
    """
    Envía [system] = rol + ejemplos, [user] = transcripción; devuelve la estimación y metadatos.

    El router LiteLLM usa ``PRIMARY_MODEL`` (OpenAI) y ``FALLBACK_MODEL`` (Anthropic);
    el orden depende de ``LLM_PROVIDER``. Se requiere al menos una API key (fallback opcional).
    """
    text = (meeting_transcript or "").strip()
    if not text:
        raise ValueError("La transcripción de la reunión no puede estar vacía")

    settings = cfg or get_settings()
    system_prompt = build_system_prompt()
    wrapper = get_llm_wrapper()

    t0 = time.perf_counter()
    result = await wrapper.acomplete(
        system_prompt=system_prompt,
        user_message=text,
        model_override=None,
        max_tokens=DEFAULT_MAX_TOKENS,
        thinking_budget=None,
        temperature=0.3,
    )
    wall_s = time.perf_counter() - t0
    latency_ms = result.get("latency_ms")
    elapsed_s = (latency_ms / 1000.0) if isinstance(latency_ms, int) else wall_s

    body = (result.get("estimation") or "").strip()
    if not body:
        raise RuntimeError("El proveedor devolvió contenido vacío")

    outcome = _wrapper_result_to_outcome({**result, "estimation": body}, elapsed_s=elapsed_s)
    return outcome
