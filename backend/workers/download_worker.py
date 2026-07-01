from __future__ import annotations

import logging
from dataclasses import dataclass, replace
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
from backend.repositories.workflow_candidate_repository import WorkflowCandidateRepository
from backend.repositories.workflow_run_repository import WorkflowRunRepository
from backend.schemas.failure_reasons import failure_detail, failure_detail_from_exception
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.candidate_download_service import (
    CandidateDownloadService,
    existing_file_behavior_from_conflict_mode,
)
from backend.services.download_service import DownloadOptions, DownloadService
from backend.services.file_downloader import FileDownloader
from backend.services.job_service import JobService, workflow_link_from_job
from backend.services.legacy_import_hydration_service import (
    LegacyImportHydrationArtistResult,
    LegacyImportHydrationRetryableError,
    LegacyImportHydrationService,
    LegacyImportHydrationSummary,
    legacy_hydration_targets_from_options,
)
from backend.services.library_sync_service import LibrarySyncService
from backend.services.pixiv_client import PixivClient, PixivClientProtocol
from backend.services.pixiv_rate_policy import (
    file_download_request_policy,
    metadata_request_policy,
)
from backend.services.settings_service import AppSettingsService

logger = logging.getLogger(__name__)


class PixivClientFactory(Protocol):
    def __call__(self) -> PixivClientProtocol: ...


class FileDownloaderFactory(Protocol):
    def __call__(self) -> FileDownloader: ...


