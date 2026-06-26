from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from backend.services.pixiv_browser_auth import PixivBrowserAuthStore
from backend.services.pixiv_oauth import PixivOAuthFlowStore
from backend.workers.job_queue import JobQueue
from backend.workers.scheduled_task_runner import ScheduledTaskRunner


def get_db_path(request: Request) -> Path | None:
    return request.app.state.db_path


def get_settings_json_path(request: Request) -> Path | None:
    return request.app.state.settings_json_path


def get_job_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


def get_scheduled_task_runner(request: Request) -> ScheduledTaskRunner:
    return request.app.state.scheduled_task_runner


def get_pixiv_oauth_flow_store(request: Request) -> PixivOAuthFlowStore:
    return request.app.state.pixiv_oauth_flow_store


def get_pixiv_browser_auth_store(request: Request) -> PixivBrowserAuthStore:
    return request.app.state.pixiv_browser_auth_store


DbPath = Annotated[Path | None, Depends(get_db_path)]
SettingsJsonPath = Annotated[Path | None, Depends(get_settings_json_path)]
Queue = Annotated[JobQueue, Depends(get_job_queue)]
Scheduler = Annotated[ScheduledTaskRunner, Depends(get_scheduled_task_runner)]
PixivOAuthStore = Annotated[PixivOAuthFlowStore, Depends(get_pixiv_oauth_flow_store)]
PixivBrowserAuthStoreDep = Annotated[
    PixivBrowserAuthStore,
    Depends(get_pixiv_browser_auth_store),
]
