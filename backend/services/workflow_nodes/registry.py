from __future__ import annotations

from backend.services.workflow_nodes.actions import ExecuteActionsNodeExecutor
from backend.services.workflow_nodes.base import WorkflowNodeExecutor
from backend.services.workflow_nodes.collect import CollectArtworksNodeExecutor
from backend.services.workflow_nodes.filters import FilterArtworksNodeExecutor
from backend.services.workflow_nodes.sync import SyncMetadataNodeExecutor
from backend.services.workflow_nodes.target import ArtistTargetNodeExecutor


def default_node_registry() -> dict[str, WorkflowNodeExecutor]:
    executors: list[WorkflowNodeExecutor] = [
        ArtistTargetNodeExecutor(),
        SyncMetadataNodeExecutor(),
        CollectArtworksNodeExecutor(),
        FilterArtworksNodeExecutor(),
        ExecuteActionsNodeExecutor(),
    ]
    return {executor.node_type: executor for executor in executors}
