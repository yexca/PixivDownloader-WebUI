from __future__ import annotations

from backend.repositories.workflow_candidate_repository import (
    FilterArtworkCandidatesRequest,
    WorkflowCandidateRepository,
)
from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import positive_int, string_list, string_or_none


class FilterArtworksNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "filter_artworks"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        source_set_id = string_or_none(context.values.get("candidate_set_id"))
        filters = filter_config(config)
        if source_set_id is None:
            return WorkflowNodeResult(
                output={
                    "filters": filters,
                    "candidate_set_id": None,
                    "candidate_count": 0,
                    "filtered_count": 0,
                    "message": "No candidate set.",
                }
            )

        repository = WorkflowCandidateRepository(context.db_path)
        try:
            result = repository.filter_artwork_candidates(
                FilterArtworkCandidatesRequest(
                    workflow_run_id=node_run.workflow_run_id,
                    workflow_node_run_id=node_run.id,
                    source_set_id=source_set_id,
                    ai=str(filters["ai"]),
                    required_tags=list(filters["required_tags"]),
                    blocked_tags=list(filters["blocked_tags"]),
                    stop_above_limit=filters["stop_above_limit"],
                    config=filters,
                )
            )
        finally:
            repository.close()

        return WorkflowNodeResult(
            output={
                "filters": filters,
                "source_candidate_set_id": source_set_id,
                "source_candidate_count": result.source_count,
                "candidate_set_id": result.candidate_set.id,
                "candidate_count": result.candidate_set.total_count,
                "filtered_count": result.candidate_set.total_count,
                "stopped_by_rule": result.stopped_by_rule,
            }
        )


def filter_config(config: dict[str, object]) -> dict[str, object]:
    ai = config.get("ai")
    return {
        "ai": ai if ai in {"include", "exclude", "only"} else "include",
        "required_tags": string_list(config.get("required_tags")),
        "blocked_tags": string_list(config.get("blocked_tags")),
        "stop_above_limit": positive_int(config.get("stop_above_limit")),
    }
