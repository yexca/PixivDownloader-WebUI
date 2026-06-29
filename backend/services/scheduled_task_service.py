from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.core.errors import InsufficientDiskSpaceError, PixivDownloaderError
from backend.domain.entities import (
    Artist,
    Job,
    ScheduledTask,
    ScheduledTaskConfig,
    ScheduledTaskFilter,
    ScheduledTaskTarget,
)
from backend.domain.types import ScheduledTaskAction, ScheduledTaskStatus
from backend.repositories._time import utc_now
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.scheduled_task_repository import ScheduledTaskRepository
from backend.repositories.workflow_run_repository import WorkflowRun
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
        config: ScheduledTaskConfig | None = None,
    ) -> ScheduledTask:
        if interval_days < 1:
            raise ValueError("interval_days must be at least 1")
        now = utc_now()
        status: ScheduledTaskStatus = "active" if enabled else "paused"
        task = ScheduledTask(
            id=None,
            name=name.strip() or default_task_name(action, target_artist_id, config),
            action=action,
            status=status,
            target_artist_id=target_artist_id.strip(),
            interval_days=interval_days,
            run_after_startup=run_after_startup,
            next_run_at=now,
            config=config,
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
        config: ScheduledTaskConfig | None = None,
    ) -> ScheduledTask | None:
        task = self.repository.get_by_id(task_id)
        if task is None:
            return None
        if interval_days is not None and interval_days < 1:
            raise ValueError("interval_days must be at least 1")
        next_run_at = task.next_run_at
        requested_status = status or task.status
        resolved_status = requested_status
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
            config=config or task.config,
            next_run_at=next_run_at,
            last_error_code=None if resolved_status == "active" else task.last_error_code,
            last_error_message=None if resolved_status == "active" else task.last_error_message,
        )
        self.repository.update(updated)
        return self.repository.get_by_id(task_id)

    def delete_task(self, task_id: int) -> bool:
        return self.repository.delete(task_id)

    def activate_inactive_tasks(self) -> list[ScheduledTask]:
        return []

    def run_config(self, config: ScheduledTaskConfig) -> list[Job]:
        action = config.actions[0] if config.actions else "download_artist"
        target_artist_id = config.target.artist_id or ""
        task = ScheduledTask(
            id=None,
            name=default_task_name(action, target_artist_id, config),
            action=action,
            status="active",
            target_artist_id=target_artist_id,
            interval_days=1,
            config=config,
        )
        return self._create_jobs(task, gate_one_time=True)

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
        try:
            run = self._create_workflow_run(task, manual=manual)
            jobs = [job for item in run.items for job in self._jobs_for_ids(item.job_ids)]
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

        updated = self._mark_success(task, now=now, jobs=jobs)
        summary = {
            **(updated.last_run_summary or {}),
            "workflow_run_id": run.id,
            "workflow_run_status": run.status,
            "workflow_run_source": run.source,
        }
        updated = replace(updated, last_run_summary=summary)
        self.repository.update(updated)
        updated = self.repository.get_by_id(task.id or 0) or updated
        return ScheduledTaskRunResult(
            task=updated,
            jobs=jobs,
            workflow_run_id=run.id,
            created=bool(jobs),
            skipped=not jobs,
        )

    def close(self) -> None:
        self.repository.close()

    def _create_workflow_run(self, task: ScheduledTask, *, manual: bool) -> WorkflowRun:
        from backend.services.workflow_run_service import WorkflowRunService

        service = WorkflowRunService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            return service.run_schedule(task, manual=manual)
        finally:
            service.close()

    def _jobs_for_ids(self, job_ids: list[str]) -> list[Job]:
        if not job_ids:
            return []
        repository = JobRepository(self.db_path)
        try:
            return repository.list_by_ids(job_ids)
        finally:
            repository.close()

    def _create_jobs(self, task: ScheduledTask, *, gate_one_time: bool) -> list[Job]:
        config = task.config or legacy_config(task)
        if config.target.type == "artists" and config.target.artwork_ids:
            service = JobService(self.db_path, settings_json_path=self.settings_json_path)
            try:
                job = service.create_resolve_artist_targets_job(
                    artist_ids=config.target.artist_ids,
                    artwork_ids=config.target.artwork_ids,
                    actions=config.actions,
                    download_options=config.download_options,
                    max_targets_per_run=config.max_artists_per_run,
                    options=config.download_options,
                    gate_one_time=gate_one_time,
                )
                return [] if job is None else [job]
            finally:
                service.close()
        if config.target.type == "single_artwork":
            if not config.target.artwork_id:
                return []
            active_job = self._find_active_job(
                "download_from_artwork",
                None,
                config.target.artwork_id,
            )
            if active_job is not None:
                return []
            return [
                self._create_job(
                    "download_artist",
                    None,
                    artwork_id=config.target.artwork_id,
                    options=config.download_options,
                    gate_one_time=gate_one_time,
                )
            ]
        artists = self._resolve_artists(config)
        jobs: list[Job] = []
        for artist in artists[: config.max_artists_per_run]:
            for action in config.actions:
                active_job = self._find_active_job(action, artist.id, None)
                if active_job is not None:
                    continue
                jobs.append(
                    self._create_job(
                        action,
                        artist.id,
                        options=config.download_options,
                        gate_one_time=gate_one_time,
                    )
                )
        return jobs

    def _create_job(
        self,
        action: ScheduledTaskAction,
        artist_id: str | None,
        *,
        artwork_id: str | None = None,
        options: dict[str, object] | None = None,
        gate_one_time: bool,
    ) -> Job:
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            if action == "sync_artist":
                if artist_id is None:
                    raise ValueError("sync_artist requires an artist target")
                return service.create_download_job(
                    user_id=artist_id,
                    artwork_id=None,
                    sync_only=True,
                    options=options,
                    gate_one_time=gate_one_time,
                )
            if action == "retry_failed_artist":
                if artist_id is None:
                    raise ValueError("retry_failed_artist requires an artist target")
                return service.create_download_job(
                    user_id=artist_id,
                    artwork_id=None,
                    retry_failed_artist=True,
                    options=options,
                    gate_one_time=gate_one_time,
                )
            return service.create_download_job(
                user_id=artist_id,
                artwork_id=artwork_id,
                options=options,
                gate_one_time=gate_one_time,
            )
        finally:
            service.close()

    def _find_active_job(
        self,
        action: ScheduledTaskAction,
        artist_id: str | None,
        artwork_id: str | None,
    ) -> Job | None:
        repository = JobRepository(self.db_path)
        try:
            return repository.find_active(
                job_type=job_type_for_action(action),
                user_id=artist_id,
                artwork_id=artwork_id,
            )
        finally:
            repository.close()

    def _mark_success(self, task: ScheduledTask, *, now: str, jobs: list[Job]) -> ScheduledTask:
        updated = replace(
            task,
            status="active",
            last_run_at=now,
            last_success_at=now,
            next_run_at=next_time(now, task.interval_days),
            last_job_id=jobs[-1].id if jobs else task.last_job_id,
            last_error_code=None,
            last_error_message=None,
            last_run_summary={
                "created_jobs": len(jobs),
                "job_ids": [job.id for job in jobs],
            },
        )
        self.repository.update(updated)
        return self.repository.get_by_id(task.id or 0) or updated

    def _resolve_artists(self, config: ScheduledTaskConfig) -> list[Artist]:
        repository = ArtistRepository(self.db_path)
        try:
            target = config.target
            if target.type in {"single_artist", "artists"}:
                if target.type == "artists":
                    artist_ids = target.artist_ids
                elif target.artist_id:
                    artist_ids = (target.artist_id,)
                else:
                    artist_ids = ()
                if not artist_ids:
                    return []
                artists: list[Artist] = []
                for artist_id in artist_ids:
                    artist = repository.get_by_id(artist_id)
                    artists.append(
                        artist
                        if artist is not None
                        else Artist(id=artist_id, name=artist_id)
                    )
                return artists
            if target.type == "single_artist":
                if not target.artist_id:
                    return []
                artist = repository.get_by_id(target.artist_id)
                return (
                    [artist]
                    if artist is not None
                    else [Artist(id=target.artist_id, name=target.artist_id)]
                )
            if target.type == "artists_with_tag":
                tags = target.tags or ((target.tag,) if target.tag else ())
                if not tags:
                    return []
                artists = []
                seen_artist_ids: set[str] = set()
                for tag in tags:
                    for artist in repository.list(limit=1000, local_tag=tag):
                        if artist.id in seen_artist_ids:
                            continue
                        artists.append(artist)
                        seen_artist_ids.add(artist.id)
            else:
                artists = repository.list(limit=1000)
        finally:
            repository.close()

        if config.target.type == "artists_not_checked":
            days = config.target.days or 30
            artists = [artist for artist in artists if artist_is_stale(artist, days)]
        for item in config.filters:
            artists = self._apply_filter(artists, item)
        if config.skip_unavailable_artists:
            artists = [artist for artist in artists if artist.account_status != "unavailable"]
        return select_artists(artists, config)

    def _apply_filter(
        self,
        artists: list[Artist],
        item: ScheduledTaskFilter,
    ) -> list[Artist]:
        if item.type == "last_checked_before_days":
            return [artist for artist in artists if artist_is_stale(artist, item.days or 30)]
        if item.type == "has_failed_files":
            repository = ArtworkFileRepository(self.db_path)
            try:
                return [
                    artist
                    for artist in artists
                    if repository.list_failed_by_artist(artist.id, limit=1)
                ]
            finally:
                repository.close()
        return artists

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
        created: bool,
        skipped: bool,
        job: Job | None = None,
        jobs: list[Job] | None = None,
        workflow_run_id: str | None = None,
    ) -> None:
        self.task = task
        self.jobs = jobs or ([] if job is None else [job])
        self.job = self.jobs[-1] if self.jobs else None
        self.workflow_run_id = workflow_run_id
        self.created = created
        self.skipped = skipped


