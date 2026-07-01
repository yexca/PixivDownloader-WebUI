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
POST /api/settings/test-connection
```

Normal settings responses should not expose the full Pixiv refresh token.
Auth validation checks whether the refresh token can authenticate. Connection
testing performs one authenticated Pixiv API request and reports account or rate
limit failures when Pixiv returns them.

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
POST /api/workflows/advanced/runs
GET  /api/workflows/runs
GET  /api/workflows/runs/{run_id}
```

Workflow runs represent orchestration. Advanced runs execute workflow nodes in
linear order. A node may transform context locally or create jobs. Run status is
aggregated from node-run statuses: pending or running nodes keep the run
`running`; terminal nodes move the run to `completed`, `failed`, `partial`, or
`skipped`.

`POST /api/workflows/advanced/runs` accepts:

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

Run responses include both compatibility `items` and advanced `node_runs`.

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
