from __future__ import annotations

from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.workflow_nodes.base import WorkflowNodeContext, WorkflowNodeResult
from backend.services.workflow_nodes.utils import positive_int, string_list


class ArtistTargetNodeExecutor:
    node_type = "artist_target"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del node_run, context
        return WorkflowNodeResult(
            output={
                "artist_ids": string_list(config.get("artist_ids")),
                "artwork_ids": string_list(config.get("artwork_ids")),
                "target_scope": str(config.get("scope") or "selected"),
                "max_artists": positive_int(config.get("max_artists")),
            }
        )
