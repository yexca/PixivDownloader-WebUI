# Database Migrations

PixivDownloader-SQLite uses SQLite and applies migrations at backend startup.

## Database Location

Default database path:

```text
resources/pixiv.db
```

The path is resolved through `backend.core.paths.database_path()`, which supports both source checkout and future frozen executable layouts.

## Migration Runner

Migration code:

```text
backend/db/migrate.py
```

Migration files:

```text
backend/db/migrations/
```

Startup flow:

1. `backend.app:create_app()` enters FastAPI lifespan startup.
2. `migrate_database()` opens the SQLite database.
3. `schema_migrations` is created if missing.
4. New SQL files are applied in filename order.
5. Applied versions are recorded in `schema_migrations`.
6. Settings are synced from `resources/conf/settings.json` into the `settings` table.

Manual run:

```bat
env\python.exe -m backend.db.migrate
```

## Migration Naming

Files use this shape:

```text
001_create_webui_schema.sql
002_migrate_legacy_pic.sql
003_add_indexes.sql
```

The numeric prefix is stored as the migration version. The remainder is stored as the migration name.

## Applied Migration Table

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
```

## Current Migrations

`001_create_webui_schema.sql`

Creates:

- `artists`
- `artworks`
- `artwork_files`
- `jobs`
- `job_events`
- `settings`

`002_migrate_legacy_pic.sql`

Ensures the legacy `pic` table exists and copies rows into `artists` with `INSERT OR IGNORE`.

Legacy mapping:

- `pic.ID` -> `artists.id`
- `pic.name` -> `artists.name`
- `pic.url` -> `artists.profile_url`
- `pic.downloadedDate` -> `artists.last_checked_at`
- `pic.lastDownloadID` -> `artists.legacy_last_download_id`

The legacy `pic` table is not dropped.

`003_add_indexes.sql`

Adds indexes for common lookup paths:

- artworks by artist.
- artwork files by artwork and status.
- jobs by status.
- job events by job.

## Settings Sync

After SQL migrations, `migrate_database()` reads `resources/conf/settings.json` if it exists and writes settings into the SQLite `settings` table.

This preserves compatibility with the old configuration file during the transition. New code should use the backend settings service rather than reading the JSON file directly.

## Adding A Migration

1. Add a new SQL file under `backend/db/migrations/` with the next numeric prefix.
2. Make it idempotent where practical with `IF NOT EXISTS`, `INSERT OR IGNORE`, or guarded updates.
3. Do not drop legacy data without an explicit backup path.
4. Add or update tests under `tests/`.
5. Run:

```bat
env\python.exe -m pytest tests\test_database_migrations.py
```

Full verification:

```bat
env\python.exe -m ruff format --check .
env\python.exe -m ruff check .
env\python.exe -m pytest
```

## Packaged Builds

Packaged builds should include:

```text
resources/pixiv.db
resources/conf/settings.json
backend/db/migrations/
```

If the app is frozen into an executable, migrations must remain readable from the resolved application folder. The current path resolver uses the executable directory when `sys.frozen` is set.
