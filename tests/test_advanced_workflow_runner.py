from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Artwork
from backend.repositories.job_repository import JobRepository
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.workers.download_worker import DownloadWorker


class WorkflowTargetPixivClient:
    def get_artist_by_user_id(self, user_id: str) -> Artist:
        return Artist(id=user_id, name=f"Artist {user_id}")

    def get_artist_by_artwork_id(self, artwork_id: str) -> Artist:
        artists = {
            "999": Artist(id="456", name="Resolved Artist"),
        }
        return artists[artwork_id]

    def get_artworks_by_user_id(
        self,
        _user_id: str,
        *,
        stop_at_artwork_id: str | None = None,
    ) -> list[Artwork]:
        del stop_at_artwork_id
        return []


def test_advanced_workflow_creates_node_runs_and_action_job(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)

    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Advanced artist workflow",
            "nodes": [
                {
                    "id": "target",
                    "type": "artist_target",
                    "title": "Target artists",
                    "config": {"artist_ids": ["123"], "max_artists": 1},
                },
                {
                    "id": "actions",
                    "type": "execute_actions",
                    "title": "Execute actions",
                    "config": {"actions": ["download_artist"]},
                },
                {
                    "id": "output",
                    "type": "file_output",
                    "title": "Output",
                    "config": {"naming_rule": "{artist}/{original_filename}"},
                },
            ],
        }
    )

    runner = AdvancedWorkflowRunner(db_path)
    try:
        run = runner.create_run(definition)
    finally:
        runner.close()

    assert run.source == "advanced"
    assert run.status == "running"
    assert [node.node_id for node in run.node_runs] == ["target", "actions", "output"]
    assert run.node_runs[0].status == "running"
    assert run.node_runs[0].job_ids
    assert run.node_runs[1].status == "pending"
    assert run.node_runs[2].status == "pending"

    repository = JobRepository(db_path)
    try:
        job = repository.get_by_id(run.node_runs[0].job_ids[0])
    finally:
        repository.close()

    assert job is not None
    assert job.type == "resolve_workflow_targets"
    assert job.workflow_run_id == run.id
    assert job.workflow_source == "advanced_workflow"


def test_advanced_workflow_resolves_target_job_before_action_job(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)

    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Advanced artist workflow",
            "nodes": [
                {
                    "id": "target",
                    "type": "artist_target",
                    "title": "Target artists",
                    "config": {
                        "artist_ids": ["123"],
                        "artwork_ids": ["999"],
                        "max_artists": 10,
                    },
                },
                {
                    "id": "actions",
                    "type": "execute_actions",
                    "title": "Execute actions",
                    "config": {"actions": ["sync_artist"]},
                },
            ],
        }
    )

    runner = AdvancedWorkflowRunner(db_path)
    try:
        run = runner.create_run(definition)
        target_job_id = run.node_runs[0].job_ids[0]
        worker = DownloadWorker(
            db_path=db_path,
            pixiv_client_factory=WorkflowTargetPixivClient,
        )
        worker.run_job(target_job_id)
        run = runner.process_run(run.id, item_id=run.items[0].id)
    finally:
        runner.close()

    assert run.status == "running"
    assert run.node_runs[0].status == "completed"
    assert run.node_runs[0].output["artist_ids"] == ["123", "456"]
    assert run.node_runs[0].output["resolved_count"] == 2
    assert run.node_runs[1].status == "running"

    repository = JobRepository(db_path)
    try:
        action_job = repository.get_by_id(run.node_runs[1].job_ids[0])
    finally:
        repository.close()

    assert action_job is not None
    assert action_job.type == "resolve_artist_targets"
    assert action_job.options["artist_ids"] == ["123", "456"]
    assert action_job.options["artwork_ids"] == []


def test_advanced_workflow_sync_node_creates_artist_sync_jobs(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)

    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Advanced sync workflow",
            "nodes": [
                {
                    "id": "target",
                    "type": "artist_target",
                    "title": "Target artists",
                    "config": {
                        "artist_ids": ["123"],
                        "artwork_ids": ["999"],
                        "max_artists": 10,
                    },
                },
                {
                    "id": "sync",
                    "type": "sync_metadata",
                    "title": "Sync metadata",
                    "config": {"mode": "full"},
                },
            ],
        }
    )

    runner = AdvancedWorkflowRunner(db_path)
    try:
        run = runner.create_run(definition)
        worker = DownloadWorker(
            db_path=db_path,
            pixiv_client_factory=WorkflowTargetPixivClient,
        )
        worker.run_job(run.node_runs[0].job_ids[0])
        run = runner.process_run(run.id, item_id=run.items[0].id)
    finally:
        runner.close()

    assert run.status == "running"
    assert run.node_runs[0].status == "completed"
    assert run.node_runs[1].status == "running"
    assert run.node_runs[1].output["sync_mode"] == "full"

    repository = JobRepository(db_path)
    try:
        sync_jobs = [repository.get_by_id(job_id) for job_id in run.node_runs[1].job_ids]
    finally:
        repository.close()

    assert [(job.type, job.input_user_id) for job in sync_jobs if job is not None] == [
        ("sync_artist", "123"),
        ("sync_artist", "456"),
    ]
    assert [job.options.get("full_sync") for job in sync_jobs if job is not None] == [True, True]
