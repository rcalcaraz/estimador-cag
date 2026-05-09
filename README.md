# estimator

Servicio que recibe una **descripción de alcance** tipada (tipo de proyecto, nivel de detalle y formato de salida) y devuelve una **estimación de software** en texto libre usando un modelo de lenguaje.

Los ejemplos de referencia se inyectan en el mensaje **system** (patrón **CAG**: contexto en la misma llamada, sin base vectorial). En **`POST /api/v1/estimate`** el texto de **system** y **user** se obtiene con plantillas **Jinja2** en `app/prompts/v1/` (`render_estimation_prompt`). El cliente LLM recibe **dos mensajes** con roles separados (`system` y `user`), no un único mensaje concatenado.

Las llamadas al modelo pasan por un **wrapper LiteLLM** (`app/services/llm_wrapper.py`): un **router** con **fallback** entre un modelo **OpenAI** (por ejemplo `gpt-4o-mini`) y uno **Anthropic** (por ejemplo `claude-haiku-4-5`). El orden (intentar primero GPT o primero Claude) se controla con `LLM_PROVIDER`. Hace falta **al menos una** API key; la segunda es opcional y se usa si el primero falla. Las respuestas se pueden **cachear** en **Redis** (misma idea de clave que en el repo `ai-engineering`).

La forma prevista de ejecutar el proyecto es **con Docker**: misma versión de Python y dependencias para todo el mundo, sin instalar `uv` ni un virtualenv en la máquina host.

Opcionalmente hay una **interfaz con formulario** en Streamlit (perfil `ui` en Compose): construye un `EstimationRequest`, hace **streaming** con `POST .../api/v1/estimate/stream` (NDJSON) y el panel lateral muestra **transparencia CAG** (vista de rol + ejemplos coherente con la ruta de streaming), **tokens**, modelo, **caché** y tiempo de respuesta. La URL base de la API se configura con **`ESTIMATOR_API_BASE_URL`** (en Compose apunta al servicio `estimator` en la red Docker).

**Redis** arranca **siempre** con Compose: la API y Streamlit usan **`REDIS_URL=redis://redis:6379`** en la red Docker (el `docker-compose.yml` lo inyecta y no hace falta cambiar el `.env` para eso). Sin Redis en marcha la caché falla y verás `cache_get_failed` en los logs.

---

## Requisitos

- **Docker** y **Docker Compose** (Plugin V2: comando `docker compose`)

Los comandos de este README se ejecutan desde la carpeta **`estimator/`**, donde están `Dockerfile` y `docker-compose.yml`.

---

## Primeros pasos (Docker)

