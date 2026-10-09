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
Settings reads do not write SQLite. Updates merge the latest JSON under a SQLite write lock and batch the compatibility mirror into one commit. The SQLite `settings` table is kept in sync on updates for repository compatibility, but
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
- `max_concurrent_downloads`: maximum simultaneously executing queue jobs in this service process, including metadata/resolver jobs. Separate image and metadata rate limiters are shared across workers.
- `max_active_run_jobs`: maximum queued/running jobs across one-time workflow runs; remaining jobs stay inactive until capacity is available.
- `max_active_workflow_triggers`: maximum simultaneously running workflows started by scheduled triggers. Automatic dispatch does not overlap the same trigger's unfinished run; an explicit manual run remains user-controlled.
- `existing_file_behavior`: `skip`, `overwrite` or `save_duplicate`. The old `overwrite_existing_files` and `skip_existing_files` keys remain input compatibility aliases.

Explicit workflow `conflict_mode` (`skip`, `overwrite`, `rename`) overrides the global file policy; an omitted option inherits it. Failed/downloading database records always retry through a temporary file instead of trusting an existing fragment, even with `skip`. A complete existing file remains intact until replacement succeeds.

`force_rescan` and `full_download` refresh all remote metadata and allow all synced files, preserving the older rescan behavior. A pending-only request still selects pending pages; an explicit retry action still selects failed pages. `pending_only` selects `pending`/`remote_only`; retry selects only `failed` pages. New-artwork collection selects incomplete artworks above the download watermark and never advances that watermark past a known gap. Limits and filters leave excluded files available for a later appropriate workflow. Historical watermarks are preserved: use pending/failed collection to repair incomplete older records.

Naming and tag rules flow through shortcuts, scheduled and advanced workflows. The first matching tag rule applies; its naming rule overrides the default, and its `skip` behavior is an intentional completion. A `retry_failed` tag behavior leaves other pages untouched. Missing update fields retain their values; explicit null settings values are rejected with HTTP 422.

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
header token is configured with a private random `PIXIV_AUTH_BROWSER_TOKEN`. noVNC also requires `PIXIV_AUTH_BROWSER_VNC_PASSWORD`. Follow the secret generation and protected remote access steps in [Deployment](deployment.md) before starting the auth profile.

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
PIXIV_AUTH_BROWSER_VNC_PASSWORD
```

## Schedule Timezones and Outcomes

New calendar schedules default to the browser's IANA timezone, with an editable timezone field. For example `09:00` in `Asia/Tokyo` is `00:00Z`. Daily, weekly and monthly schedules use local calendar arithmetic and persist execution instants in UTC. An existing schedule without a timezone retains UTC; editing it defaults to UTC until you deliberately choose another timezone. Interval schedules measure elapsed UTC duration.

During daylight-saving transitions, an absent local time moves forward through the gap; a repeated local time runs at its first occurrence only. Weekly day values use ISO Monday=1 through Sunday=7; a monthly day beyond month length is clamped to the last day.

`last_run_at` records dispatch and `last_success_at` advances only after a completed workflow. Partial, failed and cancelled executions record an error without claiming success. Startup execution requires `run_after_startup=true`; omitted advanced-workflow flags remain false, and explicit legacy startup flags are preserved. Dispatch exceptions advance the next interval and persist the error, while executor infrastructure errors are retried and reflected in health.

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
