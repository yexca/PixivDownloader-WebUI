from __future__ import annotations

from backend.domain.entities import Job
from backend.repositories.legacy_import_repository import LegacyImportRepository
from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import string_list


class LegacyImportHydrationNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "legacy_import_hydration"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        import_id = str(config.get("import_id") or "").strip()
        cursor_map: dict[str, object] = {}
        if import_id:
            repository = LegacyImportRepository(context.db_path)
            try:
                targets = repository.list_artists(import_id)
            finally:
                repository.close()
            artist_ids = tuple(target.artist_id for target in targets)
            cursor_map = {target.artist_id: target.legacy_latest_download_id for target in targets}
        else:
            artist_ids = tuple(string_list(config.get("artist_ids")))
            raw_cursor_map = config.get("legacy_latest_download_id_by_artist")
            if isinstance(raw_cursor_map, dict):
                cursor_map = raw_cursor_map
        if not artist_ids:
            return WorkflowNodeResult(
                output={
                    "import_id": import_id or None,
                    "artist_ids": [],
                    "hydration_job_ids": [],
                    "artist_count": 0,
                }
            )
        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            job = service.create_legacy_import_hydration_job(
                artist_ids=artist_ids,
                legacy_latest_download_id_by_artist={
                    str(key): str(value) if value is not None else None
                    for key, value in cursor_map.items()
                },
                workflow_link=WorkflowJobLink(
                    run_id=node_run.workflow_run_id,
                    node_run_id=context.workflow_node_run_id,
                    source="legacy_import",
                ),
            )
        finally:
            service.close()
        job_ids = [] if job is None else [job.id]
        return WorkflowNodeResult(
            output={
                "artist_ids": list(artist_ids),
                "import_id": import_id or None,
                "hydration_job_ids": job_ids,
                "artist_count": len(artist_ids),
            },
            job_ids=job_ids,
        )

    def complete_from_jobs(
        self,
        node_run: WorkflowNodeRun,
        jobs: list[Job],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del context
        return WorkflowNodeResult(
            output={
                **node_run.output,
                "completed_jobs": [job.id for job in jobs],
            }
        )


class LegacyDatabaseImportNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "legacy_database_import"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        import_id = str(config.get("import_id") or "").strip()
        if not import_id:
            raise ValueError("legacy database import node requires import_id")
        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            job = service.create_legacy_database_import_job(
                import_id=import_id,
                workflow_link=WorkflowJobLink(
                    run_id=node_run.workflow_run_id,
                    node_run_id=context.workflow_node_run_id,
                    source="legacy_import",
                ),
            )
        finally:
            service.close()
        return WorkflowNodeResult(
            output={
                "import_id": import_id,
                "import_job_ids": [job.id],
            },
            job_ids=[job.id],
        )

    def complete_from_jobs(
        self,
        node_run: WorkflowNodeRun,
        jobs: list[Job],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        del context
        return WorkflowNodeResult(
            output={
                **node_run.output,
                "completed_jobs": [job.id for job in jobs],
            }
        )
