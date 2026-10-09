import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from dataclasses import replace

import pytest
import requests
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.config import Settings, SettingsService
from backend.core.errors import DatabaseError, DownloadError, JobCancelledError
from backend.db.connection import connect
from backend.db.migrate import (
    Migration,
    apply_migration,
    discover_migrations,
    ensure_migration_table,
    migrate_database,
)
from backend.domain.entities import Artist, Artwork, ArtworkFile, Job
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_candidate_repository import (
    CollectArtworkCandidatesRequest,
    FilterArtworkCandidatesRequest,
    WorkflowCandidateRepository,
)
from backend.repositories.workflow_run_repository import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunRepository,
)
from backend.schemas.downloads import DownloadCreateRequest
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.candidate_download_service import CandidateDownloadService
from backend.services.download_service import DownloadOptions
from backend.services.file_downloader import FileDownloader
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.pixiv_rate_policy import (
    PixivRequestPolicy,
    RateLimiter,
    RateLimitRule,
    RetryRule,
)
from backend.services.settings_service import AppSettingsService
from backend.services.shortcut_workflows import download_artist_definition
from backend.services.workflow_read_service import WorkflowReadService
from backend.services.workflow_recovery_service import WorkflowRecoveryService
from backend.services.workflow_schedule_service import WorkflowScheduleService, next_run_time
from backend.workers.download_worker import DownloadWorker
from backend.workers.job_queue import JobQueue


class Response:
    def __init__(self, *, fail=False, chunks=None, length=None):
        self.fail = fail
        self.chunks = chunks or [b"complete"]
        self.headers = {} if length is None else {"Content-Length": str(length)}
        self.closed = False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        assert chunk_size > 0
        yield from self.chunks
        if self.fail:
            raise requests.ConnectionError("stream interrupted")

    def close(self):
        self.closed = True


class Http:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        assert kwargs["timeout"] > 0
        self.calls.append(url)
        return next(self.responses)


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.sqlite3"
    config = tmp_path / "settings.json"
    migrate_database(db)
    SettingsService(config).save(
        Settings(
            download_path=str(tmp_path / "downloads"), min_free_space_gb=0, max_active_run_jobs=2
        )
    )
    config.with_name("settings.example.json").write_text(config.read_text(), encoding="utf-8")
    with ExitStack() as stack:
        repos = [
            stack.enter_context(closing(cls(db)))
            for cls in (
                ArtistRepository,
                ArtworkRepository,
                ArtworkFileRepository,
                WorkflowCandidateRepository,
                WorkflowRunRepository,
                JobRepository,
            )
        ]
        yield (db, config, *repos)


def seed(store, statuses=("pending", "pending", "pending", "pending"), *, pages=1):
    _, _, artists, artworks, files, _, runs, _ = store
    artists.upsert(Artist(id="1", name="Artist", last_download_id="99"))
    for index, status in enumerate(statuses, 100):
        artwork = Artwork(id=str(index), artist_id="1", tags=("cat",), page_count=pages)
        artworks.upsert(artwork)
        for page in range(pages):
            files.upsert(
                ArtworkFile(
                    artwork_id=str(index),
                    page_index=page,
                    original_url=f"https://example.test/{index}_p{page}.jpg",
                    file_name=f"{index}_p{page}.jpg",
                    status=status,
                )
            )
    runs.create_run(
        WorkflowRun(
            id="run",
            status="running",
            total=1,
            completed=0,
            failed=0,
            skipped=0,
            concurrency=1,
            source="advanced",
        )
    )


def collect(store, source="new_since_last_download", limit=None):
    return store[5].collect_artwork_candidates(
        CollectArtworkCandidatesRequest(
            workflow_run_id="run",
            workflow_node_run_id=None,
            artist_ids=["1"],
            source=source,
            sort_order="newest_first",
            limit=limit,
        )
    )


def service(store, downloader):
    return CandidateDownloadService(
        artist_repository=store[2],
        file_repository=store[4],
        candidate_repository=store[5],
        file_downloader=downloader,
    )


@pytest.mark.parametrize("behavior", ["skip", "overwrite"])
def test_interrupted_stream_never_publishes_fragment(tmp_path, behavior):
    broken, good = Response(fail=True, chunks=[b"partial"]), Response()
    http = Http([broken, good])
    downloader = FileDownloader(tmp_path, http_client=http, existing_file_behavior=behavior)
    target = tmp_path / "Artist - 1" / "100_p0.jpg"
    if behavior == "overwrite":
        target.parent.mkdir()
        target.write_bytes(b"original")
    with pytest.raises(DownloadError):
        downloader.download("Artist", "1", "https://example.test/100_p0.jpg")
    assert broken.closed
    assert not list(tmp_path.rglob("*.part"))
    assert target.read_bytes() == b"original" if behavior == "overwrite" else not target.exists()
    result = downloader.download("Artist", "1", "https://example.test/100_p0.jpg")
    assert not result.skipped
    assert target.read_bytes() == b"complete"
    assert good.closed


def test_length_mismatch_and_cancel_clean_temporary_file(tmp_path):
    for response, callback, error in [
        (Response(length=50), None, DownloadError),
        (Response(chunks=[b"one", b"two"]), lambda: True, JobCancelledError),
    ]:
        downloader = FileDownloader(tmp_path, http_client=Http([response]))
        with pytest.raises(error):
            downloader.download("A", "1", "https://example.test/100.jpg", cancel_callback=callback)
        assert not list(tmp_path.rglob("*.part"))
        assert not list(tmp_path.rglob("*.jpg"))


