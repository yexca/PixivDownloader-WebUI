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
env\python.exe -m backend.db.migrate
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
- `jobs`
- `job_events`
- `settings`

`artists.latest_downloaded_artwork_id` stores the latest artwork ID reached by incremental artist downloads.

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

Jobs are persisted so the UI can show history and progress.

Common job statuses:

```text
queued
running
completed
failed
cancelled
```

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
4. Do not put one-time legacy import logic in schema migrations.
5. Add or update tests.
6. Run:

```bat
env\python.exe -m pytest tests\test_database_migrations.py
```

Full check:

```bat
env\python.exe -m ruff format --check .
env\python.exe -m ruff check .
env\python.exe -m pytest
```
