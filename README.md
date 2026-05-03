# estimador-cag

API **FastAPI** que genera **estimaciones de software** a partir de la transcripción de una reunión. El modelo recibe en el mensaje *system* el rol de estimador y **ejemplos históricos** definidos en `app/context/examples.py` (arquitectura tipo **CAG**: el contexto viaja en la propia llamada al LLM). El proveedor (**OpenAI** o **Anthropic**) se elige con `LLM_PROVIDER` en `.env`.

Además incluye una **interfaz de chat con Streamlit** (`streamlit_app.py`) que usa el mismo servicio LLM y la misma configuración por `.env` que la API: conversación por turnos, respuesta en streaming y una barra lateral con transparencia CAG (system prompt y bloque de ejemplos en solo lectura) y métricas de la última respuesta (modelo, proveedor, tokens, tiempo).

## Requisitos

- Python 3.9 o superior (`requires-python` en `pyproject.toml`)
- Opcional: [uv](https://docs.astral.sh/uv/) para instalar dependencias y ejecutar el servidor

## Instalación

Con **uv** (recomendado):

```bash
cd estimador-cag
uv sync
```

Con **pip** y un venv clásico:

```bash
cd estimador-cag
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install .
```

## Variables de entorno

Copia `.env.example` a `.env` y rellena los valores. El archivo **`.env` está en `.gitignore`**; no subas claves al repositorio.

| Variable | Descripción | Valor por defecto (en código) |
|----------|-------------|----------------------------------|
| `OPENAI_API_KEY` | Clave de OpenAI | Ninguno (obligatoria si `LLM_PROVIDER=openai`) |
| `ANTHROPIC_API_KEY` | Clave de Anthropic | Ninguno (obligatoria si `LLM_PROVIDER=anthropic`) |
| `LLM_PROVIDER` | `openai` o `anthropic` | `openai` |
| `LLM_MODEL` | Modelo del proveedor | `gpt-4o-mini` (OpenAI); con Anthropic, si dejas un modelo GPT, se usa `claude-haiku-4-5` por defecto en el servicio) |
| `APP_ENV` | Entorno de ejecución | `development` |
| `LOG_LEVEL` | Nivel de logging | `DEBUG` |

La carga real la hace **`app/config.py`** con Pydantic `BaseSettings` y `env_file=".env"`. Ejecuta siempre el servidor **desde la raíz del proyecto** (`estimador-cag/`) para que se encuentre el `.env`.

## Arranque en desarrollo

```bash
cd estimador-cag
uv run uvicorn app.main:app --reload
```

Equivalente con venv activado:

```bash
uvicorn app.main:app --reload
```

- Documentación interactiva: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (Swagger UI)
- Esquema OpenAPI JSON: [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

### Puerto ocupado (`Address already in use`)

Si el **8000** ya está en uso por otro proceso (por ejemplo un `uvicorn` anterior):

```bash
kill $(lsof -t -iTCP:8000 -sTCP:LISTEN)
```

O arranca en otro puerto:

```bash
uv run uvicorn app.main:app --reload --port 8001
```

## Interfaz web (Streamlit)

Chat para pegar o escribir la transcripción y ver la estimación con **streaming**. La barra lateral muestra el *system prompt* completo, el bloque de ejemplos CAG y, tras cada respuesta completada, modelo, proveedor, tokens de entrada/salida y tiempo de respuesta.

Ejecuta **desde la raíz del proyecto** `estimador-cag/` (igual que la API, para que se cargue `.env`):

```bash
cd estimador-cag
uv run streamlit run streamlit_app.py
```

Con venv activado:

```bash
streamlit run streamlit_app.py
```

Por defecto Streamlit suele abrir en [http://localhost:8501](http://localhost:8501). Si el puerto está ocupado:

```bash
uv run streamlit run streamlit_app.py --server.port 8502
```

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Estado del servicio (`200`, JSON con `status` y `time` en UTC) |
| `POST` | `/api/v1/estimate` | Cuerpo JSON: `{ "transcription": "..." }`. Respuesta: `estimation`, `model`, `provider`, `generated_at`, uso de tokens opcional |

Ejemplo con **curl**:

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/estimate" \
  -H "Content-Type: application/json" \
  -d '{"transcription": "El cliente describe el alcance del proyecto en esta reunión..."}'
```

## Estructura del código

```text
streamlit_app.py            # UI Streamlit: chat + sidebar CAG / métricas
app/
├── main.py                 # FastAPI: título/descripción, router, /health
├── config.py               # Settings desde .env
├── routers/
│   └── estimations.py      # POST /api/v1/estimate
├── services/
│   └── llm_service.py      # System prompt + ejemplos; llamadas OpenAI / Anthropic
└── context/
    └── examples.py         # ESTIMATION_EXAMPLES (few-shot / CAG)
```

## Dependencias principales

- **fastapi**, **uvicorn[standard]** — API y servidor ASGI
- **streamlit** — interfaz de chat en el navegador
- **pydantic-settings** — configuración desde entorno
- **openai**, **anthropic** — clientes LLM
- **python-dotenv** — lectura de `.env` (coherente con el uso típico en local)

Tras cambiar `pyproject.toml`, vuelve a instalar (`uv sync` o `pip install .`).
