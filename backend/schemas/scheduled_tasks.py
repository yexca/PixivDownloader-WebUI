from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.entities import ScheduledTask
from backend.domain.types import ScheduledTaskAction, ScheduledTaskStatus


class ScheduledTaskCreateRequest(BaseModel):
    name: str = ""
    action: ScheduledTaskAction
    target_artist_id: str = Field(min_length=1)
    interval_days: int = Field(ge=1)
    enabled: bool = True
    run_after_startup: bool = True


class ScheduledTaskUpdateRequest(BaseModel):
    name: str | None = None
    action: ScheduledTaskAction | None = None
    status: ScheduledTaskStatus | None = None
    target_artist_id: str | None = Field(default=None, min_length=1)
    interval_days: int | None = Field(default=None, ge=1)
    run_after_startup: bool | None = None


class ScheduledTaskResponse(BaseModel):
    id: int
    name: str
    action: str
    status: str
    target_artist_id: str
    interval_days: int
    run_after_startup: bool
    last_run_at: str | None
    last_success_at: str | None
    next_run_at: str | None
    last_job_id: str | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: str | None
    updated_at: str | None


class ScheduledTaskListResponse(BaseModel):
    items: list[ScheduledTaskResponse]
    total: int


class ScheduledTaskRunResponse(BaseModel):
    task: ScheduledTaskResponse
    job_id: str | None
    created: bool
    skipped: bool


def scheduled_task_response(task: ScheduledTask) -> ScheduledTaskResponse:
    if task.id is None:
        raise ValueError("scheduled task id is required")
    return ScheduledTaskResponse(
        id=task.id,
        name=task.name,
        action=task.action,
        status=task.status,
        target_artist_id=task.target_artist_id,
        interval_days=task.interval_days,
        run_after_startup=task.run_after_startup,
        last_run_at=task.last_run_at,
        last_success_at=task.last_success_at,
        next_run_at=task.next_run_at,
        last_job_id=task.last_job_id,
        last_error_code=task.last_error_code,
        last_error_message=task.last_error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
