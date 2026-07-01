from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.core.errors import JobNotFoundError
from backend.domain.entities import Job
from backend.domain.types import JobStatus
from backend.repositories.job_repository import JobRepository
from backend.schemas.jobs import (
    JobActionResponse,
    JobBulkActionError,
    JobBulkCancelRequest,
    JobBulkCancelResponse,
    JobCancelResponse,
    JobDetailResponse,
    JobEventResponse,
    JobListResponse,
    JobQueueStateResponse,
    JobStreamMessage,
    job_event_response,
    job_response,
)
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@router.get("", response_model=JobListResponse)
def list_jobs(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobListResponse:
    service = JobService(db_path, settings_json_path=settings_json_path)
    try:
        jobs, total = service.list_jobs(status=status, limit=limit, offset=offset)
        return JobListResponse(
            items=[job_response(job, related_jobs=service.list_child_jobs(job.id)) for job in jobs],
            total=total,
        )
    finally:
        service.close()


@router.get("/queue", response_model=JobQueueStateResponse)
def get_queue_state(queue: Queue) -> JobQueueStateResponse:
    return JobQueueStateResponse(paused=bool(getattr(queue, "paused", False)))


@router.post("/queue/pause", response_model=JobQueueStateResponse)
def pause_queue(queue: Queue) -> JobQueueStateResponse:
    if hasattr(queue, "pause"):
        queue.pause()
    return JobQueueStateResponse(paused=bool(getattr(queue, "paused", False)))


@router.post("/queue/resume", response_model=JobQueueStateResponse)
def resume_queue(queue: Queue) -> JobQueueStateResponse:
    if hasattr(queue, "resume"):
        queue.resume()
    else:
        queue.wake()
    return JobQueueStateResponse(paused=bool(getattr(queue, "paused", False)))


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(
    job_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> JobDetailResponse:
    service = JobService(db_path, settings_json_path=settings_json_path)
    try:
        job = service.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"job {job_id} was not found")
        return JobDetailResponse(
            **job_response(job, related_jobs=service.list_child_jobs(job_id)).model_dump(),
            events=[job_event_response(event) for event in service.list_events(job_id)],
        )
    finally:
        service.close()


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
def cancel_job(job_id: str, db_path: DbPath, queue: Queue) -> JobCancelResponse:
    service = JobService(db_path)
    try:
        job = service.cancel_job(job_id)
        if job is None:
            raise JobNotFoundError(f"job {job_id} was not found")
    finally:
        service.close()
    queue.wake()
    return JobCancelResponse(
        job_id=job.id,
        status=job.status,
        cancel_requested=job.cancel_requested,
    )


@router.post("/{job_id}/retry", response_model=JobActionResponse)
def retry_job(
    job_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> JobActionResponse:
    job = run_job_action_workflow(
        job_id,
        action="retry",
        db_path=db_path,
        settings_json_path=settings_json_path,
    )
    queue.wake()
    return JobActionResponse(
        job_id=job.id,
        status=job.status,
        source_job_id=job_id,
        action=str(job.options.get("job_action", "retry")),
    )


@router.post("/{job_id}/rerun", response_model=JobActionResponse)
def rerun_job(
    job_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> JobActionResponse:
    job = run_job_action_workflow(
        job_id,
        action="rerun",
        db_path=db_path,
        settings_json_path=settings_json_path,
    )
    queue.wake()
    return JobActionResponse(
        job_id=job.id,
        status=job.status,
        source_job_id=job_id,
        action="rerun",
    )


def run_job_action_workflow(
    job_id: str,
    *,
    action: str,
    db_path,
    settings_json_path,
) -> Job:
    title = "Retry job" if action == "retry" else "Rerun job"
    runner = AdvancedWorkflowRunner(db_path, settings_json_path=settings_json_path)
    try:
        run = runner.create_run(
            AdvancedWorkflowDefinitionRequest.model_validate(
                {
                    "name": title,
                    "nodes": [
                        {
                            "id": "job_action",
                            "type": "job_action",
                            "title": title,
                            "config": {
                                "source_job_id": job_id,
                                "action": action,
                            },
                        }
                    ],
                }
            ),
            source=f"job_{action}",
        )
    finally:
        runner.close()
    if not run.node_runs or not run.node_runs[0].job_ids:
        raise JobNotFoundError(f"job {job_id} was not found")
    repository = JobRepository(db_path)
    try:
        job = repository.get_by_id(run.node_runs[0].job_ids[0])
    finally:
        repository.close()
    if job is None:
        raise JobNotFoundError(f"job {job_id} was not found")
    return job


@router.post("/bulk-cancel", response_model=JobBulkCancelResponse)
def bulk_cancel_jobs(
    request: JobBulkCancelRequest,
    db_path: DbPath,
    queue: Queue,
) -> JobBulkCancelResponse:
    service = JobService(db_path)
    try:
        cancelled, errors = service.cancel_jobs(request.job_ids)
    finally:
        service.close()
    queue.wake()
    return JobBulkCancelResponse(
        cancelled=[
            JobCancelResponse(
                job_id=job.id,
                status=job.status,
                cancel_requested=job.cancel_requested,
            )
            for job in cancelled
        ],
        errors=[JobBulkActionError(**error) for error in errors],
    )


@router.get("/{job_id}/events", response_model=list[JobEventResponse])
def list_job_events(job_id: str, db_path: DbPath) -> list[JobEventResponse]:
    service = JobService(db_path)
    try:
        if service.get_job(job_id) is None:
            raise JobNotFoundError(f"job {job_id} was not found")
        return [job_event_response(event) for event in service.list_events(job_id)]
    finally:
        service.close()


@router.websocket("/{job_id}/stream")
async def stream_job(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    db_path = websocket.app.state.db_path
    last_event_id = 0
    try:
        while True:
            service = JobService(db_path)
            try:
                job = service.get_job(job_id)
                if job is None:
                    await websocket.close(code=1008, reason="job not found")
                    return
                events = service.list_events(job_id)
            finally:
                service.close()

            latest_event = next((event for event in reversed(events) if event.id), None)
            message = latest_event.message if latest_event is not None else "Current job state"
            created_at = latest_event.created_at if latest_event is not None else job.created_at
            event_id = latest_event.id or last_event_id
            if event_id != last_event_id:
                last_event_id = event_id
                await websocket.send_json(
                    JobStreamMessage(
                        type=stream_type(job.status, latest_event is not None),
                        job_id=job.id,
                        status=job.status,
                        total_files=job.total_files,
                        completed_files=job.completed_files,
                        skipped_files=job.skipped_files,
                        failed_files=job.failed_files,
                        message=message,
                        created_at=created_at,
                    ).model_dump()
                )
            if job.status in TERMINAL_STATUSES:
                await websocket.close(code=1000)
                return
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return


def stream_type(status: str, has_event: bool) -> str:
    if status == "completed":
        return "job_completed"
    if status == "failed":
        return "job_failed"
    if status == "cancelled":
        return "job_cancelled"
    return "job_event" if has_event else "job_progress"
