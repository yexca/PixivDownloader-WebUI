from dataclasses import replace

from backend.db.migrate import migrate_database
from backend.domain.entities import Job
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import (
    WorkflowRun,
    WorkflowRunItem,
    WorkflowRunRepository,
)
from backend.schemas.workflows import WorkflowBatchItemRequest
from backend.services.workflow_run_service import (
    WorkflowRunService,
    workflow_item_request_to_dict,
)


def test_recover_interrupted_workflow_run_processes_pending_item(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = write_settings(tmp_path)
    migrate_database(db_path, settings_json_path=settings_path)
    repository = WorkflowRunRepository(db_path)
    request = workflow_request("draft-1", "Recover pending", "123")
    try:
        repository.create_run(
            WorkflowRun(
                id="run-1",
                status="running",
                total=1,
                completed=0,
                failed=0,
                skipped=0,
                concurrency=1,
            )
        )
        repository.create_item(
            WorkflowRunItem(
                id=None,
                run_id="run-1",
                draft_id=request.draft_id,
                title=request.title,
                status="pending",
                config=request.config.model_dump(),
                request=workflow_item_request_to_dict(request),
            )
        )
    finally:
        repository.close()

    service = WorkflowRunService(db_path, settings_json_path=settings_path)
    try:
        recovered = service.recover_interrupted_runs()
    finally:
        service.close()

    assert len(recovered) == 1
    assert recovered[0].status == "running"
    assert recovered[0].completed == 0
    assert recovered[0].items[0].status == "running"
    assert len(recovered[0].items[0].job_ids) == 1
    job_repository = JobRepository(db_path)
    try:
        job = job_repository.get_by_id(recovered[0].items[0].job_ids[0])
    finally:
        job_repository.close()
    assert job is not None
    assert job.type == "download_artist"
    assert job.input_user_id == "123"


def test_recover_interrupted_workflow_run_does_not_duplicate_existing_item_jobs(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = write_settings(tmp_path)
    migrate_database(db_path, settings_json_path=settings_path)
    repository = WorkflowRunRepository(db_path)
    job_repository = JobRepository(db_path)
    request = workflow_request("draft-1", "Existing job", "123")
    try:
        job_repository.create(
            Job(
                id="job-1",
                type="download_artist",
                status="queued",
                input_user_id="123",
            )
        )
        repository.create_run(
            WorkflowRun(
                id="run-1",
                status="running",
                total=1,
                completed=0,
                failed=0,
                skipped=0,
                concurrency=1,
            )
        )
        repository.create_item(
            WorkflowRunItem(
                id=None,
                run_id="run-1",
                draft_id=request.draft_id,
                title=request.title,
                status="running",
                job_ids=["job-1"],
                config=request.config.model_dump(),
                request=workflow_item_request_to_dict(request),
            )
        )
    finally:
        repository.close()
        job_repository.close()

    service = WorkflowRunService(db_path, settings_json_path=settings_path)
    try:
        recovered = service.recover_interrupted_runs()
    finally:
        service.close()

    assert recovered[0].status == "running"
    assert recovered[0].items[0].job_ids == ["job-1"]
    job_repository = JobRepository(db_path)
    try:
        jobs = job_repository.list(status="queued")
    finally:
        job_repository.close()
    assert [job.id for job in jobs] == ["job-1"]


def test_recover_interrupted_workflow_run_fails_legacy_item_without_request(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = write_settings(tmp_path)
    migrate_database(db_path, settings_json_path=settings_path)
    repository = WorkflowRunRepository(db_path)
    request = workflow_request("draft-1", "Legacy running item", "123")
    try:
        repository.create_run(
            WorkflowRun(
                id="run-1",
                status="running",
                total=1,
                completed=0,
                failed=0,
                skipped=0,
                concurrency=1,
            )
        )
        repository.create_item(
            WorkflowRunItem(
                id=None,
                run_id="run-1",
                draft_id=request.draft_id,
                title=request.title,
                status="running",
                config=request.config.model_dump(),
            )
        )
    finally:
        repository.close()

    service = WorkflowRunService(db_path, settings_json_path=settings_path)
    try:
        recovered = service.recover_interrupted_runs()
    finally:
        service.close()

    assert recovered[0].status == "failed"
    assert recovered[0].failed == 1
    assert recovered[0].items[0].status == "failed"
    assert "request metadata is missing" in recovered[0].items[0].error_message


def test_process_run_respects_skip_if_last_run_failed_without_matching_current_item(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = write_settings(tmp_path)
    migrate_database(db_path, settings_json_path=settings_path)
    service = WorkflowRunService(db_path, settings_json_path=settings_path)
    try:
        first = service.run_batch(
            items=[workflow_request("draft-1", "First", "123")],
            concurrency=1,
        )
        repository = WorkflowRunRepository(db_path)
        try:
            item = first.items[0]
            repository.update_item(
                replace(
                    item,
                    status="failed",
                    job_ids=[],
                    error_message="previous failure",
                    finished_at=item.finished_at,
                )
            )
        finally:
            repository.close()
        second = service.run_batch(
            items=[
                workflow_request(
                    "draft-1",
                    "Second",
                    "456",
                    skip_if_last_run_failed=True,
                )
            ],
            concurrency=1,
        )
    finally:
        service.close()

    assert second.status == "skipped"
    assert second.items[0].status == "skipped"


def workflow_request(
    draft_id: str,
    title: str,
    artist_id: str,
    *,
    skip_if_last_run_failed: bool = False,
) -> WorkflowBatchItemRequest:
    return WorkflowBatchItemRequest.model_validate(
        {
            "draft_id": draft_id,
            "title": title,
            "skip_if_last_run_failed": skip_if_last_run_failed,
            "config": {
                "target": {"type": "single_artist", "artist_id": artist_id},
                "filters": [],
                "actions": ["download_artist"],
                "max_artists_per_run": 25,
            },
        }
    )


def write_settings(tmp_path):
    settings_example_path = tmp_path / "settings.example.json"
    settings_example_path.write_text(
        f"""
        {{
            "download_path": "{str(tmp_path / "downloads").replace("\\", "\\\\")}",
            "refresh_token": "",
            "request_base_delay_seconds": 0,
            "request_random_delay_seconds": 0,
            "max_concurrent_downloads": 1,
            "max_active_scheduled_tasks": 1,
            "max_active_one_time_tasks": 1,
            "min_free_space_gb": 0,
            "existing_file_behavior": "skip",
            "library_stale_check_days": 30
        }}
        """,
        encoding="utf-8",
    )
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    return settings_path
