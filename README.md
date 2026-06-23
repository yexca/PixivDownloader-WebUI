# PixivDownloader-SQLite

> Languages: [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

PixivDownloader-SQLite is a Windows-first, local WebUI downloader for Pixiv artwork backup and management. It runs a FastAPI backend from the local `env` folder, serves a React + TypeScript frontend, and stores metadata in a local SQLite database.

The project was originally a PyQt6 desktop application and is being refactored into a local-first WebUI while preserving the existing SQLite data.

## Features

- Start downloads by Pixiv user ID or artwork ID.
- Manage download settings, including download path and Pixiv refresh token.
- Track jobs, progress, history, artists, artworks, and file status in SQLite.
- Migrate legacy `resources/pixiv.db` data from the old `pic` table.
- Run locally through `run-gui.bat`; no separate database server is required.

## Runtime Architecture

```text
run-gui.bat
  -> env\python.exe -m backend.app
  -> FastAPI on http://127.0.0.1:7653
  -> serves frontend\dist
  -> opens the WebUI in the browser
```

Main components:

- `backend/`: FastAPI API, services, repositories, SQLite migrations, and download workers.
- `frontend/`: React, TypeScript, Vite, Tailwind CSS WebUI.
- `resources/`: local configuration and SQLite database.
- `app/`: legacy PyQt code retained for compatibility during the transition; the WebUI is the current user-facing interface.

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

```bat
run-gui.bat
```

The script checks that `env\python.exe` and `frontend\dist\index.html` exist, starts the backend, and opens <http://127.0.0.1:7653>.

Set `PIXIVDOWNLOADER_PORT` before running the scripts if you need a different local port.

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

- [Project overview](docs/project-overview.md)
- [WebUI architecture](docs/webui-architecture.md)
- [Database migrations](docs/database-migrations.md)
- [UI verification notes](docs/ui-verification.md)

## Packaging Notes

In source checkout mode, the backend resolves resources from the repository root:

- `resources\conf\settings.json`
- `resources\pixiv.db`
- `frontend\dist`

For a packaged executable, resources should be placed beside the executable with the same relative layout. The backend path resolver uses the executable directory when running from a frozen build.

## Disclaimer

This tool is intended for personal learning, research, or backup purposes only. Use it responsibly and follow Pixiv's Terms of Service. Do not use it for mass downloading or redistribution of content.
