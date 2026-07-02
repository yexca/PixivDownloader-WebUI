# PixivDownloader-SQLite

> Languages: [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

PixivDownloader-SQLite is a local WebUI downloader for Pixiv artwork backup and management. It runs a FastAPI backend, serves a React + TypeScript frontend, and stores metadata in a local SQLite database.

This repository contains the WebUI rewrite. It keeps migration support for old PyQt `pixiv.db` files, but the old desktop application source is not part of this project.

## Features

- Start downloads by Pixiv user ID or artwork ID.
- Manage download settings, including download path and Pixiv refresh token.
- Track jobs, progress, history, artists, artworks, and file status in SQLite.
- Import old PyQt `pixiv.db` data explicitly from WebUI Settings.
- Run the WebUI with Docker Compose or local Windows scripts.

## Recommended: Docker Compose

Start the WebUI:

```bat
docker compose up -d
```

Open:

```text
http://127.0.0.1:7653
```

Docker Compose also starts the `pixiv-auth-browser` sidecar and exposes noVNC:

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

After clicking Pixiv sign-in in WebUI Settings, complete Pixiv login in the noVNC browser. The backend captures the callback and saves the `refresh_token` automatically.

Stop:

```bat
docker compose down
```

The compose file can build `yexca/pixivdownloader:v0.2.0`, maps `7653:7653`, and mounts local `config/`, `resources/`, and `downloads/` for persistence.

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
  -> SQLite database in resources/
  -> downloaded files in the configured download directory
```

Main components:

- `backend/`: FastAPI API, services, repositories, SQLite migrations, and download workers.
- `frontend/`: React, TypeScript, Vite, Tailwind CSS WebUI.
- `auth-browser/`: Docker sidecar for Pixiv browser authentication.
- `config/`: WebUI configuration; `settings.example.json` is committed and `settings.json` stores local user settings.
- `resources/`: SQLite database and static resources.

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
- [Deployment](docs/deployment.md)
- [Database](docs/database.md)
- [Development Guide](docs/development.md)

## Packaging Notes

In source checkout mode, the backend resolves resources from the repository root:

- `config\settings.example.json`
- `config\settings.json`
- `resources\pixiv.sqlite3`
- `frontend\dist`

For a packaged executable, resources should be placed beside the executable with the same relative layout. The backend path resolver uses the executable directory when running from a frozen build.

## Disclaimer

This tool is intended for personal learning, research, or backup purposes only. Use it responsibly and follow Pixiv's Terms of Service. Do not use it for mass downloading or redistribution of content.
