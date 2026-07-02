from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.schemas.workflows import (
    AdvancedWorkflowRunRequest,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionSaveRequest,
    WorkflowDefinitionSaveResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowTriggerResponse,
    WorkflowTriggerUpdateRequest,
    workflow_definition_response,
    workflow_run_response,
    workflow_trigger_response,
)
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.workflow_read_service import WorkflowReadService
from backend.services.workflow_schedule_service import WorkflowScheduleService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("/advanced/runs", response_model=WorkflowRunResponse)
def create_advanced_workflow_run(
    request: AdvancedWorkflowRunRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowRunResponse:
    runner = AdvancedWorkflowRunner(db_path, settings_json_path=settings_json_path)
    try:
        run = runner.create_run(request.definition)
    finally:
        runner.close()
    if any(node.job_ids for node in run.node_runs):
        queue.wake()
    return workflow_run_response(run)


@router.get("/definitions", response_model=WorkflowDefinitionListResponse)
def list_workflow_definitions(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> WorkflowDefinitionListResponse:
    _ = settings_json_path
    service = WorkflowScheduleService(db_path)
    try:
        items = service.list_definitions()
    finally:
        service.close()
    return WorkflowDefinitionListResponse(
        items=[workflow_definition_response(item) for item in items],
        total=len(items),
    )


@router.post("/definitions", response_model=WorkflowDefinitionSaveResponse)
def save_workflow_definition(
    request: WorkflowDefinitionSaveRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowDefinitionSaveResponse:
    service = WorkflowScheduleService(db_path, settings_json_path=settings_json_path)
    try:
        trigger = None
        if request.trigger is None:
            definition = service.save_definition(
                request.definition,
                definition_id=request.definition_id,
            )
        else:
            definition, trigger = service.save_with_trigger(
                request.definition,
                definition_id=request.definition_id,
                trigger_id=request.trigger.trigger_id,
                enabled=request.trigger.enabled,
                schedule=request.trigger.schedule,
            )
        run = (
            service.run_definition(
                definition.id,
                source="advanced_manual",
                trigger_id=trigger.id if trigger is not None else None,
            )
            if request.trigger is not None and request.trigger.run_now
            else None
        )
    finally:
        service.close()
    if run is not None and any(node.job_ids for node in run.node_runs):
        queue.wake()
    return WorkflowDefinitionSaveResponse(
        definition=workflow_definition_response(definition),
        trigger=workflow_trigger_response(trigger) if trigger is not None else None,
        run=workflow_run_response(run) if run is not None else None,
    )


@router.put("/definition-triggers/{trigger_id}", response_model=WorkflowTriggerResponse)
def update_definition_trigger(
    trigger_id: int,
    request: WorkflowTriggerUpdateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> WorkflowTriggerResponse:
    _ = settings_json_path
    if request.status is None:
        raise HTTPException(status_code=400, detail="No trigger update fields provided")
    service = WorkflowScheduleService(db_path)
    try:
        try:
            trigger = service.update_trigger_status(trigger_id, status=request.status)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        service.close()
    return workflow_trigger_response(trigger)


@router.delete("/definitions/{definition_id}", status_code=204)
def delete_workflow_definition(
    definition_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> None:
    _ = settings_json_path
    service = WorkflowScheduleService(db_path)
    try:
        if not service.delete_definition(definition_id):
            raise HTTPException(status_code=404, detail="Workflow definition not found")
    finally:
        service.close()


@router.post("/definitions/{definition_id}/run", response_model=WorkflowRunResponse)
def run_workflow_definition(
    definition_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowRunResponse:
    service = WorkflowScheduleService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_definition(definition_id, source="advanced_manual")
    finally:
        service.close()
    if any(node.job_ids for node in run.node_runs):
        queue.wake()
    return workflow_run_response(run)


@router.get("/runs", response_model=WorkflowRunListResponse)
def list_workflow_runs(
    db_path: DbPath,
    limit: int = Query(default=5, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> WorkflowRunListResponse:
    service = WorkflowReadService(db_path)
    try:
        runs, total = service.list_runs(limit=limit, offset=offset)
    finally:
        service.close()
    return WorkflowRunListResponse(
        items=[workflow_run_response(run) for run in runs],
        total=total,
    )


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
def get_workflow_run(run_id: str, db_path: DbPath) -> WorkflowRunResponse:
    service = WorkflowReadService(db_path)
    try:
        run = service.get_run(run_id)
    finally:
        service.close()
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return workflow_run_response(run)
