from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, Queue, Scheduler, SettingsJsonPath
from backend.core.errors import JobNotFoundError
from backend.schemas.workflow_triggers import (
    WorkflowTriggerCreateRequest,
    WorkflowTriggerListResponse,
    WorkflowTriggerResponse,
    WorkflowTriggerRunResponse,
    WorkflowTriggerUpdateRequest,
    workflow_trigger_config_from_request,
    workflow_trigger_runtime_response,
)
from backend.services.workflow_trigger_facade_service import WorkflowTriggerFacadeService

router = APIRouter(prefix="/api/workflows/triggers", tags=["workflows"])


@router.get("", response_model=WorkflowTriggerListResponse)
def list_workflow_triggers(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> WorkflowTriggerListResponse:
    service = WorkflowTriggerFacadeService(db_path, settings_json_path=settings_json_path)
    try:
        triggers = service.list_triggers()
        return WorkflowTriggerListResponse(
            items=[workflow_trigger_runtime_response(trigger) for trigger in triggers],
            total=len(triggers),
        )
    finally:
        service.close()


@router.post("", response_model=WorkflowTriggerResponse)
def create_workflow_trigger(
    request: WorkflowTriggerCreateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    scheduler: Scheduler,
    queue: Queue,
) -> WorkflowTriggerResponse:
    service = WorkflowTriggerFacadeService(db_path, settings_json_path=settings_json_path)
    config = (
        workflow_trigger_config_from_request(request.config)
        if request.config is not None
        else None
    )
    action = request.action or (config.actions[0] if config is not None else "download_artist")
    target_artist_id = request.target_artist_id or (
        config.target.artist_id if config is not None and config.target.artist_id else ""
    )
    try:
        trigger = service.create_trigger(
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
    return workflow_trigger_runtime_response(trigger)


@router.put("/{trigger_id}", response_model=WorkflowTriggerResponse)
def update_workflow_trigger(
    trigger_id: int,
    request: WorkflowTriggerUpdateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    scheduler: Scheduler,
) -> WorkflowTriggerResponse:
    service = WorkflowTriggerFacadeService(db_path, settings_json_path=settings_json_path)
    config = (
        workflow_trigger_config_from_request(request.config)
        if request.config is not None
        else None
    )
    try:
        trigger = service.update_trigger(
            trigger_id,
            name=request.name,
            action=request.action,
            status=request.status,
            target_artist_id=request.target_artist_id,
            interval_days=request.interval_days,
            run_after_startup=request.run_after_startup,
            config=config,
        )
        if trigger is None:
            raise JobNotFoundError(f"workflow trigger {trigger_id} was not found")
        scheduler.wake()
        return workflow_trigger_runtime_response(trigger)
    finally:
        service.close()


@router.post("/{trigger_id}/run", response_model=WorkflowTriggerRunResponse)
def run_workflow_trigger(
    trigger_id: int,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowTriggerRunResponse:
    service = WorkflowTriggerFacadeService(db_path, settings_json_path=settings_json_path)
    try:
        result = service.run_trigger(trigger_id, manual=True)
    finally:
        service.close()
    if result.created:
        queue.wake()
    return WorkflowTriggerRunResponse(
        trigger=workflow_trigger_runtime_response(result.trigger),
        job_id=result.job.id if result.job is not None else None,
        job_ids=[job.id for job in result.jobs],
        workflow_run_id=result.workflow_run_id,
        created=result.created,
        skipped=result.skipped,
    )


@router.delete("/{trigger_id}", status_code=204)
def delete_workflow_trigger(
    trigger_id: int,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    scheduler: Scheduler,
) -> None:
    service = WorkflowTriggerFacadeService(db_path, settings_json_path=settings_json_path)
    try:
        if not service.delete_trigger(trigger_id):
            raise JobNotFoundError(f"workflow trigger {trigger_id} was not found")
        scheduler.wake()
    finally:
        service.close()