def test_failed_legacy_fragment_is_replaced_even_with_skip(store, tmp_path):
    seed(store, ("failed",))
    candidates = collect(store, "failed_files")
    path = tmp_path / "downloads" / "Artist - 1" / "100_p0.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"partial")
    downloader = FileDownloader(
        tmp_path / "downloads", http_client=Http([Response()]), existing_file_behavior="skip"
    )
    summary = service(store, downloader).download(candidate_set_id=candidates.id)
    assert summary.downloaded_files == 1 and summary.skipped_files == 0
    assert path.read_bytes() == b"complete"


@pytest.mark.parametrize(
    "source,expected",
    [
        ("failed_files", ["100"]),
        ("pending_files", ["101"]),
        ("new_since_last_download", ["101", "100"]),
        ("all_synced", ["102", "101", "100"]),
    ],
)
def test_chained_filters_preserve_file_source(store, tmp_path, source, expected):
    seed(store, ("failed", "pending", "downloaded"))
    candidates = collect(store, source)
    for _ in range(2):
        candidates = (
            store[5]
            .filter_artwork_candidates(
                FilterArtworkCandidatesRequest(
                    workflow_run_id="run",
                    workflow_node_run_id=None,
                    source_set_id=candidates.id,
                    required_tags=["cat"],
                )
            )
            .candidate_set
        )
    http = Http([Response() for _ in expected])
    summary = service(store, FileDownloader(tmp_path / "files", http_client=http)).download(
        candidate_set_id=candidates.id
    )
    assert summary.total_files == len(expected)
    assert [url.rsplit("/", 1)[-1].split("_")[0] for url in http.calls] == expected


def test_incremental_limit_cannot_jump_over_unfinished_artworks(store, tmp_path):
    seed(store)
    downloader = FileDownloader(
        tmp_path / "files", http_client=Http([Response() for _ in range(4)])
    )
    first = collect(store, limit=2)
    assert store[5].list_artwork_ids(first.id) == ["103", "102"]
    service(store, downloader).download(candidate_set_id=first.id)
    assert store[2].get_by_id("1").last_download_id == "99"
    second = collect(store, limit=2)
    assert store[5].list_artwork_ids(second.id) == ["101", "100"]
    service(store, downloader).download(candidate_set_id=second.id)
    assert store[2].get_by_id("1").last_download_id == "103"
    assert collect(store).total_count == 0


def test_failed_page_and_restart_keep_cursor_gap(store, tmp_path):
    seed(store, ("pending", "pending"), pages=2)
    downloader = FileDownloader(
        tmp_path / "files",
        http_client=Http(
            [
                Response(),
                Response(fail=True),
                Response(),
                Response(),
                Response(),
            ]
        ),
    )
    summary = service(store, downloader).download(candidate_set_id=collect(store).id)
    assert summary.failed_files == 1
    assert store[2].get_by_id("1").last_download_id == "100"
    # A new service instance after recovery selects only the unfinished page.
    next_set = collect(store)
    assert store[5].list_artwork_ids(next_set.id) == ["101"]
    summary = service(store, downloader).download(candidate_set_id=next_set.id)
    assert summary.total_files == 1
    assert store[2].get_by_id("1").last_download_id == "101"


def test_cancel_keeps_completed_files_and_blocks_next_file(store, tmp_path):
    seed(store, ("pending", "pending"))
    candidates = collect(store)
    job = Job(
        id="download",
        type="download_candidate_set",
        status="queued",
        options={"candidate_set_id": candidates.id},
    )
    store[7].create(job)
    http = Http([Response(), Response()])
    worker = DownloadWorker(
        db_path=store[0],
        settings_json_path=store[1],
        file_downloader_factory=lambda: FileDownloader(tmp_path / "files", http_client=http),
    )
    original_progress = worker._record_progress

    def cancel_after_first(repository, job_id, progress):
        original_progress(repository, job_id, progress)
        repository.request_cancel(job_id)

    worker._record_progress = cancel_after_first
    result = worker.run_job(job.id)
    assert result.status == "cancelled" and result.completed_files == 1
    assert len(http.calls) == 1
    assert store[2].get_by_id("1").last_download_id == "99"
    assert store[5].list_artwork_ids(collect(store).id) == ["100"]


@pytest.mark.parametrize(
    "responses,result_kind,completed",
    [
        ([Response(fail=True), Response(fail=True)], "failed", 0),
        ([Response(), Response(fail=True)], "partial", 1),
        ([Response(), Response()], "completed", 2),
    ],
)
def test_candidate_job_propagates_failure_result(
    store, tmp_path, responses, result_kind, completed
):
    seed(store, ("pending", "pending"))
    candidates = collect(store)
    store[7].create(
        Job(
            id="download",
            type="download_candidate_set",
            status="queued",
            options={"candidate_set_id": candidates.id},
        )
    )
    result = DownloadWorker(
        db_path=store[0],
        settings_json_path=store[1],
        file_downloader_factory=lambda: FileDownloader(
            tmp_path / "files", http_client=Http(responses)
        ),
    ).run_job("download")
    assert result.options["result"] == result_kind
    assert result.status == ("completed" if result_kind == "completed" else "failed")
    assert result.completed_files == completed
    assert result.options["error_retryable"] == (result_kind != "completed")


