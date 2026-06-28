from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.types import FailureReason
from backend.repositories.workflow_run_repository import WorkflowRun, WorkflowRunItem
from backend.schemas.failure_reasons import classify_failure_reason
from backend.schemas.scheduled_tasks import ScheduledTaskConfigRequest


class WorkflowRunRequest(BaseModel):
    config: ScheduledTaskConfigRequest


class WorkflowRunResponse(BaseModel):
    job_ids: list[str]
    created: bool


class WorkflowBatchItemRequest(BaseModel):
    draft_id: str
    title: str
    config: ScheduledTaskConfigRequest
    skip_if_last_run_failed: bool = False
    schedule: bool = False
    name: str = ""
    interval_days: int = Field(default=30, ge=1)
    enabled: bool = True
    run_after_startup: bool = True


class WorkflowBatchRunRequest(BaseModel):
    concurrency: int = Field(default=1, ge=1, le=6)
    items: list[WorkflowBatchItemRequest] = Field(default_factory=list)


class WorkflowRunItemResponse(BaseModel):
    id: int | None
    run_id: str
    draft_id: str
    title: str
    status: str
    job_ids: list[str]
    error_message: str | None
    failure_reason: FailureReason
    config: dict[str, object]
    request: dict[str, object]
    created_at: str | None
    finished_at: str | None


class WorkflowBatchRunResponse(BaseModel):
    id: str
    status: str
    total: int
    completed: int
    failed: int
    skipped: int
    concurrency: int
    source: str
    schedule_id: int | None
    failure_reason: FailureReason
    created_at: str | None
    finished_at: str | None
    items: list[WorkflowRunItemResponse]


class WorkflowBatchRunListResponse(BaseModel):
    items: list[WorkflowBatchRunResponse]
    total: int


def workflow_run_response(run: WorkflowRun) -> WorkflowBatchRunResponse:
    items = [workflow_run_item_response(item) for item in run.items]
    return WorkflowBatchRunResponse(
        id=run.id,
        status=run.status,
        total=run.total,
        completed=run.completed,
        failed=run.failed,
        skipped=run.skipped,
        concurrency=run.concurrency,
        source=run.source,
        schedule_id=run.schedule_id,
        failure_reason=workflow_run_failure_reason(run, items),
        created_at=run.created_at,
        finished_at=run.finished_at,
        items=items,
    )


def workflow_run_item_response(item: WorkflowRunItem) -> WorkflowRunItemResponse:
    return WorkflowRunItemResponse(
        id=item.id,
        run_id=item.run_id,
        draft_id=item.draft_id,
        title=item.title,
        status=item.status,
        job_ids=item.job_ids,
        error_message=item.error_message,
        failure_reason=classify_failure_reason(
            item.error_message,
            item.status if item.status == "failed" else None,
        ),
        config=item.config,
        request=item.request,
        created_at=item.created_at,
        finished_at=item.finished_at,
    )


def workflow_run_failure_reason(
    run: WorkflowRun,
    items: list[WorkflowRunItemResponse],
) -> FailureReason:
    if run.status not in {"failed", "partial"}:
        return "unknown"
    for item in items:
        if item.status == "failed" and item.failure_reason != "unknown":
            return item.failure_reason
    return classify_failure_reason(
        *(item.error_message for item in items if item.status == "failed"),
        run.status,
    )
