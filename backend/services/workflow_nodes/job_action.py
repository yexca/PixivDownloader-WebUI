from __future__ import annotations

from backend.domain.entities import Job
from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import string_or_none


class JobActionNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "job_action"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        source_job_id = string_or_none(config.get("source_job_id"))
        action = normalize_job_action(config.get("action"))
        if source_job_id is None:
            raise ValueError("job_action requires source_job_id")

        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            workflow_link = WorkflowJobLink(
                run_id=node_run.workflow_run_id,
                node_run_id=context.workflow_node_run_id,
                source="advanced_workflow",
            )
            job = (
                service.retry_job(source_job_id, workflow_link=workflow_link)
                if action == "retry"
                else service.rerun_job(source_job_id, workflow_link=workflow_link)
            )
        finally:
            service.close()

        return WorkflowNodeResult(
            output={
                "source_job_id": source_job_id,
                "action": action,
                "job_ids": [job.id],
                "created_job_type": job.type,
                "created_job_status": job.status,
            },
            job_ids=[job.id],
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
                "created_job_statuses": {job.id: job.status for job in jobs},
            }
        )


def normalize_job_action(value: object) -> str:
    return "rerun" if value == "rerun" else "retry"
