from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.core.errors import InsufficientDiskSpaceError, PixivDownloaderError
from backend.domain.entities import Job, ScheduledTask
from backend.domain.types import ScheduledTaskAction, ScheduledTaskStatus
from backend.repositories._time import utc_now
from backend.repositories.job_repository import JobRepository
from backend.repositories.scheduled_task_repository import ScheduledTaskRepository
from backend.services.job_service import JobService


class ScheduledTaskService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.repository = ScheduledTaskRepository(db_path)

    def create_task(
        self,
        *,
        name: str,
        action: ScheduledTaskAction,
        target_artist_id: str,
        interval_days: int,
        enabled: bool = True,
        run_after_startup: bool = True,
    ) -> ScheduledTask:
        if interval_days < 1:
            raise ValueError("interval_days must be at least 1")
        now = utc_now()
        task = ScheduledTask(
            id=None,
            name=name.strip() or default_task_name(action, target_artist_id),
            action=action,
            status="active" if enabled else "paused",
            target_artist_id=target_artist_id.strip(),
            interval_days=interval_days,
            run_after_startup=run_after_startup,
            next_run_at=now,
        )
        return self.repository.create(task)

    def list_tasks(self) -> list[ScheduledTask]:
        return self.repository.list()

    def get_task(self, task_id: int) -> ScheduledTask | None:
        return self.repository.get_by_id(task_id)

    def update_task(
        self,
        task_id: int,
        *,
        name: str | None = None,
        action: ScheduledTaskAction | None = None,
        status: ScheduledTaskStatus | None = None,
        target_artist_id: str | None = None,
        interval_days: int | None = None,
        run_after_startup: bool | None = None,
    ) -> ScheduledTask | None:
        task = self.repository.get_by_id(task_id)
        if task is None:
            return None
        if interval_days is not None and interval_days < 1:
            raise ValueError("interval_days must be at least 1")
        next_run_at = task.next_run_at
        resolved_status = status or task.status
        if resolved_status == "active" and task.status != "active" and next_run_at is None:
            next_run_at = utc_now()
        updated = replace(
            task,
            name=(name.strip() if name is not None and name.strip() else task.name),
            action=action or task.action,
            status=resolved_status,
            target_artist_id=target_artist_id.strip()
            if target_artist_id is not None
            else task.target_artist_id,
            interval_days=interval_days or task.interval_days,
            run_after_startup=task.run_after_startup
            if run_after_startup is None
            else run_after_startup,
            next_run_at=next_run_at,
            last_error_code=None if resolved_status == "active" else task.last_error_code,
            last_error_message=None if resolved_status == "active" else task.last_error_message,
        )
        self.repository.update(updated)
        return self.repository.get_by_id(task_id)

    def delete_task(self, task_id: int) -> bool:
        return self.repository.delete(task_id)

    def run_due_tasks(self, *, startup_scan: bool = False) -> list[ScheduledTaskRunResult]:
        now = utc_now()
        results: list[ScheduledTaskRunResult] = []
        for task in self.repository.due(now):
            if not task.id:
                continue
            if startup_scan and not task.run_after_startup:
                skipped = self._skip_startup_missed_task(task, now=now)
                results.append(
                    ScheduledTaskRunResult(
                        task=skipped,
                        job=None,
                        created=False,
                        skipped=True,
                    )
                )
                continue
            results.append(self.run_task(task.id, manual=False))
        return results

    def run_task(self, task_id: int, *, manual: bool) -> ScheduledTaskRunResult:
        task = self.repository.get_by_id(task_id)
        if task is None:
            raise ValueError(f"scheduled task not found: {task_id}")
        if task.status == "paused" and not manual:
            return ScheduledTaskRunResult(task=task, job=None, created=False, skipped=True)

        now = utc_now()
        active_job = self._find_active_job(task)
        if active_job is not None:
            updated = self._mark_success(task, now=now, job=active_job)
            return ScheduledTaskRunResult(
                task=updated,
                job=active_job,
                created=False,
                skipped=True,
            )

        try:
            job = self._create_job(task)
        except InsufficientDiskSpaceError as exc:
            updated = replace(
                task,
                status="blocked",
                last_run_at=now,
                next_run_at=None,
                last_error_code="insufficient_disk_space",
                last_error_message=str(exc),
            )
            self.repository.update(updated)
            return ScheduledTaskRunResult(
                task=self.repository.get_by_id(task.id or task_id) or updated,
                job=None,
                created=False,
                skipped=False,
            )
        except PixivDownloaderError as exc:
            updated = replace(
                task,
                last_run_at=now,
                next_run_at=next_time(now, task.interval_days),
                last_error_code=type(exc).__name__,
                last_error_message=str(exc),
            )
            self.repository.update(updated)
            return ScheduledTaskRunResult(
                task=self.repository.get_by_id(task.id or task_id) or updated,
                job=None,
                created=False,
                skipped=False,
            )

        updated = self._mark_success(task, now=now, job=job)
        return ScheduledTaskRunResult(task=updated, job=job, created=True, skipped=False)

    def close(self) -> None:
        self.repository.close()

    def _create_job(self, task: ScheduledTask) -> Job:
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            if task.action == "sync_artist":
                return service.create_download_job(
                    user_id=task.target_artist_id,
                    artwork_id=None,
                    sync_only=True,
                )
            if task.action == "retry_failed_artist":
                return service.create_download_job(
                    user_id=task.target_artist_id,
                    artwork_id=None,
                    retry_failed_artist=True,
                )
            return service.create_download_job(
                user_id=task.target_artist_id,
                artwork_id=None,
            )
        finally:
            service.close()

    def _find_active_job(self, task: ScheduledTask) -> Job | None:
        repository = JobRepository(self.db_path)
        try:
            return repository.find_active(
                job_type=job_type_for_action(task.action),
                user_id=task.target_artist_id,
            )
        finally:
            repository.close()

    def _mark_success(self, task: ScheduledTask, *, now: str, job: Job) -> ScheduledTask:
        updated = replace(
            task,
            status="active",
            last_run_at=now,
            last_success_at=now,
            next_run_at=next_time(now, task.interval_days),
            last_job_id=job.id,
            last_error_code=None,
            last_error_message=None,
        )
        self.repository.update(updated)
        return self.repository.get_by_id(task.id or 0) or updated

    def _skip_startup_missed_task(self, task: ScheduledTask, *, now: str) -> ScheduledTask:
        updated = replace(
            task,
            next_run_at=next_time(now, task.interval_days),
            last_error_code=None,
            last_error_message=None,
        )
        self.repository.update(updated)
        return self.repository.get_by_id(task.id or 0) or updated


class ScheduledTaskRunResult:
    def __init__(
        self,
        *,
        task: ScheduledTask,
        job: Job | None,
        created: bool,
        skipped: bool,
    ) -> None:
        self.task = task
        self.job = job
        self.created = created
        self.skipped = skipped


def job_type_for_action(action: ScheduledTaskAction) -> str:
    if action == "sync_artist":
        return "sync_artist"
    if action == "retry_failed_artist":
        return "retry_failed_artist"
    return "download_artist"


def default_task_name(action: ScheduledTaskAction, artist_id: str) -> str:
    labels = {
        "sync_artist": "Sync artist",
        "download_artist": "Download artist",
        "retry_failed_artist": "Retry failed artist",
    }
    return f"{labels[action]} {artist_id}"


def next_time(from_time: str, interval_days: int) -> str:
    return (
        parse_time(from_time) + timedelta(days=interval_days)
    ).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
