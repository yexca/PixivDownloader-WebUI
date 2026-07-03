# PixivDownloader WebUI

> Languages: [English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

PixivDownloader WebUI is a local-first browser interface for Pixiv artwork backup, workflow automation, and library management. It runs a FastAPI backend, serves a React + TypeScript frontend, and stores metadata, jobs, workflow runs, and file status in a local SQLite database.

This repository contains the maintained WebUI for PixivDownloader. It supports importing `pixiv.db` databases created by [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite), but that source project is not bundled here.

## Features

- Dashboard for workflow runs, trigger health, queue pressure, and library attention states.
- Reusable workflow definitions with manual runs and scheduled triggers.
- Shortcut downloads by Pixiv artist ID or artwork ID.
- Library, artist detail, artwork file status, local tags, retry, sync, and delete actions.
- Queue controls, job retry/rerun/cancel, bulk cancellation, and live job progress over WebSocket.
- Settings for download path, Pixiv authentication, request/file delays, concurrency, disk-space guard, existing-file behavior, library stale checks, and theme preferences.
- Optional Docker noVNC authentication sidecar for Pixiv browser login.
- Explicit database import from [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite) through Settings.
- Docker Compose runtime and local Windows script runtime.

## Recommended Runtime: Docker Compose

Start the WebUI:

```bat
docker compose up -d
```

Open:

```text
http://127.0.0.1:7653
```

The default Compose startup runs only the WebUI. When Pixiv browser authentication is needed, start the optional `pixiv-auth-browser` sidecar:

```bat
docker compose --profile auth up -d pixiv-auth-browser
```

The sidecar exposes noVNC:

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

After clicking Pixiv sign-in in WebUI Settings, complete Pixiv login in the noVNC browser. The sidecar posts the callback to the backend and the backend saves the `refresh_token` automatically.

After the token is configured and tested, stop the sidecar:

```bat
docker compose stop pixiv-auth-browser
```

Stop the WebUI:

```bat
docker compose down
```

The compose file can build `yexca/pixivdownloader:v0.2.0`, maps `7653:7653`, and mounts local `config/`, `resources/`, and `downloads/` for persistence. The `auth` profile can also build and run `yexca/pixivdownloader-auth-browser:v0.2.0`.

## Local Windows Runtime

Install from the project folder:

```bat
run-install.bat
```

Run:

```bat
run-webui.bat
```

The script checks that `env\python\python.exe` and `frontend\dist\index.html` exist, starts the backend, and opens <http://127.0.0.1:7653>.

Set `PIXIVDOWNLOADER_PORT` before running the script if you need a different local port.

## Runtime Architecture

```text
Browser WebUI
  -> FastAPI backend on http://127.0.0.1:7653
  -> workflow runs, triggers, queue, jobs, and workers
  -> SQLite database in resources/
  -> downloaded files in the configured download directory
```

Main components:

- `backend/`: FastAPI API, services, repositories, SQLite migrations, workflow runners, schedulers, and download workers.
- `frontend/`: React, TypeScript, Vite, Tailwind CSS WebUI.
- `auth-browser/`: optional Docker sidecar for Pixiv browser authentication.
- `config/`: WebUI configuration; `settings.example.json` is committed and `settings.json` stores local user settings and secrets.
- `resources/`: SQLite database, imported PixivDownloader-SQLite databases, cached assets, and static resources.
- `tools/`: maintenance helpers such as historical settings migration.
- `tests/`: backend regression tests.

## Configuration Migration

WebUI settings load defaults from:

```text
config\settings.example.json
```

Local user overrides and secrets are saved to the ignored file:

```text
config\settings.json
```

Previous `resources\conf\settings.json` is not read automatically. To migrate it explicitly:

```bat
env\python\python.exe tools\migrate_settings_to_config.py
```

Use `--overwrite` if `config\settings.json` already exists.

## Development

Backend dev server:

```bat
env\python\python.exe -m uvicorn backend.app:create_app --factory --reload --host 127.0.0.1 --port 7653
```

Frontend dev server:

```bat
cd frontend
npm run dev
```

Manual checks:

```bat
env\python\python.exe -m ruff format --check .
env\python\python.exe -m ruff check .
env\python\python.exe -m pytest
```

```bat
cd frontend
npm run lint
npm run typecheck
npm run build
```

## Documentation

- [Documentation index](docs/README.md)
- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [API Reference](docs/api-reference.md)
- [Deployment](docs/deployment.md)
- [Database](docs/database.md)
- [Development Guide](docs/development.md)
- [Verification](docs/verification.md)

## Packaging Notes

In source checkout mode, the backend resolves resources from the repository root:

- `config\settings.example.json`
- `config\settings.json`
- `resources\pixiv.sqlite3`
- `frontend\dist`

For a packaged executable, resources should be placed beside the executable with the same relative layout. The backend path resolver uses the executable directory when running from a frozen build.

## Disclaimer

This tool is intended for personal learning, research, or backup purposes only. Use it responsibly and follow Pixiv's Terms of Service. Do not use it for mass downloading or redistribution of content.