def job_type_for_action(action: str) -> str:
    if action == "download_from_artwork":
        return "download_from_artwork"
    if action == "sync_artist":
        return "sync_artist"
    if action == "retry_failed_artist":
        return "retry_failed_artist"
    return "download_artist"


def default_task_name(
    action: ScheduledTaskAction,
    artist_id: str,
    config: ScheduledTaskConfig | None = None,
) -> str:
    labels = {
        "sync_artist": "Sync artist",
        "download_artist": "Download artist",
        "retry_failed_artist": "Retry failed artist",
    }
    if config is not None:
        target = config.target
        if target.type == "artists":
            if target.artist_source == "artwork_ids":
                return "Download artists from artworks"
            return "Download artists"
        if target.type == "artworks":
            return "Download artworks"
        if target.type == "single_artwork" and target.artwork_id:
            return f"Download artwork {target.artwork_id}"
        if target.type == "all_artists":
            return f"{labels[action]} all artists"
        if target.type == "artists_with_tag":
            tag_label = ", ".join(target.tags) if target.tags else target.tag or "tag"
            return f"{labels[action]} artists tagged {tag_label}"
        if target.type == "artists_not_checked":
            return f"{labels[action]} unchecked artists"
    return f"{labels[action]} {artist_id}"


def legacy_config(task: ScheduledTask) -> ScheduledTaskConfig:
    return ScheduledTaskConfig(
        target=ScheduledTaskTarget(type="single_artist", artist_id=task.target_artist_id),
        actions=(task.action,),
    )


def artist_is_stale(artist: Artist, days: int) -> bool:
    if artist.last_checked_at is None:
        return True
    return parse_time(artist.last_checked_at) <= datetime.now(UTC) - timedelta(days=days)


def select_artists(artists: list[Artist], config: ScheduledTaskConfig) -> list[Artist]:
    if config.target.type in {"single_artist", "artists"}:
        return artists
    if config.artist_selection == "random":
        return random.sample(artists, k=len(artists))
    reverse = config.artist_selection == "newest_checked_first"
    return sorted(artists, key=artist_checked_sort_key, reverse=reverse)


def artist_checked_sort_key(artist: Artist) -> datetime:
    if artist.last_checked_at is None:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return parse_time(artist.last_checked_at)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def next_time(from_time: str, interval_days: int) -> str:
    return (
        (parse_time(from_time) + timedelta(days=interval_days)).isoformat().replace("+00:00", "Z")
    )


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
