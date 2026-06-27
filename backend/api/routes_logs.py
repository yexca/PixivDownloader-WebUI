from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from backend.api.dependencies import DbPath
from backend.repositories.job_repository import JobRepository
from backend.schemas.jobs import JobEventListResponse, JobEventResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/recent", response_model=JobEventListResponse)
def recent_logs(
    db_path: DbPath,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    level: str | None = None,
) -> JobEventListResponse:
    repository = JobRepository(db_path)
    try:
        return JobEventListResponse(
            items=[
                JobEventResponse(
                    id=event.id,
                    job_id=event.job_id,
                    level=event.level,
                    message=event.message,
                    payload=event.payload,
                    created_at=event.created_at,
                )
                for event in repository.list_recent_events(
                    level=level,
                    limit=limit,
                    offset=offset,
                )
            ],
            total=repository.count_events(level=level),
        )
    finally:
        repository.close()
