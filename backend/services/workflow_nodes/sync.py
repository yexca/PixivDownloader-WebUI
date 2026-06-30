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


class SyncMetadataNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "sync_metadata"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        artist_ids = tuple(string_list(context.values.get("artist_ids")))
        mode = sync_mode(config.get("mode"))
        output = {
            "artist_ids": list(artist_ids),
            "sync_mode": mode,
            "full_sync": mode == "full",
        }
        if not artist_ids:
            return WorkflowNodeResult(
                output={**output, "sync_job_ids": [], "synced_artist_ids": []}
            )

        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            jobs = [
                service.create_download_job(
                    user_id=artist_id,
                    artwork_id=None,
                    sync_only=True,
                    options={"full_sync": mode == "full"},
                    workflow_link=WorkflowJobLink(
                        run_id=node_run.workflow_run_id,
                        item_id=context.workflow_item_id,
                        source="advanced_workflow",
                    ),
                )
                for artist_id in artist_ids
            ]
        finally:
            service.close()

        job_ids = [job.id for job in jobs]
        return WorkflowNodeResult(
            output={**output, "sync_job_ids": job_ids},
            job_ids=job_ids,
        )

    def complete_from_jobs(
        self,
        node_run: WorkflowNodeRun,
        jobs: list[Job],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del context
        synced_artist_ids = [job.input_user_id for job in jobs if job.input_user_id]
        return WorkflowNodeResult(
            output={
                **node_run.output,
                "artist_ids": synced_artist_ids,
                "synced_artist_ids": synced_artist_ids,
                "completed_jobs": [job.id for job in jobs],
            }
        )


def sync_mode(value: object) -> str:
    return "full" if value == "full" else "incremental"
