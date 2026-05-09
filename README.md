# estimator

Servicio que convierte la **transcripción de una reunión** en una **estimación de software** usando un modelo de lenguaje.

Los ejemplos de referencia van incluidos en la petición al modelo (patrón **CAG**: contexto en la misma llamada, sin base vectorial).

Las llamadas al modelo pasan por un **wrapper LiteLLM** (`app/services/llm_wrapper.py`): un **router** con **fallback** entre un modelo **OpenAI** (por ejemplo `gpt-4o-mini`) y uno **Anthropic** (por ejemplo `claude-haiku-4-5`). El orden (intentar primero GPT o primero Claude) se controla con `LLM_PROVIDER`. Hace falta **al menos una** API key; la segunda es opcional y se usa si el primero falla. Las respuestas se pueden **cachear** en **Redis** (misma clave lógica que en el repo `ai-engineering`).

La forma prevista de ejecutar el proyecto es **con Docker**: misma versión de Python y dependencias para todo el mundo, sin instalar `uv` ni un virtualenv en la máquina host.

Opcionalmente hay una **interfaz de chat** con Streamlit (perfil `ui` en Compose): mismos ajustes que la API, respuesta en streaming y panel lateral con el contexto enviado al modelo y métricas (tokens, tiempo).

**Redis** es **opcional**: la app sigue respondiendo sin Redis; solo pierdes la caché (más coste y latencia en peticiones repetidas). Puedes levantar Redis con un **perfil de Compose** (`redis`), igual que la UI usa el perfil `ui`, o con un contenedor suelto en local.

---

## Requisitos

- **Docker** y **Docker Compose** (Plugin V2: comando `docker compose`)

Los comandos de este README se ejecutan desde la carpeta **`estimator/`**, donde están `Dockerfile` y `docker-compose.yml`.

---

## Primeros pasos (Docker)

1. Configura las claves y, si usas caché con Docker, la URL de Redis (ver [Redis y caché](#redis-y-caché)):

   ```bash
   cd estimator
   cp .env.example .env
   ```

   Edita `.env` y pon al menos **una** de `OPENAI_API_KEY` o `ANTHROPIC_API_KEY`. Detalle en [Variables de entorno](#variables-de-entorno).

2. Solo **API** (puerto **8000**, recarga al cambiar código gracias al volumen de desarrollo):

   ```bash
   docker compose up --build
   ```

3. **API + Streamlit** (UI en puerto **8501**):

   ```bash
   docker compose --profile ui up --build
   ```

4. **API + Redis** (servicio de caché en la misma red de Compose). Antes, en `.env`, pon **`REDIS_URL=redis://redis:6379`** (nombre del servicio `redis` dentro de Docker):

   ```bash
   docker compose --profile redis up --build
   ```

5. **API + Redis + Streamlit** (todo junto):

   ```bash
   docker compose --profile redis --profile ui up --build
   ```

6. Documentación interactiva de la API: [http://localhost:8000/docs](http://localhost:8000/docs)  
   Streamlit (si usaste el perfil `ui`): [http://localhost:8501](http://localhost:8501)

El `docker-compose.yml` monta `app/` y `streamlit_app.py` para desarrollo. **Producción:** quita esos volúmenes y el `command` con `--reload`; la imagen usa `uvicorn` sin recarga y un `HEALTHCHECK` sobre `GET /health`.

Tras cambiar `.env`, reinicia los contenedores (`docker compose down` y vuelve a `up`).

---

## Redis y caché

- **Sin Redis:** la aplicación funciona; los accesos a caché fallan de forma controlada (solo se pierde deduplicación de respuestas).
- **Con perfil `redis` en Compose:** arranca el contenedor `redis` y debes usar **`REDIS_URL=redis://redis:6379`** en `.env` para que la API y Streamlit resuelvan el host correcto **dentro** de la red de Docker.
- **Sin Compose, solo Redis en tu máquina:** por ejemplo `docker run -d --name redis-estimator -p 6379:6379 redis:7-alpine` y en `.env` deja **`REDIS_URL=redis://localhost:6379`** (adecuado también para `uv run uvicorn` en el host).
- Los perfiles son independientes: **`redis`** solo añade el servicio Redis; **`ui`** solo añade Streamlit. Combínalos como en el apartado anterior.

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
| `REDIS_URL` | URL de Redis para la caché (`redis://localhost:6379` en local; `redis://redis:6379` con Compose y perfil `redis`). |
| `CACHE_TTL` | Segundos de vida de cada entrada en caché. |
| `APP_ENV` | Entorno de ejecución. |
| `LOG_LEVEL` | Nivel de log, p. ej. `DEBUG`. |

Compose inyecta el mismo `.env` que usa la aplicación vía `env_file`.

---

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Comprueba que el servicio responde |
| `POST` | `/api/v1/estimate` | Envías JSON con `transcription`; devuelve la estimación y metadatos |

Ejemplo (API ya levantada):

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/estimate" \
  -H "Content-Type: application/json" \
  -d '{"transcription": "El cliente describe el alcance del proyecto..."}'
```

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
# Streamlit (otra terminal)
uv run streamlit run streamlit_app.py
```

Si cambias `pyproject.toml`, vuelve a ejecutar `uv sync`.

---

## Estructura del proyecto

```text
estimator/
├── Dockerfile / docker-compose.yml
├── streamlit_app.py          # Interfaz web
└── app/
    ├── main.py               # FastAPI y rutas base
    ├── config.py             # Ajustes desde .env
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
