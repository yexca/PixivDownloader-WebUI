from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from backend.repositories._time import utc_now
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunItem,
    WorkflowRunRepository,
)
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
        item_id = self.repository.create_item(
            WorkflowRunItem(
                id=None,
                run_id=run.id,
                draft_id=f"advanced:{run.id}",
                title=definition.name or "Advanced workflow",
                status="running",
                config=definition.model_dump(mode="json"),
                request={
                    "source": source,
                    "schedule_id": schedule_id,
                    "definition": definition.model_dump(mode="json"),
                },
                created_at=now,
            )
        )
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
        return self.process_run(run.id, item_id=item_id)

    def process_run(self, run_id: str, *, item_id: int | None = None) -> WorkflowRun:
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
            if node_run.status == "running" and node_run.job_ids:
                refreshed = self._refresh_node_jobs(node_run, context, item_id=item_id)
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
                node_run = self._execute_node(node_run, context, item_id=item_id)
            except Exception as exc:
                failed = replace(
                    node_run,
                    status="failed",
                    error_message=str(exc),
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
        *,
        item_id: int | None,
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
                workflow_item_id=item_id,
                values=context,
            ),
        )
        if not result.job_ids:
            return self._complete(node_run, result.output)
        running = replace(
            node_run,
            status="running",
            job_ids=result.job_ids,
            output=result.output,
        )
        self.repository.update_node_run(running)
        self._sync_item_jobs(node_run.workflow_run_id, item_id, result.job_ids)
        return running

    def _refresh_node_jobs(
        self,
        node_run: WorkflowNodeRun,
        context: dict[str, object],
        *,
        item_id: int | None,
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
            message = next((job.error_message for job in jobs if job.error_message), None)
            failed = replace(
                node_run,
                status="failed",
                error_message=message or node_run.error_message,
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
                workflow_item_id=item_id,
                values=context,
            ),
        )
        return self._complete(node_run, result.output)

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
        node_runs = self.repository.list_node_runs(run.id)
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
        for item in run.items:
            self.repository.update_item(
                replace(
                    item,
                    status="running" if has_active else status,
                    finished_at=None if has_active else item.finished_at or utc_now(),
                )
            )
        return self.repository.get_run(run_id) or refreshed

    def _sync_item_jobs(self, run_id: str, item_id: int | None, job_ids: list[str]) -> None:
        if item_id is None:
            return
        for item in self.repository.list_items(run_id):
            if item.id != item_id:
                continue
            merged = dedupe([*item.job_ids, *job_ids])
            self.repository.update_item(replace(item, status="running", job_ids=merged))
            break


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
