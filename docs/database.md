# Database

PixivDownloader WebUI uses SQLite for local metadata, migration state, settings, jobs, and file status.

## Location

Default WebUI database:

```text
resources/pixiv.sqlite3
```

Resolved by:

```text
backend.core.paths.database_path()
```

[yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite) uses `resources/pixiv.db`. That file is treated only as an optional import source for PixivDownloader WebUI.

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

Schema migrations do not create or read PixivDownloader-SQLite source tables.

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
- `artist_name_history`
- `artworks`
- `artwork_files`
- `local_tags`
- `artist_local_tags`
- `jobs`
- `job_events`
- `workflow_candidate_sets`
- `workflow_candidate_artworks`
- `workflow_definitions`
- `workflow_triggers`
- `workflow_runs`
- `workflow_node_runs`
- `legacy_imports`
- `legacy_import_artists`
- `settings`

`artists.latest_downloaded_artwork_id` stores the latest artwork ID reached by incremental artist downloads.

## PixivDownloader-SQLite Database Import

PixivDownloader-SQLite databases are not migrated automatically. Use WebUI Settings to upload a `pixiv.db` from [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite).

The upload is copied to:

```text
resources/imports/{import_id}/pixiv.db
```

The backend then creates a `legacy_import` workflow run with two nodes:

```text
legacy_database_import
legacy_import_hydration
```

The import reads the source `pic` table and upserts rows into `artists`:

```text
pic.ID             -> artists.id
pic.name           -> artists.name
pic.url            -> artists.profile_url
pic.downloadedDate -> artists.last_checked_at
pic.lastDownloadID -> artists.latest_downloaded_artwork_id
```

The source database is read-only during import. Import state is tracked in
`legacy_imports` and `legacy_import_artists`. The WebUI continues to use
`resources/pixiv.sqlite3`.

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

The canonical node-to-job link is `workflow_node_runs.job_ids_json`.
`jobs.workflow_node_run_id` is a direct lookup aid for jobs created by a node.

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
```

Common workflow node-run statuses:

```text
pending
running
completed
failed
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

## Adding A Migration

1. Add a SQL file under `backend/db/migrations/`.
2. Use the next numeric prefix, for example `003_add_example.sql`.
3. Keep it idempotent where practical.
4. Do not put one-time PixivDownloader-SQLite import logic in schema migrations.
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
