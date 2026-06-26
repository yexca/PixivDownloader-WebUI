# Getting Started

PixivDownloader-SQLite is a local Pixiv artwork backup and management tool. The maintained UI is a browser-based WebUI served by a FastAPI backend.

## Recommended Path

Use Docker Compose for normal local use:

```bat
docker compose up -d
```

Open:

```text
http://127.0.0.1:7653
```

The default Compose startup only runs the WebUI. When Pixiv browser authentication is needed, the Settings page prompts you to start the auth sidecar:

```bat
docker compose --profile auth up -d pixiv-auth-browser
```

Pixiv browser authentication is then available through noVNC:

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

After the token is configured and tested, the Settings page prompts you to stop the auth sidecar:

```bat
docker compose stop pixiv-auth-browser
```

Stop:

```bat
docker compose down
```

## Prerequisites

For Docker Compose:

- Docker Desktop or another Docker engine with Compose support.
- A Pixiv account. The WebUI can help retrieve and save a Pixiv `refresh_token`.

For the Windows script workflow:

- Windows.
- Internet access for Python, frontend, and Pixiv dependencies.
- Node.js LTS on `PATH` for frontend installation and build.

`run-install.bat` installs Miniconda if needed and creates the local Python environment under `env/`. It does not use global Python.

## Windows Script Install

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

## Run The WebUI With Scripts

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
- Pixiv authentication. In Docker Compose, use **Sign in with Pixiv**. If the auth sidecar is stopped, the WebUI shows the command to start it, then opens the noVNC browser. In the script runtime, paste a callback URL, authorization code, or known Pixiv `refresh_token` if browser sidecar authentication is not configured.
- Request delay options.
- Existing file behavior.

The WebUI masks the refresh token in normal API responses. The full token should not appear in logs.

## Start A Download

Open the Download page and choose one input mode:

- Pixiv user ID.
- Pixiv artwork ID.

The backend creates a job, runs downloads in the background, writes progress into SQLite, and streams updates to the WebUI.

## Legacy PyQt Archive

The old PyQt desktop application is archived under `legacy/pyqt/`. It is kept for historical reference only and is not part of the maintained runtime.
