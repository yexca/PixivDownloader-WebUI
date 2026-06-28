from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.entities import Job, JobEvent


class RelatedJobResponse(BaseModel):
    id: str
    status: str
    action: str
    created_at: str | None


class JobResponse(BaseModel):
    id: str
    type: str
    status: str
    artist_id: str | None
    input_user_id: str | None
    input_artwork_id: str | None
    options: dict[str, object]
    workflow_run_id: str | None
    workflow_item_id: int | None
    workflow_source: str | None
    total_files: int
    completed_files: int
    skipped_files: int
    failed_files: int
    cancel_requested: bool
    created_at: str | None
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    related_jobs: list[RelatedJobResponse] = Field(default_factory=list)


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


class JobEventListResponse(BaseModel):
    items: list[JobEventResponse]
    total: int


class JobDetailResponse(JobResponse):
    events: list[JobEventResponse]


class JobCancelResponse(BaseModel):
    job_id: str
    status: str
    cancel_requested: bool


class JobActionResponse(BaseModel):
    job_id: str
    status: str
    source_job_id: str
    action: str


class JobBulkCancelRequest(BaseModel):
    job_ids: list[str]


class JobBulkActionError(BaseModel):
    job_id: str
    message: str


class JobBulkCancelResponse(BaseModel):
    cancelled: list[JobCancelResponse]
    errors: list[JobBulkActionError]


class JobQueueStateResponse(BaseModel):
    paused: bool


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


def job_response(job: Job, *, related_jobs: list[Job] | None = None) -> JobResponse:
    return JobResponse(
        id=job.id,
        type=job.type,
        status=job.status,
        artist_id=job.artist_id,
        input_user_id=job.input_user_id,
        input_artwork_id=job.input_artwork_id,
        options=job.options,
        workflow_run_id=job.workflow_run_id,
        workflow_item_id=job.workflow_item_id,
        workflow_source=job.workflow_source,
        total_files=job.total_files,
        completed_files=job.completed_files,
        skipped_files=job.skipped_files,
        failed_files=job.failed_files,
        cancel_requested=job.cancel_requested,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
        related_jobs=[related_job_response(child) for child in related_jobs or []],
    )


def related_job_response(job: Job) -> RelatedJobResponse:
    action = job.options.get("job_action", "retry")
    return RelatedJobResponse(
        id=job.id,
        status=job.status,
        action=str(action),
        created_at=job.created_at,
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
