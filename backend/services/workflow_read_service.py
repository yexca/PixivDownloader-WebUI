from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backend.repositories.workflow_run_repository import WorkflowRun, WorkflowRunRepository


class WorkflowReadService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.repository = WorkflowRunRepository(db_path)

    def list_runs(self, *, limit: int = 5, offset: int = 0) -> tuple[list[WorkflowRun], int]:
        runs = self.repository.list_runs(limit=limit, offset=offset)
        total = self.repository.count_runs()
        return [self.refresh_run(run) for run in runs], total

    def get_run(self, run_id: str) -> WorkflowRun | None:
        run = self.repository.get_run(run_id)
        if run is None:
            return None
        return self.refresh_run(run)

    def refresh_run(self, run: WorkflowRun) -> WorkflowRun:
        return replace(
            run,
            completed=sum(node.status == "completed" for node in run.node_runs),
            failed=sum(node.status in {"failed", "partial"} for node in run.node_runs),
            skipped=sum(node.status in {"skipped", "cancelled"} for node in run.node_runs),
        )

    def close(self) -> None:
        self.repository.close()
