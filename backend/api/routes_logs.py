from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from backend.api.dependencies import DbPath
from backend.db.connection import connect
from backend.repositories.job_repository import job_event_from_row
from backend.schemas.jobs import JobEventResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/recent", response_model=list[JobEventResponse])
def recent_logs(
    db_path: DbPath,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[JobEventResponse]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM job_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            JobEventResponse(
                id=event.id,
                job_id=event.job_id,
                level=event.level,
                message=event.message,
                payload=event.payload,
                created_at=event.created_at,
            )
            for event in (job_event_from_row(row) for row in reversed(rows))
        ]
    finally:
        conn.close()
