from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.core.errors import JobNotCancellableError, JobNotFoundError
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
        gate_one_time: bool = True,
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
        cleaned_options = clean_job_options(options or {})
        status: JobStatus = "queued"
        if gate_one_time:
            cleaned_options["activation_scope"] = "one_time"
            status = self._next_one_time_status()
        job = Job(
            id=str(uuid4()),
            type=job_type,
            status=status,
            input_user_id=user_id,
            input_artwork_id=artwork_id,
            options=cleaned_options,
        )
        self.repository.create(job)
        self.repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message=(
                    "Job queued" if status == "queued" else "Job waiting for one-time task capacity"
                ),
                payload={
                    "force_rescan": force_rescan,
                    "retry_failed": retry_failed,
                    "sync_only": sync_only,
                    "retry_failed_artist": retry_failed_artist,
                    "options": cleaned_options,
                },
            )
        )
        return self.repository.get_by_id(job.id) or job

    def create_legacy_import_hydration_job(
        self,
        *,
        artist_ids: tuple[str, ...],
        legacy_latest_download_id_by_artist: dict[str, str | None],
    ) -> Job | None:
        if not artist_ids:
            return None
        options = {
            "source": "legacy_database",
            "artist_ids": list(artist_ids),
            "legacy_latest_download_id_by_artist": legacy_latest_download_id_by_artist,
            "activation_scope": "one_time",
        }
        status: JobStatus = self._next_one_time_status()
        job = Job(
            id=str(uuid4()),
            type="hydrate_legacy_import",
            status=status,
            options=options,
        )
        self.repository.create(job)
        self.repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message="Legacy import hydration queued"
                if status == "queued"
                else "Legacy import hydration waiting for one-time task capacity",
                payload=options,
            )
        )
        return self.repository.get_by_id(job.id) or job

    def rerun_job(self, job_id: str) -> Job:
        source = self.repository.get_by_id(job_id)
        if source is None:
            raise JobNotFoundError(f"job {job_id} was not found")
        return self._create_from_source(source, action="rerun", options=source.options)

    def retry_job(self, job_id: str) -> Job:
        source = self.repository.get_by_id(job_id)
        if source is None:
            raise JobNotFoundError(f"job {job_id} was not found")
        if source.type == "hydrate_legacy_import":
            retry_options = self._legacy_hydration_retry_options(source)
            return self._create_from_source(
                source,
                action="retry_failed_artists",
                options=retry_options,
            )
        return self._create_from_source(source, action="retry", options=source.options)

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
        if job.status in {"inactive", "queued"}:
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

    def activate_inactive_one_time_jobs(self) -> list[Job]:
        capacity = self._one_time_activation_capacity()
        if capacity <= 0:
            return []
        activated: list[Job] = []
        for job in self.repository.list_inactive_one_time(limit=capacity):
            updated = Job(
                id=job.id,
                type=job.type,
                status="queued",
                input_user_id=job.input_user_id,
                input_artwork_id=job.input_artwork_id,
                options=job.options,
                artist_id=job.artist_id,
                total_files=job.total_files,
                completed_files=job.completed_files,
                skipped_files=job.skipped_files,
                failed_files=job.failed_files,
                cancel_requested=job.cancel_requested,
                error_message=job.error_message,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
            )
            self.repository.update(updated)
            self.repository.add_event(
                JobEvent(job_id=job.id, level="info", message="Job activated")
            )
            activated.append(self.repository.get_by_id(job.id) or updated)
        return activated

    def requeue_interrupted_running_jobs(self) -> list[Job]:
        jobs = self.repository.requeue_running()
        for job in jobs:
            self.repository.add_event(
                JobEvent(
                    job_id=job.id,
                    level="warning",
                    message="Job requeued after service restart",
                )
            )
        return jobs

    def _next_one_time_status(self) -> JobStatus:
        return "queued" if self._one_time_activation_capacity() > 0 else "inactive"

    def _one_time_activation_capacity(self) -> int:
        return max(0, self._max_active_one_time_tasks() - self.repository.count_active_one_time())

    def _max_active_one_time_tasks(self) -> int:
        settings_service = AppSettingsService(
            db_path=self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            return settings_service.load().max_active_one_time_tasks
        finally:
            settings_service.close()

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

    def _create_from_source(
        self,
        source: Job,
        *,
        action: str,
        options: dict[str, object],
    ) -> Job:
        if source.type in DOWNLOAD_JOB_TYPES:
            self._ensure_download_space()
        cleaned_options = dict(options)
        cleaned_options["activation_scope"] = "one_time"
        cleaned_options["source_job_id"] = source.id
        cleaned_options["job_action"] = action
        status: JobStatus = self._next_one_time_status()
        job = Job(
            id=str(uuid4()),
            type=source.type,
            status=status,
            input_user_id=source.input_user_id,
            input_artwork_id=source.input_artwork_id,
            artist_id=source.artist_id,
            options=cleaned_options,
        )
        self.repository.create(job)
        self.repository.add_event(
            JobEvent(
                job_id=job.id,
                level="info",
                message="Job queued from previous job"
                if status == "queued"
                else "Job waiting for one-time task capacity",
                payload={
                    "action": action,
                    "source_job_id": source.id,
                    "options": cleaned_options,
                },
            )
        )
        return self.repository.get_by_id(job.id) or job

    def _legacy_hydration_retry_options(self, source: Job) -> dict[str, object]:
        legacy_latest_by_artist = source.options.get("legacy_latest_download_id_by_artist")
        if not isinstance(legacy_latest_by_artist, dict):
            legacy_latest_by_artist = {}
        source_artist_ids = [
            artist_id
            for artist_id in source.options.get("artist_ids", [])
            if isinstance(artist_id, str)
        ]
        event_limit = max(1000, len(source_artist_ids) + 100)
        failed_artist_ids = self._failed_legacy_hydration_artist_ids(
            source.id,
            limit=event_limit,
        )
        if not failed_artist_ids:
            failed_artist_ids = source_artist_ids
        return {
            "source": source.options.get("source", "legacy_database"),
            "artist_ids": failed_artist_ids,
            "legacy_latest_download_id_by_artist": {
                artist_id: legacy_latest_by_artist.get(artist_id)
                for artist_id in failed_artist_ids
            },
        }

    def _failed_legacy_hydration_artist_ids(self, job_id: str, *, limit: int) -> list[str]:
        failed_artist_ids: list[str] = []
        seen: set[str] = set()
        for event in self.repository.list_events(job_id, limit=limit):
            payload = event.payload or {}
            if payload.get("status") != "failed_retryable":
                continue
            artist_id = payload.get("artist_id")
            if not isinstance(artist_id, str) or not artist_id or artist_id in seen:
                continue
            seen.add(artist_id)
            failed_artist_ids.append(artist_id)
        return failed_artist_ids


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
    tag_variants = clean_tag_variants(options.get("tag_variants"))
    if not tag_variants:
        tag_variants = legacy_tag_variants(options)
    if tag_variants:
        cleaned["tag_variants"] = tag_variants
    return cleaned


def clean_tag_variants(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag")
        behavior = item.get("behavior")
        naming_rule = item.get("naming_rule")
        if not isinstance(tag, str) or not tag.strip():
            continue
        variant: dict[str, str] = {"tag": tag.strip()}
        if isinstance(behavior, str) and behavior in {"download", "skip", "retry_failed"}:
            variant["behavior"] = behavior
        if isinstance(naming_rule, str) and naming_rule.strip():
            variant["naming_rule"] = naming_rule.strip()
        if len(variant) > 1:
            cleaned.append(variant)
    return cleaned


def legacy_tag_variants(options: dict[str, object]) -> list[dict[str, str]]:
    naming_variants = options.get("naming_tag_variants")
    if not isinstance(naming_variants, list):
        return []
    behavior = legacy_action_to_behavior(options.get("tag_variant_action"))
    result: list[dict[str, str]] = []
    for item in naming_variants:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag")
        naming_rule = item.get("naming_rule")
        if not isinstance(tag, str) or not tag.strip():
            continue
        variant = {"tag": tag.strip(), "behavior": behavior}
        if isinstance(naming_rule, str) and naming_rule.strip():
            variant["naming_rule"] = naming_rule.strip()
        result.append(variant)
    return result


def legacy_action_to_behavior(value: object) -> str:
    if value == "retry_failed_artist":
        return "retry_failed"
    if value == "sync_artist":
        return "skip"
    return "download"