def test_activation_cancel_and_recovery_preserve_node_link(store):
    seed(store, ())
    node_id = store[6].create_node_run(
        WorkflowNodeRun(
            id=None,
            workflow_run_id="run",
            node_id="n",
            node_type="sync_metadata",
            title="Sync",
            position=0,
            status="running",
            output={"jobs_initialized": True},
        )
    )
    store[7].create(
        Job(
            id="inactive",
            type="sync_artist",
            status="inactive",
            input_user_id="1",
            options={"activation_scope": "one_time"},
            workflow_run_id="run",
            workflow_node_run_id=node_id,
        )
    )
    with closing(JobService(store[0], settings_json_path=store[1])) as jobs:
        activated = jobs.activate_inactive_one_time_jobs()
        assert activated[0].workflow_node_run_id == node_id
        cancelled = jobs.cancel_job("inactive")
        assert cancelled.workflow_node_run_id == node_id
    with closing(WorkflowRecoveryService(store[0], settings_json_path=store[1])) as recovery:
        recovered = recovery.recover_startup()
    assert recovered[0].status == "cancelled"
    assert store[7].count() == 1


@pytest.mark.parametrize(
    "first,expected", [("failed", "failed"), ("cancelled", "cancelled"), ("partial", "partial")]
)
def test_upstream_terminal_state_finishes_downstream(store, first, expected):
    seed(store, ())
    for position, state in enumerate([first, "pending"]):
        store[6].create_node_run(
            WorkflowNodeRun(
                id=None,
                workflow_run_id="run",
                node_id=str(position),
                node_type="execute_actions",
                title="Action",
                position=position,
                status=state,
            )
        )
    with closing(AdvancedWorkflowRunner(store[0])) as runner:
        result = runner.process_run("run")
    assert result.status == expected and result.finished_at
    assert [node.status for node in result.node_runs] == [first, "skipped"]
    assert store[7].count() == 0


def test_concurrent_progress_claim_and_read_only_queries(store):
    seed(store, ())
    store[6].create_node_run(
        WorkflowNodeRun(
            id=None,
            workflow_run_id="run",
            node_id="target",
            node_type="artist_target",
            title="Target",
            position=0,
            status="pending",
            input={"config": {"artist_ids": ["1"]}},
        )
    )
    with closing(WorkflowReadService(store[0])) as reader:
        before = store[6].conn.total_changes
        reader.get_run("run")
        reader.list_runs()
        assert store[7].count() == 0
        assert store[6].conn.total_changes == before
    barrier = threading.Barrier(2)

    def progress():
        with closing(AdvancedWorkflowRunner(store[0], settings_json_path=store[1])) as runner:
            barrier.wait()
            return runner.process_run("run")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(progress) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    assert store[7].count() == 1
    node = store[6].get_run("run").node_runs[0]
    persisted = json.loads(
        store[6]
        .conn.execute("SELECT job_ids_json FROM workflow_node_runs WHERE id = ?", (node.id,))
        .fetchone()[0]
    )
    assert persisted == node.job_ids and len(persisted) == 1


def test_restart_during_multiple_artist_job_creation_is_idempotent(store):
    seed(store, ())
    target_id = store[6].create_node_run(
        WorkflowNodeRun(
            id=None,
            workflow_run_id="run",
            node_id="target",
            node_type="artist_target",
            title="Target",
            position=0,
            status="completed",
            output={"artist_ids": ["1", "2"]},
        )
    )
    node_id = store[6].create_node_run(
        WorkflowNodeRun(
            id=None,
            workflow_run_id="run",
            node_id="sync",
            node_type="sync_metadata",
            title="Sync",
            position=1,
            status="running",
            input={"config": {"mode": "full"}, "execution_started": True},
        )
    )
    assert target_id
    with closing(JobService(store[0], settings_json_path=store[1])) as jobs:
        first = jobs.create_download_job(
            user_id="1",
            artwork_id=None,
            sync_only=True,
            workflow_link=WorkflowJobLink(
                run_id="run", node_run_id=node_id, source="advanced_workflow"
            ),
        )
    with closing(WorkflowRecoveryService(store[0], settings_json_path=store[1])) as recovery:
        recovery.recover_startup()
    node = store[6].get_run("run").node_runs[1]
    assert len(node.job_ids) == 2 and first.id in node.job_ids
    store[7].update(replace(store[7].get_by_id(first.id), status="completed"))
    with closing(AdvancedWorkflowRunner(store[0], settings_json_path=store[1])) as runner:
        result = runner.process_run("run")
        assert result.status == "running"
        remaining = next(job for job in store[7].list_by_ids(node.job_ids) if job.id != first.id)
        store[7].update(replace(remaining, status="completed"))
        result = runner.process_run("run")
        assert result.status == "completed"
    assert store[7].count() == 2


def test_migration_sql_and_version_rollback_together(tmp_path):
    path = tmp_path / "broken.sql"
    path.write_text("CREATE TABLE partial (id INTEGER); INSERT INTO missing VALUES (1);")
    with closing(connect(tmp_path / "test.db")) as conn:
        ensure_migration_table(conn)
        with pytest.raises(DatabaseError):
            apply_migration(conn, Migration("999", "broken", path))
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchone() is None
        )
        assert conn.execute("SELECT * FROM schema_migrations").fetchall() == []
        path.write_text("CREATE TABLE complete (id INTEGER);")
        apply_migration(conn, Migration("999", "complete", path))
        assert conn.execute("SELECT * FROM schema_migrations").fetchone()["version"] == "999"


