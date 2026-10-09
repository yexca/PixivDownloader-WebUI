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
  "version": "0.2.0",
  "executors": {"enabled": true, "queue": true, "scheduler": true}
}
```

Enabled executor faults return HTTP 503 with `status="degraded"`. Explicitly disabled executors report `enabled=false`.

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
`workflow_node_run_id`.

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

Run responses include `node_runs`. Each node run records its input, output,
status, failure detail, and linked job IDs.

Reusable workflow definitions and triggers are managed with:

```text
GET  /api/workflows/definitions
POST /api/workflows/definitions
POST /api/workflows/definitions/{definition_id}/run
GET  /api/workflows/triggers
POST /api/workflows/triggers
PUT  /api/workflows/triggers/{trigger_id}
POST /api/workflows/triggers/{trigger_id}/run
DELETE /api/workflows/triggers/{trigger_id}
```

Workflow triggers contain schedule rules and create workflow runs when they are
due or manually run.

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
  "workflow_node_run_id": 1,
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

## Execution and Validation Contracts

The `artist_target` node resolves these target protocols:

| Scope | Active target fields | Advanced editor |
| --- | --- | --- |
| `selected` (also the default when scope is absent) | `artist_id` plus `artist_ids`, and `artwork_id` plus `artwork_ids` | Artist IDs are editable; nonempty artwork targets block editing/saving. |
| `single_artist` | A nonempty `artist_id` takes precedence; otherwise uses `artist_ids`. | Single artist field; a fallback list with multiple artists blocks editing/saving. Switching to Selected artists explicitly converts the effective single ID into `artist_ids`. |
| `artists` | Artist IDs, unless `artist_source="artwork_ids"`, which uses artwork IDs instead. | Artist ID sources are editable and retain the original scope so dormant artwork IDs stay inactive. Artwork sources block editing/saving. |
| `single_artwork` / `artworks` | `artwork_id` / `artwork_ids`; a nonempty scalar takes precedence for `single_artwork`. | Blocks editing/saving. |
| `all_artists` / `all` | All local artists; ignores artist/artwork IDs. | Editable. |
| `artists_with_tag` / `tagged` | Union of the `tags` list and scalar `tag`; each matching artist appears once. Empty tags select nobody. | Scalar tag and additional tags are separately editable. Additional tags use one tag per line; spaces and commas remain part of a tag. |
| `artists_not_checked` / `stale` | `days`, falling back to `stale_days`, then 30 days. | Editable; an edited day value is saved as `days`. |

Common target options include `filters` with `last_checked_before_days`, `artist_selection` (`oldest_checked_first`, `newest_checked_first`, or `random`), `skip_unavailable_artists`, and `max_artists`. The editor preserves existing options even when it has no dedicated controls for them. Missing/null limits retain the backend defaults: bulk/ordered selection defaults to 25; explicit unordered artist lists default to their size. Bulk scopes ignore fields belonging to other scopes. Resolution and execution behavior are unchanged.

Opening and saving a supported definition retains its original valid target parameters, other nodes (including node IDs, titles and retry pipelines), and metadata. Only edited fields are updated; bulk scope aliases are saved canonically. Explicitly switching the target scope clears incompatible target fields, while common selection/filter options remain. Reset restores the loaded configuration. Unknown scopes and target values that cannot be represented safely display an error, preserve the original JSON for inspection, and disable saving/running in this editor; use the workflow APIs to edit those definitions.

Saving target or node edits leaves unchanged schedules and every existing trigger untouched, including pause state and next-run time. Explicit schedule edits retain compatibility options and the existing pause state.

Workflow list/detail GETs only read persisted state; background executors progress runs. Download failures propagate through job/node/run failure details, and workflow nodes may end partial or cancelled. Explicit null settings values are rejected while omitted fields are retained. Validation responses are HTTP 422 with JSON-safe `error.details.errors` entries containing `loc`, `msg` and `type`.

Legacy database import accepts at most 64 MiB per file and 65 MiB for the total multipart request, returning HTTP 413 for excess input before unbounded parsing.