@dataclass(frozen=True)
class ResolvedTargetArtists:
    artist_ids: list[str]
    from_artworks: list[dict[str, str]]
    skipped_count: int


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
        self._custom_file_downloader_factory = file_downloader_factory is not None
        self.file_downloader_factory = file_downloader_factory or self._create_file_downloader

    def run_job(self, job_id: str) -> Job:
        repository = JobRepository(self.db_path)
        result: Job | None = None
        try:
            job = repository.get_by_id(job_id)
            if job is None:
                raise ValueError(f"job not found: {job_id}")
            if job.cancel_requested or job.status == "cancelled":
                result = self._finish(repository, job, "cancelled", "Job cancelled before start")
                return result

            job = self._start(repository, job)
            if job.type == "hydrate_legacy_import":
                result = self._run_legacy_import_hydration_job(repository, job)
                return result
            if job.type == "resolve_workflow_targets":
                result = self._run_resolve_workflow_targets_job(repository, job)
                return result
            if job.type == "resolve_artist_targets":
                result = self._run_resolve_artist_targets_job(repository, job)
                return result
            if job.type == "sync_artist":
                result = self._run_sync_job(repository, job)
                return result
            if job.type in {"download_candidate_artist", "download_candidate_set"}:
                result = self._run_candidate_download_job(repository, job)
                return result
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
                pending_only=bool(job.options.get("pending_only", False)),
                source=job_source(job),
                max_artworks=positive_int_option(job.options.get("max_artworks")),
                min_artwork_id=string_option(job.options.get("min_artwork_id")),
                max_artwork_id=string_option(job.options.get("max_artwork_id")),
                naming_rule=string_option(job.options.get("naming_rule")),
                only_new_artworks=bool(job.options.get("only_new_artworks", False)),
                stop_if_artwork_count_above=positive_int_option(
                    job.options.get("stop_if_artwork_count_above")
                ),
                naming_tag_variants=tuple_dict_option(job.options.get("naming_tag_variants")),
                tag_variants=tuple_tag_variant_option(
                    job.options.get("tag_variants"),
                    legacy_variants=job.options.get("naming_tag_variants"),
                    legacy_action=job.options.get("tag_variant_action"),
                ),
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
            result = repository.get_by_id(job.id) or finished
            return result
        except JobCancelledError:
            latest = repository.get_by_id(job_id)
            if latest is None:
                raise
            result = self._finish(
                repository,
                latest,
                "cancelled",
                "Job cancelled",
                error_code="cancelled",
            )
            return result
        except Exception as exc:
            logger.exception("download job failed: %s", job_id)
            latest = repository.get_by_id(job_id)
            if latest is None:
                raise
            result = self._finish(
                repository,
                latest,
                "failed",
                user_safe_error_message(exc),
                level="error",
                payload={"error_type": type(exc).__name__},
                error_code=failure_detail_from_exception(exc).code,
            )
            return result
        finally:
            repository.close()
            if result is not None:
                self._continue_advanced_workflow(result)

    def _run_legacy_import_hydration_job(self, repository: JobRepository, job: Job) -> Job:
        targets = legacy_hydration_targets_from_options(job.options)
        service = LegacyImportHydrationService(
            pixiv_client=self.pixiv_client_factory(),
            artist_repository=ArtistRepository(self.db_path),
            name_history_repository=ArtistNameHistoryRepository(self.db_path),
            artwork_repository=ArtworkRepository(self.db_path),
            file_repository=ArtworkFileRepository(self.db_path),
        )
        summary: LegacyImportHydrationSummary | None = None
        try:
            repository.add_event(
                JobEvent(
                    job_id=job.id,
                    level="info",
                    message=f"Hydrating {len(targets)} legacy imported artist(s)",
                )
            )
            summary = service.hydrate(
                targets,
                progress_callback=lambda result: self._record_legacy_hydration_progress(
                    repository,
                    job.id,
                    result,
                ),
            )
        except LegacyImportHydrationRetryableError as exc:
            summary = exc.summary
            latest = repository.get_by_id(job.id) or job
            failed = replace(
                latest,
                status="failed",
                total_files=summary.total_artists,
                completed_files=legacy_hydrated_artist_count(summary),
                skipped_files=summary.skipped_no_legacy_cursor_artists,
                failed_files=summary.failed_retryable_artists,
                error_message=str(exc),
                finished_at=utc_now(),
            )
            repository.update(failed)
            repository.add_event(
                JobEvent(
                    job_id=job.id,
                    level="error",
                    message=str(exc),
                    payload=legacy_hydration_summary_payload(summary),
                )
            )
            return repository.get_by_id(job.id) or failed
        finally:
            service.close()

        latest = repository.get_by_id(job.id) or job
        finished = replace(
            latest,
            status="completed",
            total_files=summary.total_artists if summary else 0,
            completed_files=legacy_hydrated_artist_count(summary) if summary else 0,
            skipped_files=summary.skipped_no_legacy_cursor_artists if summary else 0,
            failed_files=0,
            finished_at=utc_now(),
        )
        repository.update(finished)
        repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message="Legacy import hydration completed",
                payload=legacy_hydration_summary_payload(summary),
            )
        )
        return repository.get_by_id(job.id) or finished

    def _run_resolve_artist_targets_job(self, repository: JobRepository, job: Job) -> Job:
        artist_ids = string_list_option(job.options.get("artist_ids"))
        artwork_ids = string_list_option(job.options.get("artwork_ids"))
        actions = action_list_option(job.options.get("actions"))
        download_options = dict_option(job.options.get("download_options"))
        resolved = self._resolve_target_artists(artist_ids, artwork_ids, job.options)
        finished = replace(
            repository.get_by_id(job.id) or job,
            status="completed",
            total_files=len(artist_ids) + len(artwork_ids),
            completed_files=len(resolved.artist_ids),
            skipped_files=resolved.skipped_count,
            failed_files=0,
            finished_at=utc_now(),
        )
        repository.update(finished)
        repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message=f"Resolved {len(resolved.artist_ids)} artist target(s)",
                payload={
                    "artist_ids": resolved.artist_ids,
                    "resolved_artist_ids": resolved.artist_ids,
                    "resolved_from_artworks": resolved.from_artworks,
                },
            )
        )

        created_jobs = self._create_resolved_artist_jobs(
            source_job=finished,
            artist_ids=resolved.artist_ids,
            actions=actions,
            download_options=download_options,
        )
        if created_jobs:
            self._append_workflow_item_jobs(finished, [created.id for created in created_jobs])
        return repository.get_by_id(job.id) or finished

    def _run_candidate_download_job(self, repository: JobRepository, job: Job) -> Job:
        candidate_set_id = string_option(job.options.get("candidate_set_id"))
        if candidate_set_id is None:
            raise ValueError("candidate download job requires candidate_set_id")
        artist_repository = ArtistRepository(self.db_path)
        file_repository = ArtworkFileRepository(self.db_path)
        candidate_repository = WorkflowCandidateRepository(self.db_path)
        service = CandidateDownloadService(
            candidate_repository=candidate_repository,
            artist_repository=artist_repository,
            file_repository=file_repository,
            file_downloader=self._create_candidate_file_downloader(job),
        )
        try:
            summary = service.download(
                candidate_set_id=candidate_set_id,
                artist_id=job.input_user_id if job.type == "download_candidate_artist" else None,
                naming_rule=string_option(job.options.get("naming_rule")),
            )
        finally:
            candidate_repository.close()
            artist_repository.close()
            file_repository.close()
        latest = repository.get_by_id(job.id) or job
        finished = replace(
            latest,
            status="completed",
            artist_id=job.input_user_id,
            total_files=summary.total_files,
            completed_files=summary.downloaded_files,
            skipped_files=summary.skipped_files,
            failed_files=summary.failed_files,
            finished_at=utc_now(),
        )
        repository.update(finished)
        repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message=f"Downloaded {summary.downloaded_files} candidate file(s)",
                payload={
                    "candidate_set_id": candidate_set_id,
                    "artist_ids": summary.artist_ids,
                    "total_files": summary.total_files,
                    "downloaded_files": summary.downloaded_files,
                    "skipped_files": summary.skipped_files,
                    "failed_files": summary.failed_files,
                },
            )
        )
        return repository.get_by_id(job.id) or finished

    def _run_resolve_workflow_targets_job(self, repository: JobRepository, job: Job) -> Job:
        artist_ids = string_list_option(job.options.get("artist_ids"))
        artwork_ids = string_list_option(job.options.get("artwork_ids"))
        resolved = self._resolve_target_artists(artist_ids, artwork_ids, job.options)
        finished = replace(
            repository.get_by_id(job.id) or job,
            status="completed",
            total_files=len(artist_ids) + len(artwork_ids),
            completed_files=len(resolved.artist_ids),
            skipped_files=resolved.skipped_count,
            failed_files=0,
            finished_at=utc_now(),
        )
        repository.update(finished)
        repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message=f"Resolved {len(resolved.artist_ids)} workflow artist target(s)",
                payload={
                    "artist_ids": resolved.artist_ids,
                    "resolved_artist_ids": resolved.artist_ids,
                    "resolved_from_artworks": resolved.from_artworks,
                    "skipped_count": resolved.skipped_count,
                },
            )
        )
        return repository.get_by_id(job.id) or finished

    def _resolve_target_artists(
        self,
        artist_ids: list[str],
        artwork_ids: list[str],
        options: dict[str, object],
    ) -> ResolvedTargetArtists:
        max_targets = positive_int_option(options.get("max_targets_per_run")) or max(
            1,
            len(artist_ids) + len(artwork_ids),
        )
        pixiv_client = self.pixiv_client_factory()
        resolved_artist_ids = list(artist_ids)
        resolved_from_artworks: list[dict[str, str]] = []
        for artwork_id in artwork_ids:
            artist = pixiv_client.get_artist_by_artwork_id(artwork_id)
            resolved_artist_ids.append(artist.id)
            resolved_from_artworks.append(
                {"artwork_id": artwork_id, "artist_id": artist.id, "artist_name": artist.name}
            )

        deduped_artist_ids = dedupe_preserve_order(resolved_artist_ids)[:max_targets]
        return ResolvedTargetArtists(
            artist_ids=deduped_artist_ids,
            from_artworks=resolved_from_artworks,
            skipped_count=max(0, len(resolved_artist_ids) - len(deduped_artist_ids)),
        )

    def _create_resolved_artist_jobs(
        self,
        *,
        source_job: Job,
        artist_ids: list[str],
        actions: list[str],
        download_options: dict[str, object],
    ) -> list[Job]:
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            jobs: list[Job] = []
            workflow_link = workflow_link_from_job(source_job)
            for artist_id in artist_ids:
                for action in actions:
                    job = service.create_download_job(
                        user_id=artist_id,
                        artwork_id=None,
                        sync_only=action == "sync_artist",
                        retry_failed_artist=action == "retry_failed_artist",
                        options=download_options,
                        workflow_link=workflow_link,
                    )
                    jobs.append(job)
            return jobs
        finally:
            service.close()

    def _append_workflow_item_jobs(self, job: Job, job_ids: list[str]) -> None:
        if not job.workflow_run_id or job.workflow_item_id is None:
            return
        repository = WorkflowRunRepository(self.db_path)
        try:
            for item in repository.list_items(job.workflow_run_id):
                if item.id != job.workflow_item_id:
                    continue
                next_job_ids = dedupe_preserve_order([*item.job_ids, *job_ids])
                repository.update_item(replace(item, status="running", job_ids=next_job_ids))
                break
        finally:
            repository.close()

    def _continue_advanced_workflow(self, job: Job) -> None:
        if job.workflow_source != "advanced_workflow" or not job.workflow_run_id:
            return
        if job.status not in {"completed", "failed", "cancelled"}:
            return
        runner = AdvancedWorkflowRunner(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            runner.process_run(job.workflow_run_id)
        except Exception:
            logger.exception("advanced workflow continuation failed: %s", job.workflow_run_id)
        finally:
            runner.close()

    def _record_legacy_hydration_progress(
        self,
        repository: JobRepository,
        job_id: str,
        result: LegacyImportHydrationArtistResult,
    ) -> None:
        job = repository.get_by_id(job_id)
        if job is None:
            return
        completed_artist_count = job.completed_files + (
            1 if result.status in {"completed", "completed_unavailable"} else 0
        )
        skipped_artist_count = job.skipped_files + (
            1 if result.status == "skipped_no_legacy_cursor" else 0
        )
        failed_artist_count = job.failed_files + (1 if result.status == "failed_retryable" else 0)
        updated = replace(
            job,
            completed_files=completed_artist_count,
            skipped_files=skipped_artist_count,
            failed_files=failed_artist_count,
        )
        repository.update(updated)
        level = "error" if result.status == "failed_retryable" else "info"
        repository.add_event(
            JobEvent(
                job_id=job_id,
                level=level,
                message=f"Legacy import hydration artist {result.artist_id}: {result.status}",
                payload={
                    "artist_id": result.artist_id,
                    "status": result.status,
                    "artwork_count": result.artwork_count,
                    "file_count": result.file_count,
                    "downloaded_file_count": result.downloaded_file_count,
                    "remote_file_count": result.remote_file_count,
                    "reason": result.reason,
                },
            )
        )

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
            summary = service.sync_artist(
                job.input_user_id,
                source=job_source(job),
                full_sync=bool(job.options.get("full_sync", False)),
            )
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
        error_code: str | None = None,
    ) -> Job:
        failure = (
            failure_detail(code=error_code, message=message, status=status)
            if status in {"failed", "cancelled"}
            else None
        )
        options = job.options
        if failure is not None:
            options = {
                **job.options,
                "error_code": failure.code,
                "error_retryable": failure.retryable,
            }
            repository.update_options(job.id, options)
            payload = {
                **(payload or {}),
                "error_code": failure.code,
                "error_reason": failure.reason,
                "retryable": failure.retryable,
            }
        finished = replace(
            job,
            status=status,  # type: ignore[arg-type]
            options=options,
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
        return PixivClient(
            refresh_token=settings.refresh_token,
            request_policy=metadata_request_policy(
                min_interval_seconds=settings.request_base_delay_seconds,
                random_delay_seconds=settings.request_random_delay_seconds,
            ),
        )

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
            existing_file_behavior=settings.existing_file_behavior,
            request_policy=file_download_request_policy(
                min_interval_seconds=settings.file_download_base_delay_seconds,
                random_delay_seconds=settings.file_download_random_delay_seconds,
            ),
        )

    def _create_candidate_file_downloader(self, job: Job) -> FileDownloader:
        if self._custom_file_downloader_factory:
            return self.file_downloader_factory()
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
            existing_file_behavior=existing_file_behavior_from_conflict_mode(
                job.options.get("conflict_mode")
            ),
            request_policy=file_download_request_policy(
                min_interval_seconds=settings.file_download_base_delay_seconds,
                random_delay_seconds=settings.file_download_random_delay_seconds,
            ),
        )