@pytest.mark.parametrize("action", ["sync_artist", "retry_failed_artist", "download_artist"])
def test_upgrade_repairs_017_semantics_without_running_jobs(tmp_path, action):
    db = tmp_path / "upgrade.db"
    with closing(connect(db)) as conn:
        ensure_migration_table(conn)
        for migration in discover_migrations():
            if migration.version <= "016":
                apply_migration(conn, migration)
        conn.execute(
            """INSERT INTO scheduled_tasks
            (name,action,status,target_artist_id,interval_days,run_after_startup,created_at,updated_at)
            VALUES ('Legacy',?,'paused','1',2,0,'2025-01-01T00:00:00Z','2025-01-02T00:00:00Z')""",
            (action,),
        )
        conn.commit()
        for migration in discover_migrations():
            if "017" <= migration.version <= "021":
                apply_migration(conn, migration)
        before = conn.execute(
            "SELECT status,schedule_json,next_run_at FROM workflow_triggers"
        ).fetchone()
    migrate_database(db)
    with closing(connect(db)) as conn:
        definition = json.loads(
            conn.execute("SELECT definition_json FROM workflow_definitions").fetchone()[0]
        )
        after = conn.execute(
            "SELECT status,schedule_json,next_run_at FROM workflow_triggers"
        ).fetchone()
        assert tuple(before) == tuple(after)
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    nodes = definition["nodes"]
    if action == "sync_artist":
        assert [node["type"] for node in nodes] == ["artist_target", "sync_metadata"]
    elif action == "retry_failed_artist":
        assert (
            next(node for node in nodes if node["type"] == "collect_artworks")["config"]["mode"]
            == "failed_files"
        )


def test_settings_reads_are_write_free_and_concurrent_updates_merge(store):
    db, config = store[:2]
    with closing(AppSettingsService(db_path=db, settings_json_path=config)) as settings:
        before = settings.repository.conn.total_changes
        for _ in range(3):
            settings.load()
        assert settings.repository.conn.total_changes == before
    barrier = threading.Barrier(2)

    def update(values):
        with closing(AppSettingsService(db_path=db, settings_json_path=config)) as settings:
            barrier.wait()
            settings.update(values)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(update, {"max_concurrent_downloads": 3}),
            pool.submit(update, {"max_active_run_jobs": 4}),
        ]
        for future in futures:
            future.result(timeout=10)
    loaded = SettingsService(config).load()
    assert loaded.max_concurrent_downloads == 3 and loaded.max_active_run_jobs == 4


def test_validation_errors_are_serializable_and_null_is_rejected(store):
    client = TestClient(
        create_app(db_path=store[0], settings_json_path=store[1], start_queue=False)
    )
    empty = client.post("/api/downloads", json={})
    null = client.put("/api/settings", json={"max_active_run_jobs": None})
    assert empty.status_code == 422
    assert "exactly one" in empty.json()["error"]["details"]["errors"][0]["msg"]
    assert null.status_code == 422
    assert "cannot be null" in null.json()["error"]["details"]["errors"][0]["msg"]


def test_global_conflicts_force_rescan_and_tag_options(store):
    with closing(AppSettingsService(db_path=store[0], settings_json_path=store[1])) as settings:
        settings.update({"existing_file_behavior": "overwrite"})
    worker = DownloadWorker(db_path=store[0], settings_json_path=store[1])
    downloader = worker._create_candidate_file_downloader(
        Job(id="j", type="download_candidate_set", status="queued")
    )
    assert downloader.existing_file_behavior == "overwrite"
    request = DownloadCreateRequest(user_id="1", force_rescan=True)
    assert request.force_rescan
    variants = [{"tag": "cat", "behavior": "skip", "naming_rule": "cat/{original_filename}"}]
    definition = download_artist_definition(
        name="Test",
        artist_ids=["1"],
        artwork_ids=[],
        options={"force_rescan": True, "tag_variants": variants},
        collect_mode="new_since_last_download",
    )
    assert definition.nodes[1].config["mode"] == "full"
    assert definition.nodes[-1].config["tag_variants"] == variants


def test_tag_behavior_and_naming_are_executed(store, tmp_path):
    seed(store, ("pending",))
    http = Http([Response()])
    candidates = collect(store)
    summary = service(store, FileDownloader(tmp_path / "files", http_client=http)).download(
        candidate_set_id=candidates.id,
        options=DownloadOptions(tag_variants=({"tag": "cat", "behavior": "skip"},)),
    )
    assert summary.skipped_files == 1 and http.calls == []


def test_retry_wait_is_cancellable():
    cancelled = False
    sleeps = []

    def sleep(seconds):
        nonlocal cancelled
        sleeps.append(seconds)
        cancelled = True

    policy = PixivRequestPolicy(RateLimiter(RateLimitRule(0)), RetryRule({}, (30,)), sleep=sleep)

    def request():
        raise requests.ConnectionError("offline")

    with pytest.raises(JobCancelledError):
        policy.run("test", request, cancel_callback=lambda: cancelled)
    assert sum(sleeps) <= 0.2


