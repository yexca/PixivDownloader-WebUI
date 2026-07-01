from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from backend.domain.entities import Job
from backend.repositories._time import utc_now
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunRepository,
)
from backend.services.advanced_workflow_runner import (
    AdvancedWorkflowRunner,
)
from backend.services.job_service import JobService


class WorkflowRecoveryService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.repository = WorkflowRunRepository(db_path)

    def recover_startup(self) -> list[WorkflowRun]:
        recovered: list[WorkflowRun] = []
        for run in self.repository.list_runs_by_status("running"):
            recovered.append(self._recover_running_run(run))
        orphan_run = self._recover_active_orphan_jobs()
        if orphan_run is not None:
            recovered.append(orphan_run)
        return recovered

    def close(self) -> None:
        self.repository.close()

    def _recover_running_run(self, run: WorkflowRun) -> WorkflowRun:
        self._requeue_interrupted_node_jobs(run)
        return self._resume_advanced_run(run)

    def _resume_advanced_run(self, run: WorkflowRun) -> WorkflowRun:
        runner = AdvancedWorkflowRunner(
            self.db_path,
            settings_json_path=self.settings_json_path,
        )
        try:
            return runner.process_run(run.id)
        finally:
            runner.close()

    def _requeue_interrupted_node_jobs(self, run: WorkflowRun) -> None:
        running_job_ids = [
            job.id
            for job in self._jobs_for_node_runs(run.node_runs)
            if job.status == "running"
        ]
        self._requeue_jobs(running_job_ids)

    def _recover_active_orphan_jobs(self) -> WorkflowRun | None:
        orphan_jobs = self._active_orphan_jobs()
        if not orphan_jobs:
            return None

        now = utc_now()
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            status="running",
            total=1,
            completed=0,
            failed=0,
            skipped=0,
            concurrency=1,
            source="startup_recovery",
            created_at=now,
        )
        self.repository.create_run(run)
        node_id = self.repository.create_node_run(
            WorkflowNodeRun(
                id=None,
                workflow_run_id=run.id,
                node_id="recover_jobs",
                node_type="job_recovery",
                title="Recover jobs",
                position=0,
                status="running",
                input={"source": "startup_recovery"},
                output={"job_count": len(orphan_jobs)},
                created_at=now,
                started_at=now,
            )
        )
        self._link_orphan_jobs(
            orphan_jobs,
            run_id=run.id,
            node_run_id=node_id,
        )
        self._requeue_jobs([job.id for job in orphan_jobs if job.status == "running"])
        created = self.repository.get_run(run.id)
        node_run = WorkflowNodeRun(
            id=node_id,
            workflow_run_id=run.id,
            node_id="recover_jobs",
            node_type="job_recovery",
            title="Recover jobs",
            position=0,
            status="running",
            output={"job_count": len(orphan_jobs)},
            job_ids=[job.id for job in orphan_jobs],
            created_at=now,
            started_at=now,
        )
        return replace(created or run, node_runs=[node_run])

    def _active_orphan_jobs(self) -> list[Job]:
        repository = JobRepository(self.db_path)
        try:
            return repository.list_active_orphan_jobs()
        finally:
            repository.close()

    def _jobs_for_node_runs(self, node_runs: list[WorkflowNodeRun]) -> list[Job]:
        repository = JobRepository(self.db_path)
        try:
            job_ids = node_job_ids(node_runs)
            jobs = repository.list_by_ids(job_ids)
            seen = {job.id for job in jobs}
            for node_run in node_runs:
                if node_run.id is None:
                    continue
                for job in repository.list_by_workflow_node_run_id(node_run.id):
                    if job.id in seen:
                        continue
                    jobs.append(job)
                    seen.add(job.id)
            return jobs
        finally:
            repository.close()

    def _link_orphan_jobs(
        self,
        jobs: list[Job],
        *,
        run_id: str,
        node_run_id: int,
    ) -> None:
        repository = JobRepository(self.db_path)
        try:
            for job in jobs:
                repository.update(
                    replace(
                        job,
                        workflow_run_id=run_id,
                        workflow_node_run_id=node_run_id,
                        workflow_source="startup_recovery",
                    )
                )
        finally:
            repository.close()

    def _requeue_jobs(self, job_ids: list[str]) -> None:
        if not job_ids:
            return
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            service.requeue_interrupted_jobs(job_ids)
        finally:
            service.close()


def node_job_ids(node_runs: list[WorkflowNodeRun]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for node_run in node_runs:
        for job_id in node_run.job_ids:
            if job_id in seen:
                continue
            result.append(job_id)
            seen.add(job_id)
    return result
