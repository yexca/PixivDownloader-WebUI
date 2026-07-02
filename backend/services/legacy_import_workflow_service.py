from __future__ import annotations

import logging
from pathlib import Path

from backend.domain.entities import Job
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner

logger = logging.getLogger(__name__)


class LegacyImportWorkflowService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path

    def continue_after_job(self, job: Job) -> None:
        if job.workflow_source != "legacy_import" or not job.workflow_run_id:
            return
        if job.status not in {"completed", "failed", "cancelled"}:
            return
        runner = AdvancedWorkflowRunner(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            runner.process_run(job.workflow_run_id)
        except Exception:
            logger.exception("legacy import workflow continuation failed: %s", job.workflow_run_id)
        finally:
            runner.close()