def test_calendar_timezone_and_legacy_utc():
    base = "2026-10-08T23:00:00Z"
    assert (
        next_run_time({"type": "daily", "time": "09:00", "timezone": "Asia/Tokyo"}, from_time=base)
        == "2026-10-09T00:00:00Z"
    )
    assert (
        next_run_time({"type": "daily", "time": "09:00"}, from_time=base) == "2026-10-09T09:00:00Z"
    )


def test_trigger_success_waits_for_execution_and_overlap_is_limited(store):
    with closing(WorkflowScheduleService(store[0], settings_json_path=store[1])) as scheduler:
        definition = AdvancedWorkflowDefinitionRequest.model_validate(
            {
                "name": "Scheduled",
                "nodes": [
                    {"id": "target", "type": "artist_target", "config": {"artist_ids": ["1"]}},
                ],
            }
        )
        _, trigger = scheduler.save_with_trigger(
            definition, schedule={"type": "interval", "every": 1, "unit": "minutes"}
        )
        scheduler.repository.update_trigger(replace(trigger, next_run_at="2000-01-01T00:00:00Z"))
        result = scheduler.run_due_triggers()[0]
        assert result.trigger.last_success_at is None
        current = scheduler.repository.get_trigger(trigger.id)
        scheduler.repository.update_trigger(replace(current, next_run_at="2000-01-01T00:00:00Z"))
        assert scheduler.run_due_triggers() == []
        with closing(WorkflowRunRepository(store[0])) as runs:
            run = runs.get_run(result.run.id)
            runs.update_run(replace(run, status="completed", finished_at="2099-01-01T00:00:00Z"))
        scheduler._reconcile_results()
        assert (
            scheduler.repository.get_trigger(trigger.id).last_success_at == "2099-01-01T00:00:00Z"
        )


def test_queue_retries_and_stops_without_orphan_threads(store):
    async def exercise():
        queue = JobQueue(db_path=store[0], settings_json_path=store[1], poll_interval_seconds=0.01)
        attempts = 0
        original = queue._next_queued_job_id

        def flaky():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise DatabaseError("temporary failure")
            return original()

        queue._next_queued_job_id = flaky
        await queue.start()
        for _ in range(200):
            await asyncio.sleep(0.01)
            if attempts >= 2:
                break
        assert attempts >= 2 and queue.healthy
        await queue.stop()
        assert queue._task.done() and not queue._active

    asyncio.run(exercise())


def test_cancel_during_response_stream_preserves_old_file(tmp_path):
    cancelled = False

    class StreamingResponse(Response):
        def iter_content(self, chunk_size):
            assert chunk_size > 0
            nonlocal cancelled
            yield b"partial"
            cancelled = True
            yield b"remaining"

    response = StreamingResponse()
    downloader = FileDownloader(tmp_path, http_client=Http([response]))
    target = tmp_path / "Artist - 1" / "100.jpg"
    target.parent.mkdir()
    target.write_bytes(b"original")
    with pytest.raises(JobCancelledError):
        downloader.download(
            "Artist", "1", "https://example.test/100.jpg", cancel_callback=lambda: cancelled
        )
    assert target.read_bytes() == b"original"
    assert response.closed and not list(tmp_path.rglob("*.part"))


def test_filter_exclusion_leaves_incremental_gap_and_tag_naming_is_applied(store, tmp_path):
    seed(store, ("pending", "pending"))
    store[3].upsert(Artwork(id="100", artist_id="1", tags=("dog",)))
    all_candidates = collect(store)
    filtered = (
        store[5]
        .filter_artwork_candidates(
            FilterArtworkCandidatesRequest(
                workflow_run_id="run",
                workflow_node_run_id=None,
                source_set_id=all_candidates.id,
                required_tags=["cat"],
            )
        )
        .candidate_set
    )
    downloader = FileDownloader(tmp_path, http_client=Http([Response()]))
    service(store, downloader).download(
        candidate_set_id=filtered.id,
        options=DownloadOptions(
            tag_variants=({"tag": "cat", "naming_rule": "cats/{artwork_id}/{page}.{ext}"},)
        ),
    )
    assert (tmp_path / "cats" / "101" / "0.jpg").read_bytes() == b"complete"
    assert store[2].get_by_id("1").last_download_id == "99"
    assert store[5].list_artwork_ids(collect(store).id) == ["100"]


def test_candidate_job_retry_only_downloads_failed_pages(store, tmp_path):
    seed(store, ("downloaded", "failed"))
    candidates = collect(store, "all_synced")
    source = Job(
        id="original",
        type="download_candidate_set",
        status="failed",
        options={"candidate_set_id": candidates.id},
    )
    store[7].create(source)
    with closing(JobService(store[0], settings_json_path=store[1])) as jobs:
        retry = jobs.retry_job(source.id)
    http = Http([Response()])
    worker = DownloadWorker(
        db_path=store[0],
        settings_json_path=store[1],
        file_downloader_factory=lambda: FileDownloader(tmp_path, http_client=http),
    )
    result = worker.run_job(retry.id)
    assert result.status == "completed" and result.total_files == 1
    assert http.calls == ["https://example.test/101_p0.jpg"]


