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
  "version": "1.0.0"
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

Creates a background job from either:

- Pixiv user ID.
- Pixiv artwork ID.

The job is persisted and processed by the worker queue.

## Jobs

```text
GET  /api/jobs
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
GET  /api/jobs/{job_id}/events
WS   /api/jobs/{job_id}/stream
```

The WebSocket stream is used by the WebUI for live progress updates.

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

Creates a retry job for a failed file or its artwork context.

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
