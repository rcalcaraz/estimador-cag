"""Tests unitarios del render Jinja v1 (sin LLM ni red)."""

from __future__ import annotations

from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

_BASE = dict(
    project_type=ProjectType.WEB_SAAS,
    detail_level=DetailLevel.MEDIUM,
    output_format=OutputFormat.LINE_ITEMS,
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


def test_system_phases_table_includes_format_keywords_narrative_does_not() -> None:
    common = dict(
        description="Texto de descripción suficientemente largo.",
        detail_level=DetailLevel.SUMMARY,
        project_type=ProjectType.MOBILE_APP,
    )
    system_table, _ = render_estimation_prompt(
        _request(output_format=OutputFormat.PHASES_TABLE, **common)
    )
    system_narrative, _ = render_estimation_prompt(
        _request(output_format=OutputFormat.NARRATIVE, **common)
    )

    assert "phases_table" in system_table
    assert "confidence_pct" in system_table
    assert "phases_table" not in system_narrative
    assert "confidence_pct" not in system_narrative


def test_system_detailed_includes_per_phase_assumptions_summary_does_not() -> None:
    phrase = "por cada fase o hito"
    common = dict(
        description="Otro texto de descripción que cumple el mínimo.",
        output_format=OutputFormat.NARRATIVE,
        project_type=ProjectType.INTERNAL_TOOL,
    )
    system_detailed, _ = render_estimation_prompt(
        _request(detail_level=DetailLevel.DETAILED, **common)
    )
    system_summary, _ = render_estimation_prompt(
        _request(detail_level=DetailLevel.SUMMARY, **common)
    )

    assert phrase in system_detailed
    assert phrase not in system_summary