1. Configura las claves en `.env` (ver [Variables de entorno](#variables-de-entorno)):

   ```bash
   cd estimator
   cp .env.example .env
   ```

   Edita `.env` y pon al menos **una** de `OPENAI_API_KEY` o `ANTHROPIC_API_KEY`.  
   Para desarrollo **solo en tu máquina** (sin Docker), usa `REDIS_URL=redis://localhost:6379` si tienes Redis local. En Docker Compose **no hace falta** tocar `REDIS_URL`: el compose fuerza `redis://redis:6379`.

2. **API + Redis** (puerto **8000**, recarga al cambiar código gracias al volumen de desarrollo):

   ```bash
   docker compose up --build
   ```

3. **API + Redis + Streamlit** (UI en puerto **8501**):

   ```bash
   docker compose --profile ui up --build
   ```

   Con el perfil `ui`, Compose fija **`ESTIMATOR_API_BASE_URL=http://estimator:8000`** en el servicio Streamlit para que las peticiones vayan al contenedor de la API en la red interna.

4. Documentación interactiva de la API: [http://localhost:8000/docs](http://localhost:8000/docs)  
   Streamlit (si usaste el perfil `ui`): [http://localhost:8501](http://localhost:8501)

El `docker-compose.yml` monta `app/` y `streamlit_app.py` para desarrollo. **Producción:** quita esos volúmenes y el `command` con `--reload`; la imagen usa `uvicorn` sin recarga y un `HEALTHCHECK` sobre `GET /health`.

Tras cambiar `.env`, reinicia los contenedores (`docker compose down` y vuelve a `up`).

---

## Redis y caché

- **Con Docker Compose:** el servicio `redis` sube siempre; `estimator` y `streamlit` esperan a que Redis esté sano y reciben **`REDIS_URL=redis://redis:6379`** por variables de entorno del compose (sustituye el `localhost` del `.env`).
- **Sin Redis** (solo si cae el contenedor o no usas Compose): la aplicación sigue respondiendo; los accesos a caché fallan de forma controlada (`cache_get_failed` en logs).
- **Sin Compose, en el host:** Redis en `localhost` y en `.env` **`REDIS_URL=redis://localhost:6379`** (adecuado para `uv run uvicorn` / Streamlit en local).

La clave de caché incluye el texto **system** y **user** completos y el modelo; si cambias plantillas o parámetros del encargo, no se reutiliza una respuesta antigua por error.

---

## Variables de entorno

Copia `.env.example` a `.env`. No subas `.env` al repositorio (está ignorado por git).

| Variable | Para qué sirve |
|----------|----------------|
| `OPENAI_API_KEY` | Clave OpenAI (obligatoria si es el único proveedor que vas a usar; recomendable si quieres fallback GPT). |
| `ANTHROPIC_API_KEY` | Clave Anthropic (igual que la anterior para Claude). |
| `LLM_PROVIDER` | `openai` (por defecto: intenta primero el modelo OpenAI) o `anthropic` (intenta primero Claude). |
| `PRIMARY_MODEL` | Modelo en la ranura OpenAI del router (p. ej. `gpt-4o-mini`). |
| `FALLBACK_MODEL` | Modelo en la ranura Anthropic (p. ej. `claude-haiku-4-5`). |
| `LLM_MODEL` | Legado; para configuraciones nuevas usa `PRIMARY_MODEL` / `FALLBACK_MODEL`. |
| `LLM_TIMEOUT` | Timeout de cada llamada al LLM (segundos). |
| `LLM_RETRIES` | Reintentos que delega LiteLLM. |
| `REDIS_URL` | URL de Redis (`redis://localhost:6379` en el host; con Docker Compose el `docker-compose.yml` fuerza `redis://redis:6379`). |
| `CACHE_TTL` | Segundos de vida de cada entrada en caché. |
| `ESTIMATOR_API_BASE_URL` | URL base de la API FastAPI para el cliente Streamlit (por defecto `http://127.0.0.1:8000`; con Docker Compose y perfil `ui` suele ser `http://estimator:8000`). |
| `APP_ENV` | Entorno de ejecución. |
| `LOG_LEVEL` | Nivel de log, p. ej. `DEBUG`. |

Compose inyecta el mismo `.env` que usa la aplicación vía `env_file`.

---

## Flujo de ejecución

A alto nivel, una petición tipada atraviesa validación Pydantic, construcción de prompts (según el endpoint), el wrapper LiteLLM (con posible acierto en Redis) y la respuesta normalizada.

### Diagrama

```mermaid
flowchart TD
  subgraph cliente["Cliente"]
    C[HTTP JSON]
  end

  subgraph api["FastAPI app.main"]
    R["Router /api/v1 estimations"]
    V["Validación EstimationRequest"]
  end

  subgraph sync["POST /estimate"]
    J["render_estimation_prompt\n(Jinja app/prompts/v1/)"]
    SYS["Mensaje system"]
    USR["Mensaje user"]
    CE["complete_estimation"]
  end

  subgraph stream["POST /estimate/stream"]
    B["build_system_prompt +\nbuild_estimation_user_message"]
    ST["stream_estimation"]
  end

  subgraph llm["LLMWrapper"]
    CACHE{"¿Redis tiene\nrespuesta?"}
    MISS["LiteLLM Router\n(OpenAI ↔ Anthropic)"]
    NORM["Tokens, coste,\nproveedor"]
  end

  subgraph salida["Respuesta"]
    ER["EstimationResponse\n(prompt_version según constante)"]
  end

  C --> R --> V

  V --> J
  J --> SYS
  J --> USR
  SYS --> CE
  USR --> CE

  V --> B --> ST

  CE --> CACHE
  ST --> CACHE

  CACHE -->|hit| ER
  CACHE -->|miss| MISS --> NORM --> ER
```

### Pasos detallados

1. **Entrada:** el cuerpo JSON se valida contra `EstimationRequest` (longitud de `description`, enums en snake_case).
2. **Prompts:**
   - **`POST /api/v1/estimate`:** `render_estimation_prompt` renderiza `system.j2` y `user.j2` (con `examples.j2` incluido en el system) y devuelve dos cadenas. La constante `ESTIMATION_PROMPT_VERSION` en `llm_service` está alineada con el directorio de plantillas (actualmente **`v1`**).
   - **`POST /api/v1/estimate/stream`:** el servicio construye system y user en Python (`build_system_prompt`, `build_estimation_user_message`) y llama al streaming del wrapper. La línea final NDJSON incluye el mismo campo `prompt_version` por construcción de la respuesta; la UI lateral muestra el bloque estático equivalente al stream para transparencia.
3. **Llamada al modelo:** `LLMWrapper` arma la lista de mensajes `[{role: system, ...}, {role: user, ...}]` y delega en LiteLLM (no concatena ambos textos en un solo mensaje).
4. **Caché:** antes de llamar al proveedor se consulta Redis; si hay hit, se devuelve la estimación guardada con metadatos y `cache_hit: true`.
5. **Salida:** se normaliza texto, modelo efectivo, proveedor, uso de tokens, tiempo y coste estimado; el router devuelve `EstimationResponse` (o NDJSON en streaming).

---

## API

El contrato está definido en Pydantic v2 en `app/schemas.py`:

- **`EstimationRequest`**: `description` (20–2000 caracteres), `project_type`, `detail_level`, `output_format` (enums con valores en snake_case, p. ej. `mobile_app`, `summary`, `phases_table`).
- **`EstimationResponse`**: `text`, `prompt_version` (identifica la versión de plantillas / contrato de prompt expuesto por la API), `model`, `provider` (`openai` \| `anthropic`), `cache_hit`, tokens (`input_tokens`, `output_tokens`, `total_tokens`), `response_time_seconds`, `cost_usd` (opcionales salvo los campos obligatorios del modelo).

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Comprueba que el servicio responde |
| `POST` | `/api/v1/estimate` | Cuerpo JSON `EstimationRequest`; respuesta JSON única `EstimationResponse`. Prompts vía **Jinja** (`v1`). |
| `POST` | `/api/v1/estimate/stream` | Mismo cuerpo; respuesta **NDJSON**: líneas `{"type":"delta","text":"..."}` y una línea final `{"type":"final", ...}` con el mismo esquema que `EstimationResponse`. Prompts vía funciones en **`llm_service`** (streaming). |

Ejemplo (API ya levantada):

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/estimate" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "El cliente necesita un panel web para gestionar pedidos, con login y notificaciones por email. Integración con su ERP vía API REST.",
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "phases_table"
  }'
```

En [http://localhost:8000/docs](http://localhost:8000/docs) verás el esquema OpenAPI generado a partir de los mismos modelos.

---

## Puerto ya en uso

Si **8000**, **8501** o **6379** están ocupados en tu máquina, puedes liberarlos o ajustar el mapeo de puertos en `docker-compose.yml`. En macOS/Linux, para ver qué usa el 8000:

```bash
lsof -iTCP:8000 -sTCP:LISTEN
```

---

## Sin Docker (opcional)

Solo tiene sentido si quieres ejecutar tests, linters o depurar fuera del contenedor (la sección [Tests](#tests) describe cómo lanzar `pytest`). Necesitas **Python ≥ 3.9** y **[uv](https://docs.astral.sh/uv/)**. Para caché, Redis accesible en `localhost:6379` o la URL que pongas en `REDIS_URL`.

```bash
cd estimator
uv sync
cp .env.example .env   # si aún no existe
# API
uv run uvicorn app.main:app --reload
# Streamlit (otra terminal; misma máquina que la API)
export ESTIMATOR_API_BASE_URL=http://127.0.0.1:8000
uv run streamlit run streamlit_app.py
```

Si cambias `pyproject.toml`, vuelve a ejecutar `uv sync`.

---

## Tests

La suite usa **pytest** y **fakeredis** (sin Redis real para la mayoría de casos). Las rutas HTTP sustituyen las llamadas al LLM con *fakes*, así que **no** necesitas API keys válidas para pasar los tests: `tests/conftest.py` define valores de entorno de marcador antes de importar la aplicación si aún no existen.

Instala dependencias de desarrollo y ejecuta todos los tests:

```bash
cd estimator
uv sync --group dev
uv run pytest
```

Útiles durante el desarrollo:

```bash
uv run pytest -v
uv run pytest tests/test_health.py
uv run pytest tests/test_estimate_endpoint.py::test_estimate_returns_200_and_matches_schema -v
```

Si al lanzar pytest falla la validación de Settings por claves vacías en tu `.env`, asegúrate de que `OPENAI_API_KEY` y/o `ANTHROPIC_API_KEY` no estén definidas como cadenas vacías, o usa solo el entorno que rellena `conftest.py` (sin `.env` conflictivo en esas variables).

Archivos de tests destacados:

| Archivo | Qué cubre |
|---------|-----------|
| `tests/test_estimate_endpoint.py` | Router `/estimate` y `/estimate/stream` (esquema y errores) |
| `tests/test_llm_wrapper.py` | Wrapper LiteLLM, caché en llamadas simuladas |
| `tests/test_cache.py` | Claves y TTL de Redis |
| `tests/test_examples_context.py` | Prompts legacy / ejemplos CAG |
| `tests/test_health.py` | `GET /health` |

---

## Estructura del proyecto

```text
estimator/
├── Dockerfile / docker-compose.yml
├── streamlit_app.py          # Formulario web → POST /api/v1/estimate/stream (NDJSON)
├── tests/                    # pytest (salud, caché, wrapper LLM, router estimaciones)
└── app/
    ├── main.py               # FastAPI, lifespan, GET /health
    ├── config.py             # Ajustes desde .env
    ├── schemas.py            # Contrato API (Pydantic): request/response y enums
    ├── dependencies.py       # Singletons: caché y wrapper LLM
    ├── routers/estimations.py   # POST /estimate, /estimate/stream
    ├── prompts/
    │   ├── loader.py         # render_estimation_prompt → (system, user)
    │   └── v1/
    │       ├── system.j2
    │       ├── user.j2
    │       └── examples.j2   # Few-shot CAG incluido en system
    ├── services/
    │   ├── llm_service.py    # complete_estimation, streaming, helpers de prompt
    │   ├── llm_wrapper.py    # LiteLLM (router + fallback + streaming async)
    │   └── cache.py          # Caché Redis
    └── context/examples.py   # Datos de ejemplos de estimación (CAG)
```

---

## Dependencias

Las gestiona la imagen Docker a partir de `pyproject.toml`. En local sin Docker, `uv sync` las instala en un `.venv`. Entre otras: **FastAPI**, **LiteLLM**, **Redis** (cliente), **Jinja2** (plantillas de prompt), **structlog**, **Pydantic v2**.
