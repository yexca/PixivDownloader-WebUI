# API Reference

The backend API is served by FastAPI under `/api`.

Default local base URL:

```text
http://127.0.0.1:7653
```

## Health

```text
GET /api/health
```

Response:

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

## Settings

```text
GET /api/settings
PUT /api/settings
POST /api/settings/validate-auth
```

Normal settings responses should not expose the full Pixiv refresh token.

## Imports

```text
POST /api/imports/legacy-database
```

Uploads an old PyQt `pixiv.db` and imports its `pic` table into the current WebUI database.

## Downloads

```text
POST /api/downloads
```

Creates a workflow run and dispatches a background job from either:

- Pixiv user ID.
- Pixiv artwork ID.

The response keeps the shortcut shape used by the UI:

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

The job is linked to the workflow run through `workflow_run_id` and
`workflow_item_id`.

## Workflows

```text
POST /api/workflows/run
POST /api/workflows/runs
GET  /api/workflows/runs
GET  /api/workflows/runs/{run_id}
```

Workflow runs represent orchestration. A run expands targets and actions into
workflow items, then dispatches jobs. Run status is aggregated from linked jobs:
active jobs keep the run `running`; terminal jobs move the run to `completed`,
`failed`, `partial`, or `skipped`.

## Jobs

```text
GET  /api/jobs
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
GET  /api/jobs/{job_id}/events
WS   /api/jobs/{job_id}/stream
```

The WebSocket stream is used by the WebUI for live progress updates.

Job responses include workflow linkage fields when a job was created by a
workflow shortcut or workflow batch:

```json
{
  "workflow_run_id": "uuid",
  "workflow_item_id": 1,
  "workflow_source": "download_api"
}
```

## Artists And Artworks

```text
GET /api/artists
GET /api/artists/{artist_id}
GET /api/artists/{artist_id}/artworks
GET /api/artworks/{artwork_id}/files
```

These endpoints back the Library and Artist Detail pages.

## Artwork Files

```text
POST /api/artwork-files/{file_id}/retry
```

Creates a workflow run and retry job for a failed file or its artwork context.

## Logs

```text
GET /api/logs
```

The UI should prefer user-facing job events over raw implementation logs when possible.

## Error Shape

Errors should follow this structure:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": {}
  }
}
```

Common codes:

- `validation_error`
- `config_error`
- `pixiv_auth_failed`
- `pixiv_api_error`
- `download_error`
- `job_not_found`
- `job_not_cancellable`
- `database_error`
- `internal_error`
