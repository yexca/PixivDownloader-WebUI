# Architecture

PixivDownloader-SQLite is split into a local WebUI, a Python backend, and local persistent storage.

## Runtime Shape

```text
Browser WebUI
    |
    | HTTP / WebSocket
    v
FastAPI backend
    |
    +-- job queue and workers
    +-- Pixiv API client
    +-- file downloader
    +-- repositories
    +-- SQLite database
```

Normal local runtime:

```text
run-webui.bat
  -> env\python.exe -m backend.app
  -> FastAPI on http://127.0.0.1:7653
  -> serves frontend/dist
  -> opens the browser
```

Container runtime:

```text
docker compose up -d
  -> yexca/pixivdownloader:v0.2.0
  -> FastAPI on 0.0.0.0:7653 inside the container
  -> host port 7653
```

## Directory Ownership

```text
backend/
  api/              FastAPI route modules.
  core/             path resolution, config, logging, and shared errors.
  db/               SQLite connection and migration runner.
  domain/           typed domain entities.
  repositories/     SQL access layer.
  schemas/          Pydantic request and response models.
  services/         Pixiv, settings, jobs, files, and download workflows.
  workers/          in-process background job queue and download worker.

frontend/
  src/api/          typed frontend API functions.
  src/components/   app shell, job UI, data states, and UI primitives.
  src/hooks/        WebSocket streaming and local UI state.
  src/pages/        Dashboard, Download, Library, Jobs, Settings, Logs.

app/
  legacy PyQt code available through run-gui.bat.

config/
  settings.example.json
  settings.json

resources/
  pixiv.db
  static application assets
```

## Backend Startup

`backend.app:create_app()`:

1. Creates the FastAPI application.
2. Registers API routers.
3. Installs exception handlers.
4. Runs database migrations during lifespan startup.
5. Starts the background job queue.
6. Serves `frontend/dist` when the build exists.

`backend.app:main()` reads:

- `PIXIVDOWNLOADER_HOST`, default `127.0.0.1`.
- `PIXIVDOWNLOADER_PORT`, default `7653`.

Docker Compose sets `PIXIVDOWNLOADER_HOST=0.0.0.0` so host port mapping works.

## Backend Layers

Routes should stay thin:

```text
API route
  -> schema validation
  -> service call
  -> response schema
```

Services own workflows:

- settings read/write.
- Pixiv API access.
- download job creation.
- file download and status updates.

Repositories own SQL:

- artists.
- artworks.
- artwork files.
- jobs.
- settings.

## Frontend

The frontend uses:

- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- TanStack Query.
- shadcn/ui-style components.

The release build is written to:

```text
frontend/dist
```

The backend serves built files directly. During development, Vite runs separately and proxies `/api` and WebSocket traffic to the backend.

## Background Jobs

Downloads run as persisted jobs.

Typical lifecycle:

```text
queued -> running -> completed
queued -> running -> failed
queued -> running -> cancelled
```

Job progress and events are stored in SQLite and exposed to the WebUI by API/WebSocket endpoints.

## Legacy PyQt Entry

The project began as a PyQt6 GUI. The `app/` tree remains available through `run-gui.bat`, but the maintained architecture is:

- `backend/` for behavior.
- `frontend/` for user interaction.
- `resources/` and migrations for local data.
