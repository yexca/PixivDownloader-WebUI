# Development Guide

## Setup

Install the local environment:

```bat
run-install.bat
```

This creates local runtimes under `env/`, installs Python dependencies into `env/python`, installs frontend dependencies with `env/node`, and builds `frontend/dist`.

Alternatively, with an existing Python 3.12 and Node 22.12 or newer:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -c requirements.lock -e ".[dev]"
cd frontend
npm ci
```

Use `.venv\Scripts\python.exe` instead of `env\python\python.exe` in the commands below when using this alternative. Keep application dependencies pinned with `requirements.lock`; regenerate it only in a clean Python 3.12 environment and verify both Windows and Linux installation. Frontend and auth-browser dependencies have independent npm lockfiles.

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
npm run test
npm run build
```

Database migration tests:

```bat
env\python\python.exe -m pytest tests\test_database_migrations.py
```

`typecheck` explicitly checks `tsconfig.app.json` and `tsconfig.node.json`, including application, tests and build configuration. `build` runs that check before Vite. CI also runs frontend lint and behavior tests, Ruff lint/format, backend tests, and sidecar syntax/lockfile checks.

Tests redirect all default runtime paths into temporary folders and reject unmocked requests. Do not point a development smoke test at a user's database or run real scheduled triggers without their authorization. See [Verification](verification.md) for the current baseline.

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

Current top-level WebUI pages are:

```text
Dashboard
Library
Workflows
Artists
Runs
Queue
Events
Settings
About
```

The route labels are owned by `frontend/src/components/AppShell.tsx`, and the browser routes are owned by `frontend/src/main.tsx`.

PixivDownloader-SQLite compatibility is limited to explicit `pixiv.db` import paths. Do not add runtime code or default verification requirements for [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite).

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
