from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.schemas.workflows import (
    WorkflowBatchItemRequest,
    WorkflowBatchRunListResponse,
    WorkflowBatchRunRequest,
    WorkflowBatchRunResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    workflow_run_response,
)
from backend.services.workflow_run_service import WorkflowRunService

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
    return workflow_run_response(run)
