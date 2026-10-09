# Database

PixivDownloader-SQLite uses SQLite for local metadata, migration state, settings, jobs, and file status.

## Location

Default WebUI database:

```text
resources/pixiv.sqlite3
```

Resolved by:

```text
backend.core.paths.database_path()
```

The old PyQt application used `resources/pixiv.db`. That file is treated only as an optional legacy import source.

## Migration Runner

Code:

```text
backend/db/migrate.py
```

SQL files:

```text
backend/db/migrations/
```

Manual run:

```bat
env\python\python.exe -m backend.db.migrate
```

Startup flow:

1. FastAPI lifespan startup calls `migrate_database()`.
2. SQLite connection opens.
3. `schema_migrations` is created if missing.
4. SQL migrations are applied in filename order.
5. Applied versions are recorded.
6. Runtime settings are synced by the settings service when the WebUI reads or saves them.

Schema migrations do not create or read legacy PyQt tables.

## Migration Metadata

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
```

## Current Tables

Main WebUI tables:

- `artists`
- `artworks`
- `artwork_files`
- `artwork_file_download_claims`
- `jobs`
- `job_events`
- `workflow_definitions`
- `workflow_triggers`
- `workflow_runs`
- `workflow_node_runs`
- `settings`

`artists.latest_downloaded_artwork_id` stores the latest artwork ID reached by incremental artist downloads.
`artists.metadata_synced_artwork_id` separately stores the latest artwork ID from a completely committed metadata snapshot.

## Legacy Database Import

Legacy PyQt databases are not migrated automatically. Use Settings -> Import Legacy Database to upload an old `pixiv.db`.

The import reads the old `pic` table and upserts rows into `artists`:

```text
pic.ID             -> artists.id
pic.name           -> artists.name
pic.url            -> artists.profile_url
pic.downloadedDate -> artists.last_checked_at
pic.lastDownloadID -> artists.latest_downloaded_artwork_id
```

The old database is read-only during import. The WebUI continues to use `resources/pixiv.sqlite3`.

## Job And File State

Workflow runs are persisted so the UI can show orchestration history. Advanced
workflow execution is stored as node runs. Each `workflow_node_runs` row records
one module execution:

```text
node_id
node_type
position
status
input_json
output_json
job_ids_json
error_message
```

Jobs are persisted so the UI can show execution history and progress. Jobs
created by workflow nodes store workflow links:

```text
jobs.workflow_run_id      -> workflow_runs.id
jobs.workflow_node_run_id -> workflow_node_runs.id
jobs.workflow_source      -> workflow source label
```

Node job IDs are persisted in `workflow_node_runs.job_ids_json`; recovery also checks `jobs.workflow_node_run_id` so it can reconnect a job created just before an interrupted node update. Creation uses a SQLite write transaction to reuse a node/target job on retry.

Workflow definitions and triggers store reusable workflow configs and their
schedule rules. A due trigger creates a workflow run; the run then progresses
through node runs and jobs like any other workflow.

Common job statuses:

```text
inactive
queued
running
completed
failed
cancelled
```

Common workflow run statuses:

```text
running
completed
failed
partial
skipped
cancelled
```

Workflow run status is derived from node runs. A run remains `running` while any
node run is pending or running. Node runs that create jobs remain running until
their linked jobs become terminal.

Artwork file statuses:

```text
pending
downloading
downloaded
skipped
failed
```

## Integrity Upgrade (022–023)

Migration SQL and its version record now execute in one explicit transaction; a mid-script failure rolls back both. Existing migration scripts remain unchanged.

022 adds execution and scheduler claims. These serialize competing progression calls and schedule scans; recovery releases abandoned claims before starting the single application process. GET endpoints only read state. The queue progresses workflows independently of browser polling. Failed/cancelled/partial predecessor nodes terminate pending descendants as skipped, with completion timestamps.

023 repairs generated `scheduled-task:*` definitions produced by 017, using their preserved compatibility snapshot. Sync-only actions stay sync-only, retry actions select failed pages, and targets, filters and download options are recompiled with their original intent. Trigger status, next execution time and success/error history are preserved; the migration creates no jobs and does not execute a workflow. Definitions edited after 017 are left untouched and require a deliberate review; it is unsafe to overwrite a user's later workflow design from its old snapshot.

No migration deletes user downloads or resets historic watermarks. Already present incomplete records below a historic watermark are accessible through pending/failed collection. New download progress advances the watermark only across a complete prefix of the known library.

## Metadata Snapshots And File Ownership (024)

024 adds an independent metadata sync watermark and per-page download claims. Existing download cursors, file status, paths, and download timestamps are retained. Existing artists start without the new metadata watermark: their next sync fetches all metadata once, so a historic partial write or an incomplete legacy import cannot hide older artworks behind a local maximum ID.

Artist metadata is inserted before name history. The artist, old and new names, all fetched artworks, all fetched pages, and the metadata watermark commit together in one SQLite transaction. Missing or duplicate declared pages are rejected before persistence. Any write error or process interruption rolls back the entire snapshot. Remote-page upserts update only the remote URL and name, preserving current download status and local download details. Avatar caching runs after the database commit.

Both candidate downloads and the legacy download service acquire ownership of a page before changing its status. Other tasks wait for that page with cancellation checks; unrelated pages continue concurrently. Each claimant reads the current page state under the SQLite write lock. Completion, failure, and cancellation use conditional updates that require the same owner and a still-active `downloading` state. Cancelling a waiter changes no file status. Cancelling an owner restores its acquisition-time state; a failed overwrite retains a previously downloaded file and its path while the task still reports failure. Download cursors advance from committed file states.

Before workers start, startup recovery restores only abandoned claims that still have `downloading` status and releases their ownership. A file already completed before an interruption is retained. This continues the existing single-application-process deployment contract; simultaneous application startups against the same database are unsupported.

## Adding A Migration

1. Add a SQL file under `backend/db/migrations/`.
2. Use the next numeric prefix, for example `003_add_example.sql`.
3. Keep it idempotent where practical.
4. Do not put one-time legacy import logic in schema migrations.
5. Add or update tests.
6. Run:

```bat
env\python\python.exe -m pytest tests\test_database_migrations.py
```

Full check:

```bat
env\python\python.exe -m ruff format --check .
env\python\python.exe -m ruff check .
env\python\python.exe -m pytest
```
