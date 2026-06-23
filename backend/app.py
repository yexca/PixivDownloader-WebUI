from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api import (
    routes_artists,
    routes_artwork_files,
    routes_downloads,
    routes_health,
    routes_jobs,
    routes_logs,
    routes_settings,
)
from backend.core.errors import ConfigError, DatabaseError, PixivApiError, PixivAuthError
from backend.db.migrate import migrate_database
from backend.workers.job_queue import JobQueue

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
        if start_queue:
            await queue.start()
        try:
            yield
        finally:
            if start_queue:
                await queue.stop()

    app = FastAPI(title="PixivDownloader API", version="1.0.0", lifespan=lifespan)
    app.state.db_path = Path(db_path) if db_path is not None else None
    app.state.settings_json_path = (
        Path(settings_json_path) if settings_json_path is not None else None
    )
    app.state.job_queue = job_queue or JobQueue(db_path=db_path)
    app.include_router(routes_health.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_downloads.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_artists.router)
    app.include_router(routes_artwork_files.router)
    app.include_router(routes_logs.router)
    register_exception_handlers(app)
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


def main() -> None:
    uvicorn.run("backend.app:create_app", factory=True, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
