# Deployment

PixivDownloader-SQLite supports two local deployment paths:

- Windows scripts using a local Python environment.
- Docker Compose using the published/local-build image.

## Windows Script Runtime

Install:

```bat
run-install.bat
```

Run WebUI:

```bat
run-webui.bat
```

Run legacy PyQt GUI:

```bat
run-gui.bat
```

The script runtime uses:

- `%UserProfile%\Miniconda3` as the Miniconda installation.
- `env/` as the project-local Python environment.
- `frontend/dist` as the built WebUI.
- `config/` as the local WebUI configuration folder.
- `resources/` as the local database and resource folder.

## Docker Compose

Build:

```bat
docker compose build
```

Run:

```bat
docker compose up -d
```

Open:

```text
http://127.0.0.1:7653
```

Pixiv browser sign-in opens the authentication sidecar through noVNC:

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

Complete Pixiv login in that remote browser window. The sidecar captures the
Pixiv OAuth callback and the main backend saves the `refresh_token`
automatically.

Stop:

```bat
docker compose down
```

The compose service uses:

```yaml
image: yexca/pixivdownloader:v0.2.0
build:
  context: .
  dockerfile: Dockerfile
ports:
  - "7653:7653"
```

Compose also starts `pixiv-auth-browser`, which exposes:

```yaml
ports:
  - "6080:6080"
```

## Docker Volumes

Compose mounts:

```text
./config:/app/config
./resources:/app/resources
./downloads:/app/downloads
```

`config/` persists WebUI settings and Pixiv authentication secrets.

`resources/` persists SQLite metadata.

`downloads/` is intended for downloaded files when the container configuration points downloads there.

## Ports

Default port:

```text
7653
```

Pixiv auth browser noVNC port:

```text
6080
```

Windows scripts:

```bat
set PIXIVDOWNLOADER_PORT=8765
run-webui.bat
```

Docker Compose:

```yaml
ports:
  - "8765:7653"
environment:
  PIXIVDOWNLOADER_PORT: "7653"
```

The container should keep `PIXIVDOWNLOADER_HOST=0.0.0.0`.

## Dockerfile

The Dockerfile is multi-stage:

1. `node:22-bookworm-slim` builds `frontend/dist`.
2. `python:3.12-slim` installs the backend package and serves the built frontend.

The image entrypoint is:

```text
python -m backend.app
```

## Packaged Executable Expectations

For a future frozen executable, keep runtime resources beside the executable:

```text
release-folder/
  PixivDownloader.exe
  config/
  frontend/dist/
  resources/
```

`backend.core.paths.project_root()` uses the executable directory when `sys.frozen` is set. In source checkout mode it uses the repository root.
