from __future__ import annotations

import calendar
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.domain.workflow_schedule import effective_weekdays
from backend.repositories._time import utc_now
from backend.repositories.workflow_definition_repository import (
    WorkflowDefinition,
    WorkflowDefinitionRepository,
    WorkflowDefinitionWithTriggers,
    WorkflowTrigger,
)
from backend.repositories.workflow_run_repository import WorkflowRun
from backend.schemas.failure_reasons import failure_detail_from_exception
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.settings_service import AppSettingsService


class WorkflowScheduleService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.repository = WorkflowDefinitionRepository(db_path)

    def save_definition(
        self,
        definition: AdvancedWorkflowDefinitionRequest,
        *,
        definition_id: str | None = None,
    ) -> WorkflowDefinition:
        if not definition.nodes:
            raise ValueError("workflow definition requires at least one node")
        workflow_id = definition_id or str(uuid.uuid4())
        return self.repository.upsert_definition(
            WorkflowDefinition(
                id=workflow_id,
                name=definition.name or "Advanced workflow",
                definition=definition.model_dump(mode="json"),
            )
        )

    def save_with_trigger(
        self,
        definition: AdvancedWorkflowDefinitionRequest,
        *,
        schedule: dict[str, object],
        enabled: bool = True,
        definition_id: str | None = None,
        trigger_id: int | None = None,
    ) -> tuple[WorkflowDefinition, WorkflowTrigger]:
        now = utc_now()
        next_run_at = next_run_time(schedule, from_time=now)
        saved = self.save_definition(definition, definition_id=definition_id)
        if trigger_id is not None:
            current = self.repository.get_trigger(trigger_id)
            if current is None:
                raise ValueError(f"workflow trigger not found: {trigger_id}")
            if current.workflow_definition_id != saved.id:
                raise ValueError(
                    f"workflow trigger {trigger_id} does not belong to definition {saved.id}"
                )
            updated = replace(
                current,
                status="active" if enabled else "paused",
                schedule=schedule,
                next_run_at=next_run_at if enabled else None,
                last_error_code=None if enabled else current.last_error_code,
                last_error_message=None if enabled else current.last_error_message,
            )
            self.repository.update_trigger(updated)
            reloaded = self.repository.get_trigger(trigger_id)
            if reloaded is None:
                raise ValueError(f"workflow trigger not found: {trigger_id}")
            return saved, reloaded
        trigger = self.repository.create_trigger(
            WorkflowTrigger(
                id=None,
                workflow_definition_id=saved.id,
                status="active" if enabled else "paused",
                schedule=schedule,
                next_run_at=next_run_at if enabled else None,
            )
        )
        return saved, trigger

    def list_definitions(self) -> list[WorkflowDefinitionWithTriggers]:
        return self.repository.list_definitions()

    def delete_definition(self, definition_id: str) -> bool:
        return self.repository.delete_definition(definition_id)

    def update_trigger_status(self, trigger_id: int, *, status: str) -> WorkflowTrigger:
        if status not in {"active", "paused"}:
            raise ValueError(f"unsupported workflow trigger status: {status}")
        current = self.repository.get_trigger(trigger_id)
        if current is None:
            raise ValueError(f"workflow trigger not found: {trigger_id}")
        now = utc_now()
        updated = replace(
            current,
            status=status,
            next_run_at=(
                next_run_time(current.schedule, from_time=now) if status == "active" else None
            ),
            last_error_code=None if status == "active" else current.last_error_code,
            last_error_message=None if status == "active" else current.last_error_message,
        )
        self.repository.update_trigger(updated)
        reloaded = self.repository.get_trigger(trigger_id)
        if reloaded is None:
            raise ValueError(f"workflow trigger not found: {trigger_id}")
        return reloaded

    def run_definition(
        self,
        definition_id: str,
        *,
        source: str = "advanced_manual",
        trigger_id: int | None = None,
    ) -> WorkflowRun:
        saved = self.repository.get_definition(definition_id)
        if saved is None:
            raise ValueError(f"workflow definition not found: {definition_id}")
        definition = AdvancedWorkflowDefinitionRequest.model_validate(saved.definition)
        runner = AdvancedWorkflowRunner(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            return runner.create_run(
                definition,
                source=source,
                schedule_id=trigger_id,
                definition_id=saved.id,
                name=saved.name,
            )
        finally:
            runner.close()

    def run_due_triggers(self, *, startup_scan: bool = False) -> list[WorkflowTriggerRunResult]:
        owner = str(uuid.uuid4())
        with self.repository.conn:
            claimed = self.repository.conn.execute(
                "INSERT OR IGNORE INTO workflow_scheduler_claim VALUES (1, ?)",
                (owner,),
            ).rowcount
        if not claimed:
            return []
        try:
            return self._run_due_claimed(startup_scan=startup_scan)
        finally:
            with self.repository.conn:
                self.repository.conn.execute(
                    "DELETE FROM workflow_scheduler_claim WHERE owner = ?", (owner,)
                )

    def _run_due_claimed(self, *, startup_scan: bool) -> list[WorkflowTriggerRunResult]:
        now = utc_now()
        self._reconcile_results()
        settings = AppSettingsService(
            db_path=self.db_path, settings_json_path=self.settings_json_path
        )
        try:
            limit = settings.load().max_active_workflow_triggers
        finally:
            settings.close()
        results: list[WorkflowTriggerRunResult] = []
        triggers = self.repository.due_triggers(now)
        if startup_scan:
            seen = {trigger.id for trigger in triggers}
            for item in self.repository.list_definitions():
                for trigger in item.triggers:
                    compat = (
                        trigger.schedule.get("compat_scheduled_task")
                        or trigger.schedule.get("compat_workflow_trigger")
                        or {}
                    )
                    startup = trigger.schedule.get(
                        "run_after_startup", compat.get("run_after_startup", False)
                    )
                    if startup and trigger.status == "active" and trigger.id not in seen:
                        triggers.append(trigger)
        for trigger in triggers:
            if trigger.id is None:
                continue
            active = self.repository.conn.execute(
                "SELECT schedule_id FROM workflow_runs "
                "WHERE status = 'running' AND schedule_id IS NOT NULL"
            ).fetchall()
            if len(active) >= limit:
                break
            if any(row["schedule_id"] == trigger.id for row in active):
                continue
            try:
                run = self.run_definition(
                    trigger.workflow_definition_id,
                    source="workflow_trigger",
                    trigger_id=trigger.id,
                )
            except Exception as exc:
                failure = failure_detail_from_exception(exc)
                next_run_at = next_run_time(trigger.schedule, from_time=now)
                updated = replace(
                    trigger,
                    next_run_at=next_run_at,
                    last_run_at=now,
                    last_error_code=failure.code,
                    last_error_message=str(exc),
                )
                self.repository.update_trigger(updated)
                results.append(WorkflowTriggerRunResult(trigger=updated, run=None, created=False))
                continue
            next_run_at = next_run_time(trigger.schedule, from_time=now)
            updated = replace(
                trigger,
                next_run_at=next_run_at,
                last_run_at=now,
                last_error_code=None,
                last_error_message=None,
            )
            self.repository.update_trigger(updated)
            results.append(WorkflowTriggerRunResult(trigger=updated, run=run, created=True))
        self._reconcile_results()
        return results

    def _reconcile_results(self) -> None:
        for item in self.repository.list_definitions():
            for trigger in item.triggers:
                row = self.repository.conn.execute(
                    "SELECT * FROM workflow_runs WHERE schedule_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (trigger.id,),
                ).fetchone()
                if row is None or row["status"] == "running" or row["finished_at"] is None:
                    continue
                if trigger.last_run_at and parse_time(row["created_at"]) < parse_time(
                    trigger.last_run_at
                ):
                    # An older success must not erase a newer dispatch failure.
                    continue
                if row["status"] == "completed":
                    updated = replace(
                        trigger,
                        last_success_at=row["finished_at"],
                        last_error_code=None,
                        last_error_message=None,
                    )
                else:
                    updated = replace(
                        trigger,
                        last_error_code="workflow_" + row["status"],
                        last_error_message=f"Workflow execution ended as {row['status']}",
                    )
                if updated != trigger:
                    self.repository.update_trigger(updated)

    def close(self) -> None:
        self.repository.close()


class WorkflowTriggerRunResult:
    def __init__(
        self,
        *,
        trigger: WorkflowTrigger,
        run: WorkflowRun | None,
        created: bool,
    ) -> None:
        self.trigger = trigger
        self.run = run
        self.created = created


def next_run_time(schedule: dict[str, object], *, from_time: str) -> str:
    base = parse_time(from_time)
    schedule_type = str(schedule.get("type") or "interval")
    if schedule_type in {"daily", "weekly", "monthly"}:
        base = base.astimezone(ZoneInfo(str(schedule.get("timezone") or "UTC")))
    if schedule_type == "daily":
        return isoformat_utc(next_daily(base, time_text(schedule.get("time"))))
    if schedule_type == "weekly":
        weekdays = effective_weekdays(schedule.get("days_of_week"))
        return isoformat_utc(
            next_weekly(base, weekdays or [base.isoweekday()], time_text(schedule.get("time")))
        )
    if schedule_type == "monthly":
        return isoformat_utc(
            next_monthly(base, schedule.get("day"), time_text(schedule.get("time")))
        )
    every = positive_int(schedule.get("every"), default=1)
    unit = str(schedule.get("unit") or "days")
    delta = {
        "minutes": timedelta(minutes=every),
        "hours": timedelta(hours=every),
        "days": timedelta(days=every),
    }.get(unit, timedelta(days=every))
    return (base + delta).isoformat().replace("+00:00", "Z")


def next_daily(base: datetime, time: tuple[int, int]) -> datetime:
    candidate = base.replace(hour=time[0], minute=time[1], second=0, microsecond=0, fold=0)
    if candidate.astimezone(UTC) <= base.astimezone(UTC):
        candidate += timedelta(days=1)
    return candidate


def next_weekly(base: datetime, weekdays: list[int], time: tuple[int, int]) -> datetime:
    for offset in range(0, 8):
        day = base + timedelta(days=offset)
        if day.isoweekday() not in weekdays:
            continue
        candidate = day.replace(hour=time[0], minute=time[1], second=0, microsecond=0, fold=0)
        if candidate.astimezone(UTC) > base.astimezone(UTC):
            return candidate
    return (base + timedelta(days=7)).replace(
        hour=time[0], minute=time[1], second=0, microsecond=0, fold=0
    )


def next_monthly(base: datetime, day_value: object, time: tuple[int, int]) -> datetime:
    year = base.year
    month = base.month
    for _ in range(14):
        last_day = calendar.monthrange(year, month)[1]
        if day_value == "last":
            day = last_day
        else:
            day = min(max(1, positive_int(day_value, default=1)), last_day)
        candidate = base.replace(
            year=year,
            month=month,
            day=day,
            hour=time[0],
            minute=time[1],
            second=0,
            microsecond=0,
            fold=0,
        )
        if candidate.astimezone(UTC) > base.astimezone(UTC):
            return candidate
        month += 1
        if month > 12:
            month = 1
            year += 1
    return base + timedelta(days=31)


def positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def time_text(value: object) -> tuple[int, int]:
    if not isinstance(value, str):
        return (0, 0)
    hour_text, _, minute_text = value.partition(":")
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return (0, 0)
    return (min(max(hour, 0), 23), min(max(minute, 0), 59))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
