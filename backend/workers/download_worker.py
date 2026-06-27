from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from backend.core.errors import JobCancelledError
from backend.domain.entities import DownloadProgress, Job, JobEvent
from backend.repositories._time import utc_now
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.repositories.job_repository import JobRepository
from backend.services.download_service import DownloadOptions, DownloadService
from backend.services.file_downloader import FileDownloader
from backend.services.library_sync_service import LibrarySyncService
from backend.services.pixiv_client import PixivClient, PixivClientProtocol
from backend.services.random_sleep import RandomSleep
from backend.services.settings_service import AppSettingsService

logger = logging.getLogger(__name__)


class PixivClientFactory(Protocol):
    def __call__(self) -> PixivClientProtocol: ...


class FileDownloaderFactory(Protocol):
    def __call__(self) -> FileDownloader: ...


class DownloadWorker:
    def __init__(
        self,
        *,
        db_path: Path | str | None = None,
        settings_json_path: Path | str | None = None,
        pixiv_client_factory: PixivClientFactory | None = None,
        file_downloader_factory: FileDownloaderFactory | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.pixiv_client_factory = pixiv_client_factory or self._create_pixiv_client
        self.file_downloader_factory = file_downloader_factory or self._create_file_downloader

    def run_job(self, job_id: str) -> Job:
        repository = JobRepository(self.db_path)
        try:
            job = repository.get_by_id(job_id)
            if job is None:
                raise ValueError(f"job not found: {job_id}")
            if job.cancel_requested or job.status == "cancelled":
                return self._finish(repository, job, "cancelled", "Job cancelled before start")

            job = self._start(repository, job)
            if job.type == "sync_artist":
                return self._run_sync_job(repository, job)
            service = DownloadService(
                pixiv_client=self.pixiv_client_factory(),
                file_downloader=self.file_downloader_factory(),
                artist_repository=ArtistRepository(self.db_path),
                name_history_repository=ArtistNameHistoryRepository(self.db_path),
                artwork_repository=ArtworkRepository(self.db_path),
                file_repository=ArtworkFileRepository(self.db_path),
                sleeper=lambda: None,
            )
            options = DownloadOptions(
                force_rescan=job.type == "rescan_artist",
                retry_failed=job.type in {"retry_failed", "retry_failed_artist"},
                full_download=bool(job.options.get("full_download", False)),
                max_artworks=positive_int_option(job.options.get("max_artworks")),
                min_artwork_id=string_option(job.options.get("min_artwork_id")),
                max_artwork_id=string_option(job.options.get("max_artwork_id")),
            )
            summary = service.download(
                user_id=job.input_user_id,
                artwork_id=job.input_artwork_id,
                options=options,
                progress_callback=lambda progress: self._record_progress(
                    repository,
                    job.id,
                    progress,
                ),
                cancel_callback=lambda: self._is_cancel_requested(repository, job.id),
            )
            finished = replace(
                repository.get_by_id(job.id) or job,
                status="completed",
                artist_id=summary.artist.id,
                total_files=summary.total_files,
                completed_files=summary.downloaded_files,
                skipped_files=summary.skipped_files,
                failed_files=summary.failed_files,
                finished_at=utc_now(),
            )
            repository.update(finished)
            repository.add_event(JobEvent(job_id=job.id, level="info", message="Job completed"))
            return repository.get_by_id(job.id) or finished
        except JobCancelledError:
            latest = repository.get_by_id(job_id)
            if latest is None:
                raise
            return self._finish(repository, latest, "cancelled", "Job cancelled")
        except Exception as exc:
            logger.exception("download job failed: %s", job_id)
            latest = repository.get_by_id(job_id)
            if latest is None:
                raise
            return self._finish(
                repository,
                latest,
                "failed",
                user_safe_error_message(exc),
                level="error",
                payload={"error_type": type(exc).__name__},
            )
        finally:
            repository.close()

    def _run_sync_job(self, repository: JobRepository, job: Job) -> Job:
        if not job.input_user_id:
            raise ValueError("sync artist job requires user ID")
        service = LibrarySyncService(
            pixiv_client=self.pixiv_client_factory(),
            artist_repository=ArtistRepository(self.db_path),
            name_history_repository=ArtistNameHistoryRepository(self.db_path),
            artwork_repository=ArtworkRepository(self.db_path),
            file_repository=ArtworkFileRepository(self.db_path),
        )
        try:
            repository.add_event(
                JobEvent(job_id=job.id, level="info", message="Syncing Pixiv metadata")
            )
            summary = service.sync_artist(job.input_user_id)
        finally:
            service.close()
        finished = replace(
            repository.get_by_id(job.id) or job,
            status="completed",
            artist_id=summary.artist.id,
            total_files=summary.file_count,
            skipped_files=summary.file_count,
            finished_at=utc_now(),
        )
        repository.update(finished)
        repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message=(f"Synced {summary.artwork_count} artworks and {summary.file_count} files"),
            )
        )
        return repository.get_by_id(job.id) or finished

    def _start(self, repository: JobRepository, job: Job) -> Job:
        running = replace(job, status="running", started_at=utc_now())
        repository.update(running)
        repository.add_event(JobEvent(job_id=job.id, level="info", message="Job started"))
        return running

    def _finish(
        self,
        repository: JobRepository,
        job: Job,
        status: str,
        message: str,
        *,
        level: str = "info",
        payload: dict[str, object] | None = None,
    ) -> Job:
        finished = replace(
            job,
            status=status,  # type: ignore[arg-type]
            cancel_requested=job.cancel_requested or status == "cancelled",
            error_message=message if status == "failed" else job.error_message,
            finished_at=utc_now(),
        )
        repository.update(finished)
        repository.add_event(JobEvent(job_id=job.id, level=level, message=message, payload=payload))  # type: ignore[arg-type]
        return repository.get_by_id(job.id) or finished

    def _record_progress(
        self,
        repository: JobRepository,
        job_id: str,
        progress: str | DownloadProgress,
    ) -> None:
        job = repository.get_by_id(job_id)
        if job is None:
            return
        if isinstance(progress, str):
            message = progress
            payload: dict[str, object] = {}
            updated = job
        else:
            message = progress.message
            payload = {
                "total_files": progress.total_files,
                "completed_files": progress.completed_files,
                "skipped_files": progress.skipped_files,
                "failed_files": progress.failed_files,
            }
            updated = replace(
                job,
                total_files=progress.total_files,
                completed_files=progress.completed_files,
                skipped_files=progress.skipped_files,
                failed_files=progress.failed_files,
            )
            repository.update(updated)
        repository.add_event(
            JobEvent(job_id=job_id, level="info", message=message, payload=payload)
        )

    def _is_cancel_requested(self, repository: JobRepository, job_id: str) -> bool:
        job = repository.get_by_id(job_id)
        return job.cancel_requested if job is not None else True

    def _create_pixiv_client(self) -> PixivClient:
        settings_service = AppSettingsService(
            db_path=self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            settings = settings_service.load()
        finally:
            settings_service.close()
        sleeper = RandomSleep(
            base_seconds=settings.request_base_delay_seconds,
            random_seconds=settings.request_random_delay_seconds,
        )
        return PixivClient(refresh_token=settings.refresh_token, sleeper=sleeper)

    def _create_file_downloader(self) -> FileDownloader:
        settings_service = AppSettingsService(
            db_path=self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            settings = settings_service.load()
        finally:
            settings_service.close()
        return FileDownloader(
            settings.download_path,
            skip_existing=settings.skip_existing_files,
        )


def user_safe_error_message(exc: Exception) -> str:
    if isinstance(exc, JobCancelledError):
        return "Job cancelled"
    message = str(exc).strip()
    if not message:
        return "Download job failed"
    return message.replace("\n", " ")[:500]


def positive_int_option(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def string_option(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
