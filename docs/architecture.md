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
    +-- workflow runs and workflow triggers
    +-- job queue and workers
    +-- Pixiv API client
    +-- file downloader
    +-- repositories
    +-- SQLite database
```

Normal local runtime:

```text
run-webui.bat
  -> env\python\python.exe -m backend.app
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
  services/         Workflows, jobs, Pixiv, settings, files, and downloads.
  services/workflow_nodes/
                    Independent advanced workflow node executors.
  workers/          in-process background job queue and download worker.

frontend/
  src/api/          typed frontend API functions.
  src/components/   app shell, job UI, data states, and UI primitives.
  src/hooks/        WebSocket streaming and local UI state.
  src/pages/        Dashboard, Download, Library, Jobs, Settings, Logs.

auth-browser/
  Docker sidecar for Pixiv browser authentication.

config/
  settings.example.json
  settings.json

resources/
  pixiv.sqlite3
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

Services own orchestration and domain behavior:

- settings read/write.
- workflow planning and node-run progression.
- job creation, queue state, and recovery.
- Pixiv API access through Pixiv/download/library services.
- file download and status updates through download/file services.

Workflow code must not call Pixiv directly. A workflow node either transforms
workflow context locally or creates persisted jobs. Jobs and workers are the
boundary that call Pixiv-facing services.

Repositories own SQL:

- artists.
- artworks.
- artwork files.
- workflow runs.
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

## Workflows, Jobs, And Events

The maintained advanced execution model is:

```text
WorkflowRun
  -> WorkflowNodeRun
      -> Job[]
          -> JobEvent
```

Workflow runs represent user intent and orchestration. Workflow node runs are
the executable stages in a workflow. Each node has isolated input, output,
status, error, and linked job IDs.

The advanced linear workflow currently uses these node types:

```text
artist_target
sync_metadata
collect_artworks
filter_artworks
execute_actions
file_output
```

The workflow runner owns only orchestration:

```text
create run
create node runs
load previous node output into context
execute the next ready node executor
wait for linked jobs to become terminal
derive run status from node-run status
```

Node executors live under `backend/services/workflow_nodes/`. Each executor owns
one module's config parsing and output shape. Heavy work is expressed by
creating jobs, not by calling Pixiv or downloading files directly.

Jobs are persisted execution units. A single workflow node can create zero, one,
or many jobs. Jobs remain responsible for queueing, cancellation, retry,
progress, and worker execution.

Pixiv-facing behavior stays below the job layer:

```text
WorkflowNodeRun
  -> Job
      -> worker
          -> download_service / library_sync_service / Pixiv client
```

The runtime boundary is `WorkflowRun -> WorkflowNodeRun -> Job[]`.

Workflow triggers are reusable workflow definitions with schedule rules. When a
trigger is due, it creates a workflow run from its stored definition. Manual
runs, shortcut runs, and trigger runs all use the same node-run and job
execution layer.

Downloads run as persisted jobs.

Typical lifecycle:

```text
queued -> running -> completed
queued -> running -> failed
queued -> running -> cancelled
```

Job progress and events are stored in SQLite and exposed to the WebUI by API/WebSocket endpoints.

Workflow run status is aggregated from node-run statuses. A run stays `running`
while any node is pending or running, and reaches `completed`, `failed`,
`partial`, or `skipped` after node runs reach terminal states.

## Legacy Data Import

The WebUI can import old PyQt `pixiv.db` files for user migration. The old desktop application source is not part of this repository.

The maintained architecture is:

- `backend/` for behavior.
- `frontend/` for user interaction.
- `auth-browser/` for Docker browser authentication.
- `resources/` and migrations for local data.

New work should target the WebUI and backend. Legacy compatibility code should stay limited to explicit data import paths.
