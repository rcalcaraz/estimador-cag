"""
Interfaz de chat (Streamlit) para el estimador CAG.
Ejecutar desde la raíz del proyecto: streamlit run streamlit_app.py
Las claves API se leen de variables de entorno / .env (pydantic-settings), igual que la API.
"""

from __future__ import annotations

import streamlit as st

from app.services.llm_service import (
    EstimationOutcome,
    build_system_prompt,
    format_cag_examples_block,
    stream_estimation_text,
)


def _init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_llm_outcome" not in st.session_state:
        st.session_state.last_llm_outcome = None


def _format_token_value(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", ".")


def _render_cag_sidebar() -> None:
    st.sidebar.header("Transparencia CAG")
    st.sidebar.caption(
        "El mensaje *system* incluye rol y ejemplos de referencia; tu transcripción va en el mensaje de usuario."
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
    outcome: EstimationOutcome | None = st.session_state.last_llm_outcome
    if outcome is None:
        st.sidebar.info("Aún no hay una respuesta completada en esta sesión.")
        return

    st.sidebar.metric("Modelo", outcome.model)
    st.sidebar.caption(f"Proveedor: **{outcome.provider}**")
    c1, c2 = st.sidebar.columns(2)
    c1.metric("Tokens entrada", _format_token_value(outcome.input_tokens))
    c2.metric("Tokens salida", _format_token_value(outcome.output_tokens))
    if outcome.total_tokens is not None:
        st.sidebar.caption(f"Total tokens (reportado): {_format_token_value(outcome.total_tokens)}")
    if outcome.response_time_seconds is not None:
        t = outcome.response_time_seconds
        st.sidebar.metric(
            "Tiempo de respuesta",
            f"{t:.2f} s" if t < 60 else f"{t / 60:.1f} min",
        )


def main() -> None:
    st.set_page_config(page_title="Estimador CAG", page_icon="📋", layout="wide")
    st.title("Estimador de software (CAG)")
    st.caption(
        "Pega o escribe una transcripción de reunión para obtener una estimación de software."
    )

    _init_session_state()
    _render_cag_sidebar()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Transcripción de la reunión…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            outcome_holder: list[EstimationOutcome] = []
            try:
                reply = st.write_stream(
                    stream_estimation_text(prompt, outcome_holder=outcome_holder)
                )
                if not reply and outcome_holder:
                    reply = outcome_holder[0].estimation
                elif not reply:
                    reply = ""
            except ValueError as e:
                reply = f"**Error de configuración:** {e}"
                st.markdown(reply)
            except Exception as e:
                reply = f"**Error al llamar al proveedor LLM:** {e}"
                st.markdown(reply)
            else:
                if outcome_holder:
                    st.session_state.last_llm_outcome = outcome_holder[0]

            st.session_state.messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
