from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI

from app.config import get_settings
from app.routers import estimations


def configure_logging() -> None:
    """Configura structlog: JSON en producción, consola legible en desarrollo."""
    settings = get_settings()

    if settings.app_env == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = structlog.get_logger()
    settings = get_settings()
    log.info("application_started", environment=settings.app_env)
    yield
    log.info("application_shutdown")


app = FastAPI(
    title="Estimador CAG",
    description=(
        "API que genera estimaciones de proyectos de software a partir de transcripciones de reunión, "
        "inyectando ejemplos históricos en el contexto del modelo (CAG)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(estimations.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
