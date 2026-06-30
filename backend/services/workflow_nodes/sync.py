from __future__ import annotations

from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.workflow_nodes.base import WorkflowNodeContext, WorkflowNodeResult


class SyncMetadataNodeExecutor:
    node_type = "sync_metadata"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del node_run, context
        return WorkflowNodeResult(output={"sync_mode": str(config.get("mode") or "incremental")})
