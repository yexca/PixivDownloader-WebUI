from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from backend.domain.entities import Job
from backend.repositories.workflow_run_repository import WorkflowNodeRun


@dataclass(frozen=True)
class WorkflowNodeContext:
    db_path: Path | str | None
    settings_json_path: Path | str | None
    workflow_node_run_id: int | None
    values: dict[str, object]


@dataclass(frozen=True)
class WorkflowNodeResult:
    output: dict[str, object] = field(default_factory=dict)
    job_ids: list[str] = field(default_factory=list)


class WorkflowNodeExecutor(Protocol):
    node_type: str

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        ...

    def complete_from_jobs(
        self,
        node_run: WorkflowNodeRun,
        jobs: list[Job],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        ...


class WorkflowNodeExecutorBase:
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
