# estimator

Servicio que convierte la **transcripción de una reunión** en una **estimación de software** usando un modelo de lenguaje.

Los ejemplos de referencia van incluidos en la petición al modelo (patrón **CAG**: contexto en la misma llamada, sin base vectorial). El proveedor del modelo (**OpenAI** o **Anthropic**) se configura en `.env`.

La forma prevista de ejecutar el proyecto es **con Docker**: misma versión de Python y dependencias para todo el mundo, sin instalar `uv` ni un virtualenv en la máquina host.

Opcionalmente hay una **interfaz de chat** con Streamlit (perfil `ui` en Compose): mismos ajustes que la API, respuesta en streaming y panel lateral con el contexto enviado al modelo y métricas (tokens, tiempo).

---

## Requisitos

- **Docker** y **Docker Compose** (Plugin V2: comando `docker compose`)

Los comandos de este README se ejecutan desde la carpeta **`estimator/`**, donde están `Dockerfile` y `docker-compose.yml`.

---

## Primeros pasos (Docker)

1. Configura las claves:

   ```bash
   cd estimator
   cp .env.example .env
   ```

   Edita `.env` y pon al menos la API key del proveedor que uses (`OPENAI_API_KEY` o `ANTHROPIC_API_KEY`). Detalle en [Variables de entorno](#variables-de-entorno).

2. Solo **API** (puerto **8000**, recarga al cambiar código gracias al volumen de desarrollo):

   ```bash
   docker compose up --build
   ```

3. **API + Streamlit** (UI en puerto **8501**):

   ```bash
   docker compose --profile ui up --build
   ```

4. Documentación interactiva de la API: [http://localhost:8000/docs](http://localhost:8000/docs)  
   Streamlit (si usaste el perfil `ui`): [http://localhost:8501](http://localhost:8501)

El `docker-compose.yml` monta `app/` y `streamlit_app.py` para desarrollo. **Producción:** quita esos volúmenes y el `command` con `--reload`; la imagen usa `uvicorn` sin recarga y un `HEALTHCHECK` sobre `GET /health`.

Tras cambiar `.env`, reinicia los contenedores (`docker compose down` y vuelve a `up`).

---

## Variables de entorno

Copia `.env.example` a `.env`. No subas `.env` al repositorio (está ignorado por git).

| Variable | Para qué sirve |
|----------|----------------|
| `LLM_PROVIDER` | `openai` (por defecto) o `anthropic` |
| `OPENAI_API_KEY` | Obligatoria si usas OpenAI |
| `ANTHROPIC_API_KEY` | Obligatoria si usas Anthropic |
| `LLM_MODEL` | Modelo concreto (por defecto algo razonable por proveedor; ver `app/config.py`) |
| `APP_ENV` | `development`, `staging` o `production` |
| `LOG_LEVEL` | Nivel de log, p. ej. `DEBUG` |

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

Si **8000** u **8501** están ocupados en tu máquina, puedes liberarlos o ajustar el mapeo de puertos en `docker-compose.yml`. En macOS/Linux, para ver qué usa el 8000:

```bash
lsof -iTCP:8000 -sTCP:LISTEN
```

---

## Sin Docker (opcional)

Solo tiene sentido si quieres ejecutar tests, linters o depurar fuera del contenedor. Necesitas **Python ≥ 3.9** y **[uv](https://docs.astral.sh/uv/)**.

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
    ├── routers/estimations.py
    ├── services/llm_service.py   # Prompt, ejemplos y llamadas al LLM
    └── context/examples.py      # Ejemplos de estimación (CAG)
```

---

## Dependencias

Las gestiona la imagen Docker a partir de `pyproject.toml`. En local sin Docker, `uv sync` las instala en un `.venv`.
