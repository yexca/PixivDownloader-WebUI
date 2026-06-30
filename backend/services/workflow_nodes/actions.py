from __future__ import annotations

from backend.repositories.workflow_candidate_repository import WorkflowCandidateRepository
from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import string_or_none


class ExecuteActionsNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "execute_actions"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        candidate_set_id = string_or_none(context.values.get("candidate_set_id"))
        download_enabled = bool(config.get("download"))
        execution_unit = normalize_execution_unit(config.get("execution_unit"))
        output = {
            "candidate_set_id": candidate_set_id,
            "download": download_enabled,
            "execution_unit": execution_unit,
        }
        if candidate_set_id is None:
            return WorkflowNodeResult(output={**output, "job_ids": [], "message": "No candidates."})
        if not download_enabled:
            return WorkflowNodeResult(
                output={**output, "job_ids": [], "message": "No file action."}
            )

        options = {
            "candidate_set_id": candidate_set_id,
            "candidate_source": context.values.get("candidate_source"),
            "execution_unit": execution_unit,
            "conflict_mode": config.get("conflict_mode"),
            "naming_rule": config.get("naming_rule") or context.values.get("naming_rule"),
        }
        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            job_ids = create_candidate_jobs(
                service,
                context,
                node_run,
                candidate_set_id=candidate_set_id,
                execution_unit=execution_unit,
                options=options,
            )
        finally:
            service.close()

        return WorkflowNodeResult(
            output={**output, "job_ids": job_ids},
            job_ids=job_ids,
        )


def create_candidate_jobs(
    service: JobService,
    context: WorkflowNodeContext,
    node_run: WorkflowNodeRun,
    *,
    candidate_set_id: str,
    execution_unit: str,
    options: dict[str, object],
) -> list[str]:
    workflow_link = WorkflowJobLink(
        run_id=node_run.workflow_run_id,
        item_id=context.workflow_item_id,
        source="advanced_workflow",
    )
    if execution_unit == "set":
        job = service.create_candidate_download_job(
            candidate_set_id=candidate_set_id,
            options=options,
            workflow_link=workflow_link,
        )
        return [job.id]

    repository = WorkflowCandidateRepository(context.db_path)
    try:
        artist_ids = repository.list_artist_ids(candidate_set_id)
    finally:
        repository.close()
    return [
        service.create_candidate_download_job(
            candidate_set_id=candidate_set_id,
            artist_id=artist_id,
            options=options,
            workflow_link=workflow_link,
        ).id
        for artist_id in artist_ids
    ]


def normalize_execution_unit(value: object) -> str:
    return "set" if value == "set" else "artist"
