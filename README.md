# estimator

Servicio que recibe una **descripción de alcance** tipada (tipo de proyecto, nivel de detalle y formato de salida) y devuelve una **estimación de software** en texto libre, usando un modelo de lenguaje.

Los ejemplos de referencia van incluidos en la petición al modelo (patrón **CAG**: contexto en la misma llamada, sin base vectorial).

Las llamadas al modelo pasan por un **wrapper LiteLLM** (`app/services/llm_wrapper.py`): un **router** con **fallback** entre un modelo **OpenAI** (por ejemplo `gpt-4o-mini`) y uno **Anthropic** (por ejemplo `claude-haiku-4-5`). El orden (intentar primero GPT o primero Claude) se controla con `LLM_PROVIDER`. Hace falta **al menos una** API key; la segunda es opcional y se usa si el primero falla. Las respuestas se pueden **cachear** en **Redis** (misma clave lógica que en el repo `ai-engineering`).

La forma prevista de ejecutar el proyecto es **con Docker**: misma versión de Python y dependencias para todo el mundo, sin instalar `uv` ni un virtualenv en la máquina host.

Opcionalmente hay una **interfaz con formulario** en Streamlit (perfil `ui` en Compose): construye un `EstimationRequest`, hace **streaming** con `POST .../estimate/stream` (NDJSON) y el panel lateral muestra **transparencia CAG** (system prompt y ejemplos en solo lectura), **tokens**, modelo, **caché** y tiempo de respuesta. La URL base de la API se configura con **`ESTIMATOR_API_BASE_URL`** (en Compose apunta al servicio `estimator` en la red Docker).

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

## API

El contrato está definido en Pydantic v2 en `app/schemas.py`:

- **`EstimationRequest`**: `description` (20–2000 caracteres), `project_type`, `detail_level`, `output_format` (enums con valores en snake_case, p. ej. `mobile_app`, `summary`, `phases_table`).
- **`EstimationResponse`**: `text`, `prompt_version`, `model`, `provider` (`openai` \| `anthropic`), `cache_hit`, tokens (`input_tokens`, `output_tokens`, `total_tokens`), `response_time_seconds`, `cost_usd` (opcionales salvo los campos obligatorios del modelo).

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Comprueba que el servicio responde |
| `POST` | `/api/v1/estimate` | Cuerpo JSON `EstimationRequest`; respuesta JSON única `EstimationResponse` |
| `POST` | `/api/v1/estimate/stream` | Mismo cuerpo; respuesta **NDJSON**: líneas `{"type":"delta","text":"..."}` y una línea final `{"type":"final", ...}` con el mismo esquema que `EstimationResponse` |

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

Solo tiene sentido si quieres ejecutar tests, linters o depurar fuera del contenedor. Necesitas **Python ≥ 3.9** y **[uv](https://docs.astral.sh/uv/)**. Para caché, Redis accesible en `localhost:6379` o la URL que pongas en `REDIS_URL`.

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

## Estructura del proyecto

```text
estimator/
├── Dockerfile / docker-compose.yml
├── streamlit_app.py          # Formulario web → POST /api/v1/estimate
└── app/
    ├── main.py               # FastAPI y rutas base
    ├── config.py             # Ajustes desde .env
    ├── schemas.py            # Contrato API (Pydantic): request/response y enums
    ├── dependencies.py       # Singletons: caché y wrapper LLM
    ├── routers/estimations.py
    ├── services/
    │   ├── llm_service.py    # Prompt CAG y orquestación
    │   ├── llm_wrapper.py    # LiteLLM (router + fallback + streaming async)
    │   └── cache.py          # Caché Redis
    └── context/examples.py   # Ejemplos de estimación (CAG)
```

---

## Dependencias

Las gestiona la imagen Docker a partir de `pyproject.toml`. En local sin Docker, `uv sync` las instala en un `.venv`.
