"""
Interfaz de chat (Streamlit) para el estimador CAG.
Ejecutar desde la raíz del proyecto: streamlit run streamlit_app.py
Las claves API se leen de variables de entorno / .env (pydantic-settings), igual que la API.
"""

from __future__ import annotations

import asyncio

import streamlit as st

from app.services.llm_service import generate_estimation


def _init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []


def main() -> None:
    st.set_page_config(page_title="Estimador CAG", page_icon="📋", layout="centered")
    st.title("Estimador de software (CAG)")
    st.caption(
        "Pega o escribe una transcripción de reunión para obtener una estimación de software."
    )

    _init_session_state()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Transcripción de la reunión…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Generando estimación…"):
                try:
                    outcome = asyncio.run(generate_estimation(prompt))
                except ValueError as e:
                    reply = f"**Error de configuración:** {e}"
                    st.markdown(reply)
                except Exception as e:
                    reply = f"**Error al llamar al proveedor LLM:** {e}"
                    st.markdown(reply)
                else:
                    reply = outcome.estimation
                    st.markdown(reply)
                    meta = f"*Modelo: `{outcome.model}` · Proveedor: {outcome.provider}*"
                    if outcome.total_tokens is not None:
                        meta += f" · Tokens: {outcome.total_tokens}"
                    st.caption(meta)

            st.session_state.messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
