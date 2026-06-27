from __future__ import annotations

from pydantic import BaseModel

from backend.schemas.scheduled_tasks import ScheduledTaskConfigRequest


class WorkflowRunRequest(BaseModel):
    config: ScheduledTaskConfigRequest


class WorkflowRunResponse(BaseModel):
    job_ids: list[str]
    created: bool
