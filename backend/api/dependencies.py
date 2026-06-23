from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from backend.workers.job_queue import JobQueue


def get_db_path(request: Request) -> Path | None:
    return request.app.state.db_path


def get_settings_json_path(request: Request) -> Path | None:
    return request.app.state.settings_json_path


def get_job_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


DbPath = Annotated[Path | None, Depends(get_db_path)]
SettingsJsonPath = Annotated[Path | None, Depends(get_settings_json_path)]
Queue = Annotated[JobQueue, Depends(get_job_queue)]
