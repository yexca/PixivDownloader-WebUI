from __future__ import annotations

from pathlib import Path

from backend.repositories.workflow_run_repository import WorkflowRun, WorkflowRunRepository
from backend.services.advanced_workflow_runner import (
    AdvancedWorkflowRunner,
    is_advanced_workflow_source,
)
from backend.services.workflow_run_service import LegacyWorkflowItemRunService


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
        if is_advanced_workflow_source(run.source):
            runner = AdvancedWorkflowRunner(
                self.db_path,
                settings_json_path=self.settings_json_path,
            )
            try:
                return runner.process_run(run.id)
            finally:
                runner.close()
        service = LegacyWorkflowItemRunService(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            return service.refresh_run_status(run)
        finally:
            service.close()

    def close(self) -> None:
        self.repository.close()
