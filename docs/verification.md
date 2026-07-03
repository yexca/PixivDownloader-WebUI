# Verification

Use this checklist before handing off changes.

## Automated Python Checks

```bat
env\python\python.exe -m ruff format --check .
env\python\python.exe -m ruff check .
env\python\python.exe -m pytest
```

Expected current baseline:

```text
137 passed
```

There may be a third-party Starlette/FastAPI deprecation warning from `TestClient`.

## Frontend Checks

```bat
cd frontend
npm run lint
npm run typecheck
npm run build
```

If `npm` is not available on the machine but `frontend/node_modules` exists, equivalent direct tool execution is acceptable for local verification.

## Backend Smoke Test

```bat
env\python\python.exe -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 7653
```

Then check:

```text
http://127.0.0.1:7653/api/health
```

Expected response:

```json
{
  "status": "ok",
  "version": "0.2.0"
}
```

## Docker Verification

```bat
docker compose config
docker compose build
docker compose up -d
```

Then check:

```text
http://127.0.0.1:7653/api/health
http://127.0.0.1:7653/
```

Expected:

- `/api/health` returns JSON health.
- `/` returns the built WebUI `index.html`.

Stop after testing:

```bat
docker compose down
```

## Manual WebUI Checklist

Use `run-webui.bat`, then verify:

- Dashboard loads and shows recent job state.
- Dashboard shows workflow run groups, trigger health, queue state, and library attention states.
- Settings loads masked refresh token state.
- Settings saves download path and request options.
- Settings `Test Auth` reports success or a clear token failure.
- Settings imports a `pixiv.db` from PixivDownloader-SQLite and updates Library artists.
- Workflows can create a manual definition and run it.
- Workflows can create a scheduled definition and pause/resume its trigger.
- Runs opens a workflow run and shows node-run details plus linked jobs.
- Library lists artists after jobs discover them.
- Library filters by file state, tags, update state, account status, and stale state.
- Artist detail opens and lists artworks/files for the selected artist.
- Artist sync creates a workflow run from a Pixiv user ID.
- Artwork or failed-file retry creates a workflow run and linked job.
- Active job progress and recent events update.
- Queue pause/resume changes job activation behavior.
- Running or queued jobs can be cancelled.
- Failed jobs can be retried, and previous jobs can be rerun.
- Failed files can be retried.
- Events page shows recent job events without exposing the refresh token.

## Pixiv Network Note

Do not run Pixiv network tests unless a valid local refresh token is configured and the user expects real API access.

Automated regression tests should mock Pixiv and file download boundaries.

PixivDownloader-SQLite verification is limited to explicit `pixiv.db` import behavior.
