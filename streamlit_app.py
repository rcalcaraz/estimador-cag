"""
Interfaz Streamlit para el estimador CAG: formulario → API → vista de estimación.
Ejecutar desde la raíz del proyecto: streamlit run streamlit_app.py
"""

from __future__ import annotations

import html
import json

import httpx
import streamlit as st
from pydantic import ValidationError

from app.config import get_settings
from app.schemas import (
    CacheKind,
    DetailLevel,
    EstimationRequest,
    EstimationResponse,
    OutputFormat,
    ProjectType,
    StructuredEstimation,
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

_DARK_CSS = """
<style>
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #0f1419;
    }
    [data-testid="stSidebar"] {
        background-color: #151b23;
        border-right: 1px solid #2a3441;
    }
    h1, h2, h3, p, label, .stMarkdown, span {
        color: #e8eaed;
    }
    .est-summary-text {
        color: #9aa0a6;
        font-size: 0.95rem;
        margin: 0 0 1.5rem 0;
        line-height: 1.5;
    }
    .est-metric-card {
        background: #1a2332;
        border: 1px solid #2a3441;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.5rem;
    }
    .est-metric-label {
        color: #9aa0a6;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }
    .est-metric-value {
        color: #ffffff;
        font-size: 1.75rem;
        font-weight: 600;
        line-height: 1.2;
    }
    .est-table-wrap {
        border: 1px solid #2a3441;
        border-radius: 10px;
        overflow: hidden;
        margin-top: 0.5rem;
    }
    .est-table-header {
        display: grid;
        grid-template-columns: 1fr 90px 120px;
        gap: 1rem;
        padding: 0.75rem 1.25rem;
        background: #151b23;
        border-bottom: 1px solid #2a3441;
        color: #9aa0a6;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .est-table-header span:nth-child(2),
    .est-table-header span:nth-child(3) {
        text-align: right;
    }
    .est-phase-row {
        display: grid;
        grid-template-columns: 1fr 90px 120px;
        gap: 1rem;
        padding: 1.1rem 1.25rem;
        border-bottom: 1px solid #2a3441;
        align-items: start;
    }
    .est-phase-row:last-child {
        border-bottom: none;
    }
    .est-phase-name {
        color: #ffffff;
        font-weight: 600;
        font-size: 1rem;
        margin-bottom: 0.35rem;
    }
    .est-phase-desc {
        color: #9aa0a6;
        font-size: 0.875rem;
        line-height: 1.45;
        margin: 0;
    }
    .est-phase-weeks,
    .est-phase-cost {
        color: #ffffff;
        font-size: 1rem;
        font-weight: 500;
        text-align: right;
        padding-top: 0.15rem;
    }
    .est-new-btn + div[data-testid="stVerticalBlock"] button {
        background: transparent !important;
        border: none !important;
        color: #c9a227 !important;
        padding: 0.25rem 0 !important;
        font-size: 0.95rem !important;
        box-shadow: none !important;
    }
    .est-new-btn + div[data-testid="stVerticalBlock"] button:hover {
        color: #e0b83d !important;
        border: none !important;
    }
    div[data-testid="stForm"] {
        background: #1a2332;
        border: 1px solid #2a3441;
        border-radius: 10px;
        padding: 1rem 1.25rem;
    }
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        font-size: 1.05rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
    }
    [data-testid="stSidebar"] .stCaption {
        font-size: 0.78rem !important;
    }
    [data-testid="stSidebar"] h2 {
        font-size: 1rem !important;
    }
</style>
"""


def _render_html(fragment: str) -> None:
    """Renderiza HTML sin que Streamlit lo trate como bloque de código."""
    if hasattr(st, "html"):
        st.html(fragment)
    else:
        import streamlit.components.v1 as components

        components.html(fragment, scrolling=False)


def _init_session_state() -> None:
    if "last_estimation" not in st.session_state:
        st.session_state.last_estimation = None
    if "show_form" not in st.session_state:
        st.session_state.show_form = True


def _format_token_value(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", ".")


def _format_money(amount: float, currency: str) -> str:
    rounded = int(round(amount))
    formatted = f"{rounded:,}".replace(",", ".")
    symbol = "€" if currency.upper() == "EUR" else currency
    return f"{formatted} {symbol}"


def _format_weeks(weeks: float) -> str:
    if weeks == int(weeks):
        return f"{int(weeks)} wk"
    return f"{weeks:.1f} wk"


def _post_estimate(base_url: str, req: EstimationRequest) -> EstimationResponse:
    url = base_url.rstrip("/") + "/api/v1/estimate"
    payload = req.model_dump(mode="json")
    timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        detail = response.text
        try:
            body = response.json()
            if isinstance(body, dict) and "detail" in body:
                raw_detail = body["detail"]
                if isinstance(raw_detail, dict) and "message" in raw_detail:
                    detail = str(raw_detail["message"])
                else:
                    detail = str(raw_detail)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"HTTP {response.status_code}: {detail}")
    try:
        return EstimationResponse.model_validate(response.json())
    except ValidationError as e:
        raise RuntimeError(
            "La API devolvió un JSON que no coincide con el esquema del front. "
            "Reinicia los contenedores para cargar el código actual: "
            "`docker compose --profile ui up --build --force-recreate`"
        ) from e


def _render_phase_rows(est: StructuredEstimation) -> str:
    rows: list[str] = []
    for phase in est.phases:
        rows.append(
            f"""
            <div class="est-phase-row">
                <div>
                    <div class="est-phase-name">{html.escape(phase.name)}</div>
                    <p class="est-phase-desc">{html.escape(phase.description)}</p>
                </div>
                <div class="est-phase-weeks">{html.escape(_format_weeks(phase.weeks))}</div>
                <div class="est-phase-cost">{html.escape(_format_money(phase.cost, est.totals.currency))}</div>
            </div>
            """
        )
    return "\n".join(rows)


def _render_metric_cards_html(est: StructuredEstimation) -> str:
    return f"""
    <div class="est-metric-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:1.25rem;">
        <div class="est-metric-card">
            <div class="est-metric-label">Duration</div>
            <div class="est-metric-value">{html.escape(_format_weeks(est.totals.duration_weeks))}</div>
        </div>
        <div class="est-metric-card">
            <div class="est-metric-label">Cost</div>
            <div class="est-metric-value">{html.escape(_format_money(est.totals.cost, est.totals.currency))}</div>
        </div>
        <div class="est-metric-card">
            <div class="est-metric-label">Confidence</div>
            <div class="est-metric-value">{est.totals.confidence_pct}%</div>
        </div>
    </div>
    """


def _dashboard_fragment_styles() -> str:
    """Estilos embebidos para que el dashboard se vea bien dentro de st.html."""
    return """
    <style>
    .est-dash { color: #e8eaed; font-family: inherit; }
    .est-dash .est-summary-text { color: #9aa0a6; font-size: 0.95rem; margin: 0 0 1.5rem 0; line-height: 1.5; }
    .est-dash .est-metric-card { background: #1a2332; border: 1px solid #2a3441; border-radius: 10px; padding: 1rem 1.25rem; }
    .est-dash .est-metric-label { color: #9aa0a6; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.35rem; }
    .est-dash .est-metric-value { color: #fff; font-size: 1.75rem; font-weight: 600; line-height: 1.2; }
    .est-dash .est-table-wrap { border: 1px solid #2a3441; border-radius: 10px; overflow: hidden; margin-top: 0.5rem; }
    .est-dash .est-table-header { display: grid; grid-template-columns: 1fr 90px 120px; gap: 1rem; padding: 0.75rem 1.25rem; background: #151b23; border-bottom: 1px solid #2a3441; color: #9aa0a6; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }
    .est-dash .est-table-header span:nth-child(2), .est-dash .est-table-header span:nth-child(3) { text-align: right; }
    .est-dash .est-phase-row { display: grid; grid-template-columns: 1fr 90px 120px; gap: 1rem; padding: 1.1rem 1.25rem; border-bottom: 1px solid #2a3441; align-items: start; }
    .est-dash .est-phase-row:last-child { border-bottom: none; }
    .est-dash .est-phase-name { color: #fff; font-weight: 600; font-size: 1rem; margin-bottom: 0.35rem; }
    .est-dash .est-phase-desc { color: #9aa0a6; font-size: 0.875rem; line-height: 1.45; margin: 0; }
    .est-dash .est-phase-weeks, .est-dash .est-phase-cost { color: #fff; font-size: 1rem; font-weight: 500; text-align: right; padding-top: 0.15rem; }
    </style>
    """


def _render_estimation_dashboard(est: StructuredEstimation) -> None:
    dashboard_html = (
        _dashboard_fragment_styles()
        + '<div class="est-dash">'
        + f'<p class="est-summary-text">{html.escape(est.summary)}</p>'
        + _render_metric_cards_html(est)
        + f"""
        <div class="est-table-wrap">
            <div class="est-table-header">
                <span>Phase</span>
                <span>Weeks</span>
                <span>Cost</span>
            </div>
            {_render_phase_rows(est)}
        </div>
        </div>
        """
    )
    _render_html(dashboard_html)


def _total_tokens(last: EstimationResponse) -> int | None:
    if last.total_tokens is not None:
        return last.total_tokens
    if last.input_tokens is not None and last.output_tokens is not None:
        return last.input_tokens + last.output_tokens
    return None


def _format_cost_usd(value: float | None, *, total_tokens: int | None = None) -> str:
    if value is None:
        return "—"
    if value == 0 and total_tokens and total_tokens > 0:
        return "no calculado"
    if 0 < value < 0.0001:
        return f"${value:.8f}".rstrip("0").rstrip(".")
    if value < 0.01:
        return f"${value:.6f}"
    return f"${value:.4f}"


def _format_model_label(response: EstimationResponse) -> str:
    if response.model:
        return response.model
    if response.cache_kind == CacheKind.SEMANTIC:
        return "— (caché semántica; sin llamada al LLM)"
    return "—"


def _format_provider_label(response: EstimationResponse) -> str:
    if response.provider:
        return response.provider
    if response.cache_kind in (CacheKind.SEMANTIC, CacheKind.EXACT):
        return "— (respuesta desde caché)"
    return "—"


def _cache_kind_label(kind: CacheKind) -> str:
    if kind == CacheKind.SEMANTIC:
        return "Caché semántica (similitud vectorial)"
    if kind == CacheKind.EXACT:
        return "Caché exacta (clave SHA-256)"
    return "Sin caché — llamada al modelo"


def _render_cache_status(response: EstimationResponse) -> None:
    """Badge visible en la vista principal y coherente con el sidebar."""
    kind = response.cache_kind
    if kind == CacheKind.SEMANTIC:
        st.success(f"**Respuesta desde caché:** {_cache_kind_label(kind)}")
    elif kind == CacheKind.EXACT:
        st.success(f"**Respuesta desde caché:** {_cache_kind_label(kind)}")
    else:
        st.info(_cache_kind_label(kind))


def _render_cag_sidebar() -> None:
    st.sidebar.header("Metadatos")
    last: EstimationResponse | None = st.session_state.last_estimation
    if last is None:
        st.sidebar.caption("Sin estimación en esta sesión.")
        return

    st.sidebar.caption(f"**prompt_version:** `{last.prompt_version}`")
    kind = last.cache_kind
    if kind == CacheKind.SEMANTIC:
        st.sidebar.success(_cache_kind_label(kind))
    elif kind == CacheKind.EXACT:
        st.sidebar.success(_cache_kind_label(kind))
    else:
        st.sidebar.info(_cache_kind_label(kind))
    st.sidebar.caption(f"**cache_kind:** `{kind.value}` · **cache_hit:** `{last.cache_hit}`")

    st.sidebar.metric("Tokens totales", _format_token_value(_total_tokens(last)))
    st.sidebar.metric(
        "Coste solicitud",
        _format_cost_usd(last.cost_usd, total_tokens=_total_tokens(last)),
    )

    st.sidebar.caption(
        f"Desglose: **{_format_token_value(last.input_tokens)}** in · "
        f"**{_format_token_value(last.output_tokens)}** out"
    )
    st.sidebar.metric("Modelo", _format_model_label(last))
    st.sidebar.caption(f"Proveedor: **{_format_provider_label(last)}**")
    if last.response_time_seconds is not None:
        t = last.response_time_seconds
        st.sidebar.metric("Tiempo", f"{t:.2f} s" if t < 60 else f"{t / 60:.1f} min")

    with st.sidebar.expander("Transparencia CAG", expanded=False):
        st.caption("System prompt y ejemplos usados por el servicio.")
        st.text_area("system", value=build_system_prompt(), height=180, disabled=True)
        st.text_area("examples", value=format_cag_examples_block(), height=200, disabled=True)


def _render_form(api_base: str) -> None:
    with st.form("estimation_form"):
        description = st.text_area(
            "Descripción del alcance (20–2000 caracteres)",
            height=180,
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
        submitted = st.form_submit_button("Obtener estimación", type="primary")

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
            with st.spinner("Generando estimación…"):
                try:
                    result = _post_estimate(api_base, req)
                except RuntimeError as e:
                    st.error(str(e))
                else:
                    st.session_state.last_estimation = result
                    st.session_state.show_form = False
                    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Estimador",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_DARK_CSS, unsafe_allow_html=True)

    _init_session_state()
    settings = get_settings()
    api_base = settings.estimator_api_base_url

    has_result = st.session_state.last_estimation is not None and not st.session_state.show_form

    if has_result:
        last = st.session_state.last_estimation
        _render_cache_status(last)
        _render_estimation_dashboard(last.estimation)
        st.markdown('<div class="est-new-btn"></div>', unsafe_allow_html=True)
        if st.button("← New estimation"):
            st.session_state.show_form = True
            st.session_state.last_estimation = None
            st.rerun()
    else:
        st.title("Estimador de software")
        st.caption("Describe el alcance del proyecto para obtener una estimación por fases.")
        _render_form(api_base)

    _render_cag_sidebar()


if __name__ == "__main__":
    main()
