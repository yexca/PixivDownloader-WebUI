# PixivDownloader-SQLite

> Languages: [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

PixivDownloader-SQLite is a Windows-first, local WebUI downloader for Pixiv artwork backup and management. It runs a FastAPI backend from the local `env` folder, serves a React + TypeScript frontend, and stores metadata in a local SQLite database.

The project was originally a PyQt6 desktop application and is being refactored into a local-first WebUI while preserving the existing SQLite data.

## Features

- Start downloads by Pixiv user ID or artwork ID.
- Manage download settings, including download path and Pixiv refresh token.
- Track jobs, progress, history, artists, artworks, and file status in SQLite.
- Migrate legacy `resources/pixiv.db` data from the old `pic` table.
- Run the WebUI locally through `run-webui.bat`; no separate database server is required.
- Keep the legacy PyQt desktop GUI available through `run-gui.bat`.

## Runtime Architecture

```text
run-webui.bat
  -> env\python.exe -m backend.app
  -> FastAPI on http://127.0.0.1:7653
  -> serves frontend\dist
  -> opens the WebUI in the browser
```

Main components:

- `backend/`: FastAPI API, services, repositories, SQLite migrations, and download workers.
- `frontend/`: React, TypeScript, Vite, Tailwind CSS WebUI.
- `config/`: WebUI configuration; `settings.example.json` is committed and `settings.json` stores local user settings.
- `resources/`: SQLite database and static resources.
- `app/`: legacy PyQt code available through `run-gui.bat`; the WebUI is the current user-facing interface.

## Install

Run from the project folder:

```bat
run-install.bat
```

The installer:

1. Installs Miniconda to `%UserProfile%\Miniconda3` if it is missing.
2. Creates the local `env` folder.
3. Installs Python dependencies into `env`.
4. Installs frontend dependencies with `npm`.
5. Builds frontend assets into `frontend\dist`.

The installer does not rely on global Python. Node.js is currently detected from the system PATH; install the Windows LTS version from <https://nodejs.org/> if `npm` is missing.

## Run

WebUI:

```bat
run-webui.bat
```

The script checks that `env\python.exe` and `frontend\dist\index.html` exist, starts the backend, and opens <http://127.0.0.1:7653>.

Legacy PyQt GUI:

```bat
run-gui.bat
```

The script starts the original PyQt desktop interface through `main.py`.

Set `PIXIVDOWNLOADER_PORT` before running the scripts if you need a different local port.

## Docker Compose

Run the published image on the same local port:

```bat
docker compose up -d
```

The compose file uses and can build `yexca/pixivdownloader:v0.2.0`, maps `7653:7653`, and mounts local `config/`, `resources/`, and `downloads/` for persistence.

Docker Compose also starts the `pixiv-auth-browser` sidecar and maps noVNC on `6080:6080`. After clicking Pixiv sign-in in WebUI Settings, complete Pixiv login in <http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale>; the backend captures the callback and saves the `refresh_token` automatically.

```bat
docker compose build
```

## Configuration Migration

WebUI settings now load defaults from:

```text
config\settings.example.json
```

Local user overrides and secrets are saved to ignored file:

```text
config\settings.json
```

Legacy `resources\conf\settings.json` is not read automatically. To migrate it explicitly:

```bat
env\python.exe tools\migrate_settings_to_config.py
```

Use `--overwrite` if `config\settings.json` already exists.

## Development

Backend dev server:

```bat
run-backend-dev.bat
```

Frontend dev server:

```bat
run-frontend-dev.bat
```

Manual checks:

```bat
env\python.exe -m ruff format --check .
env\python.exe -m ruff check .
env\python.exe -m pytest
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
- [Deployment](docs/deployment.md)
- [Database](docs/database.md)
- [Development Guide](docs/development.md)

## Packaging Notes

In source checkout mode, the backend resolves resources from the repository root:

- `config\settings.example.json`
- `config\settings.json`
- `resources\pixiv.db`
- `frontend\dist`

For a packaged executable, resources should be placed beside the executable with the same relative layout. The backend path resolver uses the executable directory when running from a frozen build.

## Disclaimer

This tool is intended for personal learning, research, or backup purposes only. Use it responsibly and follow Pixiv's Terms of Service. Do not use it for mass downloading or redistribution of content.
