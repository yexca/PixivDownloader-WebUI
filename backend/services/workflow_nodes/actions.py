from __future__ import annotations

from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.workflow_nodes.base import WorkflowNodeContext, WorkflowNodeResult
from backend.services.workflow_nodes.utils import (
    action_list,
    dict_option,
    positive_int,
    string_list,
)


class ExecuteActionsNodeExecutor:
    node_type = "execute_actions"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        artist_ids = tuple(string_list(context.values.get("artist_ids")))
        artwork_ids = tuple(string_list(context.values.get("artwork_ids")))
        actions = tuple(action_list(config.get("actions")))
        if not artist_ids and not artwork_ids:
            return WorkflowNodeResult(output={"job_ids": [], "message": "No artist targets."})

        download_options = {
            "full_download": context.values.get("collect_mode") == "all_local",
            "pending_only": context.values.get("collect_mode") == "new",
            "max_artworks": context.values.get("max_artworks"),
            "min_artwork_id": context.values.get("min_artwork_id"),
            "max_artwork_id": context.values.get("max_artwork_id"),
            "naming_rule": config.get("naming_rule") or context.values.get("naming_rule"),
            "stop_if_artwork_count_above": dict_option(context.values.get("filters")).get(
                "stop_above_limit"
            ),
        }
        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            job = service.create_resolve_artist_targets_job(
                artist_ids=artist_ids,
                artwork_ids=artwork_ids,
                actions=actions,
                download_options=download_options,
                max_targets_per_run=positive_int(context.values.get("max_artists"))
                or max(1, len(artist_ids) + len(artwork_ids)),
                options=download_options,
                workflow_link=WorkflowJobLink(
                    run_id=node_run.workflow_run_id,
                    item_id=context.workflow_item_id,
                    source="advanced_workflow",
                ),
            )
        finally:
            service.close()

        job_ids = [] if job is None else [job.id]
        return WorkflowNodeResult(
            output={"job_ids": job_ids, "actions": list(actions)},
            job_ids=job_ids,
        )
