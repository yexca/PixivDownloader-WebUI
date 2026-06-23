from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from backend.api.dependencies import DbPath
from backend.repositories.job_repository import JobRepository
from backend.schemas.jobs import JobEventResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/recent", response_model=list[JobEventResponse])
def recent_logs(
    db_path: DbPath,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[JobEventResponse]:
    repository = JobRepository(db_path)
    try:
        return [
            JobEventResponse(
                id=event.id,
                job_id=event.job_id,
                level=event.level,
                message=event.message,
                payload=event.payload,
                created_at=event.created_at,
            )
            for event in repository.list_recent_events(limit=limit)
        ]
    finally:
        repository.close()