def user_safe_error_message(exc: Exception) -> str:
    if isinstance(exc, JobCancelledError):
        return "Job cancelled"
    message = str(exc).strip()
    if not message:
        return "Download job failed"
    return message.replace("\n", " ")[:500]


def legacy_hydration_summary_payload(
    summary: LegacyImportHydrationSummary | None,
) -> dict[str, object]:
    if summary is None:
        return {}
    return {
        "total_artists": summary.total_artists,
        "completed_artists": summary.completed_artists,
        "completed_unavailable_artists": summary.completed_unavailable_artists,
        "skipped_no_legacy_cursor_artists": summary.skipped_no_legacy_cursor_artists,
        "failed_retryable_artists": summary.failed_retryable_artists,
        "artwork_count": summary.artwork_count,
        "file_count": summary.file_count,
        "downloaded_file_count": summary.downloaded_file_count,
        "remote_file_count": summary.remote_file_count,
    }


def legacy_hydrated_artist_count(summary: LegacyImportHydrationSummary) -> int:
    return summary.completed_artists + summary.completed_unavailable_artists


def job_source(job: Job) -> str | None:
    if job.workflow_source:
        return job.workflow_source
    source = job.options.get("source")
    return source if isinstance(source, str) and source else None


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


def tuple_dict_option(value: object) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        return ()
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag")
        naming_rule = item.get("naming_rule")
        if isinstance(tag, str) and isinstance(naming_rule, str):
            result.append({"tag": tag, "naming_rule": naming_rule})
    return tuple(result)


