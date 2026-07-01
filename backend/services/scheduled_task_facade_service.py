from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backend.core.errors import InsufficientDiskSpaceError
from backend.domain.entities import ScheduledTask, ScheduledTaskConfig
from backend.domain.types import ScheduledTaskAction, ScheduledTaskStatus
from backend.repositories._time import utc_now
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_definition_repository import (
    WorkflowDefinition,
    WorkflowDefinitionRepository,
    WorkflowTrigger,
)
from backend.repositories.workflow_run_repository import WorkflowRun
from backend.schemas.failure_reasons import failure_detail_from_exception
from backend.services.scheduled_task_service import ScheduledTaskRunResult, workflow_run_job_ids
from backend.services.scheduled_workflow_compiler import (
    legacy_config,
    scheduled_task_definition,
    scheduled_task_downloads,
)
from backend.services.settings_service import AppSettingsService
from backend.services.storage_service import check_free_space
from backend.services.workflow_schedule_service import WorkflowScheduleService, next_run_time


class ScheduledTaskFacadeService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.repository = WorkflowDefinitionRepository(db_path)

    def create_task(
        self,
        *,
        name: str,
        action: ScheduledTaskAction,
        target_artist_id: str,
        interval_days: int,
        enabled: bool = True,
        run_after_startup: bool = True,
        config: ScheduledTaskConfig | None = None,
    ) -> ScheduledTask:
        if interval_days < 1:
            raise ValueError("interval_days must be at least 1")
        task = ScheduledTask(
            id=None,
            name=name.strip() or default_compat_task_name(action, target_artist_id),
            action=action,
            status="active" if enabled else "paused",
            target_artist_id=target_artist_id,
            interval_days=interval_days,
            run_after_startup=run_after_startup,
            config=config,
        )
        definition = self._upsert_definition(task)
        schedule = schedule_from_task(task)
        trigger = self.repository.create_trigger(
            WorkflowTrigger(
                id=None,
                workflow_definition_id=definition.id,
                status=task.status,
                schedule=schedule,
                next_run_at=next_run_time(
                    schedule,
                    from_time=definition.updated_at or definition.created_at or utc_epoch(),
                )
                if task.status == "active"
                else None,
            )
        )
        return task_from_definition(definition, trigger)

    def list_tasks(self) -> list[ScheduledTask]:
        tasks: list[ScheduledTask] = []
        for item in self.repository.list_definitions():
            for trigger in item.triggers:
                if is_compat_schedule(item.definition, trigger):
                    tasks.append(task_from_definition(item.definition, trigger))
        return tasks

    def get_task(self, task_id: int) -> ScheduledTask | None:
        loaded = self._load_task(task_id)
        if loaded is None:
            return None
        definition, trigger = loaded
        return task_from_definition(definition, trigger)

    def activate_inactive_tasks(self) -> list[ScheduledTask]:
        return []

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
        config: ScheduledTaskConfig | None = None,
    ) -> ScheduledTask | None:
        loaded = self._load_task(task_id)
        if loaded is None:
            return None
        definition, trigger = loaded
        current = task_from_definition(definition, trigger)
        if interval_days is not None and interval_days < 1:
            raise ValueError("interval_days must be at least 1")
        updated = replace(
            current,
            name=(name.strip() if name is not None and name.strip() else current.name),
            action=action or current.action,
            status=status or current.status,
            target_artist_id=target_artist_id.strip()
            if target_artist_id is not None
            else current.target_artist_id,
            interval_days=interval_days or current.interval_days,
            run_after_startup=current.run_after_startup
            if run_after_startup is None
            else run_after_startup,
            config=config or current.config,
        )
        saved = self._upsert_definition(updated, definition_id=definition.id)
        schedule = schedule_from_task(updated)
        next_run_at = trigger.next_run_at
        if updated.status == "active" and current.status != "active":
            next_run_at = next_run_time(
                schedule,
                from_time=saved.updated_at or saved.created_at or utc_epoch(),
            )
        if updated.status != "active":
            next_run_at = None
        self.repository.update_trigger(
            replace(
                trigger,
                status=updated.status,
                schedule=schedule,
                next_run_at=next_run_at,
                last_error_code=None if updated.status == "active" else trigger.last_error_code,
                last_error_message=(
                    None if updated.status == "active" else trigger.last_error_message
                ),
            )
        )
        reloaded = self._load_task(task_id)
        if reloaded is None:
            return None
        return task_from_definition(*reloaded)

    def delete_task(self, task_id: int) -> bool:
        return self.repository.delete_trigger(task_id)

    def run_task(self, task_id: int, *, manual: bool) -> ScheduledTaskRunResult:
        loaded = self._load_task(task_id)
        if loaded is None:
            raise ValueError(f"scheduled task {task_id} was not found")
        definition, trigger = loaded
        task = task_from_definition(definition, trigger)
        if task.config is not None and scheduled_task_downloads(task.config):
            try:
                self._ensure_download_space()
            except InsufficientDiskSpaceError as exc:
                failure = failure_detail_from_exception(exc)
                blocked = replace(
                    trigger,
                    status="blocked",
                    last_run_at=utc_now(),
                    next_run_at=None,
                    last_error_code=failure.code,
                    last_error_message=str(exc),
                )
                self.repository.update_trigger(blocked)
                return ScheduledTaskRunResult(
                    task=task_from_definition(
                        definition,
                        self.repository.get_trigger(task_id) or blocked,
                    ),
                    jobs=[],
                    workflow_run_id=None,
                    created=False,
                    skipped=False,
                )
        schedule_service = WorkflowScheduleService(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            run = schedule_service.run_definition(
                definition.id,
                source="manual_schedule" if manual else "workflow_trigger",
                trigger_id=trigger.id,
            )
        finally:
            schedule_service.close()
        jobs = self._jobs_for_run(run)
        now = utc_now()
        updated_trigger = replace(
            trigger,
            last_run_at=now,
            last_success_at=now,
            last_error_code=None,
            last_error_message=None,
        )
        self.repository.update_trigger(updated_trigger)
        refreshed_trigger = self.repository.get_trigger(task_id) or trigger
        refreshed_task = replace(
            task_from_definition(definition, refreshed_trigger),
            last_job_id=jobs[-1].id if jobs else None,
            last_run_summary={
                "created_jobs": len(jobs),
                "job_ids": [job.id for job in jobs],
                "workflow_run_id": run.id,
                "workflow_run_status": run.status,
                "workflow_run_source": run.source,
            },
        )
        return ScheduledTaskRunResult(
            task=refreshed_task,
            jobs=jobs,
            workflow_run_id=run.id,
            created=bool(jobs),
            skipped=not jobs,
        )

    def close(self) -> None:
        self.repository.close()

    def _upsert_definition(
        self,
        task: ScheduledTask,
        *,
        definition_id: str | None = None,
    ) -> WorkflowDefinition:
        config = task.config or legacy_config(task)
        definition = scheduled_task_compat_definition(
            task,
            config,
            db_path=self.db_path,
            settings_json_path=self.settings_json_path,
        )
        service = WorkflowScheduleService(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            return service.save_definition(definition, definition_id=definition_id)
        finally:
            service.close()

    def _load_task(self, task_id: int) -> tuple[WorkflowDefinition, WorkflowTrigger] | None:
        trigger = self.repository.get_trigger(task_id)
        if trigger is None:
            return None
        definition = self.repository.get_definition(trigger.workflow_definition_id)
        if definition is None or not is_compat_schedule(definition, trigger):
            return None
        return definition, trigger

    def _jobs_for_run(self, run: WorkflowRun):
        job_ids = workflow_run_job_ids(run)
        if not job_ids:
            return []
        repository = JobRepository(self.db_path)
        try:
            return repository.list_by_ids(job_ids)
        finally:
            repository.close()

    def _ensure_download_space(self) -> None:
        settings_service = AppSettingsService(
            db_path=self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            settings = settings_service.load()
        finally:
            settings_service.close()
        check_free_space(settings.download_path, settings.min_free_space_gb)


def scheduled_task_compat_definition(
    task: ScheduledTask,
    config: ScheduledTaskConfig,
    *,
    db_path: Path | str | None,
    settings_json_path: Path | str | None,
):
    _ = db_path, settings_json_path
    definition = scheduled_task_definition(task, config)
    dumped = definition.model_dump(mode="json")
    dumped["metadata"] = {
        **dict(dumped.get("metadata") if isinstance(dumped.get("metadata"), dict) else {}),
        "compat_scheduled_task": compat_metadata(task, config),
    }
    return definition.model_validate(dumped)


def compat_metadata(task: ScheduledTask, config: ScheduledTaskConfig) -> dict[str, object]:
    return {
        "action": task.action,
        "target_artist_id": task.target_artist_id,
        "interval_days": task.interval_days,
        "run_after_startup": task.run_after_startup,
        "config": config_to_dict(config),
    }


def is_compat_schedule(definition: WorkflowDefinition, trigger: WorkflowTrigger) -> bool:
    metadata = definition.definition.get("metadata")
    return bool(trigger.schedule.get("compat_scheduled_task")) or (
        isinstance(metadata, dict) and bool(metadata.get("compat_scheduled_task"))
    )


def task_from_definition(
    definition: WorkflowDefinition,
    trigger: WorkflowTrigger,
) -> ScheduledTask:
    meta = compat_meta(definition, trigger)
    config = config_from_meta(meta)
    action = str(meta.get("action") or (config.actions[0] if config.actions else "download_artist"))
    if action not in {"sync_artist", "download_artist", "retry_failed_artist"}:
        action = "download_artist"
    status = trigger.status
    if status not in {"active", "inactive", "paused", "blocked", "archived"}:
        status = "paused"
    return ScheduledTask(
        id=trigger.id,
        name=definition.name,
        action=action,
        status=status,
        target_artist_id=str(meta.get("target_artist_id") or config.target.artist_id or ""),
        interval_days=int(
            meta.get("interval_days") or interval_days_from_schedule(trigger.schedule)
        ),
        run_after_startup=bool(meta.get("run_after_startup", True)),
        last_run_at=trigger.last_run_at,
        last_success_at=trigger.last_success_at,
        next_run_at=trigger.next_run_at,
        last_error_code=trigger.last_error_code,
        last_error_message=trigger.last_error_message,
        config=config,
        last_run_summary=None,
        created_at=trigger.created_at,
        updated_at=trigger.updated_at,
    )


def compat_meta(definition: WorkflowDefinition, trigger: WorkflowTrigger) -> dict[str, object]:
    meta = trigger.schedule.get("compat_scheduled_task")
    if isinstance(meta, dict):
        return meta
    metadata = definition.definition.get("metadata")
    meta = metadata.get("compat_scheduled_task") if isinstance(metadata, dict) else None
    return meta if isinstance(meta, dict) else {}


def schedule_from_task(task: ScheduledTask) -> dict[str, object]:
    return {
        "type": "interval",
        "every": task.interval_days,
        "unit": "days",
        "compat_scheduled_task": {
            "action": task.action,
            "target_artist_id": task.target_artist_id,
            "interval_days": task.interval_days,
            "run_after_startup": task.run_after_startup,
            "config": config_to_dict(task.config or legacy_config(task)),
        },
    }


def interval_days_from_schedule(schedule: dict[str, object]) -> int:
    if schedule.get("type") != "interval" or schedule.get("unit") != "days":
        return 1
    try:
        return max(1, int(schedule.get("every") or 1))
    except (TypeError, ValueError):
        return 1


def utc_epoch() -> str:
    return "1970-01-01T00:00:00Z"


def config_to_dict(config: ScheduledTaskConfig | None) -> dict[str, object]:
    from backend.schemas.scheduled_tasks import scheduled_task_config_to_dict

    return scheduled_task_config_to_dict(config)


def config_from_meta(meta: dict[str, object]) -> ScheduledTaskConfig:
    from backend.schemas.scheduled_tasks import (
        ScheduledTaskConfigRequest,
        scheduled_task_config_from_request,
    )

    raw = meta.get("config")
    if not isinstance(raw, dict):
        return legacy_config(
            ScheduledTask(
                id=None,
                name="",
                action="download_artist",
                status="paused",
                target_artist_id=str(meta.get("target_artist_id") or ""),
                interval_days=interval_days_from_schedule({}),
            )
        )
    return scheduled_task_config_from_request(ScheduledTaskConfigRequest.model_validate(raw))


def default_compat_task_name(action: ScheduledTaskAction, target_artist_id: str) -> str:
    labels = {
        "sync_artist": "Sync artist",
        "download_artist": "Download artist",
        "retry_failed_artist": "Retry failed artist",
    }
    return f"{labels[action]} {target_artist_id}".strip()
