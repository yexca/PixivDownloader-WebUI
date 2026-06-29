from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, Queue
from backend.repositories.dashboard_repository import DashboardRepository
from backend.schemas.dashboard import DashboardSummaryResponse

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db_path: DbPath, queue: Queue) -> DashboardSummaryResponse:
    repository = DashboardRepository(db_path)
    try:
        return DashboardSummaryResponse(
            library=repository.library_counts(),
            workflows=repository.workflow_counts(),
            jobs=repository.job_counts(),
            queue_paused=bool(getattr(queue, "paused", False)),
        )
    finally:
        repository.close()
