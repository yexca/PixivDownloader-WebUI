# Configuration

The application is local-first. Configuration lives in local files and SQLite.

## Settings Sources

Committed defaults:

```text
config/settings.example.json
```

User overrides and secrets:

```text
config/settings.json
```

SQLite metadata:

```text
resources/pixiv.sqlite3
```

The WebUI loads `settings.example.json` first, then overlays values from
`settings.json` when it exists. WebUI saves write to `config/settings.json`.
The SQLite `settings` table is kept in sync for repository compatibility, but
startup database migrations do not import legacy settings automatically.

Legacy `resources/conf/settings.json` is not read by the WebUI. Use the explicit
migration tool if you need to copy old settings:

```bat
env\python\python.exe tools\migrate_settings_to_config.py
```

## Important Settings

- `download_path`: local target directory for downloaded files.
- `refresh_token`: Pixiv refresh token.
- `request_base_delay_seconds`: minimum delay before Pixiv metadata API requests.
- `request_random_delay_seconds`: random delay range for Pixiv metadata API requests.
- `file_download_base_delay_seconds`: minimum delay before real image file downloads.
- `file_download_random_delay_seconds`: random delay range for image file downloads.
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

## Pixiv Authentication

The Settings page supports two ways to configure Pixiv authentication:

- **Sign in with Pixiv** starts a short-lived PKCE login flow based on the Pixiv
  mobile OAuth endpoints. In Docker Compose, the flow opens a noVNC browser
  sidecar where the user logs in to Pixiv. The backend listens for the Pixiv
  callback and saves the resulting `refresh_token` automatically.
- If the browser sidecar is not configured, **Sign in with Pixiv** falls back to
  the manual flow: after logging in, paste the Pixiv callback URL or the `code`
  value back into Settings so the backend can exchange it for a `refresh_token`.
- Manual token entry remains available as a fallback if Pixiv changes the login
  flow or you already have a valid `refresh_token`.

The temporary PKCE verifier is stored only in backend memory and expires after
five minutes. Successful token exchanges are saved through the normal settings
service into `config/settings.json`.

## Docker Browser Authentication

Docker Compose includes an optional `pixiv-auth-browser` sidecar. It runs Chromium inside
Xvfb and exposes the browser through noVNC. Start it only when browser authentication is needed:

```text
docker compose --profile auth up -d pixiv-auth-browser
```

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

The main backend starts the sidecar through the Docker network, then the sidecar
posts the captured Pixiv callback URL back to the backend. The shared callback
header token is configured with `PIXIV_AUTH_BROWSER_TOKEN`.

After authentication is configured and tested, stop the sidecar:

```text
docker compose stop pixiv-auth-browser
```

Relevant environment variables:

```text
PIXIV_AUTH_BROWSER_INTERNAL_URL
PIXIV_AUTH_BROWSER_PUBLIC_URL
PIXIV_AUTH_BROWSER_CALLBACK_URL
PIXIV_AUTH_BROWSER_TOKEN
```

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
project-root/config
project-root/resources
project-root/frontend/dist
```

Frozen executable layout:

```text
executable-folder/resources
executable-folder/config
executable-folder/frontend/dist
```

## Local Data

Persistent local data:

- `config/settings.json`
- `resources/pixiv.sqlite3`
- the configured download directory

Ignored/generated data:

- `env/`
- `config/settings.json`
- `frontend/node_modules/`
- `frontend/dist/`
- `downloads/`
