from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
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
        description="API key de OpenAI. Requerida si se usa OpenAI.",
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="API key de Anthropic. Requerida si se usa Anthropic.",
    )
    llm_provider: Literal["openai", "anthropic"] = Field(
        default="openai",
        description="Proveedor a utilizar: openai o anthropic.",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Modelo a utilizar.",
    )
    app_env: str = Field(
        default="development",
        description="Entorno de ejecución.",
    )
    log_level: str = Field(
        default="DEBUG",
        description="Nivel de logging.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