def test_explicit_targets_honor_staleness_and_unavailable_filters(store):
    from backend.services.workflow_nodes.target import resolve_artist_ids

    for artist in [
        Artist(id="1", name="Old", last_checked_at="2000-01-01T00:00:00Z"),
        Artist(id="2", name="Recent", last_checked_at="2099-01-01T00:00:00Z"),
        Artist(
            id="3",
            name="Gone",
            account_status="unavailable",
            last_checked_at="2000-01-01T00:00:00Z",
        ),
    ]:
        store[2].upsert(artist)
    config = {
        "scope": "artists",
        "artist_ids": ["1", "2", "3"],
        "filters": [{"type": "last_checked_before_days", "days": 30}],
    }
    assert resolve_artist_ids(config, store[0]) == ["1"]
    assert resolve_artist_ids({"scope": "artists_with_tag"}, store[0]) == []


def test_single_artwork_shortcut_keeps_collection_scope(store):
    seed(store)
    definition = download_artist_definition(
        name="Single", artist_ids=[], artwork_ids=["101"], options={}, collect_mode="all_synced"
    )
    assert definition.nodes[0].config["scope"] == "artworks"
    candidates = store[5].collect_artwork_candidates(
        CollectArtworkCandidatesRequest(
            workflow_run_id="run",
            workflow_node_run_id=None,
            artist_ids=["1"],
            artwork_ids=["101"],
            source="all_synced",
            sort_order="newest_first",
        )
    )
    assert store[5].list_artwork_ids(candidates.id) == ["101"]


def test_queue_concurrency_and_shutdown_wait_for_real_threads(store):
    with closing(AppSettingsService(db_path=store[0], settings_json_path=store[1])) as settings:
        settings.update({"max_concurrent_downloads": 2})
    for number in range(3):
        store[7].create(Job(id=f"parallel-{number}", type="download", status="queued"))

    class Worker:
        stop_event = threading.Event()
        lock = threading.Lock()
        active = 0
        peak = 0
        finished = 0

        def run_job(self, job_id):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            assert self.stop_event.wait(timeout=5), "Queue failed to signal its threads"
            with closing(JobRepository(store[0])) as jobs:
                jobs.update(replace(jobs.get_by_id(job_id), status="cancelled"))
            with self.lock:
                self.active -= 1
                self.finished += 1

    worker = Worker()

    async def exercise():
        queue = JobQueue(
            db_path=store[0], settings_json_path=store[1], worker=worker, poll_interval_seconds=0.01
        )
        await queue.start()
        try:
            for _ in range(200):
                if worker.active == 2:
                    break
                await asyncio.sleep(0.01)
            assert worker.active == 2 and worker.peak == 2
        finally:
            await queue.stop()
        assert worker.active == 0 and worker.finished == 2 and not queue._active
        assert store[7].get_by_id("parallel-2").status == "queued"

    asyncio.run(exercise())


def test_upload_body_limit_before_parser_even_without_content_length():
    from backend.core.request_limits import LegacyUploadLimit

    async def exercise():
        reached = False
        messages = iter(
            [
                {"type": "http.request", "body": b"1234", "more_body": True},
                {"type": "http.request", "body": b"5678", "more_body": False},
            ]
        )
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        async def downstream(*_args):
            nonlocal reached
            reached = True

        await LegacyUploadLimit(downstream, max_bytes=5)(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/imports/legacy-database",
                "headers": [],
            },
            receive,
            send,
        )
        assert not reached and sent[0]["status"] == 413

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "schedule,base,expected",
    [
        (
            {"type": "weekly", "days_of_week": [1], "time": "09:00", "timezone": "Asia/Tokyo"},
            "2026-10-09T00:00:00Z",
            "2026-10-12T00:00:00Z",
        ),
        (
            {"type": "monthly", "day": "last", "time": "09:00", "timezone": "Asia/Tokyo"},
            "2026-10-09T00:00:00Z",
            "2026-10-31T00:00:00Z",
        ),
        (
            {"type": "daily", "time": "02:30", "timezone": "America/New_York"},
            "2026-03-08T05:00:00Z",
            "2026-03-08T07:30:00Z",
        ),
        (
            {"type": "daily", "time": "01:30", "timezone": "America/New_York"},
            "2026-11-01T06:15:00Z",
            "2026-11-02T06:30:00Z",
        ),
    ],
)
def test_weekly_monthly_and_dst_schedules(schedule, base, expected):
    assert next_run_time(schedule, from_time=base) == expected


def test_invalid_schedule_timezone_returns_specific_validation_error(store):
    client = TestClient(
        create_app(db_path=store[0], settings_json_path=store[1], start_queue=False)
    )
    response = client.post(
        "/api/workflows/definitions",
        json={
            "definition": {"nodes": [{"id": "target", "type": "artist_target"}]},
            "trigger": {"schedule": {"type": "daily", "time": "09:00", "timezone": "Invalid/Zone"}},
        },
    )
    assert response.status_code == 422
    assert "IANA" in response.json()["error"]["details"]["errors"][0]["msg"]


def test_health_reports_failed_executor(store):
    from types import SimpleNamespace

    app = create_app(db_path=store[0], settings_json_path=store[1], start_queue=False)
    app.state.executors_enabled = True
    app.state.job_queue = SimpleNamespace(healthy=False)
    app.state.workflow_trigger_runner = SimpleNamespace(healthy=True)
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json()["executors"]["queue"] is False


