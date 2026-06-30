from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from backend.services.scheduled_task_service import ScheduledTaskService
from backend.services.workflow_schedule_service import WorkflowScheduleService
from backend.workers.job_queue import JobQueue

logger = logging.getLogger(__name__)


class ScheduledTaskRunner:
    def __init__(
        self,
        *,
        db_path: Path | str | None = None,
        settings_json_path: Path | str | None = None,
        queue: JobQueue,
        poll_interval_seconds: float = 60.0,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.queue = queue
        self.poll_interval_seconds = poll_interval_seconds
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._startup_scan = True

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._startup_scan = True
            self._task = asyncio.create_task(
                self._run(),
                name="pixiv-scheduled-task-runner",
            )

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def wake(self) -> None:
        self._wake_event.set()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            created_any = await asyncio.to_thread(self._run_due_once, self._startup_scan)
            self._startup_scan = False
            if created_any:
                self.queue.wake()
            self._wake_event.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._wake_event.wait(),
                    timeout=self.poll_interval_seconds,
                )

    def _run_due_once(self, startup_scan: bool) -> bool:
        legacy_service = ScheduledTaskService(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        workflow_service = WorkflowScheduleService(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            legacy_service.activate_inactive_tasks()
            results = legacy_service.run_due_tasks(startup_scan=startup_scan)
            workflow_results = workflow_service.run_due_triggers()
        except Exception:
            logger.exception("scheduled task scan failed")
            return False
        finally:
            legacy_service.close()
            workflow_service.close()
        return any(result.created for result in results) or any(
            result.created for result in workflow_results
        )
