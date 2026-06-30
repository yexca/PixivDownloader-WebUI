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
35 passed
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
  "version": "0.1.0"
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
- Settings loads masked refresh token state.
- Settings saves download path and request options.
- Settings `Test Auth` reports success or a clear token failure.
- Settings imports an old PyQt `pixiv.db` and updates Library artists.
- Download creates a job from a Pixiv user ID.
- Download creates a job from an artwork ID.
- Active job progress and recent events update.
- Running or queued jobs can be cancelled.
- Failed files can be retried.
- Library lists artists after jobs discover them.
- Artist detail opens and lists artworks/files for the selected artist.
- Logs page shows recent job events without exposing the refresh token.

## Pixiv Network Note

Do not run Pixiv network tests unless a valid local refresh token is configured and the user expects real API access.

Automated regression tests should mock Pixiv and file download boundaries.

Legacy verification is limited to explicit old `pixiv.db` import behavior.
