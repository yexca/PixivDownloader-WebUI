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

        completed = 0
        failed = 0
        skipped = 0
        previous_failed: set[str] = set()

        for request in items:
            config = scheduled_task_config_from_request(request.config)
            config_dict = scheduled_task_config_to_dict(config)
            previous_status = self.repository.last_item_status(request.draft_id)
            item = WorkflowRunItem(
                id=None,
                run_id=run.id,
                draft_id=request.draft_id,
                title=request.title,
                status="running",
                config=config_dict,
                created_at=utc_now(),
            )
            item_id = self.repository.create_item(item)
            item = replace(item, id=item_id)

            if (
                request.skip_if_last_run_failed
                and (request.draft_id in previous_failed or previous_status == "failed")
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

        status = "completed"
        if failed and completed:
            status = "partial"
        elif failed and not completed:
            status = "failed"
        elif skipped and not completed:
            status = "skipped"

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

    def list_runs(self, *, limit: int = 5, offset: int = 0) -> tuple[list[WorkflowRun], int]:
        return self.repository.list_runs(limit=limit, offset=offset), self.repository.count_runs()

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self.repository.get_run(run_id)

    def close(self) -> None:
        self.repository.close()


def request_config_to_dict(request: ScheduledTaskConfigRequest) -> dict[str, object]:
    return scheduled_task_config_to_dict(scheduled_task_config_from_request(request))
