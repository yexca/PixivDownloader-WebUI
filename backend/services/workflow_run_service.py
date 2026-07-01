from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from backend.repositories._time import utc_now
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import (
    WorkflowRun,
    WorkflowRunItem,
    WorkflowRunRepository,
)
from backend.schemas.scheduled_tasks import (
    ScheduledTaskConfigRequest,
    scheduled_task_config_from_request,
    scheduled_task_config_to_dict,
)
from backend.schemas.workflows import WorkflowBatchItemRequest
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.scheduled_task_service import ScheduledTaskService

ACTIVE_JOB_STATUSES = {"inactive", "queued", "running"}
FAILED_JOB_STATUSES = {"failed", "cancelled"}


class WorkflowRunService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.repository = WorkflowRunRepository(db_path)

    def run_batch(
        self,
        *,
        items: list[WorkflowBatchItemRequest],
        concurrency: int,
    ) -> WorkflowRun:
        now = utc_now()
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            status="running",
            total=len(items),
            completed=0,
            failed=0,
            skipped=0,
            concurrency=concurrency,
            created_at=now,
        )
        self.repository.create_run(run)
        for request in items:
            config = scheduled_task_config_from_request(request.config)
            config_dict = scheduled_task_config_to_dict(config)
            self.repository.create_item(
                WorkflowRunItem(
                    id=None,
                    run_id=run.id,
                    draft_id=request.draft_id,
                    title=request.title,
                    status="pending",
                    config=config_dict,
                    request=workflow_item_request_to_dict(request),
                    created_at=utc_now(),
                )
            )
        return self.process_run(run.id)

    def run_legacy_import_hydration(
        self,
        *,
        artist_ids: tuple[str, ...],
        legacy_latest_download_id_by_artist: dict[str, str | None],
    ) -> WorkflowRun | None:
        if not artist_ids:
            return None
        now = utc_now()
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            status="running",
            total=1,
            completed=0,
            failed=0,
            skipped=0,
            concurrency=1,
            source="legacy_import",
            created_at=now,
        )
        self.repository.create_run(run)
        config = {
            "target": {"type": "legacy_import", "artist_count": len(artist_ids)},
            "actions": ["hydrate_legacy_import"],
        }
        item_id = self.repository.create_item(
            WorkflowRunItem(
                id=None,
                run_id=run.id,
                draft_id=f"legacy-import:{run.id}",
                title="Legacy import hydration",
                status="running",
                config=config,
                request={
                    "source": "legacy_import",
                    "artist_count": len(artist_ids),
                },
                created_at=utc_now(),
            )
        )
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            job = service.create_legacy_import_hydration_job(
                artist_ids=artist_ids,
                legacy_latest_download_id_by_artist=legacy_latest_download_id_by_artist,
                workflow_link=WorkflowJobLink(
                    run_id=run.id,
                    item_id=item_id,
                    source="legacy_import",
                ),
            )
        finally:
            service.close()
        item = self.repository.list_items(run.id)[0]
        updated_item = replace(
            item,
            id=item_id,
            status="running" if job is not None else "completed",
            job_ids=[] if job is None else [job.id],
            finished_at=None if job is not None else utc_now(),
        )
        self.repository.update_item(updated_item)
        updated_run = replace(
            run,
            status="running" if job is not None else "completed",
            completed=0 if job is not None else 1,
            finished_at=None if job is not None else utc_now(),
            items=[updated_item],
        )
        self.repository.update_run(updated_run)
        return self.refresh_run_status(updated_run)

    def process_run(self, run_id: str) -> WorkflowRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"workflow run not found: {run_id}")
        previous_failed: set[str] = set()

        for item in self.repository.list_items(run.id):
            if item.status in {"completed", "failed", "skipped"}:
                if item.status == "failed":
                    previous_failed.add(item.draft_id)
                continue
            if item.status == "running" and item.job_ids:
                refreshed_item = self._refresh_item_status(item)
                if refreshed_item.status == "failed":
                    previous_failed.add(item.draft_id)
                continue
            request = workflow_item_request_from_dict(item.request)
            if request is None:
                previous_failed.add(item.draft_id)
                self.repository.update_item(
                    replace(
                        item,
                        status="failed",
                        error_message=(
                            "Workflow item cannot be recovered: request metadata is missing."
                        ),
                        finished_at=utc_now(),
                    )
                )
                continue

            self.repository.update_item(replace(item, status="running"))
            config = scheduled_task_config_from_request(request.config)
            previous_status = self.repository.last_item_status(
                request.draft_id,
                exclude_run_id=run.id,
            )

            if request.skip_if_last_run_failed and (
                request.draft_id in previous_failed or previous_status == "failed"
            ):
                self.repository.update_item(
                    replace(
                        item,
                        status="skipped",
                        error_message="Skipped because the last run failed",
                        finished_at=utc_now(),
                    )
                )
                continue

            task_service = ScheduledTaskService(
                self.db_path,
                settings_json_path=self.settings_json_path,
            )
            try:
                if request.schedule:
                    action = config.actions[0] if config.actions else "download_artist"
                    target_artist_id = config.target.artist_id or ""
                    task_service.create_task(
                        name=request.name or request.title,
                        action=action,
                        target_artist_id=target_artist_id,
                        interval_days=request.interval_days,
                        enabled=request.enabled,
                        run_after_startup=request.run_after_startup,
                        config=config,
                    )
                    jobs = []
                else:
                    jobs = task_service.run_config(
                        config,
                        workflow_link=WorkflowJobLink(
                            run_id=run.id,
                            item_id=item.id,
                            source="workflow_batch",
                        ),
                    )
            except Exception as exc:
                previous_failed.add(request.draft_id)
                self.repository.update_item(
                    replace(
                        item,
                        status="failed",
                        error_message=str(exc),
                        finished_at=utc_now(),
                    )
                )
            else:
                item_status = "running" if jobs else "completed"
                updated_item = replace(
                    item,
                    status=item_status,
                    job_ids=[job.id for job in jobs],
                    finished_at=None if jobs else utc_now(),
                )
                self.repository.update_item(updated_item)
                self._refresh_item_status(updated_item)
            finally:
                task_service.close()

        run = replace(
            run,
            items=self.repository.list_items(run.id),
        )
        return self.refresh_run_status(run)

    def recover_interrupted_runs(self) -> list[WorkflowRun]:
        recovered: list[WorkflowRun] = []
        for run in self.repository.list_runs_by_status("running"):
            self._requeue_interrupted_item_jobs(run)
            recovered.append(self.process_run(run.id))
        return recovered

    def recover_startup(self) -> list[WorkflowRun]:
        recovered = self.recover_interrupted_runs()
        orphan_run = self._recover_active_orphan_jobs()
        if orphan_run is not None:
            recovered.append(orphan_run)
        return recovered

    def list_runs(self, *, limit: int = 5, offset: int = 0) -> tuple[list[WorkflowRun], int]:
        runs = [
            self.refresh_run_status(run)
            for run in self.repository.list_runs(limit=limit, offset=offset)
        ]
        return runs, self.repository.count_runs()

    def get_run(self, run_id: str) -> WorkflowRun | None:
        run = self.repository.get_run(run_id)
        return self.refresh_run_status(run) if run is not None else None

    def refresh_run_status(self, run: WorkflowRun) -> WorkflowRun:
        refreshed_items = [self._refresh_item_status(item) for item in run.items]
        completed = sum(1 for item in refreshed_items if item.status == "completed")
        failed = sum(1 for item in refreshed_items if item.status == "failed")
        skipped = sum(1 for item in refreshed_items if item.status == "skipped")
        has_active = any(item.status in {"pending", "running"} for item in refreshed_items)
        status = workflow_run_status(
            completed=completed,
            failed=failed,
            skipped=skipped,
            running=has_active,
        )
        finished_at = None if has_active else run.finished_at or utc_now()
        refreshed_run = replace(
            run,
            status=status,
            completed=completed,
            failed=failed,
            skipped=skipped,
            finished_at=finished_at,
            items=refreshed_items,
        )
        self.repository.update_run(refreshed_run)
        return refreshed_run

    def close(self) -> None:
        self.repository.close()

    def _refresh_item_status(self, item: WorkflowRunItem) -> WorkflowRunItem:
        if not item.job_ids:
            return item
        repository = JobRepository(self.db_path)
        try:
            jobs = repository.list_by_ids(item.job_ids)
        finally:
            repository.close()

        if len(jobs) != len(item.job_ids):
            refreshed = replace(
                item,
                status="failed",
                error_message="Workflow item cannot be resolved: a linked job is missing.",
                finished_at=item.finished_at or utc_now(),
            )
        elif any(job.status in ACTIVE_JOB_STATUSES for job in jobs):
            refreshed = replace(item, status="running", finished_at=None)
        elif any(job.status in FAILED_JOB_STATUSES for job in jobs):
            messages = [job.error_message for job in jobs if job.error_message]
            refreshed = replace(
                item,
                status="failed",
                error_message=messages[0] if messages else item.error_message,
                finished_at=item.finished_at or utc_now(),
            )
        else:
            refreshed = replace(
                item,
                status="completed",
                error_message=None,
                finished_at=item.finished_at or utc_now(),
            )
        if refreshed != item:
            self.repository.update_item(refreshed)
        return refreshed

    def _requeue_interrupted_item_jobs(self, run: WorkflowRun) -> None:
        running_job_ids: list[str] = []
        for item in run.items:
            if item.status != "running" or not item.job_ids:
                continue
            repository = JobRepository(self.db_path)
            try:
                jobs = repository.list_by_ids(item.job_ids)
            finally:
                repository.close()
            running_job_ids.extend(job.id for job in jobs if job.status == "running")
        if not running_job_ids:
            return
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            service.requeue_interrupted_jobs(running_job_ids)
        finally:
            service.close()

    def _recover_active_orphan_jobs(self) -> WorkflowRun | None:
        job_repository = JobRepository(self.db_path)
        try:
            orphan_jobs = job_repository.list_active_orphan_jobs()
        finally:
            job_repository.close()
        if not orphan_jobs:
            return None

        now = utc_now()
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            status="running",
            total=1,
            completed=0,
            failed=0,
            skipped=0,
            concurrency=1,
            source="startup_recovery",
            created_at=now,
        )
        self.repository.create_run(run)
        item_id = self.repository.create_item(
            WorkflowRunItem(
                id=None,
                run_id=run.id,
                draft_id=f"startup-recovery:{run.id}",
                title="Startup recovery",
                status="running",
                job_ids=[job.id for job in orphan_jobs],
                config={
                    "target": {"type": "orphan_jobs", "job_count": len(orphan_jobs)},
                    "actions": ["recover_jobs"],
                },
                request={
                    "source": "startup_recovery",
                    "job_ids": [job.id for job in orphan_jobs],
                },
                created_at=utc_now(),
            )
        )
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            running_job_ids: list[str] = []
            for job in orphan_jobs:
                if job.workflow_run_id is None or job.workflow_item_id is None:
                    updated = replace(
                        job,
                        workflow_run_id=run.id,
                        workflow_item_id=item_id,
                        workflow_source="startup_recovery",
                    )
                    service.repository.update(updated)
                if job.status == "running":
                    running_job_ids.append(job.id)
            service.requeue_interrupted_jobs(running_job_ids)
        finally:
            service.close()
        refreshed = replace(
            run,
            items=self.repository.list_items(run.id),
        )
        return self.refresh_run_status(refreshed)


def request_config_to_dict(request: ScheduledTaskConfigRequest) -> dict[str, object]:
    return scheduled_task_config_to_dict(scheduled_task_config_from_request(request))


def workflow_item_request_to_dict(request: WorkflowBatchItemRequest) -> dict[str, object]:
    return {
        "draft_id": request.draft_id,
        "title": request.title,
        "config": request_config_to_dict(request.config),
        "skip_if_last_run_failed": request.skip_if_last_run_failed,
        "schedule": request.schedule,
        "name": request.name,
        "interval_days": request.interval_days,
        "enabled": request.enabled,
        "run_after_startup": request.run_after_startup,
    }


def workflow_item_request_from_dict(data: dict[str, object]) -> WorkflowBatchItemRequest | None:
    if not data:
        return None
    try:
        return WorkflowBatchItemRequest.model_validate(data)
    except ValueError:
        return None


def workflow_run_status(
    *,
    completed: int,
    failed: int,
    skipped: int,
    running: bool = False,
) -> str:
    if running:
        return "running"
    if failed and completed:
        return "partial"
    if failed and not completed:
        return "failed"
    if skipped and not completed:
        return "skipped"
    return "completed"
