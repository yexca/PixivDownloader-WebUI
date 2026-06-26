# Getting Started

PixivDownloader-SQLite is a local Pixiv artwork backup and management tool. The current primary UI is a browser-based WebUI served by a local FastAPI backend.

## Prerequisites

For the Windows script workflow:

- Windows.
- Internet access for Python, frontend, and Pixiv dependencies.
- Node.js LTS on `PATH` for frontend installation and build.
- A Pixiv account. The WebUI can help retrieve and save a Pixiv `refresh_token`.

`run-install.bat` installs Miniconda if needed and creates the local Python environment under `env/`. It does not use global Python.

For Docker Compose:

- Docker Desktop or another Docker engine with Compose support.

## Install

From the project root:

```bat
run-install.bat
```

The installer:

1. Installs Miniconda to `%UserProfile%\Miniconda3` if missing.
2. Creates `env/` in the project root.
3. Installs backend dependencies into `env/`.
4. Installs frontend dependencies with `npm`.
5. Builds frontend assets into `frontend/dist`.

## Run The WebUI

```bat
run-webui.bat
```

The script starts the backend and opens:

```text
http://127.0.0.1:7653
```

Use `PIXIVDOWNLOADER_PORT` to override the port:

```bat
set PIXIVDOWNLOADER_PORT=8765
run-webui.bat
```

## First Configuration

Open the Settings page and configure:

- Download path.
- Pixiv authentication. Use **Sign in with Pixiv** to open the Pixiv login page,
  then paste the callback URL or authorization code back into Settings. You can
  also paste a known Pixiv `refresh_token` manually.
- Request delay options.
- Existing file behavior.

The WebUI masks the refresh token in normal API responses. The full token should not appear in logs.

## Start A Download

Open the Download page and choose one input mode:

- Pixiv user ID.
- Pixiv artwork ID.

The backend creates a job, runs downloads in the background, writes progress into SQLite, and streams updates to the WebUI.

## Legacy PyQt GUI

The old PyQt desktop interface is still available:

```bat
run-gui.bat
```

New functionality should target the WebUI and backend.

## Docker Quick Start

```bat
docker compose build
docker compose up -d
```

Open:

```text
http://127.0.0.1:7653
```

Stop it with:

```bat
docker compose down
```
