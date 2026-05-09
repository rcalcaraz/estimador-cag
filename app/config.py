from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración cargada desde variables de entorno (y archivo `.env`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    openai_api_key: Optional[str] = Field(
        default=None,
        description="API key de OpenAI.",
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="API key de Anthropic.",
    )
    llm_provider: Literal["openai", "anthropic"] = Field(
        default="openai",
        description=(
            "Proveedor preferido: define el orden del router LiteLLM "
            "(openai primero o anthropic primero)."
        ),
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Legado: modelo único en configuraciones antiguas; usa PRIMARY_MODEL y FALLBACK_MODEL para el router.",
    )
    primary_model: str = Field(
        default="gpt-4o-mini",
        description="Modelo OpenAI usado en la primera ranura del router (gpt-4o-mini, etc.).",
    )
    fallback_model: str = Field(
        default="claude-haiku-4-5",
        description="Modelo Anthropic en la segunda ranura del router.",
    )
    llm_timeout: int = Field(default=30, description="Timeout por llamada al LLM (segundos).")
    llm_retries: int = Field(default=2, description="Reintentos LiteLLM.")

    redis_url: str = Field(
        default="redis://localhost:6379",
        description="URL Redis para la caché de respuestas.",
    )
    cache_ttl: int = Field(default=86400, description="TTL de la caché (segundos).")

    estimator_api_base_url: str = Field(
        default="http://127.0.0.1:8000",
        description="URL base de la API FastAPI (cliente Streamlit vía HTTP).",
    )

    app_env: str = Field(
        default="development",
        description="Entorno de ejecución.",
    )
    log_level: str = Field(
        default="DEBUG",
        description="Nivel de logging.",
    )

    @model_validator(mode="after")
    def validate_api_keys(self) -> Settings:
        """LiteLLM puede usar cualquiera de los dos proveedores vía fallback."""
        has_oai = bool(self.openai_api_key and self.openai_api_key.strip())
        has_ant = bool(self.anthropic_api_key and self.anthropic_api_key.strip())
        if not has_oai and not has_ant:
            raise ValueError(
                "Se requiere al menos una de: OPENAI_API_KEY o ANTHROPIC_API_KEY",
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
