from __future__ import annotations

from backend.domain.entities import Job
from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import string_list


class LegacyImportHydrationNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "legacy_import_hydration"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        artist_ids = tuple(string_list(config.get("artist_ids")))
        cursor_map = config.get("legacy_latest_download_id_by_artist")
        if not isinstance(cursor_map, dict):
            cursor_map = {}
        if not artist_ids:
            return WorkflowNodeResult(
                output={"artist_ids": [], "hydration_job_ids": [], "artist_count": 0}
            )
        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            job = service.create_legacy_import_hydration_job(
                artist_ids=artist_ids,
                legacy_latest_download_id_by_artist={
                    str(key): str(value) if value is not None else None
                    for key, value in cursor_map.items()
                },
                workflow_link=WorkflowJobLink(
                    run_id=node_run.workflow_run_id,
                    node_run_id=context.workflow_node_run_id,
                    source="advanced_workflow",
                ),
            )
        finally:
            service.close()
        job_ids = [] if job is None else [job.id]
        return WorkflowNodeResult(
            output={
                "artist_ids": list(artist_ids),
                "hydration_job_ids": job_ids,
                "artist_count": len(artist_ids),
            },
            job_ids=job_ids,
        )

    def complete_from_jobs(
        self,
        node_run: WorkflowNodeRun,
        jobs: list[Job],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del context
        return WorkflowNodeResult(
            output={
                **node_run.output,
                "completed_jobs": [job.id for job in jobs],
            }
        )
