"""Llamadas al LLM para generar estimaciones (CAG: contexto en el system prompt)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config import Settings, get_settings
from app.context.examples import ESTIMATION_EXAMPLES

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"

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


def build_system_prompt() -> str:
    """Instrucciones de rol + ejemplos históricos inyectados (mensaje *system*)."""
    blocks: List[str] = [_SYSTEM_ROLE.strip(), "## Estimaciones de referencia (contexto CAG)"]
    for i, ex in enumerate(ESTIMATION_EXAMPLES, start=1):
        blocks.append(
            f"### Ejemplo {i}\n"
            f"**Resumen de la reunión original:**\n{ex['meeting_summary'].strip()}\n\n"
            f"**Estimación generada entonces:**\n{ex['estimation'].strip()}"
        )
    return "\n\n".join(blocks)


def _resolve_model(cfg: Settings) -> str:
    if cfg.llm_provider == "anthropic":
        m = (cfg.llm_model or "").strip()
        if not m or m.startswith("gpt"):
            return DEFAULT_ANTHROPIC_MODEL
        return m
    return (cfg.llm_model or "").strip() or DEFAULT_OPENAI_MODEL


def _require_api_key(cfg: Settings) -> None:
    if cfg.llm_provider == "openai":
        if not (cfg.openai_api_key and cfg.openai_api_key.strip()):
            raise ValueError("Falta OPENAI_API_KEY para LLM_PROVIDER=openai")
    else:
        if not (cfg.anthropic_api_key and cfg.anthropic_api_key.strip()):
            raise ValueError("Falta ANTHROPIC_API_KEY para LLM_PROVIDER=anthropic")


def _anthropic_text_content(message: object) -> str:
    parts: List[str] = []
    for block in getattr(message, "content", []) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


async def _call_openai(cfg: Settings, system_prompt: str, user_transcript: str) -> EstimationOutcome:
    client = AsyncOpenAI(api_key=cfg.openai_api_key)
    model = _resolve_model(cfg)
    completion = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_transcript},
        ],
        temperature=0.3,
    )
    choice = completion.choices[0].message
    text = (choice.content or "").strip()
    if not text:
        raise RuntimeError("OpenAI devolvió contenido vacío")
    usage = getattr(completion, "usage", None)
    prompt_t = getattr(usage, "prompt_tokens", None) if usage else None
    completion_t = getattr(usage, "completion_tokens", None) if usage else None
    total_t = getattr(usage, "total_tokens", None) if usage else None
    return EstimationOutcome(
        estimation=text,
        model=model,
        provider="openai",
        input_tokens=prompt_t,
        output_tokens=completion_t,
        total_tokens=total_t,
    )


async def _call_anthropic(cfg: Settings, system_prompt: str, user_transcript: str) -> EstimationOutcome:
    client = AsyncAnthropic(api_key=cfg.anthropic_api_key)
    model = _resolve_model(cfg)
    message = await client.messages.create(
        model=model,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": user_transcript}],
        temperature=0.3,
    )
    text = _anthropic_text_content(message)
    if not text:
        raise RuntimeError("Anthropic devolvió contenido vacío")
    usage = getattr(message, "usage", None)
    in_t = getattr(usage, "input_tokens", None) if usage else None
    out_t = getattr(usage, "output_tokens", None) if usage else None
    total = (in_t + out_t) if in_t is not None and out_t is not None else None
    return EstimationOutcome(
        estimation=text,
        model=model,
        provider="anthropic",
        input_tokens=in_t,
        output_tokens=out_t,
        total_tokens=total,
    )


async def generate_estimation(
    meeting_transcript: str,
    *,
    cfg: Settings | None = None,
) -> EstimationOutcome:
    """
    Envía [system] = rol + ejemplos, [user] = transcripción; devuelve la estimación y metadatos.

    El proveedor y el modelo se toman de la configuración (`LLM_PROVIDER`, `LLM_MODEL`), con modelos
    económicos por defecto: gpt-4o-mini (OpenAI) y claude-haiku-4-5 (Anthropic).
    """
    text = (meeting_transcript or "").strip()
    if not text:
        raise ValueError("La transcripción de la reunión no puede estar vacía")

    settings = cfg or get_settings()
    _require_api_key(settings)
    system_prompt = build_system_prompt()

    if settings.llm_provider == "openai":
        return await _call_openai(settings, system_prompt, text)
    return await _call_anthropic(settings, system_prompt, text)
