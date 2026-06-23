from __future__ import annotations

from pydantic import BaseModel

from backend.domain.entities import Job, JobEvent


class JobResponse(BaseModel):
    id: str
    type: str
    status: str
    artist_id: str | None
    input_user_id: str | None
    input_artwork_id: str | None
    total_files: int
    completed_files: int
    skipped_files: int
    failed_files: int
    cancel_requested: bool
    created_at: str | None
    started_at: str | None
    finished_at: str | None
    error_message: str | None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


class JobEventResponse(BaseModel):
    id: int | None
    job_id: str
    level: str
    message: str
    payload: dict[str, object] | None
    created_at: str | None


class JobDetailResponse(JobResponse):
    events: list[JobEventResponse]


class JobCancelResponse(BaseModel):
    job_id: str
    status: str
    cancel_requested: bool


class JobStreamMessage(BaseModel):
    type: str
    job_id: str
    status: str
    total_files: int
    completed_files: int
    skipped_files: int
    failed_files: int
    message: str
    created_at: str | None


def job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        type=job.type,
        status=job.status,
        artist_id=job.artist_id,
        input_user_id=job.input_user_id,
        input_artwork_id=job.input_artwork_id,
        total_files=job.total_files,
        completed_files=job.completed_files,
        skipped_files=job.skipped_files,
        failed_files=job.failed_files,
        cancel_requested=job.cancel_requested,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
    )


def job_event_response(event: JobEvent) -> JobEventResponse:
    return JobEventResponse(
        id=event.id,
        job_id=event.job_id,
        level=event.level,
        message=event.message,
        payload=event.payload,
        created_at=event.created_at,
    )
