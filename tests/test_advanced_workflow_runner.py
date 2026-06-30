from backend.db.migrate import migrate_database
from backend.repositories.job_repository import JobRepository
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner


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
    assert run.node_runs[0].status == "completed"
    assert run.node_runs[1].status == "running"
    assert run.node_runs[1].job_ids
    assert run.node_runs[2].status == "pending"

    repository = JobRepository(db_path)
    try:
        job = repository.get_by_id(run.node_runs[1].job_ids[0])
    finally:
        repository.close()

    assert job is not None
    assert job.type == "resolve_artist_targets"
    assert job.workflow_run_id == run.id
    assert job.workflow_source == "advanced_workflow"
