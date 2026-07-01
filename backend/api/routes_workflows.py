from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.schemas.workflows import (
    AdvancedWorkflowRunRequest,
    WorkflowBatchItemRequest,
    WorkflowBatchRunListResponse,
    WorkflowBatchRunRequest,
    WorkflowBatchRunResponse,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionSaveRequest,
    WorkflowDefinitionSaveResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    workflow_definition_response,
    workflow_run_response,
    workflow_trigger_response,
)
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.workflow_run_service import WorkflowRunService
from backend.services.workflow_schedule_service import WorkflowScheduleService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("/run", response_model=WorkflowRunResponse)
def run_workflow(
    request: WorkflowRunRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowRunResponse:
    service = WorkflowRunService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_batch(
            items=[
                WorkflowBatchItemRequest(
                    draft_id="workflow-run",
                    title="Workflow run",
                    config=request.config,
                )
            ],
            concurrency=1,
        )
    finally:
        service.close()
    job_ids = [job_id for item in run.items for job_id in item.job_ids]
    if job_ids:
        queue.wake()
    return WorkflowRunResponse(job_ids=job_ids, created=bool(job_ids))


@router.post("/runs", response_model=WorkflowBatchRunResponse)
def create_workflow_run(
    request: WorkflowBatchRunRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowBatchRunResponse:
    service = WorkflowRunService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_batch(items=request.items, concurrency=request.concurrency)
    finally:
        service.close()
    if any(item.job_ids for item in run.items):
        queue.wake()
    return workflow_run_response(run)


@router.post("/advanced/runs", response_model=WorkflowBatchRunResponse)
def create_advanced_workflow_run(
    request: AdvancedWorkflowRunRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowBatchRunResponse:
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
                enabled=request.trigger.enabled,
                schedule=request.trigger.schedule,
            )
        run = (
            service.run_definition(definition.id, source="advanced_manual")
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


@router.post("/definitions/{definition_id}/run", response_model=WorkflowBatchRunResponse)
def run_workflow_definition(
    definition_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowBatchRunResponse:
    service = WorkflowScheduleService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_definition(definition_id, source="advanced_manual")
    finally:
        service.close()
    if any(node.job_ids for node in run.node_runs):
        queue.wake()
    return workflow_run_response(run)


@router.get("/runs", response_model=WorkflowBatchRunListResponse)
def list_workflow_runs(
    db_path: DbPath,
    limit: int = Query(default=5, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> WorkflowBatchRunListResponse:
    service = WorkflowRunService(db_path)
    try:
        runs, total = service.list_runs(limit=limit, offset=offset)
    finally:
        service.close()
    return WorkflowBatchRunListResponse(
        items=[workflow_run_response(run) for run in runs],
        total=total,
    )


@router.get("/runs/{run_id}", response_model=WorkflowBatchRunResponse)
def get_workflow_run(run_id: str, db_path: DbPath) -> WorkflowBatchRunResponse:
    service = WorkflowRunService(db_path)
    try:
        run = service.get_run(run_id)
    finally:
        service.close()
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run.source == "advanced":
        runner = AdvancedWorkflowRunner(db_path)
        try:
            run = runner.process_run(run.id)
        finally:
            runner.close()
    return workflow_run_response(run)
