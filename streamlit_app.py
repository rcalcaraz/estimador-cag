"""
Interfaz Streamlit para el estimador CAG: formulario tipado, streaming NDJSON vía API y panel de metadatos.
Ejecutar desde la raíz del proyecto: streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import List

import httpx
import streamlit as st
from pydantic import ValidationError

from app.config import get_settings
from app.schemas import (
    DetailLevel,
    EstimationRequest,
    EstimationResponse,
    OutputFormat,
    ProjectType,
)
from app.services.llm_service import build_system_prompt, format_cag_examples_block

_PROJECT_TYPE_LABEL: dict[ProjectType, str] = {
    ProjectType.MOBILE_APP: "App móvil",
    ProjectType.WEB_SAAS: "SaaS web",
    ProjectType.INTERNAL_TOOL: "Herramienta interna",
    ProjectType.DATA_PIPELINE: "Pipeline de datos",
}

_DETAIL_LEVEL_LABEL: dict[DetailLevel, str] = {
    DetailLevel.SUMMARY: "Resumen",
    DetailLevel.MEDIUM: "Medio",
    DetailLevel.DETAILED: "Detallado",
}

_OUTPUT_FORMAT_LABEL: dict[OutputFormat, str] = {
    OutputFormat.PHASES_TABLE: "Tabla por fases",
    OutputFormat.LINE_ITEMS: "Partidas / ítems",
    OutputFormat.NARRATIVE: "Narrativa",
}


def _init_session_state() -> None:
    if "last_estimation" not in st.session_state:
        st.session_state.last_estimation = None


def _format_token_value(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", ".")


def _stream_estimate_deltas(
    base_url: str,
    req: EstimationRequest,
    final_out: List[EstimationResponse],
) -> Iterator[str]:
    """Emite fragmentos de texto; al terminar deja la respuesta completa en *final_out*."""
    url = base_url.rstrip("/") + "/api/v1/estimate/stream"
    payload = req.model_dump(mode="json")
    timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST",
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as response:
            if response.status_code >= 400:
                detail = response.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"HTTP {response.status_code}: {detail}")
            for line in response.iter_lines():
                if not line.strip():
                    continue
                msg = json.loads(line)
                mtype = msg.get("type")
                if mtype == "delta" and msg.get("text"):
                    yield msg["text"]
                elif mtype == "final":
                    data = {k: v for k, v in msg.items() if k != "type"}
                    final_out.clear()
                    final_out.append(EstimationResponse.model_validate(data))
                elif mtype == "error":
                    raise RuntimeError(msg.get("detail", "Error del servicio"))


def _render_cag_sidebar() -> None:
    st.sidebar.header("Transparencia CAG")
    st.sidebar.caption(
        "El servicio incluye rol y ejemplos en el *system*; el formulario se serializa como "
        "`EstimationRequest` y la UI consume el stream NDJSON de `/estimate/stream`."
    )

    with st.sidebar.expander("System prompt activo (solo lectura)", expanded=False):
        st.text_area(
            "system_prompt_full",
            value=build_system_prompt(),
            height=260,
            disabled=True,
            label_visibility="collapsed",
        )

    with st.sidebar.expander("Contexto estático: ejemplos de estimación", expanded=False):
        st.text_area(
            "cag_examples",
            value=format_cag_examples_block(),
            height=320,
            disabled=True,
            label_visibility="collapsed",
        )

    st.sidebar.subheader("Última llamada al modelo")
    last: EstimationResponse | None = st.session_state.last_estimation
    if last is None:
        st.sidebar.info("Aún no hay una respuesta completada en esta sesión.")
        return

    st.sidebar.caption(f"**prompt_version:** `{last.prompt_version}`")

    if last.cache_hit:
        st.sidebar.success("Origen: **caché Redis** (sin nueva llamada al modelo).")
    else:
        st.sidebar.info("Origen: **llamada en directo** al modelo.")

    st.sidebar.metric("Modelo", last.model)
    st.sidebar.caption(f"Proveedor: **{last.provider}**")
    c1, c2 = st.sidebar.columns(2)
    c1.metric("Tokens entrada", _format_token_value(last.input_tokens))
    c2.metric("Tokens salida", _format_token_value(last.output_tokens))
    if last.total_tokens is not None:
        st.sidebar.caption(f"Total tokens (reportado): {_format_token_value(last.total_tokens)}")
    if last.cost_usd is not None and last.cost_usd > 0:
        st.sidebar.caption(f"Coste estimado (USD): **{last.cost_usd:.6f}**")
    if last.response_time_seconds is not None:
        t = last.response_time_seconds
        st.sidebar.metric(
            "Tiempo de respuesta",
            f"{t:.2f} s" if t < 60 else f"{t / 60:.1f} min",
        )


def main() -> None:
    st.set_page_config(page_title="Estimador CAG", page_icon="📋", layout="wide")
    st.title("Estimador de software (CAG)")
    st.caption(
        "Completa el formulario para enviar un `EstimationRequest`; la estimación se muestra en **streaming**."
    )

    _init_session_state()
    settings = get_settings()
    api_base = settings.estimator_api_base_url

    with st.sidebar.expander("Conexión", expanded=False):
        st.caption(f"Stream NDJSON `{api_base.rstrip('/')}/api/v1/estimate/stream`")

    with st.form("estimation_form"):
        description = st.text_area(
            "Descripción del alcance (20–2000 caracteres)",
            height=200,
            placeholder="Describe contexto, objetivos, integraciones y restricciones…",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            project_type = st.selectbox(
                "Tipo de proyecto",
                options=list(ProjectType),
                format_func=lambda x: _PROJECT_TYPE_LABEL[x],
            )
        with c2:
            detail_level = st.selectbox(
                "Nivel de detalle",
                options=list(DetailLevel),
                format_func=lambda x: _DETAIL_LEVEL_LABEL[x],
            )
        with c3:
            output_format = st.selectbox(
                "Formato de salida",
                options=list(OutputFormat),
                format_func=lambda x: _OUTPUT_FORMAT_LABEL[x],
            )

        submitted = st.form_submit_button("Obtener estimación")

    if submitted:
        try:
            req = EstimationRequest(
                description=description,
                project_type=project_type,
                detail_level=detail_level,
                output_format=output_format,
            )
        except ValidationError as e:
            st.error("Revisa los datos del formulario.")
            st.json(json.loads(e.json()))
        else:
            final_holder: list[EstimationResponse] = []

            def chunk_iter() -> Iterator[str]:
                yield from _stream_estimate_deltas(api_base, req, final_holder)

            try:
                with st.chat_message("assistant"):
                    st.write_stream(chunk_iter)
            except RuntimeError as e:
                st.error(str(e))
            else:
                if final_holder:
                    st.session_state.last_estimation = final_holder[0]
                    st.success("Respuesta completada.")
                else:
                    st.warning("El stream terminó sin una línea `final` válida.")

    elif st.session_state.last_estimation is not None:
        with st.chat_message("assistant"):
            st.markdown(st.session_state.last_estimation.text)

    _render_cag_sidebar()


if __name__ == "__main__":
    main()
