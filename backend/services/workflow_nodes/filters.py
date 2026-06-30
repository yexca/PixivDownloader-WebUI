from __future__ import annotations

from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)


class FilterArtworksNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "filter_artworks"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del node_run, context
        return WorkflowNodeResult(output={"filters": config})
