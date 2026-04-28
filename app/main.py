from datetime import datetime, timezone

from fastapi import FastAPI

from app.routers import estimations

app = FastAPI(
    title="Estimador CAG",
    description=(
        "API que genera estimaciones de proyectos de software a partir de transcripciones de reunión, "
        "inyectando ejemplos históricos en el contexto del modelo (CAG)."
    ),
    version="0.1.0",
)

app.include_router(estimations.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