@pytest.mark.parametrize("operation", ["artist", "artwork", "pages"])
def test_metadata_client_does_not_convert_cancellation_into_failure(operation):
    from types import SimpleNamespace

    from backend.services.pixiv_client import PixivClient

    policy = PixivRequestPolicy(
        RateLimiter(RateLimitRule(0)), RetryRule({}), cancel_callback=lambda: True
    )
    api = SimpleNamespace(auth=lambda **_kwargs: None)
    client = PixivClient(refresh_token="test-only", api=api, request_policy=policy)
    with pytest.raises(JobCancelledError):
        if operation == "artist":
            client.get_artist_by_user_id("1")
        elif operation == "artwork":
            client.get_artist_by_artwork_id("100")
        else:
            client.get_artworks_by_user_id("1")


def test_stale_metadata_upsert_cannot_regress_download_cursor(store):
    seed(store, ("downloaded",))
    stale_artist = store[2].get_by_id("1")
    store[2].advance_download_cursor("1")
    assert store[2].get_by_id("1").last_download_id == "100"
    store[2].upsert(replace(stale_artist, name="Updated"))
    assert store[2].get_by_id("1").last_download_id == "100"


def test_queue_retries_worker_infrastructure_failure_without_losing_claim(store):
    job = Job(id="flaky-worker", type="download", status="queued")
    store[7].create(job)

    class Worker:
        stop_event = threading.Event()
        calls = 0

        def run_job(self, job_id):
            self.calls += 1
            if self.calls == 1:
                raise OSError("temporary worker failure")
            with closing(JobRepository(store[0])) as jobs:
                jobs.update(replace(jobs.get_by_id(job_id), status="completed"))

    worker = Worker()

    async def exercise():
        queue = JobQueue(
            db_path=store[0], settings_json_path=store[1], worker=worker, poll_interval_seconds=0.01
        )
        await queue.start()
        try:
            for _ in range(300):
                if store[7].get_by_id(job.id).status == "completed":
                    break
                await asyncio.sleep(0.01)
            assert worker.calls == 2 and store[7].get_by_id(job.id).status == "completed"
        finally:
            await queue.stop()

    asyncio.run(exercise())


@pytest.mark.parametrize("edited", [False, True])
def test_legacy_upgrade_preserves_filters_options_and_user_edits(tmp_path, edited):
    db = tmp_path / "upgrade.db"
    config = {
        "target": {"type": "artists", "artist_ids": ["1", "2"]},
        "actions": ["retry_failed_artist"],
        "max_artists_per_run": 2,
        "filters": [{"type": "last_checked_before_days", "days": 30}],
        "download_options": {
            "force_rescan": True,
            "max_artworks": 2,
            "naming_rule": "{artist_id}/{artwork_id}/{page}.{ext}",
            "tag_variants": [{"tag": "cat", "behavior": "skip"}],
        },
    }
    with closing(connect(db)) as conn:
        ensure_migration_table(conn)
        for migration in discover_migrations():
            if migration.version <= "016":
                apply_migration(conn, migration)
        conn.execute(
            """INSERT INTO scheduled_tasks
            (name,action,status,target_artist_id,interval_days,run_after_startup,
             created_at,updated_at,config_json)
            VALUES ('Legacy','retry_failed_artist','active','1',2,0,
                    '2025-01-01T00:00:00Z','2025-01-02T00:00:00Z',?)""",
            (json.dumps(config),),
        )
        conn.commit()
        for migration in discover_migrations():
            if "017" <= migration.version <= "021":
                apply_migration(conn, migration)
        if edited:
            original = {
                "name": "User edited",
                "nodes": [
                    {"id": "target", "type": "artist_target", "config": {"artist_ids": ["9"]}}
                ],
            }
            conn.execute(
                "UPDATE workflow_definitions SET definition_json=?,"
                "updated_at='2099-01-01T00:00:00Z'",
                (json.dumps(original),),
            )
            conn.commit()
    migrate_database(db)
    with closing(connect(db)) as conn:
        repaired = json.loads(
            conn.execute("SELECT definition_json FROM workflow_definitions").fetchone()[0]
        )
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM workflow_triggers").fetchone()[0] == "active"
    if edited:
        assert repaired == original
    else:
        configs = {node["type"]: node["config"] for node in repaired["nodes"]}
        assert configs["artist_target"]["artist_ids"] == ["1", "2"]
        assert configs["artist_target"]["filters"] == config["filters"]
        assert configs["sync_metadata"]["mode"] == "full"
        assert configs["collect_artworks"]["mode"] == "failed_files"
        assert (
            configs["execute_actions"]["naming_rule"] == config["download_options"]["naming_rule"]
        )
        assert (
            configs["execute_actions"]["tag_variants"] == config["download_options"]["tag_variants"]
        )


def test_startup_trigger_flag_and_global_active_limit(store):
    with closing(WorkflowScheduleService(store[0], settings_json_path=store[1])) as scheduler:
        definition = AdvancedWorkflowDefinitionRequest.model_validate(
            {"nodes": [{"id": "target", "type": "artist_target", "config": {"artist_ids": ["1"]}}]}
        )
        triggers = []
        for startup in [False, True, True]:
            _, trigger = scheduler.save_with_trigger(
                definition,
                schedule={
                    "type": "interval",
                    "every": 1,
                    "unit": "days",
                    "run_after_startup": startup,
                },
            )
            triggers.append(trigger)
        assert scheduler.run_due_triggers() == []
        dispatched = scheduler.run_due_triggers(startup_scan=True)
        assert len(dispatched) == 1 and dispatched[0].trigger.id in {triggers[1].id, triggers[2].id}
        assert scheduler.run_due_triggers(startup_scan=True) == []
        assert store[6].count_runs() == 1


