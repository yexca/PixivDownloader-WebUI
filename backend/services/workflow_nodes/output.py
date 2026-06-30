from __future__ import annotations

from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import string_or_none


class FileOutputNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "file_output"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del node_run, context
        return WorkflowNodeResult(
            output={
                "naming_rule": string_or_none(config.get("naming_rule")),
                "summary": "Workflow output recorded.",
            }
        )
