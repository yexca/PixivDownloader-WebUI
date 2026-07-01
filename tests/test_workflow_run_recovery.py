from backend.db.migrate import migrate_database
from backend.domain.entities import Job
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunRepository,
)
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.workflow_recovery_service import WorkflowRecoveryService


def test_startup_recovery_requeues_linked_running_node_job(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = write_settings(tmp_path)
    migrate_database(db_path, settings_json_path=settings_path)
    repository = WorkflowRunRepository(db_path)
    job_repository = JobRepository(db_path)
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
                source="advanced",
            )
        )
        node_id = repository.create_node_run(
            WorkflowNodeRun(
                id=None,
                workflow_run_id="run-1",
                node_id="target",
                node_type="artist_target",
                title="Target",
                position=0,
                status="running",
            )
        )
        job_repository.create(
            Job(
                id="job-1",
                type="download_artist",
                status="running",
                input_user_id="123",
                workflow_run_id="run-1",
                workflow_node_run_id=node_id,
                workflow_source="advanced_workflow",
                total_files=10,
                completed_files=3,
                started_at="2026-01-01T00:00:00Z",
            )
        )
    finally:
        repository.close()
        job_repository.close()

    service = WorkflowRecoveryService(db_path, settings_json_path=settings_path)
    try:
        recovered = service.recover_startup()
    finally:
        service.close()

    assert [run.id for run in recovered] == ["run-1"]
    job_repository = JobRepository(db_path)
    try:
        job = job_repository.get_by_id("job-1")
        events = job_repository.list_events("job-1")
    finally:
        job_repository.close()
    assert job is not None
    assert job.status == "queued"
    assert job.total_files == 0
    assert job.completed_files == 0
    assert job.started_at is None
    assert any(event.message == "Job requeued after service restart" for event in events)


def test_startup_recovery_wraps_active_orphan_jobs(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = write_settings(tmp_path)
    migrate_database(db_path, settings_json_path=settings_path)
    job_repository = JobRepository(db_path)
    try:
        job_repository.create(
            Job(
                id="running-orphan",
                type="download_artist",
                status="running",
                input_user_id="123",
                total_files=4,
                completed_files=2,
                started_at="2026-01-01T00:00:00Z",
            )
        )
        job_repository.create(
            Job(
                id="queued-orphan",
                type="download_artist",
                status="queued",
                input_user_id="456",
            )
        )
        job_repository.create(
            Job(
                id="done-orphan",
                type="download_artist",
                status="completed",
                input_user_id="789",
            )
        )
    finally:
        job_repository.close()

    service = WorkflowRecoveryService(db_path, settings_json_path=settings_path)
    try:
        recovered = service.recover_startup()
    finally:
        service.close()

    assert len(recovered) == 1
    run = recovered[0]
    assert run.source == "startup_recovery"
    assert run.status == "running"
    assert run.node_runs[0].node_type == "job_recovery"
    assert run.node_runs[0].job_ids == ["running-orphan", "queued-orphan"]
    job_repository = JobRepository(db_path)
    try:
        running = job_repository.get_by_id("running-orphan")
        queued = job_repository.get_by_id("queued-orphan")
        done = job_repository.get_by_id("done-orphan")
    finally:
        job_repository.close()
    assert running is not None
    assert running.status == "queued"
    assert running.workflow_run_id == run.id
    assert running.workflow_node_run_id == run.node_runs[0].id
    assert running.workflow_source == "startup_recovery"
    assert queued is not None
    assert queued.status == "queued"
    assert queued.workflow_run_id == run.id
    assert queued.workflow_node_run_id == run.node_runs[0].id
    assert queued.workflow_source == "startup_recovery"
    assert done is not None
    assert done.workflow_run_id is None


def test_startup_recovery_does_not_create_empty_run(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = write_settings(tmp_path)
    migrate_database(db_path, settings_json_path=settings_path)

    service = WorkflowRecoveryService(db_path, settings_json_path=settings_path)
    try:
        recovered = service.recover_startup()
    finally:
        service.close()

    assert recovered == []
    repository = WorkflowRunRepository(db_path)
    try:
        runs, total = repository.list_runs(), repository.count_runs()
    finally:
        repository.close()
    assert runs == []
    assert total == 0


def test_legacy_import_hydration_runs_inside_advanced_workflow_boundary(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = write_settings(tmp_path)
    migrate_database(db_path, settings_json_path=settings_path)
    runner = AdvancedWorkflowRunner(db_path, settings_json_path=settings_path)
    try:
        run = runner.create_run(
            AdvancedWorkflowDefinitionRequest.model_validate(
                {
                    "name": "Legacy import hydration",
                    "nodes": [
                        {
                            "id": "hydrate",
                            "type": "legacy_import_hydration",
                            "title": "Legacy import hydration",
                            "config": {
                                "artist_ids": ["111", "222"],
                                "legacy_latest_download_id_by_artist": {
                                    "111": "1000",
                                    "222": "2000",
                                },
                            },
                        }
                    ],
                }
            ),
            source="legacy_import",
        )
    finally:
        runner.close()

    assert run.source == "legacy_import"
    assert run.status == "running"
    assert run.node_runs[0].job_ids
    job_repository = JobRepository(db_path)
    try:
        job = job_repository.get_by_id(run.node_runs[0].job_ids[0])
    finally:
        job_repository.close()
    assert job is not None
    assert job.type == "hydrate_legacy_import"
    assert job.workflow_run_id == run.id
    assert job.workflow_node_run_id == run.node_runs[0].id
    assert job.workflow_source == "advanced_workflow"
    assert job.options["source"] == "legacy_database"


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
            "max_active_workflow_triggers": 1,
            "max_active_run_jobs": 1,
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
