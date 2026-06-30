from __future__ import annotations

from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import positive_int, string_or_none


class CollectArtworksNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "collect_artworks"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del node_run, context
        return WorkflowNodeResult(
            output={
                "collect_mode": str(config.get("mode") or "new"),
                "max_artworks": positive_int(config.get("max_artworks")),
                "min_artwork_id": string_or_none(config.get("min_artwork_id")),
                "max_artwork_id": string_or_none(config.get("max_artwork_id")),
            }
        )
