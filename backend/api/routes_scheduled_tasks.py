from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, Queue, Scheduler, SettingsJsonPath
from backend.core.errors import JobNotFoundError
from backend.schemas.scheduled_tasks import (
    ScheduledTaskCreateRequest,
    ScheduledTaskListResponse,
    ScheduledTaskResponse,
    ScheduledTaskRunResponse,
    ScheduledTaskUpdateRequest,
    scheduled_task_config_from_request,
    scheduled_task_response,
)
from backend.services.scheduled_task_service import ScheduledTaskService

router = APIRouter(prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])


@router.get("", response_model=ScheduledTaskListResponse)
def list_scheduled_tasks(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> ScheduledTaskListResponse:
    service = ScheduledTaskService(db_path, settings_json_path=settings_json_path)
    try:
        tasks = service.list_tasks()
        return ScheduledTaskListResponse(
            items=[scheduled_task_response(task) for task in tasks],
            total=len(tasks),
        )
    finally:
        service.close()


@router.post("", response_model=ScheduledTaskResponse)
def create_scheduled_task(
    request: ScheduledTaskCreateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    scheduler: Scheduler,
    queue: Queue,
) -> ScheduledTaskResponse:
    service = ScheduledTaskService(db_path, settings_json_path=settings_json_path)
    config = (
        scheduled_task_config_from_request(request.config)
        if request.config is not None
        else None
    )
    action = request.action or (config.actions[0] if config is not None else "download_artist")
    target_artist_id = request.target_artist_id or (
        config.target.artist_id if config is not None and config.target.artist_id else ""
    )
    try:
        task = service.create_task(
            name=request.name,
            action=action,
            target_artist_id=target_artist_id,
            interval_days=request.interval_days,
            enabled=request.enabled,
            run_after_startup=request.run_after_startup,
            config=config,
        )
    finally:
        service.close()
    scheduler.wake()
    queue.wake()
    return scheduled_task_response(task)


@router.put("/{task_id}", response_model=ScheduledTaskResponse)
def update_scheduled_task(
    task_id: int,
    request: ScheduledTaskUpdateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> ScheduledTaskResponse:
    service = ScheduledTaskService(db_path, settings_json_path=settings_json_path)
    config = (
        scheduled_task_config_from_request(request.config)
        if request.config is not None
        else None
    )
    try:
        task = service.update_task(
            task_id,
            name=request.name,
            action=request.action,
            status=request.status,
            target_artist_id=request.target_artist_id,
            interval_days=request.interval_days,
            run_after_startup=request.run_after_startup,
            config=config,
        )
        if task is None:
            raise JobNotFoundError(f"scheduled task {task_id} was not found")
        return scheduled_task_response(task)
    finally:
        service.close()


@router.post("/{task_id}/run", response_model=ScheduledTaskRunResponse)
def run_scheduled_task(
    task_id: int,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> ScheduledTaskRunResponse:
    service = ScheduledTaskService(db_path, settings_json_path=settings_json_path)
    try:
        result = service.run_task(task_id, manual=True)
    finally:
        service.close()
    if result.created:
        queue.wake()
    return ScheduledTaskRunResponse(
        task=scheduled_task_response(result.task),
        job_id=result.job.id if result.job is not None else None,
        job_ids=[job.id for job in result.jobs],
        created=result.created,
        skipped=result.skipped,
    )


@router.delete("/{task_id}", status_code=204)
def delete_scheduled_task(
    task_id: int,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> None:
    service = ScheduledTaskService(db_path, settings_json_path=settings_json_path)
    try:
        if not service.delete_task(task_id):
            raise JobNotFoundError(f"scheduled task {task_id} was not found")
    finally:
        service.close()
