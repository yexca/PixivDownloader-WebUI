from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from backend.repositories.job_repository import JobRepository
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
        self.worker = worker or DownloadWorker(
            db_path=db_path,
            settings_json_path=settings_json_path,
        )
        self.poll_interval_seconds = poll_interval_seconds
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(), name="pixiv-download-job-queue")

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
            job_id = self._next_queued_job_id()
            if job_id is None:
                self._wake_event.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._wake_event.wait(),
                        timeout=self.poll_interval_seconds,
                    )
                continue
            await asyncio.to_thread(self.worker.run_job, job_id)

    def _next_queued_job_id(self) -> str | None:
        repository = JobRepository(self.db_path)
        try:
            job = repository.next_queued()
            return job.id if job is not None else None
        finally:
            repository.close()
