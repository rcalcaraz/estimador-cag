"""Caché semántica para el estimador.

Dos peticiones se consideran equivalentes cuando:

1. Su **bucket** coincide exactamente: ``prompt_version:project_type:detail_level:output_format``.
   Peticiones con opciones de formulario distintas nunca comparten entrada aunque
   la descripción sea similar — el prompt renderizado es distinto.

2. La similitud coseno de los embeddings de la descripción es >= ``threshold``
   (por defecto 0.85).

Con ``log_only=True`` la caché registra el score pero no sirve hits — útil para
calibrar el umbral antes de activarla en producción.

Requiere **Redis Stack** (RediSearch); ``redis:7-alpine`` sin módulos fallará al
crear el índice vectorial.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import structlog

from app.schemas import EstimationRequest, StructuredEstimation

log = structlog.get_logger()


@dataclass(frozen=True)
class SemanticCacheHit:
    """Entrada recuperada de la caché semántica."""

    estimation: StructuredEstimation
    model: str | None = None
    provider: Literal["openai", "anthropic"] | None = None


def _to_bytes(vector: list[float]) -> bytes:
    """RediSearch almacena vectores como bytes float32; redisvl rechaza listas."""
    return np.array(vector, dtype=np.float32).tobytes()


_INDEX_SCHEMA: dict[str, Any] = {
    "index": {
        "name": "estimations",
        "prefix": "estimation:semantic",
        "storage_type": "hash",
    },
    "fields": [
        {"name": "bucket", "type": "tag"},
        {"name": "result_json", "type": "text"},
        {"name": "model", "type": "text"},
        {"name": "provider", "type": "tag"},
        {
            "name": "embedding",
            "type": "vector",
            "attrs": {
                "dims": 1536,  # text-embedding-3-small
                "distance_metric": "cosine",
                "algorithm": "flat",
            },
        },
    ],
}


class EstimationSemanticCache:
    """Caché por similitud vectorial (redisvl + Redis Stack)."""

    def __init__(
        self,
        *,
        redis_client: Any,
        vectorizer: Any,
        threshold: float = 0.85,
        ttl: int = 86400,
        log_only: bool = False,
        index_name: str = "estimations",
    ) -> None:
        from redisvl.index import SearchIndex

        self.redis_client = redis_client
        self.vectorizer = vectorizer
        self.threshold = threshold
        self.ttl = ttl
        self.log_only = log_only

        schema = dict(_INDEX_SCHEMA)
        schema["index"] = {**_INDEX_SCHEMA["index"], "name": index_name}

        self.index = SearchIndex.from_dict(schema)
        self.index.set_client(redis_client)
        try:
            self.index.create(overwrite=False)
        except Exception as exc:  # noqa: BLE001 — índice ya existente
            log.debug("semantic_index_create_skipped", error=str(exc)[:120])

    @staticmethod
    def bucket_for(request: EstimationRequest, prompt_version: str) -> str:
        return (
            f"{prompt_version}"
            f":{request.project_type.value}"
            f":{request.detail_level.value}"
            f":{request.output_format.value}"
        )

    def lookup(
        self, request: EstimationRequest, prompt_version: str
    ) -> SemanticCacheHit | None:
        from redisvl.query import VectorQuery
        from redisvl.query.filter import Tag

        bucket = self.bucket_for(request, prompt_version)
        embedding = self.vectorizer.embed(request.description)

        query = VectorQuery(
            vector=_to_bytes(embedding),
            vector_field_name="embedding",
            return_fields=["result_json", "bucket", "model", "provider"],
            num_results=1,
            return_score=True,
            filter_expression=Tag("bucket") == bucket,
        )
        results = self.index.query(query)
        if not results:
            log.info("semantic_cache_miss", bucket=bucket, reason="empty_index")
            return None

        hit = results[0]
        distance = float(hit.get("vector_distance", 1.0))
        similarity = 1.0 - distance
        log.info(
            "semantic_cache_lookup",
            bucket=bucket,
            similarity=round(similarity, 4),
            threshold=self.threshold,
        )

        if similarity < self.threshold:
            log.info("semantic_cache_miss", bucket=bucket, reason="below_threshold")
            return None

        if self.log_only:
            log.info(
                "semantic_cache_hit_log_only",
                bucket=bucket,
                similarity=round(similarity, 4),
            )
            return None

        log.info("semantic_cache_hit", bucket=bucket, similarity=round(similarity, 4))
        raw_provider = hit.get("provider")
        provider: Literal["openai", "anthropic"] | None = None
        if raw_provider in ("openai", "anthropic"):
            provider = raw_provider
        raw_model = hit.get("model")
        model = str(raw_model).strip() if raw_model else None
        return SemanticCacheHit(
            estimation=StructuredEstimation.model_validate_json(hit["result_json"]),
            model=model or None,
            provider=provider,
        )

    def store(
        self,
        request: EstimationRequest,
        result: StructuredEstimation,
        prompt_version: str,
        *,
        model: str | None = None,
        provider: Literal["openai", "anthropic"] | None = None,
    ) -> None:
        bucket = self.bucket_for(request, prompt_version)
        embedding = self.vectorizer.embed(request.description)
        entry: dict[str, Any] = {
            "bucket": bucket,
            "result_json": result.model_dump_json(),
            "embedding": _to_bytes(embedding),
        }
        if model:
            entry["model"] = model
        if provider:
            entry["provider"] = provider
        payload = [entry]
        try:
            self.index.load(payload, ttl=self.ttl)
            log.info("semantic_cache_stored", bucket=bucket, ttl=self.ttl)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "semantic_cache_store_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
