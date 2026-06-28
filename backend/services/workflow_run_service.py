from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from backend.repositories._time import utc_now
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
from backend.services.scheduled_task_service import ScheduledTaskService


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

    def process_run(self, run_id: str) -> WorkflowRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"workflow run not found: {run_id}")
        completed = 0
        failed = 0
        skipped = 0
        previous_failed: set[str] = set()

        for item in self.repository.list_items(run.id):
            if item.status in {"completed", "failed", "skipped"}:
                completed += 1 if item.status == "completed" else 0
                failed += 1 if item.status == "failed" else 0
                skipped += 1 if item.status == "skipped" else 0
                if item.status == "failed":
                    previous_failed.add(item.draft_id)
                continue
            if item.status == "running" and item.job_ids:
                completed += 1
                self.repository.update_item(
                    replace(
                        item,
                        status="completed",
                        finished_at=item.finished_at or utc_now(),
                    )
                )
                continue
            request = workflow_item_request_from_dict(item.request)
            if request is None:
                failed += 1
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
                skipped += 1
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
                    jobs = task_service.run_config(config)
            except Exception as exc:
                failed += 1
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
                completed += 1
                self.repository.update_item(
                    replace(
                        item,
                        status="completed",
                        job_ids=[job.id for job in jobs],
                        finished_at=utc_now(),
                    )
                )
            finally:
                task_service.close()

        status = workflow_run_status(completed=completed, failed=failed, skipped=skipped)
        run = replace(
            run,
            status=status,
            completed=completed,
            failed=failed,
            skipped=skipped,
            finished_at=utc_now(),
            items=self.repository.list_items(run.id),
        )
        self.repository.update_run(run)
        return run

    def recover_interrupted_runs(self) -> list[WorkflowRun]:
        recovered: list[WorkflowRun] = []
        for run in self.repository.list_runs_by_status("running"):
            recovered.append(self.process_run(run.id))
        return recovered

    def list_runs(self, *, limit: int = 5, offset: int = 0) -> tuple[list[WorkflowRun], int]:
        return self.repository.list_runs(limit=limit, offset=offset), self.repository.count_runs()

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self.repository.get_run(run_id)

    def close(self) -> None:
        self.repository.close()


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


def workflow_run_status(*, completed: int, failed: int, skipped: int) -> str:
    if failed and completed:
        return "partial"
    if failed and not completed:
        return "failed"
    if skipped and not completed:
        return "skipped"
    return "completed"
