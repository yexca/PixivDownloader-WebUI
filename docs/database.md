# Database

PixivDownloader-SQLite uses SQLite for local metadata, migration state, settings, jobs, and file status.

## Location

Default database:

```text
resources/pixiv.db
```

Resolved by:

```text
backend.core.paths.database_path()
```

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
6. `resources/conf/settings.json` is synced into the `settings` table when present.

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

Imported legacy table:

- `pic`

The legacy table is preserved and not dropped.

## Legacy Migration

Migration `002_migrate_legacy_pic.sql` copies legacy data from `pic` into `artists`.

Mapping:

```text
pic.ID             -> artists.id
pic.name           -> artists.name
pic.url            -> artists.profile_url
pic.downloadedDate -> artists.last_checked_at
pic.lastDownloadID -> artists.legacy_last_download_id
```

Rows are copied with `INSERT OR IGNORE`, so existing `artists` rows are not overwritten.

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
2. Use the next numeric prefix, for example `004_add_example.sql`.
3. Keep it idempotent where practical.
4. Do not drop legacy data without a backup path.
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
