# WebUI Architecture

PixivDownloader-SQLite now runs as a local WebUI application. The backend and frontend are separate during development, then combined for normal local use by serving the built frontend from FastAPI.

## Runtime Flow

```text
run-webui.bat
  |
  v
env\python.exe -m backend.app
  |
  v
FastAPI on 127.0.0.1:7653
  |
  +-- /api/* JSON and WebSocket endpoints
  +-- frontend/dist static files
```

`run-webui.bat` opens the browser to `http://127.0.0.1:7653` after starting the backend process.

Set `PIXIVDOWNLOADER_PORT` before running scripts to use a different local port.

## Backend

The backend is organized by responsibility:

- `backend/api/`: HTTP and WebSocket route handlers.
- `backend/schemas/`: Pydantic models used at API boundaries.
- `backend/services/`: business workflows such as settings, jobs, Pixiv access, and downloads.
- `backend/repositories/`: SQLite data access.
- `backend/workers/`: background job execution.
- `backend/db/`: database connection and migrations.
- `backend/core/`: shared path resolution, config handling, logging, and domain errors.

FastAPI route handlers should stay thin. They should validate requests, call services, and return schemas. Database access belongs in repositories.

## Frontend

The frontend uses:

- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- TanStack Query.
- shadcn/ui-style component conventions.

Important directories:

- `frontend/src/api/`: typed API functions. Components should not scatter raw `fetch()` calls.
- `frontend/src/pages/`: top-level views.
- `frontend/src/components/`: shared app shell, job UI, data states, and UI primitives.
- `frontend/src/hooks/`: frontend state and streaming helpers.

The release build is written to:

```text
frontend/dist
```

## API Surface

Current API groups:

- `/api/health`
- `/api/settings`
- `/api/settings/validate-auth`
- `/api/downloads`
- `/api/jobs`
- `/api/artists`
- `/api/artworks`
- `/api/artwork-files`
- `/api/logs`

Errors should use the shared shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": {}
  }
}
```

## Static Asset Serving

`backend.app.register_frontend_routes()` checks for `frontend/dist/index.html`. If it exists, non-API paths are served from the frontend build:

- Existing files under `frontend/dist` are returned directly.
- Unknown non-API paths return `index.html` for client-side routing.
- `/api/*` paths remain API-owned.

If `frontend/dist/index.html` is missing, the static route is not registered. `run-webui.bat` catches this earlier and asks the user to run `run-install.bat`.

## Local Development

Start the backend:

```bat
run-backend-dev.bat
```

Start the frontend:

```bat
run-frontend-dev.bat
```

Vite proxies `/api` and WebSocket traffic to `http://127.0.0.1:7653` by default.

## Install And Node Strategy

`run-install.bat` creates the local Python runtime and builds the WebUI.

Python strategy:

- Install Miniconda if missing.
- Create `env` in the project root.
- Use `env\python.exe` for all Python package installation.
- Do not use global Python.

Node strategy:

- Detect `npm` on the system PATH.
- If `npm` is missing, stop with instructions to install the Windows LTS version of Node.js from <https://nodejs.org/>.

A local managed Node cache can be added later, but the current scripts intentionally fail clearly instead of silently choosing an unknown Node installation path.

## Resource Paths

Path resolution is centralized in `backend.core.paths`.

Source checkout mode:

```text
project-root/resources
project-root/frontend/dist
```

Frozen executable mode:

```text
executable-folder/resources
executable-folder/frontend/dist
```

Packaged builds should preserve those relative paths.
