from __future__ import annotations

from app.context.examples import ESTIMATION_EXAMPLES
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType
from app.services.llm_service import (
    build_estimation_user_message,
    build_system_prompt,
    format_cag_examples_block,
    get_system_role_prompt,
)


def test_estimation_examples_have_expected_keys() -> None:
    assert len(ESTIMATION_EXAMPLES) >= 1
    for ex in ESTIMATION_EXAMPLES:
        assert set(ex.keys()) == {"meeting_summary", "estimation"}
        assert len(ex["meeting_summary"].strip()) > 10
        assert len(ex["estimation"].strip()) > 50


def test_format_cag_examples_block_numbers_examples() -> None:
    block = format_cag_examples_block()
    assert "### Ejemplo 1" in block
    assert ESTIMATION_EXAMPLES[0]["meeting_summary"][:40] in block


def test_build_system_prompt_includes_role_and_cag_header() -> None:
    full = build_system_prompt()
    assert get_system_role_prompt() in full
    assert "Estimaciones de referencia (contexto CAG)" in full


def test_build_user_message_includes_enums_and_description() -> None:
    req = EstimationRequest(
        description="Descripción lo bastante larga para validar el modelo.",
        project_type=ProjectType.DATA_PIPELINE,
        detail_level=DetailLevel.DETAILED,
        output_format=OutputFormat.NARRATIVE,
    )
    msg = build_estimation_user_message(req)
    assert "data_pipeline" in msg
    assert "pipeline de datos" in msg
    assert "Descripción lo bastante larga" in msg
