from __future__ import annotations

from backend.repositories.workflow_candidate_repository import (
    CollectArtworkCandidatesRequest,
    WorkflowCandidateRepository,
)
from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import positive_int, string_list, string_or_none


class CollectArtworksNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "collect_artworks"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        artist_ids = string_list(context.values.get("artist_ids"))
        source = collect_source(config.get("mode"))
        sort_order = collect_sort_order(config.get("sort_order"))
        limit = positive_int(config.get("max_artworks"))
        min_artwork_id = numeric_string_or_none(config.get("min_artwork_id"))
        max_artwork_id = numeric_string_or_none(config.get("max_artwork_id"))
        output = {
            "artist_ids": artist_ids,
            "collect_mode": source,
            "candidate_source": source,
            "collect_sort_order": sort_order,
            "max_artworks": limit,
            "min_artwork_id": min_artwork_id,
            "max_artwork_id": max_artwork_id,
        }
        if not artist_ids:
            return WorkflowNodeResult(
                output={
                    **output,
                    "candidate_set_id": None,
                    "candidate_count": 0,
                }
            )

        repository = WorkflowCandidateRepository(context.db_path)
        try:
            candidate_set = repository.collect_artwork_candidates(
                CollectArtworkCandidatesRequest(
                    workflow_run_id=node_run.workflow_run_id,
                    workflow_node_run_id=node_run.id,
                    artist_ids=artist_ids,
                    source=source,
                    sort_order=sort_order,
                    limit=limit,
                    min_artwork_id=min_artwork_id,
                    max_artwork_id=max_artwork_id,
                    config=output,
                )
            )
        finally:
            repository.close()

        return WorkflowNodeResult(
            output={
                **output,
                "candidate_set_id": candidate_set.id,
                "candidate_count": candidate_set.total_count,
            }
        )


def collect_source(value: object) -> str:
    if value in {"pending_files", "all_synced", "failed_files"}:
        return str(value)
    return "new_since_last_download"


def collect_sort_order(value: object) -> str:
    if value in {"oldest_first", "local_order"}:
        return str(value)
    return "newest_first"


def numeric_string_or_none(value: object) -> str | None:
    text = string_or_none(value)
    if text is None:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return str(parsed) if parsed >= 0 else None
