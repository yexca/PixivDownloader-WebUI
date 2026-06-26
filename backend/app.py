from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from backend.api import (
    routes_artists,
    routes_artwork_files,
    routes_downloads,
    routes_health,
    routes_imports,
    routes_jobs,
    routes_logs,
    routes_scheduled_tasks,
    routes_settings,
)
from backend.core.errors import (
    ConfigError,
    DatabaseError,
    InsufficientDiskSpaceError,
    JobNotCancellableError,
    JobNotFoundError,
    PixivApiError,
    PixivAuthError,
)
from backend.core.paths import project_root
from backend.db.migrate import migrate_database
from backend.services.pixiv_browser_auth import PixivBrowserAuthStore
from backend.services.pixiv_oauth import PixivOAuthFlowStore
from backend.workers.job_queue import JobQueue
from backend.workers.scheduled_task_runner import ScheduledTaskRunner

logger = logging.getLogger(__name__)


def create_app(
    *,
    db_path: Path | str | None = None,
    settings_json_path: Path | str | None = None,
    start_queue: bool = True,
    job_queue: JobQueue | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        migrate_database(db_path, settings_json_path=settings_json_path)
        queue = app.state.job_queue
        scheduler = app.state.scheduled_task_runner
        if start_queue:
            await queue.start()
            await scheduler.start()
        try:
            yield
        finally:
            if start_queue:
                await scheduler.stop()
                await queue.stop()

    app = FastAPI(title="PixivDownloader API", version="0.2.0", lifespan=lifespan)
    app.state.db_path = Path(db_path) if db_path is not None else None
    app.state.settings_json_path = (
        Path(settings_json_path) if settings_json_path is not None else None
    )
    app.state.job_queue = job_queue or JobQueue(
        db_path=db_path,
        settings_json_path=settings_json_path,
    )
    app.state.scheduled_task_runner = ScheduledTaskRunner(
        db_path=db_path,
        settings_json_path=settings_json_path,
        queue=app.state.job_queue,
    )
    app.state.pixiv_oauth_flow_store = PixivOAuthFlowStore()
    app.state.pixiv_browser_auth_store = PixivBrowserAuthStore()
    app.include_router(routes_health.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_downloads.router)
    app.include_router(routes_imports.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_scheduled_tasks.router)
    app.include_router(routes_artists.router)
    app.include_router(routes_artwork_files.router)
    app.include_router(routes_logs.router)
    register_exception_handlers(app)
    register_frontend_routes(app)
    return app


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            "validation_error",
            "Request validation failed.",
            status_code=422,
            details={"errors": exc.errors()},
        )

    @app.exception_handler(ConfigError)
    async def config_exception_handler(_request: Request, exc: ConfigError) -> JSONResponse:
        return error_response("config_error", str(exc), status_code=400)

    @app.exception_handler(PixivAuthError)
    async def pixiv_auth_exception_handler(_request: Request, exc: PixivAuthError) -> JSONResponse:
        return error_response("pixiv_auth_failed", str(exc), status_code=401)

    @app.exception_handler(PixivApiError)
    async def pixiv_api_exception_handler(_request: Request, exc: PixivApiError) -> JSONResponse:
        return error_response("pixiv_api_error", str(exc), status_code=502)

    @app.exception_handler(DatabaseError)
    async def database_exception_handler(_request: Request, exc: DatabaseError) -> JSONResponse:
        return error_response("database_error", str(exc), status_code=500)

    @app.exception_handler(InsufficientDiskSpaceError)
    async def disk_space_exception_handler(
        _request: Request,
        exc: InsufficientDiskSpaceError,
    ) -> JSONResponse:
        return error_response("insufficient_disk_space", str(exc), status_code=409)

    @app.exception_handler(JobNotFoundError)
    async def job_not_found_exception_handler(
        _request: Request,
        exc: JobNotFoundError,
    ) -> JSONResponse:
        return error_response("job_not_found", str(exc), status_code=404)

    @app.exception_handler(JobNotCancellableError)
    async def job_not_cancellable_exception_handler(
        _request: Request,
        exc: JobNotCancellableError,
    ) -> JSONResponse:
        return error_response("job_not_cancellable", str(exc), status_code=409)

    @app.exception_handler(Exception)
    async def internal_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
        logger.exception("Unhandled backend error")
        return error_response("internal_error", "Internal backend error.", status_code=500)


def error_response(
    code: str,
    message: str,
    *,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def register_frontend_routes(app: FastAPI) -> None:
    frontend_dist = project_root() / "frontend" / "dist"
    index_file = frontend_dist / "index.html"
    if not index_file.is_file():
        return

    @app.get("/resources/icon.ico", include_in_schema=False)
    def serve_icon() -> FileResponse:
        return FileResponse(project_root() / "resources" / "icon.ico")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="api route not found")
        requested_path = (frontend_dist / full_path).resolve()
        if (
            full_path
            and requested_path.is_file()
            and frontend_dist.resolve() in requested_path.parents
        ):
            return FileResponse(requested_path)
        return FileResponse(index_file)


def main() -> None:
    host = os.environ.get("PIXIVDOWNLOADER_HOST", "127.0.0.1")
    port = int(os.environ.get("PIXIVDOWNLOADER_PORT", "7653"))
    uvicorn.run("backend.app:create_app", factory=True, host=host, port=port)


if __name__ == "__main__":
    main()
