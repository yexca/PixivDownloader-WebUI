from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.api.dependencies import DbPath, Queue
from backend.core.errors import JobNotFoundError
from backend.domain.types import JobStatus
from backend.schemas.jobs import (
    JobCancelResponse,
    JobDetailResponse,
    JobEventResponse,
    JobListResponse,
    JobStreamMessage,
    job_event_response,
    job_response,
)
from backend.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@router.get("", response_model=JobListResponse)
def list_jobs(
    db_path: DbPath,
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobListResponse:
    service = JobService(db_path)
    try:
        jobs, total = service.list_jobs(status=status, limit=limit, offset=offset)
        return JobListResponse(items=[job_response(job) for job in jobs], total=total)
    finally:
        service.close()


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: str, db_path: DbPath) -> JobDetailResponse:
    service = JobService(db_path)
    try:
        job = service.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"job {job_id} was not found")
        return JobDetailResponse(
            **job_response(job).model_dump(),
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
