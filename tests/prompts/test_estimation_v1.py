"""Tests unitarios del render Jinja v1 (sin LLM ni red)."""

from __future__ import annotations

from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

_BASE = dict(
    project_type=ProjectType.WEB_SAAS,
    detail_level=DetailLevel.MEDIUM,
    output_format=OutputFormat.PHASES_TABLE,
)


def _request(**overrides: object) -> EstimationRequest:
    fields = {**_BASE, **overrides}
    return EstimationRequest(**fields)


def test_user_message_includes_description_inside_project_description_block() -> None:
    description = (
        "Descripción de proyecto para test de plantilla: incluye caracteres "
        "como <tags> & \"comillas\" y saltos\nexplícitos."
    )
    _, user = render_estimation_prompt(_request(description=description))

    open_tag = "<project_description>"
    close_tag = "</project_description>"
    assert open_tag in user
    assert close_tag in user
    inner = user[user.index(open_tag) + len(open_tag) : user.index(close_tag)].strip()
    assert inner == description.strip()


def test_system_includes_simplified_json_schema() -> None:
    system, _ = render_estimation_prompt(
        _request(
            description="Texto de descripción suficientemente largo para validar.",
        )
    )
    assert '"phases"' in system
    assert '"summary"' in system
    assert '"duration_weeks"' in system
    assert '"confidence_pct"' in system
    assert "narrative_blocks" not in system


def test_system_summary_level_limits_phases_in_prompt() -> None:
    system_summary, _ = render_estimation_prompt(
        _request(
            description="Texto de descripción suficientemente largo.",
            detail_level=DetailLevel.SUMMARY,
        )
    )
    system_detailed, _ = render_estimation_prompt(
        _request(
            description="Texto de descripción suficientemente largo.",
            detail_level=DetailLevel.DETAILED,
        )
    )
    assert "summary" in system_summary.lower()
    assert "detailed" in system_detailed.lower()
