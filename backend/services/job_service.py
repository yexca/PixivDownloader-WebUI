from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.core.errors import JobNotCancellableError
from backend.domain.entities import Job, JobEvent
from backend.domain.types import JobStatus, JobType
from backend.repositories._time import utc_now
from backend.repositories.job_repository import JobRepository
from backend.services.settings_service import AppSettingsService
from backend.services.storage_service import check_free_space

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class JobService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.repository = JobRepository(db_path)
        self.db_path = db_path
        self.settings_json_path = settings_json_path

    def create_download_job(
        self,
        *,
        user_id: str | None,
        artwork_id: str | None,
        force_rescan: bool = False,
        retry_failed: bool = False,
        sync_only: bool = False,
        retry_failed_artist: bool = False,
        options: dict[str, object] | None = None,
    ) -> Job:
        if bool(user_id) == bool(artwork_id):
            raise ValueError("exactly one of user_id or artwork_id is required")
        if (sync_only or retry_failed_artist) and artwork_id is not None:
            raise ValueError("artist-only job requires user_id")

        job_type = resolve_job_type(
            user_id=user_id,
            artwork_id=artwork_id,
            force_rescan=force_rescan,
            retry_failed=retry_failed,
            sync_only=sync_only,
            retry_failed_artist=retry_failed_artist,
        )
        if job_type in DOWNLOAD_JOB_TYPES:
            self._ensure_download_space()
        job = Job(
            id=str(uuid4()),
            type=job_type,
            status="queued",
            input_user_id=user_id,
            input_artwork_id=artwork_id,
            options=clean_job_options(options or {}),
        )
        self.repository.create(job)
        self.repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message="Job queued",
                payload={
                    "force_rescan": force_rescan,
                    "retry_failed": retry_failed,
                    "sync_only": sync_only,
                    "retry_failed_artist": retry_failed_artist,
                    "options": clean_job_options(options or {}),
                },
            )
        )
        return self.repository.get_by_id(job.id) or job

    def list_jobs(
        self,
        *,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        return (
            self.repository.list(status=status, limit=limit, offset=offset),
            self.repository.count(status=status),
        )

    def get_job(self, job_id: str) -> Job | None:
        return self.repository.get_by_id(job_id)

    def cancel_job(self, job_id: str) -> Job | None:
        job = self.repository.get_by_id(job_id)
        if job is None:
            return None
        if job.status in TERMINAL_STATUSES:
            raise JobNotCancellableError(f"job {job_id} is already {job.status}")
        if job.status == "queued":
            cancelled = Job(
                id=job.id,
                type=job.type,
                status="cancelled",
                input_user_id=job.input_user_id,
                input_artwork_id=job.input_artwork_id,
                options=job.options,
                artist_id=job.artist_id,
                total_files=job.total_files,
                completed_files=job.completed_files,
                skipped_files=job.skipped_files,
                failed_files=job.failed_files,
                cancel_requested=True,
                error_message=job.error_message,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=utc_now(),
            )
            self.repository.update(cancelled)
            self.repository.add_event(
                JobEvent(job_id=job_id, level="info", message="Job cancelled before start")
            )
            return self.repository.get_by_id(job_id)

        updated = self.repository.request_cancel(job_id)
        self.repository.add_event(
            JobEvent(job_id=job_id, level="info", message="Cancellation requested")
        )
        return updated

    def cancel_jobs(self, job_ids: list[str]) -> tuple[list[Job], list[dict[str, str]]]:
        cancelled: list[Job] = []
        errors: list[dict[str, str]] = []
        for job_id in job_ids:
            try:
                job = self.cancel_job(job_id)
            except JobNotCancellableError as exc:
                errors.append({"job_id": job_id, "message": str(exc)})
                continue
            if job is None:
                errors.append({"job_id": job_id, "message": "job not found"})
                continue
            cancelled.append(job)
        return cancelled, errors

    def list_events(self, job_id: str, *, limit: int = 100) -> list[JobEvent]:
        return self.repository.list_events(job_id, limit=limit)

    def close(self) -> None:
        self.repository.close()

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


def resolve_job_type(
    *,
    user_id: str | None,
    artwork_id: str | None,
    force_rescan: bool,
    retry_failed: bool,
    sync_only: bool = False,
    retry_failed_artist: bool = False,
) -> JobType:
    if sync_only:
        return "sync_artist"
    if retry_failed_artist:
        return "retry_failed_artist"
    del user_id
    if retry_failed:
        return "retry_failed"
    if force_rescan:
        return "rescan_artist"
    if artwork_id is not None:
        return "download_from_artwork"
    return "download_artist"


DOWNLOAD_JOB_TYPES = {
    "download_artist",
    "download_from_artwork",
    "rescan_artist",
    "retry_failed",
    "retry_failed_artist",
}


def clean_job_options(options: dict[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key in ("full_download", "max_artworks", "min_artwork_id", "max_artwork_id"):
        value = options.get(key)
        if value is None or value == "":
            continue
        cleaned[key] = value
    if options.get("only_new_artworks") is True:
        cleaned["only_new_artworks"] = True
    stop_if_artwork_count_above = options.get("stop_if_artwork_count_above")
    if stop_if_artwork_count_above is not None and stop_if_artwork_count_above != "":
        cleaned["stop_if_artwork_count_above"] = stop_if_artwork_count_above
    naming_rule = options.get("naming_rule")
    if isinstance(naming_rule, str) and naming_rule.strip():
        cleaned["naming_rule"] = naming_rule.strip()
    naming_tag_variants = options.get("naming_tag_variants")
    if isinstance(naming_tag_variants, list):
        cleaned_variants: list[dict[str, str]] = []
        for item in naming_tag_variants:
            if not isinstance(item, dict):
                continue
            tag = item.get("tag")
            variant_rule = item.get("naming_rule")
            if (
                isinstance(tag, str)
                and isinstance(variant_rule, str)
                and tag.strip()
                and variant_rule.strip()
            ):
                cleaned_variants.append({"tag": tag.strip(), "naming_rule": variant_rule.strip()})
        if cleaned_variants:
            cleaned["naming_tag_variants"] = cleaned_variants
    return cleaned