def test_creation_and_activation_enforce_capacity_after_stale_reads(store):
    with closing(AppSettingsService(db_path=store[0], settings_json_path=store[1])) as settings:
        settings.update({"max_active_run_jobs": 1})
    barrier = threading.Barrier(2)

    def create(number):
        with closing(JobService(store[0], settings_json_path=store[1])) as jobs:
            jobs._next_one_time_status = lambda: "queued"
            barrier.wait()
            return jobs.create_download_job(user_id=str(number), artwork_id=None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create, number) for number in [1, 2]]
        created = [future.result(timeout=10) for future in futures]
    assert sorted(job.status for job in created) == ["inactive", "queued"]
    with closing(JobService(store[0], settings_json_path=store[1])) as jobs:
        jobs.create_download_job(user_id="3", artwork_id=None)
        jobs.cancel_job(next(job.id for job in created if job.status == "queued"))

    def activate():
        with closing(JobService(store[0], settings_json_path=store[1])) as jobs:
            barrier.wait()
            return jobs.activate_inactive_one_time_jobs()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(activate) for _ in range(2)]
        activated = [job for future in futures for job in future.result(timeout=10)]
    assert len(activated) == 1 and store[7].count_active_one_time() == 1


def test_target_scope_ignores_unused_form_values(store):
    from backend.services.workflow_nodes.target import resolve_artist_ids, resolve_artwork_ids

    config = {
        "scope": "artists",
        "artist_source": "artist_ids",
        "artist_ids": ["1"],
        "artwork_ids": ["200"],
    }
    assert resolve_artist_ids(config, store[0]) == ["1"]
    assert resolve_artwork_ids(config) == []
    config["artist_source"] = "artwork_ids"
    assert resolve_artist_ids(config, store[0]) == []
    assert resolve_artwork_ids(config) == ["200"]


def test_old_success_does_not_erase_new_dispatch_error(store):
    with closing(WorkflowScheduleService(store[0], settings_json_path=store[1])) as scheduler:
        definition = AdvancedWorkflowDefinitionRequest.model_validate(
            {"nodes": [{"id": "target", "type": "artist_target"}]}
        )
        _, trigger = scheduler.save_with_trigger(
            definition, schedule={"type": "interval", "every": 1, "unit": "minutes"}
        )
        store[6].create_run(
            WorkflowRun(
                id="old-success",
                source="workflow_trigger",
                status="completed",
                total=1,
                completed=1,
                failed=0,
                skipped=0,
                concurrency=1,
                schedule_id=trigger.id,
                created_at="2000-01-01T00:00:00Z",
                finished_at="2000-01-01T00:01:00Z",
            )
        )
        scheduler.repository.update_trigger(replace(trigger, next_run_at="2000-01-01T00:00:00Z"))

        def fail_dispatch(*_args, **_kwargs):
            raise DatabaseError("temporary dispatch failure")

        scheduler.run_definition = fail_dispatch
        result = scheduler.run_due_triggers()[0]
        assert not result.created and result.trigger.last_error_code is not None
        scheduler._reconcile_results()
        current = scheduler.repository.get_trigger(trigger.id)
        assert current.last_error_message == "temporary dispatch failure"
        assert current.last_success_at == "2000-01-01T00:01:00Z"
        assert current.next_run_at > current.last_run_at


def test_legacy_job_retry_also_limits_download_to_failed_files(store, tmp_path):
    from types import SimpleNamespace

    seed(store, ("downloaded", "failed"))
    source = Job(id="legacy-download", type="download_artist", status="failed", input_user_id="1")
    store[7].create(source)
    with closing(JobService(store[0], settings_json_path=store[1])) as jobs:
        retry = jobs.retry_job(source.id)
    client = SimpleNamespace(
        get_artist_by_user_id=lambda _user: Artist(id="1", name="Artist"),
        get_artworks_by_user_id=lambda *_args, **_kwargs: [],
    )
    http = Http([Response()])
    worker = DownloadWorker(
        db_path=store[0],
        settings_json_path=store[1],
        pixiv_client_factory=lambda: client,
        file_downloader_factory=lambda: FileDownloader(tmp_path, http_client=http),
    )
    result = worker.run_job(retry.id)
    assert result.status == "completed" and result.total_files == 1
    assert http.calls == ["https://example.test/101_p0.jpg"]


def test_node_job_idempotency_preserves_distinct_selected_source_jobs(store):
    seed(store)
    node = store[6].create_node_run(
        WorkflowNodeRun(
            id=None,
            workflow_run_id="run",
            node_id="action",
            node_type="job_action",
            title="Retry",
            position=0,
            status="running",
        )
    )
    job = Job(
        id="first",
        type="download_artist",
        status="queued",
        input_user_id="1",
        workflow_node_run_id=node,
        options={"source_job_id": "original-one"},
    )
    first = store[7].create_node_job(job)
    duplicate = store[7].create_node_job(replace(job, id="interrupted-retry"))
    second = store[7].create_node_job(
        replace(job, id="second", options={"source_job_id": "original-two"})
    )
    assert duplicate.id == first.id and second.id != first.id
    assert store[7].count() == 2
