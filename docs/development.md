# Development Guide

## Setup

Install the local environment:

```bat
run-install.bat
```

This creates local runtimes under `env/`, installs Python dependencies into `env/python`, installs frontend dependencies with `env/node`, and builds `frontend/dist`.

## Backend Development

```bat
env\python\python.exe -m uvicorn backend.app:create_app --factory --reload --host 127.0.0.1 --port 7653
```

The backend runs with Uvicorn reload on:

```text
http://127.0.0.1:7653
```

## Frontend Development

```bat
cd frontend
npm run dev
```

Vite proxies API and WebSocket traffic to the backend. Keep the backend running while developing frontend pages.

## Checks

Python:

```bat
env\python\python.exe -m ruff format --check .
env\python\python.exe -m ruff check .
env\python\python.exe -m pytest
```

Frontend:

```bat
cd frontend
npm run lint
npm run typecheck
npm run build
```

Database migration tests:

```bat
env\python\python.exe -m pytest tests\test_database_migrations.py
```

## Code Organization

Backend route handlers should stay thin:

```text
route -> schema -> service -> repository
```

Do not put SQL in API routes. Repositories own database statements.

Do not call Pixiv directly from API routes. Use service/client boundaries so tests can mock network behavior.

Frontend components should use typed API helpers under:

```text
frontend/src/api/
```

Avoid scattering raw `fetch()` calls inside pages.

Legacy PyQt compatibility is limited to explicit old `pixiv.db` import paths. Do not add PyQt runtime code or default verification requirements for the old desktop application.

## Python Standards

- Python 3.12.
- Ruff for format and lint.
- `snake_case` for functions, methods, and variables.
- `PascalCase` for classes.
- Module-level loggers with `logging.getLogger(__name__)`.
- No production `print()`.
- No wildcard imports.
- Type hints at service, repository, and API boundaries.

## Docker Development

Build:

```bat
docker compose build
```

Run:

```bat
docker compose up -d
```

Check:

```bat
curl http://127.0.0.1:7653/api/health
```

Stop:

```bat
docker compose down
```

## Troubleshooting

If frontend installation or build fails, rerun `run-install.bat` to restore the local `env\node` runtime and rebuild the assets.

If Docker Compose cannot connect to the engine, start Docker Desktop first.

If the WebUI script says `frontend/dist/index.html` is missing, run:

```bat
run-install.bat
```

or:

```bat
cd frontend
npm run build
```
