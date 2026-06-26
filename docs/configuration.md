# Configuration

The application is local-first. Configuration lives in local files and SQLite.

## Settings Sources

Legacy-compatible JSON:

```text
resources/conf/settings.json
```

SQLite settings table:

```text
resources/pixiv.db
```

The migration runner syncs values from `settings.json` into the SQLite `settings` table during startup. New backend code should use the settings service rather than reading the JSON file directly.

## Important Settings

- `download_path`: local target directory for downloaded files.
- `refresh_token`: Pixiv refresh token.
- `request_base_delay_seconds`: minimum delay before requests/downloads.
- `request_random_delay_seconds`: random delay range.
- `max_concurrent_downloads`: configured concurrency limit.
- `overwrite_existing_files`: whether existing files should be overwritten.
- `skip_existing_files`: whether existing files should be skipped.

## Secrets

The Pixiv `refresh_token` is sensitive.

Rules:

- Do not log the full token.
- Do not return the full token in normal GET settings responses.
- Prefer masked display such as `abcd...wxyz`.
- Use the Settings page auth validation action to test whether the token works.

## Environment Variables

Backend runtime:

```text
PIXIVDOWNLOADER_HOST
PIXIVDOWNLOADER_PORT
```

Defaults:

```text
PIXIVDOWNLOADER_HOST=127.0.0.1
PIXIVDOWNLOADER_PORT=7653
```

Docker Compose sets:

```text
PIXIVDOWNLOADER_HOST=0.0.0.0
PIXIVDOWNLOADER_PORT=7653
```

Frontend development:

```text
PIXIVDOWNLOADER_PORT
```

Vite uses this to proxy API and WebSocket traffic to the backend.

## Resource Paths

Path resolution is centralized in:

```text
backend/core/paths.py
```

Source checkout layout:

```text
project-root/resources
project-root/frontend/dist
```

Frozen executable layout:

```text
executable-folder/resources
executable-folder/frontend/dist
```

## Local Data

Persistent local data:

- `resources/conf/settings.json`
- `resources/pixiv.db`
- the configured download directory

Ignored/generated data:

- `env/`
- `frontend/node_modules/`
- `frontend/dist/`
- `downloads/`
