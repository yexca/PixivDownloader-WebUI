from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Artwork, ArtworkFile
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_candidate_repository import (
    CollectArtworkCandidatesRequest,
    WorkflowCandidateRepository,
)
from backend.repositories.workflow_run_repository import WorkflowRun, WorkflowRunRepository
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


def test_advanced_workflow_actions_node_creates_candidate_artist_jobs(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)
    seed_collect_library(db_path)

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
                        "max_artists": 10,
                    },
                },
                {
                    "id": "collect",
                    "type": "collect_artworks",
                    "title": "Collect candidates",
                    "config": {"mode": "pending_files"},
                },
                {
                    "id": "actions",
                    "type": "execute_actions",
                    "title": "Execute actions",
                    "config": {"download": True, "execution_unit": "artist"},
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
    assert run.node_runs[1].status == "completed"
    assert run.node_runs[2].status == "running"

    repository = JobRepository(db_path)
    try:
        action_job = repository.get_by_id(run.node_runs[2].job_ids[0])
    finally:
        repository.close()

    assert action_job is not None
    assert action_job.type == "download_candidate_artist"
    assert action_job.input_user_id == "123"
    assert action_job.options["candidate_set_id"] == run.node_runs[1].output["candidate_set_id"]


def test_advanced_workflow_actions_node_creates_candidate_set_job(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)
    seed_collect_library(db_path)

    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Advanced set action workflow",
            "nodes": [
                {
                    "id": "target",
                    "type": "artist_target",
                    "title": "Target artists",
                    "config": {"artist_ids": ["123"], "max_artists": 10},
                },
                {
                    "id": "collect",
                    "type": "collect_artworks",
                    "title": "Collect candidates",
                    "config": {"mode": "pending_files"},
                },
                {
                    "id": "actions",
                    "type": "execute_actions",
                    "title": "Execute actions",
                    "config": {"download": True, "execution_unit": "set"},
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
    assert run.node_runs[2].status == "running"
    assert len(run.node_runs[2].job_ids) == 1

    repository = JobRepository(db_path)
    try:
        action_job = repository.get_by_id(run.node_runs[2].job_ids[0])
    finally:
        repository.close()

    assert action_job is not None
    assert action_job.type == "download_candidate_set"
    assert action_job.input_user_id is None


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


def test_advanced_workflow_collect_node_materializes_candidate_set(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)
    seed_collect_library(db_path)

    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Advanced collect workflow",
            "nodes": [
                {
                    "id": "target",
                    "type": "artist_target",
                    "title": "Target artists",
                    "config": {"artist_ids": ["123"], "max_artists": 10},
                },
                {
                    "id": "collect",
                    "type": "collect_artworks",
                    "title": "Collect candidates",
                    "config": {
                        "mode": "new_since_last_download",
                        "max_artworks": 2,
                        "sort_order": "oldest_first",
                    },
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

    assert run.status == "completed"
    assert run.node_runs[1].status == "completed"
    assert run.node_runs[1].output["candidate_count"] == 2
    candidate_set_id = run.node_runs[1].output["candidate_set_id"]
    assert isinstance(candidate_set_id, str)

    repository = WorkflowCandidateRepository(db_path)
    try:
        assert repository.count_artworks(candidate_set_id) == 2
    finally:
        repository.close()


def test_advanced_workflow_filter_node_materializes_filtered_candidate_set(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)
    seed_collect_library(db_path)

    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Advanced filter workflow",
            "nodes": [
                {
                    "id": "target",
                    "type": "artist_target",
                    "title": "Target artists",
                    "config": {"artist_ids": ["123"], "max_artists": 10},
                },
                {
                    "id": "collect",
                    "type": "collect_artworks",
                    "title": "Collect candidates",
                    "config": {
                        "mode": "all_synced",
                        "sort_order": "oldest_first",
                    },
                },
                {
                    "id": "filters",
                    "type": "filter_artworks",
                    "title": "Filter candidates",
                    "config": {
                        "ai": "exclude",
                        "required_tags": ["cat"],
                        "blocked_tags": ["blocked"],
                    },
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

    assert run.status == "completed"
    assert run.node_runs[1].output["candidate_count"] == 4
    assert run.node_runs[2].output["source_candidate_count"] == 4
    assert run.node_runs[2].output["candidate_count"] == 1

    repository = WorkflowCandidateRepository(db_path)
    try:
        assert repository.list_artwork_ids(run.node_runs[2].output["candidate_set_id"]) == ["101"]
    finally:
        repository.close()


def test_advanced_workflow_filter_node_stops_above_limit(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)
    seed_collect_library(db_path)

    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Advanced filter stop workflow",
            "nodes": [
                {
                    "id": "target",
                    "type": "artist_target",
                    "title": "Target artists",
                    "config": {"artist_ids": ["123"], "max_artists": 10},
                },
                {
                    "id": "collect",
                    "type": "collect_artworks",
                    "title": "Collect candidates",
                    "config": {"mode": "all_synced"},
                },
                {
                    "id": "filters",
                    "type": "filter_artworks",
                    "title": "Filter candidates",
                    "config": {"stop_above_limit": 2},
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

    assert run.status == "completed"
    assert run.node_runs[2].output["source_candidate_count"] == 4
    assert run.node_runs[2].output["candidate_count"] == 0
    assert run.node_runs[2].output["stopped_by_rule"] is True


def test_collect_candidate_sources_separate_new_and_pending(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)
    seed_collect_library(db_path)
    run_repository = WorkflowRunRepository(db_path)
    try:
        run_repository.create_run(
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
    finally:
        run_repository.close()
    repository = WorkflowCandidateRepository(db_path)
    try:
        new_set = repository.collect_artwork_candidates(
            CollectArtworkCandidatesRequest(
                workflow_run_id="run-1",
                workflow_node_run_id=None,
                artist_ids=["123"],
                source="new_since_last_download",
                sort_order="newest_first",
                config={},
            )
        )
        new_artwork_ids = repository.list_artwork_ids(new_set.id)
        pending_set = repository.collect_artwork_candidates(
            CollectArtworkCandidatesRequest(
                workflow_run_id="run-1",
                workflow_node_run_id=None,
                artist_ids=["123"],
                source="pending_files",
                sort_order="newest_first",
                config={},
            )
        )
        pending_artwork_ids = repository.list_artwork_ids(pending_set.id)
    finally:
        repository.close()

    assert new_artwork_ids == ["103", "102", "101"]
    assert pending_artwork_ids == ["103", "102", "090"]


def seed_collect_library(db_path) -> None:
    artist_repository = ArtistRepository(db_path)
    artwork_repository = ArtworkRepository(db_path)
    file_repository = ArtworkFileRepository(db_path)
    try:
        artist_repository.upsert(Artist(id="123", name="Artist", last_download_id="100"))
        for artwork_id, status, tags in [
            ("090", "remote_only", ("old",)),
            ("101", "downloaded", ("cat",)),
            ("102", "remote_only", ("cat", "AI生成")),
            ("103", "remote_only", ("cat", "blocked")),
        ]:
            artwork_repository.upsert(
                Artwork(
                    id=artwork_id,
                    artist_id="123",
                    title=f"Artwork {artwork_id}",
                    tags=tags,
                    files=(
                        ArtworkFile(
                            artwork_id=artwork_id,
                            page_index=0,
                            original_url=f"https://i.pximg.net/{artwork_id}.jpg",
                            file_name=f"{artwork_id}.jpg",
                            status=status,
                        ),
                    ),
                )
            )
            file_repository.upsert(
                ArtworkFile(
                    artwork_id=artwork_id,
                    page_index=0,
                    original_url=f"https://i.pximg.net/{artwork_id}.jpg",
                    file_name=f"{artwork_id}.jpg",
                    status=status,
                )
            )
    finally:
        artist_repository.close()
        artwork_repository.close()
        file_repository.close()
