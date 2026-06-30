from __future__ import annotations

from backend.domain.entities import Job
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import positive_int, string_list


class ArtistTargetNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "artist_target"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        artist_ids = tuple(string_list(config.get("artist_ids")))
        artwork_ids = tuple(string_list(config.get("artwork_ids")))
        max_artists = positive_int(config.get("max_artists")) or max(
            1,
            len(artist_ids) + len(artwork_ids),
        )
        output = {
            "target_scope": str(config.get("scope") or "selected"),
            "max_artists": max_artists,
            "input_artist_ids": list(artist_ids),
            "input_artwork_ids": list(artwork_ids),
        }
        if not artist_ids and not artwork_ids:
            return WorkflowNodeResult(output={**output, "artist_ids": [], "resolved_count": 0})

        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            job = service.create_resolve_workflow_targets_job(
                artist_ids=artist_ids,
                artwork_ids=artwork_ids,
                max_targets_per_run=max_artists,
                options={"target_scope": output["target_scope"]},
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
            output={**output, "resolver_job_ids": job_ids},
            job_ids=job_ids,
        )

    def complete_from_jobs(
        self,
        node_run: WorkflowNodeRun,
        jobs: list[Job],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        payload = latest_resolver_payload(context.db_path, node_run.job_ids)
        artist_ids = string_list(payload.get("resolved_artist_ids") or payload.get("artist_ids"))
        resolved_from_artworks = payload.get("resolved_from_artworks")
        if not isinstance(resolved_from_artworks, list):
            resolved_from_artworks = []
        return WorkflowNodeResult(
            output={
                **node_run.output,
                "artist_ids": artist_ids,
                "resolved_from_artworks": resolved_from_artworks,
                "resolved_count": len(artist_ids),
                "skipped_count": sum(job.skipped_files for job in jobs),
                "completed_jobs": [job.id for job in jobs],
            }
        )


def latest_resolver_payload(db_path: object, job_ids: list[str]) -> dict[str, object]:
    if not job_ids:
        return {}
    repository = JobRepository(db_path)
    try:
        for job_id in reversed(job_ids):
            for event in reversed(repository.list_events(job_id, limit=100)):
                payload = event.payload
                if not isinstance(payload, dict):
                    continue
                if "resolved_artist_ids" in payload or "artist_ids" in payload:
                    return payload
    finally:
        repository.close()
    return {}
