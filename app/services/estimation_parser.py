"""Parseo y validación del JSON de estimación devuelto por el LLM."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas import StructuredEstimation

_JSON_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise ValueError("Respuesta vacía del proveedor")

    fence = _JSON_FENCE_RE.match(text)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e.msg}") from e

    if not isinstance(data, dict):
        raise ValueError("La estimación debe ser un objeto JSON (no un array ni un escalar)")
    return data


def parse_structured_estimation(raw: str) -> StructuredEstimation:
    """Convierte la salida del LLM en :class:`StructuredEstimation`."""
    data = _extract_json_object(raw)
    try:
        return StructuredEstimation.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Esquema de estimación inválido: {e}") from e
