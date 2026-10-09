from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from backend.repositories.job_repository import JobRepository
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.job_service import JobService
from backend.services.settings_service import AppSettingsService
from backend.workers.download_worker import DownloadWorker

logger = logging.getLogger(__name__)


class JobQueue:
    def __init__(
        self,
        *,
        db_path: Path | str | None = None,
        settings_json_path: Path | str | None = None,
        worker: DownloadWorker | None = None,
        poll_interval_seconds: float = 0.2,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.worker = worker or DownloadWorker(
            db_path=db_path, settings_json_path=settings_json_path
        )
        self.poll_interval_seconds = poll_interval_seconds
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._paused = False
        self._task: asyncio.Task[None] | None = None
        self._active: dict[str, asyncio.Task] = {}
        self.last_error: str | None = None
        self.consecutive_errors = 0

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            if hasattr(self.worker, "stop_event"):
                self.worker.stop_event.clear()
            self._task = asyncio.create_task(self._run(), name="pixiv-download-job-queue")

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if hasattr(self.worker, "stop_event"):
            self.worker.stop_event.set()
        # to_thread cancellation does not stop a thread. Wait for cooperative shutdown.
        if self._task is not None:
            await self._task
        if self._active:
            await asyncio.gather(*self._active.values(), return_exceptions=True)
        self._active.clear()

    def wake(self) -> None:
        self._wake_event.set()

    def pause(self) -> None:
        self._paused = True
        self.wake()

    def resume(self) -> None:
        self._paused = False
        self.wake()

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def healthy(self) -> bool:
        return self._task is not None and not self._task.done() and self.last_error is None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            delay = self.poll_interval_seconds
            try:
                for job_id, task in list(self._active.items()):
                    if task.done():
                        try:
                            task.result()
                        except Exception:
                            self._requeue_unfinished(job_id)
                            del self._active[job_id]
                            raise
                        del self._active[job_id]
                if not self._paused:
                    await asyncio.to_thread(self._advance_workflows)
                    capacity = await asyncio.to_thread(self._capacity)
                    while len(self._active) < capacity and not self._stop_event.is_set():
                        job_id = await asyncio.to_thread(self._next_queued_job_id)
                        if job_id is None:
                            break
                        self._active[job_id] = asyncio.create_task(
                            asyncio.to_thread(self.worker.run_job, job_id)
                        )
                self.last_error = None
                self.consecutive_errors = 0
            except Exception as exc:
                self.consecutive_errors += 1
                self.last_error = type(exc).__name__
                delay = min(
                    30.0,
                    max(0.1, self.poll_interval_seconds) * 2 ** min(self.consecutive_errors, 8),
                )
                logger.exception("job queue iteration failed; retrying in %.1fs", delay)
            self._wake_event.clear()
            if not self._stop_event.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake_event.wait(), timeout=delay)

    def _capacity(self) -> int:
        service = AppSettingsService(
            db_path=self.db_path, settings_json_path=self.settings_json_path
        )
        try:
            return service.load().max_concurrent_downloads
        finally:
            service.close()

    def _requeue_unfinished(self, job_id: str) -> None:
        repository = JobRepository(self.db_path)
        try:
            with repository.conn:
                repository.conn.execute(
                    "UPDATE jobs SET status = 'queued' WHERE id = ? AND status = 'running'",
                    (job_id,),
                )
        finally:
            repository.close()

    def _advance_workflows(self) -> None:
        runner = AdvancedWorkflowRunner(self.db_path, settings_json_path=self.settings_json_path)
        try:
            for run in runner.repository.list_runs_by_status("running"):
                runner.process_run(run.id)
        finally:
            runner.close()

    def _next_queued_job_id(self) -> str | None:
        self._activate_waiting_one_time_jobs()
        repository = JobRepository(self.db_path)
        try:
            job = repository.next_queued()
            if job is None:
                return None
            with repository.conn:
                claimed = repository.conn.execute(
                    "UPDATE jobs SET status = 'running' WHERE id = ? AND status = 'queued'",
                    (job.id,),
                ).rowcount
            return job.id if claimed else None
        finally:
            repository.close()

    def _activate_waiting_one_time_jobs(self) -> None:
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            service.activate_inactive_one_time_jobs()
        finally:
            service.close()
