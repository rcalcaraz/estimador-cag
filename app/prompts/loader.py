"""Renderizado de los prompts del estimador con Jinja2.

Las plantillas viven en ``app/prompts/<version>/`` con tres ficheros:

* ``system.j2``   – instrucciones de rol; incluye ``examples.j2``.
* ``user.j2``     – mensaje de usuario que envuelve los parámetros tipados
  y la descripción del proyecto.
* ``examples.j2`` – bloque few-shot que se inyecta en el system prompt.

El punto de entrada público es :func:`render_estimation_prompt`. Cambiar de
versión es solo cambiar el argumento ``version``; no hay que tocar nada más.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

DEFAULT_VERSION = "v1"

_PROMPTS_ROOT = Path(__file__).resolve().parent

_SYSTEM_TEMPLATE = "system.j2"
_USER_TEMPLATE = "user.j2"

# Etiquetas legibles para los enums del request. Viven aquí porque son
# decisiones de presentación del prompt (no de la API), y así los templates
# no necesitan saber nada de los enums.
_PROJECT_TYPE_LABEL: dict[ProjectType, str] = {
    ProjectType.MOBILE_APP: "aplicación móvil",
    ProjectType.WEB_SAAS: "SaaS / producto web",
    ProjectType.INTERNAL_TOOL: "herramienta interna",
    ProjectType.DATA_PIPELINE: "pipeline de datos / ETL",
}

_DETAIL_LEVEL_HINT: dict[DetailLevel, str] = {
    DetailLevel.SUMMARY: "Respuesta breve: visión general, totales aproximados y riesgos clave.",
    DetailLevel.MEDIUM: "Equilibrio entre síntesis y desglose: fases o áreas con orden de magnitud.",
    DetailLevel.DETAILED: "Muy detallado: desglose fino, supuestos explícitos, riesgos y dependencias.",
}

_OUTPUT_FORMAT_HINT: dict[OutputFormat, str] = {
    OutputFormat.PHASES_TABLE: "Prioriza una tabla por fases (o hitos) con esfuerzo y notas.",
    OutputFormat.LINE_ITEMS: "Prioriza lista de partidas / ítems numerados con estimación por ítem.",
    OutputFormat.NARRATIVE: "Prioriza narrativa continua (párrafos) manteniendo cifras donde aplique.",
}


@lru_cache(maxsize=8)
def _get_environment(version: str) -> Environment:
    """Devuelve (cacheado) un Environment de Jinja2 atado a ``app/prompts/<version>/``."""
    version_dir = _PROMPTS_ROOT / version
    if not version_dir.is_dir():
        raise FileNotFoundError(
            f"No existe el directorio de plantillas para la versión {version!r}: {version_dir}"
        )
    return Environment(
        loader=FileSystemLoader(str(version_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
        autoescape=False,
    )


def _build_context(request: EstimationRequest) -> dict[str, object]:
    """Resuelve enums a etiquetas legibles para que los templates queden tontos."""
    return {
        "description": request.description.strip(),
        "project_type": {
            "value": request.project_type.value,
            "label": _PROJECT_TYPE_LABEL[request.project_type],
        },
        "detail_level": {
            "value": request.detail_level.value,
            "hint": _DETAIL_LEVEL_HINT[request.detail_level],
        },
        "output_format": {
            "value": request.output_format.value,
            "hint": _OUTPUT_FORMAT_HINT[request.output_format],
        },
    }


def render_estimation_prompt(
    request: EstimationRequest,
    version: str = DEFAULT_VERSION,
) -> tuple[str, str]:
    """Renderiza ``(system, user)`` para una :class:`EstimationRequest`.

    Cambiar la versión del prompt es tan simple como pasar ``version="v2"``;
    el resto del código (servicios, router, tests) no necesita enterarse.
    """
    env = _get_environment(version)
    context = _build_context(request)
    system = env.get_template(_SYSTEM_TEMPLATE).render(context).strip()
    user = env.get_template(_USER_TEMPLATE).render(context).strip()
    return system, user