def tuple_tag_variant_option(
    value: object,
    *,
    legacy_variants: object = None,
    legacy_action: object = None,
) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        value = legacy_tag_variant_option(legacy_variants, legacy_action)
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag")
        behavior = item.get("behavior")
        naming_rule = item.get("naming_rule")
        if not isinstance(tag, str) or not tag.strip():
            continue
        variant: dict[str, str] = {"tag": tag}
        if isinstance(behavior, str) and behavior in {"download", "skip", "retry_failed"}:
            variant["behavior"] = behavior
        if isinstance(naming_rule, str) and naming_rule.strip():
            variant["naming_rule"] = naming_rule
        if len(variant) > 1:
            result.append(variant)
    return tuple(result)


def string_list_option(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def action_list_option(value: object) -> list[str]:
    valid_actions = {"download_artist", "sync_artist", "retry_failed_artist"}
    actions = [item for item in string_list_option(value) if item in valid_actions]
    return actions or ["download_artist"]


def dict_option(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def legacy_tag_variant_option(value: object, action: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    behavior = (
        "retry_failed"
        if action == "retry_failed_artist"
        else "skip"
        if action == "sync_artist"
        else "download"
    )
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag")
        naming_rule = item.get("naming_rule")
        if not isinstance(tag, str) or not tag.strip():
            continue
        variant = {"tag": tag, "behavior": behavior}
        if isinstance(naming_rule, str) and naming_rule.strip():
            variant["naming_rule"] = naming_rule
        result.append(variant)
    return result
