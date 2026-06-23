from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.domain.entities import Job, JobEvent
from backend.domain.types import JobStatus, JobType
from backend.repositories.job_repository import JobRepository


class JobService:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.repository = JobRepository(db_path)

    def create_download_job(
        self,
        *,
        user_id: str | None,
        artwork_id: str | None,
        force_rescan: bool = False,
        retry_failed: bool = False,
    ) -> Job:
        if bool(user_id) == bool(artwork_id):
            raise ValueError("exactly one of user_id or artwork_id is required")

        job_type = resolve_job_type(
            user_id=user_id,
            artwork_id=artwork_id,
            force_rescan=force_rescan,
            retry_failed=retry_failed,
        )
        job = Job(
            id=str(uuid4()),
            type=job_type,
            status="queued",
            input_user_id=user_id,
            input_artwork_id=artwork_id,
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
        if job.status == "queued":
            cancelled = Job(
                id=job.id,
                type=job.type,
                status="cancelled",
                input_user_id=job.input_user_id,
                input_artwork_id=job.input_artwork_id,
                artist_id=job.artist_id,
                total_files=job.total_files,
                completed_files=job.completed_files,
                skipped_files=job.skipped_files,
                failed_files=job.failed_files,
                cancel_requested=True,
                error_message=job.error_message,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
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

    def list_events(self, job_id: str, *, limit: int = 100) -> list[JobEvent]:
        return self.repository.list_events(job_id, limit=limit)

    def close(self) -> None:
        self.repository.close()


def resolve_job_type(
    *,
    user_id: str | None,
    artwork_id: str | None,
    force_rescan: bool,
    retry_failed: bool,
) -> JobType:
    del user_id
    if retry_failed:
        return "retry_failed"
    if force_rescan:
        return "rescan_artist"
    if artwork_id is not None:
        return "download_from_artwork"
    return "download_artist"
