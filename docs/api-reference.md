# API Reference

The backend API is served by FastAPI under `/api`.

Default local base URL:

```text
http://127.0.0.1:7653
```

Most list endpoints return `{ "items": [...], "total": number }`. Validation and runtime errors use the common error shape described at the end of this page.

## Health

```text
GET /api/health
```

Response:

```json
{
  "status": "ok",
  "version": "0.2.0"
}
```

## Dashboard

```text
GET /api/dashboard
```

Returns library counts, workflow counts, job counts, and whether the queue is paused. This endpoint backs the Dashboard summary cards.

## Settings

```text
GET  /api/settings
PUT  /api/settings
POST /api/settings/validate-auth
POST /api/settings/test-connection
```

Settings responses mask the Pixiv refresh token and include runtime metadata:

```json
{
  "download_path": "downloads",
  "download_path_editable": true,
  "runtime_mode": "local",
  "refresh_token_configured": true,
  "refresh_token_preview": "abcd...wxyz",
  "existing_file_behavior": "skip"
}
```

Auth validation checks whether the configured refresh token can authenticate. Connection testing performs one authenticated Pixiv API request and reports the Pixiv account or a clear failure.

Pixiv PKCE and browser-auth endpoints:

```text
POST /api/settings/pixiv-auth/start
POST /api/settings/pixiv-auth/complete
POST /api/settings/pixiv-auth/refresh
POST /api/settings/pixiv-auth/browser/start
GET  /api/settings/pixiv-auth/browser/{flow_id}
GET  /api/settings/pixiv-auth/browser-service
POST /api/settings/pixiv-auth/browser/callback
```

The browser callback endpoint is intended for the Docker auth sidecar. If `PIXIV_AUTH_BROWSER_TOKEN` is configured, the callback must include the matching `X-Pixiv-Auth-Browser-Token` header.

## Downloads

```text
POST /api/downloads
```

Creates a shortcut workflow run and dispatches a background job from either:

- Pixiv artist ID.
- Pixiv artwork ID.

The response keeps the shortcut shape used by the UI:

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

The job is linked to the workflow run through `workflow_run_id` and `workflow_node_run_id`.

## Imports

```text
POST /api/imports/legacy-database
```

Uploads a `pixiv.db` from [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite), stores it under `resources/imports/`, creates an import workflow run, and starts import plus hydration jobs when applicable.

## Workflows

One-off advanced runs:

```text
POST /api/workflows/advanced/runs
```

Reusable workflow definitions:

```text
GET    /api/workflows/definitions
POST   /api/workflows/definitions
DELETE /api/workflows/definitions/{definition_id}
POST   /api/workflows/definitions/{definition_id}/run
PUT    /api/workflows/definition-triggers/{trigger_id}
```

Run history:

```text
GET /api/workflows/runs
GET /api/workflows/runs/{run_id}
```

`POST /api/workflows/advanced/runs` accepts a linear node definition:

```json
{
  "definition": {
    "name": "Artist download pipeline",
    "nodes": [
      {
        "id": "target",
        "type": "artist_target",
        "title": "Target artists",
        "config": {
          "artist_ids": ["123456"],
          "max_artists": 1
        }
      },
      {
        "id": "actions",
        "type": "execute_actions",
        "title": "Execute actions",
        "config": {
          "actions": ["download_artist"]
        }
      }
    ]
  }
}
```

Current backend node types:

```text
artist_target
sync_metadata
collect_artworks
filter_artworks
execute_actions
job_action
legacy_database_import
legacy_import_hydration
```

Run responses include `node_runs`. Each node run records its input, output, status, failure detail, and linked job IDs.

Workflow run status is aggregated from node-run statuses. Pending or running nodes keep the run `running`; terminal nodes move the run to `completed`, `failed`, `partial`, or `skipped`.

## Workflow Triggers

```text
GET    /api/workflows/triggers
POST   /api/workflows/triggers
PUT    /api/workflows/triggers/{trigger_id}
POST   /api/workflows/triggers/{trigger_id}/run
DELETE /api/workflows/triggers/{trigger_id}
```

Workflow triggers represent scheduled work. They can target a single artist, multiple artists, artworks, library tag groups, stale artists, or other supported target configs. Manual trigger runs and due scheduled runs both create workflow runs through the same execution layer.

## Jobs And Queue

```text
GET  /api/jobs
GET  /api/jobs/queue
POST /api/jobs/queue/pause
POST /api/jobs/queue/resume
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
POST /api/jobs/{job_id}/retry
POST /api/jobs/{job_id}/rerun
POST /api/jobs/bulk-cancel
GET  /api/jobs/{job_id}/events
WS   /api/jobs/{job_id}/stream
```

The WebSocket stream is used by the WebUI for live progress updates.

Job responses include workflow linkage fields when a job was created by a shortcut, workflow node, trigger, retry, rerun, or PixivDownloader-SQLite import:

```json
{
  "workflow_run_id": "uuid",
  "workflow_node_run_id": 1,
  "workflow_source": "download_api"
}
```

Common job statuses:

```text
inactive
queued
running
completed
failed
cancelled
```

## Artists And Library

```text
GET    /api/artists
POST   /api/artists
GET    /api/artists/-/local-tags
GET    /api/artists/{artist_id}
DELETE /api/artists/{artist_id}
POST   /api/artists/{artist_id}/sync
POST   /api/artists/{artist_id}/retry-failed
PUT    /api/artists/{artist_id}/local-tags
GET    /api/artists/{artist_id}/artworks
GET    /api/artists/{artist_id}/avatar
```

`GET /api/artists` supports filtering and pagination with query parameters such as `q`, `local_tag`, `file_state`, `tag_state`, `account_status`, `update_state`, `limit`, `offset`, and `sort`.

`POST /api/artists` is a library shortcut that creates an artist sync workflow run from a Pixiv user ID.

## Artwork Files

```text
GET  /api/artworks/{artwork_id}/files
POST /api/artwork-files/{file_id}/retry
```

Retry creates a workflow run and a retry job for the failed file or its artwork context.

## Logs And Events

```text
GET /api/logs/recent
```

Supports `limit`, `offset`, and optional `level`. The UI should prefer user-facing job events over raw implementation logs when possible.

## Error Shape

Errors should follow this structure:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "failure": {
      "code": "validation_error",
      "reason": "rule",
      "retryable": false,
      "message": "Request validation failed."
    },
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
- `insufficient_disk_space`
- `job_not_found`
- `job_not_cancellable`
- `database_error`
- `internal_error`
