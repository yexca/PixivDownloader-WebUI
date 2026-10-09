# Deployment

PixivDownloader WebUI is deployed primarily with Docker Compose. Windows scripts remain available for local development or users who do not want to run Docker.

The supported deployment runs one FastAPI process and one queue/scheduler against a local SQLite database. Do not use Uvicorn `--workers` or share the database between application replicas: startup recovery releases claims left by a stopped process. Downloads can run concurrently inside this process.

## Local Docker Compose

Build the current checkout, then start the WebUI:

```bat
docker compose build
docker compose up -d
```

Open `http://127.0.0.1:7653`. Compose publishes `127.0.0.1:7653:7653`; the management API does not have user authentication and must remain on a trusted local interface. The container itself listens on `0.0.0.0` so Docker networking works.

Persistent mounts are `./config:/app/config`, `./resources:/app/resources` and `./downloads:/app/downloads`. Docker downloads always use `/app/downloads`. Back up configuration and SQLite while the service is stopped before upgrading. Do not use `docker compose down -v` as an upgrade step.

```bat
docker compose stop
docker compose down
```

`down` does not remove these bind-mounted folders.

## Browser Authentication

The optional sidecar requires two locally generated secrets. Generate them in your own terminal; do not paste them into an issue or chat. For example, with the project's Python runtime:

```bat
env\python\python.exe -c "import secrets; print('PIXIV_AUTH_BROWSER_TOKEN=' + secrets.token_hex(32)); print('PIXIV_AUTH_BROWSER_VNC_PASSWORD=' + secrets.token_hex(4))"
```

Put the two output lines in a private `.env` beside `docker-compose.yaml`. `.env` is ignored by Git and excluded from the main build context. Keep file permissions restricted. The callback token must be identical for backend and sidecar; Compose supplies it to both. Traditional VNC uses only eight password characters, so the example generates exactly eight random hexadecimal characters. Its password protects the browser session; use SSH encryption for remote access.

After changing `.env`, recreate the backend so it receives the new token, then build/start the auth profile:

```bat
docker compose up -d --force-recreate pixivdownloader
docker compose --profile auth build pixiv-auth-browser
docker compose --profile auth up -d pixiv-auth-browser
```

Select **Sign in with Pixiv** in Settings and open `http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale`. Enter the VNC password, complete login, and return to Settings. The sidecar posts the captured OAuth callback to the backend over the Docker network. Port 7654 is not published. The sidecar refuses to start without its secrets; missing callback credentials leave the manual OAuth callback/token flow available.

Stop the sidecar after use:

```bat
docker compose stop pixiv-auth-browser
```

noVNC publishes `127.0.0.1:6080:6080`; x11vnc requires the password and listens only inside the sidecar on localhost. Protect browser sessions and Docker access like other local credentials.

## Protected Remote Access

Keep both Compose bindings on loopback. From your workstation, forward them through SSH to a trusted server:

```text
ssh -N -L 7653:127.0.0.1:7653 -L 6080:127.0.0.1:6080 user@server
```

Open the same localhost URLs on your workstation. SSH supplies authentication and encryption for both the WebUI and browser. If these local ports are occupied, choose different forwarded ports and set `PIXIV_AUTH_BROWSER_PUBLIC_URL` to the corresponding local browser URL. A reverse proxy deployment must authenticate all HTTP and WebSocket routes and use TLS, including noVNC; directly publishing either unauthenticated service is unsupported.

## Windows Runtime and Ports

`run-install.bat` installs Python 3.12 under `env/python`, Miniconda under `env/conda`, and Node 22.23.1 under `env/node`. `run-webui.bat` serves `frontend/dist` at localhost. Override its port with:

```bat
set PIXIVDOWNLOADER_PORT=8765
run-webui.bat
```

For Compose change only the host mapping, for example `127.0.0.1:8765:7653`. Keep the container's `PIXIVDOWNLOADER_PORT=7653` and `PIXIVDOWNLOADER_HOST=0.0.0.0`.

## Build and Operational Checks

The main multi-stage image builds the frontend with Node 22 and installs Python 3.12 dependencies using `requirements.lock` constraints. The sidecar uses its committed npm lock and `npm ci`. OS packages and base-image tags still follow upstream updates; lockfiles pin application dependencies, not entire OS images.

Use `docker compose config --quiet` to validate without printing resolved secrets. `/api/health` returns HTTP 200 for healthy executors and 503 if the queue or scheduler is stopped or reporting errors. Check service logs on 503.

Legacy database uploads are limited to 64 MiB per file and 65 MiB including multipart framing, with bounded temporary buffering before multipart parsing. OAuth exchange requests time out after 30 seconds, sidecar API calls after 10 seconds, and sidecar callback delivery after 15 seconds. Pixiv metadata connections have connect/read timeouts of 10/30 seconds; file transfer reads time out after 60 seconds. Cancellation is cooperative and may await the current bounded network read or metadata snapshot write.

## Dockerfile

1. `node:22-bookworm-slim` builds `frontend/dist`.
2. `python:3.12-slim` installs the backend package and serves the built frontend.

The image entrypoint is:

```text
python -m backend.app
```

## PixivDownloader-SQLite Database Import

`pixiv.db` imports from [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite) are handled through the WebUI Settings page. The source project is not copied into the Docker image and is not part of deployment.

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
