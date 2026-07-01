from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from backend.repositories._time import utc_now
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunRepository,
)
from backend.schemas.failure_reasons import failure_detail_from_exception
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.workflow_nodes import default_node_registry
from backend.services.workflow_nodes.base import WorkflowNodeContext, WorkflowNodeExecutor
from backend.services.workflow_nodes.utils import dict_option

ACTIVE_JOB_STATUSES = {"inactive", "queued", "running"}
FAILED_JOB_STATUSES = {"failed", "cancelled"}
ADVANCED_WORKFLOW_SOURCES = {
    "advanced",
    "advanced_manual",
    "workflow_trigger",
    "download_api",
    "library_shortcut",
    "artwork_file_shortcut",
    "job_retry",
    "job_rerun",
    "manual_schedule",
    "schedule",
    "startup_recovery",
    "legacy_import",
}


def is_advanced_workflow_source(source: str) -> bool:
    return source in ADVANCED_WORKFLOW_SOURCES


class AdvancedWorkflowRunner:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
        node_registry: dict[str, WorkflowNodeExecutor] | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.repository = WorkflowRunRepository(db_path)
        self.node_registry = node_registry or default_node_registry()

    def create_run(
        self,
        definition: AdvancedWorkflowDefinitionRequest,
        *,
        source: str = "advanced",
        schedule_id: int | None = None,
    ) -> WorkflowRun:
        if not definition.nodes:
            raise ValueError("advanced workflow requires at least one node")
        now = utc_now()
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            status="running",
            total=len(definition.nodes),
            completed=0,
            failed=0,
            skipped=0,
            concurrency=1,
            source=source,
            schedule_id=schedule_id,
            created_at=now,
        )
        self.repository.create_run(run)
        for position, node in enumerate(definition.nodes):
            self.repository.create_node_run(
                WorkflowNodeRun(
                    id=None,
                    workflow_run_id=run.id,
                    node_id=node.id,
                    node_type=node.type,
                    title=node.title or node.type.replace("_", " ").title(),
                    position=position,
                    status="pending",
                    input={"config": node.config},
                    created_at=now,
                )
            )
        run = self.repository.get_run(run.id) or run
        return self.process_run(run.id)

    def process_run(self, run_id: str) -> WorkflowRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"workflow run not found: {run_id}")
        if not is_advanced_workflow_source(run.source):
            return run

        context: dict[str, object] = {}
        previous_output: dict[str, object] = {}
        for node_run in self.repository.list_node_runs(run.id):
            if node_run.status == "completed":
                previous_output = node_run.output
                context.update(node_run.output)
                continue
            if node_run.status == "failed":
                break
            linked_job_ids = self._linked_job_ids(node_run)
            if node_run.status == "running" and linked_job_ids:
                if linked_job_ids != node_run.job_ids:
                    node_run = replace(node_run, job_ids=linked_job_ids)
                refreshed = self._refresh_node_jobs(node_run, context)
                if refreshed.status != "completed":
                    break
                node_run = refreshed
                previous_output = node_run.output
                context.update(node_run.output)
                continue
            node_run = replace(
                node_run,
                status="running",
                started_at=node_run.started_at or utc_now(),
                input={**node_run.input, "previous": previous_output},
            )
            self.repository.update_node_run(node_run)
            try:
                node_run = self._execute_node(node_run, context)
            except Exception as exc:
                failure = failure_detail_from_exception(exc)
                failed = replace(
                    node_run,
                    status="failed",
                    error_message=str(exc),
                    output={
                        **node_run.output,
                        "error_code": failure.code,
                        "error_retryable": failure.retryable,
                    },
                    finished_at=utc_now(),
                )
                self.repository.update_node_run(failed)
                break
            if node_run.status == "running":
                break
            previous_output = node_run.output
            context.update(node_run.output)

        return self._refresh_run(run.id)

    def close(self) -> None:
        self.repository.close()

    def _execute_node(
        self,
        node_run: WorkflowNodeRun,
        context: dict[str, object],
    ) -> WorkflowNodeRun:
        config = dict_option(node_run.input.get("config"))
        executor = self.node_registry.get(node_run.node_type)
        if executor is None:
            return self._complete(node_run, {"ignored": True})
        result = executor.execute(
            node_run,
            config,
            WorkflowNodeContext(
                db_path=self.db_path,
                settings_json_path=self.settings_json_path,
                workflow_node_run_id=node_run.id,
                values=context,
            ),
        )
        if not result.job_ids:
            return self._complete(node_run, result.output)
        running = replace(
            node_run,
            status="running",
            output=result.output,
        )
        self.repository.update_node_run(running)
        return replace(running, job_ids=result.job_ids)

    def _refresh_node_jobs(
        self,
        node_run: WorkflowNodeRun,
        context: dict[str, object],
    ) -> WorkflowNodeRun:
        repository = JobRepository(self.db_path)
        try:
            jobs = repository.list_by_ids(node_run.job_ids)
        finally:
            repository.close()
        if len(jobs) != len(node_run.job_ids):
            failed = replace(
                node_run,
                status="failed",
                error_message="Workflow node cannot be resolved: a linked job is missing.",
                finished_at=utc_now(),
            )
            self.repository.update_node_run(failed)
            return failed
        if any(job.status in ACTIVE_JOB_STATUSES for job in jobs):
            return node_run
        if any(job.status in FAILED_JOB_STATUSES for job in jobs):
            failed_job = next((job for job in jobs if job.status in FAILED_JOB_STATUSES), jobs[0])
            message = failed_job.error_message
            failed = replace(
                node_run,
                status="failed",
                error_message=message or node_run.error_message,
                output={
                    **node_run.output,
                    "failed_job_id": failed_job.id,
                    "error_code": failed_job.options.get("error_code"),
                    "error_retryable": failed_job.options.get("error_retryable"),
                },
                finished_at=utc_now(),
            )
            self.repository.update_node_run(failed)
            return failed
        executor = self.node_registry.get(node_run.node_type)
        if executor is None:
            return self._complete(
                node_run,
                {
                    **node_run.output,
                    "completed_jobs": [job.id for job in jobs],
                },
            )
        result = executor.complete_from_jobs(
            node_run,
            jobs,
            WorkflowNodeContext(
                db_path=self.db_path,
                settings_json_path=self.settings_json_path,
                workflow_node_run_id=node_run.id,
                values=context,
            ),
        )
        return self._complete(node_run, result.output)

    def _linked_job_ids(self, node_run: WorkflowNodeRun) -> list[str]:
        if node_run.id is None:
            return node_run.job_ids
        repository = JobRepository(self.db_path)
        try:
            linked_job_ids = [
                job.id for job in repository.list_by_workflow_node_run_id(node_run.id)
            ]
        finally:
            repository.close()
        return dedupe([*node_run.job_ids, *linked_job_ids])

    def _complete(self, node_run: WorkflowNodeRun, output: dict[str, object]) -> WorkflowNodeRun:
        completed = replace(
            node_run,
            status="completed",
            output=output,
            error_message=None,
            finished_at=utc_now(),
        )
        self.repository.update_node_run(completed)
        return completed

    def _refresh_run(self, run_id: str) -> WorkflowRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"workflow run not found: {run_id}")
        node_runs = [
            self._hydrate_node_run_jobs(node)
            for node in self.repository.list_node_runs(run.id)
        ]
        completed = sum(1 for node in node_runs if node.status == "completed")
        failed = sum(1 for node in node_runs if node.status == "failed")
        skipped = sum(1 for node in node_runs if node.status == "skipped")
        has_active = any(node.status in {"pending", "running"} for node in node_runs)
        status = advanced_run_status(
            completed=completed,
            failed=failed,
            skipped=skipped,
            running=has_active,
        )
        refreshed = replace(
            run,
            status=status,
            total=len(node_runs),
            completed=completed,
            failed=failed,
            skipped=skipped,
            finished_at=None if has_active else run.finished_at or utc_now(),
            node_runs=node_runs,
        )
        self.repository.update_run(refreshed)
        return replace(refreshed, items=self.repository.list_items(run_id))

    def _hydrate_node_run_jobs(self, node_run: WorkflowNodeRun) -> WorkflowNodeRun:
        linked_job_ids = self._linked_job_ids(node_run)
        if linked_job_ids == node_run.job_ids:
            return node_run
        return replace(node_run, job_ids=linked_job_ids)


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def advanced_run_status(
    *,
    completed: int,
    failed: int,
    skipped: int,
    running: bool = False,
) -> str:
    if running:
        return "running"
    if failed and completed:
        return "partial"
    if failed and not completed:
        return "failed"
    if skipped and not completed:
        return "skipped"
    return "completed"
