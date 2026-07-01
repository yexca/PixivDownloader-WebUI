import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.api import routes_settings
from backend.app import create_app
from backend.core.errors import PixivApiError
from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Artwork, ArtworkFile, Job, JobEvent
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.tag_repository import LocalTagRepository
from backend.repositories.workflow_run_repository import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunItem,
    WorkflowRunRepository,
)
from backend.services import scheduled_task_service
from backend.services.job_service import JobService
from backend.services.settings_service import AppSettingsService


class NoopQueue:
    def __init__(self):
        self.wake_count = 0
        self.paused = False

    def wake(self):
        self.wake_count += 1

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False
        self.wake()


def test_health_endpoint(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_dashboard_summary_endpoint_returns_runtime_and_library_counts(tmp_path):
    queue = NoopQueue()
    queue.pause()
    client = make_client(tmp_path, queue=queue)
    db_path = tmp_path / "pixiv.sqlite3"
    artist_repository = ArtistRepository(db_path)
    artwork_repository = ArtworkRepository(db_path)
    job_repository = JobRepository(db_path)
    workflow_repository = WorkflowRunRepository(db_path)
    try:
        artist_repository.upsert(
            Artist(
                id="123",
                name="Artist",
                last_download_id="100",
                remote_latest_artwork_id="101",
            )
        )
        artwork_repository.upsert(
            Artwork(
                id="101",
                artist_id="123",
                title="Artwork",
                page_count=3,
            )
        )
        with artwork_repository.conn:
            for file in (
                ArtworkFile(
                    artwork_id="101",
                    page_index=0,
                    original_url="https://example.test/0.jpg",
                    file_name="0.jpg",
                    status="downloaded",
                ),
                ArtworkFile(
                    artwork_id="101",
                    page_index=1,
                    original_url="https://example.test/1.jpg",
                    file_name="1.jpg",
                    status="failed",
                ),
                ArtworkFile(
                    artwork_id="101",
                    page_index=2,
                    original_url="https://example.test/2.jpg",
                    file_name="2.jpg",
                    status="pending",
                ),
            ):
                artwork_repository.conn.execute(
                    """
                    INSERT INTO artwork_files(
                        artwork_id, page_index, original_url, file_name, status,
                        created_at, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, '2026-06-29T00:00:00Z', '2026-06-29T00:00:00Z')
                    """,
                    (
                        file.artwork_id,
                        file.page_index,
                        file.original_url,
                        file.file_name,
                        file.status,
                    ),
                )
        job_repository.create(
            Job(
                id="waiting-job",
                type="download_artist",
                status="inactive",
                options={"activation_scope": "one_time"},
            )
        )
        job_repository.create(Job(id="running-job", type="download_artist", status="running"))
        workflow_repository.create_run(
            WorkflowRun(
                id="run-1",
                status="failed",
                total=1,
                completed=0,
                failed=1,
                skipped=0,
                concurrency=1,
            )
        )
        with job_repository.conn:
            job_repository.conn.execute(
                """
                INSERT INTO scheduled_tasks(
                    name, action, status, target_artist_id, interval_days,
                    run_after_startup, created_at, updated_at
                )
                VALUES('Daily sync', 'sync_artist', 'blocked', '123', 1, 1,
                    '2026-06-29T00:00:00Z', '2026-06-29T00:00:00Z')
                """
            )
    finally:
        artist_repository.close()
        artwork_repository.close()
        job_repository.close()
        workflow_repository.close()

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["queue_paused"] is True
    assert body["library"]["artists"] == 1
    assert body["library"]["artworks"] == 1
    assert body["library"]["downloaded_files"] == 1
    assert body["library"]["pending_files"] == 1
    assert body["library"]["failed_files"] == 1
    assert body["library"]["attention_artists"] == 1
    assert body["library"]["artists_with_updates"] == 1
    assert body["library"]["artists_with_failed_files"] == 1
    assert body["library"]["unavailable_artists"] == 0
    assert body["workflows"]["failed_runs"] == 1
    assert body["workflows"]["blocked_schedules"] == 1
    assert body["workflows"]["waiting_jobs"] == 1
    assert body["jobs"]["inactive"] == 1
    assert body["jobs"]["running"] == 1


def test_settings_get_and_update_masks_refresh_token(tmp_path):
    client = make_client(tmp_path)

    get_response = client.get("/api/settings")
    assert get_response.status_code == 200
    assert get_response.json()["refresh_token_configured"] is True
    assert "secret-token" not in str(get_response.json())

    update_response = client.put(
        "/api/settings",
        json={
            "download_path": str(tmp_path / "new-downloads"),
            "refresh_token": "",
            "request_base_delay_seconds": 0.2,
            "request_random_delay_seconds": 0.3,
            "file_download_base_delay_seconds": 0.4,
            "file_download_random_delay_seconds": 0.5,
            "max_concurrent_downloads": 2,
            "max_active_scheduled_tasks": 3,
            "max_active_run_jobs": 4,
            "min_free_space_gb": 10.0,
            "library_stale_check_days": 14,
            "existing_file_behavior": "save_duplicate",
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["download_path"].endswith("new-downloads")
    assert body["download_path_editable"] is True
    assert body["runtime_mode"] == "local"
    assert body["max_active_scheduled_tasks"] == 3
    assert body["max_active_run_jobs"] == 4
    assert body["file_download_base_delay_seconds"] == 0.4
    assert body["file_download_random_delay_seconds"] == 0.5
    assert body["min_free_space_gb"] == 10.0
    assert body["library_stale_check_days"] == 14
    assert body["existing_file_behavior"] == "save_duplicate"
    assert body["skip_existing_files"] is False
    assert body["overwrite_existing_files"] is False
    assert body["refresh_token_configured"] is True
    assert body["refresh_token_preview"] == "secr...oken"


def test_settings_partial_update_preserves_other_values(tmp_path):
    client = make_client(tmp_path)

    response = client.put("/api/settings", json={"max_concurrent_downloads": 4})

    assert response.status_code == 200
    body = response.json()
    assert body["max_concurrent_downloads"] == 4
    assert body["refresh_token_configured"] is True
    assert body["refresh_token_preview"] == "secr...oken"
    assert body["request_base_delay_seconds"] == 0.1
    assert body["file_download_base_delay_seconds"] == 1.0
    assert body["library_stale_check_days"] == 30
    assert body["existing_file_behavior"] == "skip"


def test_settings_download_path_is_fixed_in_docker_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXIVDOWNLOADER_RUNTIME", "docker")
    client = make_client(tmp_path)

    update_response = client.put(
        "/api/settings",
        json={
            "download_path": str(tmp_path / "ignored-downloads"),
            "refresh_token": "",
            "request_base_delay_seconds": 0.2,
            "request_random_delay_seconds": 0.3,
            "file_download_base_delay_seconds": 0.4,
            "file_download_random_delay_seconds": 0.5,
            "max_concurrent_downloads": 2,
            "min_free_space_gb": 10.0,
            "library_stale_check_days": 30,
            "existing_file_behavior": "overwrite",
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["download_path"].replace("\\", "/").endswith("downloads")
    assert body["existing_file_behavior"] == "overwrite"
    assert body["download_path_editable"] is False
    assert body["runtime_mode"] == "docker"


def test_settings_validate_auth_endpoint(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    called = False

    def fake_validate_auth(_service):
        nonlocal called
        called = True

    monkeypatch.setattr(AppSettingsService, "validate_pixiv_auth", fake_validate_auth)

    response = client.post("/api/settings/validate-auth")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Pixiv authentication succeeded."}
    assert called is True


def test_settings_test_connection_endpoint(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    called = False

    def fake_test_connection(_service):
        nonlocal called
        called = True
        return {"user_id": "123", "user_name": "Artist"}

    monkeypatch.setattr(AppSettingsService, "test_pixiv_connection", fake_test_connection)

    response = client.post("/api/settings/test-connection")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "message": "Pixiv API connection succeeded for Artist (123).",
        "user_id": "123",
        "user_name": "Artist",
    }
    assert called is True


def test_settings_service_test_connection_calls_user_detail(tmp_path):
    service = make_settings_service(tmp_path)
    api = FakeConnectionPixivApi()
    try:
        result = service.test_pixiv_connection(api=api)
    finally:
        service.close()

    assert result == {"user_id": "123", "user_name": "Artist"}
    assert api.calls == [("auth", "secret-token"), ("user_detail", "123")]


def test_settings_service_test_connection_reports_pixiv_error(tmp_path):
    service = make_settings_service(tmp_path)
    api = FakeConnectionPixivApi(error_message="Your access is currently restricted")
    try:
        with pytest.raises(PixivApiError, match="Your access is currently restricted"):
            service.test_pixiv_connection(api=api)
    finally:
        service.close()


def test_pixiv_auth_start_endpoint(tmp_path):
    client = make_client(tmp_path)

    response = client.post("/api/settings/pixiv-auth/start")

    assert response.status_code == 200
    body = response.json()
    assert body["flow_id"]
    assert body["login_url"].startswith("https://app-api.pixiv.net/web/v1/login?")
    assert body["expires_at"]


def test_pixiv_auth_complete_saves_masked_refresh_token(tmp_path, monkeypatch):
    client = make_client(tmp_path)

    def fake_complete(_service, *, flow_id, code_or_callback_url):
        assert flow_id == "flow-1"
        assert code_or_callback_url == "code-1"
        return SimpleNamespace(refresh_token="new-refresh-token")

    monkeypatch.setattr(routes_settings.PixivOAuthService, "complete", fake_complete)

    response = client.post(
        "/api/settings/pixiv-auth/complete",
        json={"flow_id": "flow-1", "code_or_callback_url": "code-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Pixiv refresh token saved."
    assert body["refresh_token_configured"] is True
    assert body["refresh_token_preview"] == "new-...oken"
    assert "new-refresh-token" not in str(body)


def test_pixiv_browser_auth_start_calls_sidecar(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    calls = []

    monkeypatch.setenv("PIXIV_AUTH_BROWSER_INTERNAL_URL", "http://auth-browser.test")
    monkeypatch.setenv("PIXIV_AUTH_BROWSER_PUBLIC_URL", "http://127.0.0.1:6080/vnc.html")

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(routes_settings.requests, "post", fake_post)

    response = client.post("/api/settings/pixiv-auth/browser/start")

    assert response.status_code == 200
    body = response.json()
    assert body["flow_id"]
    assert body["novnc_url"] == "http://127.0.0.1:6080/vnc.html"
    assert calls[0]["url"] == "http://auth-browser.test/api/auth/start"
    assert calls[0]["json"]["flow_id"] == body["flow_id"]
    assert calls[0]["json"]["login_url"].startswith("https://app-api.pixiv.net/web/v1/login?")


def test_pixiv_browser_auth_service_status_reports_running(tmp_path, monkeypatch):
    client = make_client(tmp_path)

    monkeypatch.setenv("PIXIV_AUTH_BROWSER_INTERNAL_URL", "http://auth-browser.test")
    monkeypatch.setenv("PIXIV_AUTH_BROWSER_PUBLIC_URL", "http://127.0.0.1:6080/vnc.html")

    def fake_get(url, *, timeout):
        assert url == "http://auth-browser.test/health"
        assert timeout == 2
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(routes_settings.requests, "get", fake_get)

    response = client.get("/api/settings/pixiv-auth/browser-service")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["running"] is True
    assert body["novnc_url"] == "http://127.0.0.1:6080/vnc.html"
    assert body["start_command"] == "docker compose --profile auth up -d pixiv-auth-browser"
    assert body["stop_command"] == "docker compose stop pixiv-auth-browser"


def test_pixiv_browser_auth_service_status_reports_stopped(tmp_path, monkeypatch):
    client = make_client(tmp_path)

    monkeypatch.setenv("PIXIV_AUTH_BROWSER_INTERNAL_URL", "http://auth-browser.test")

    def fake_get(url, *, timeout):
        _ = (url, timeout)
        raise routes_settings.requests.ConnectionError("not running")

    monkeypatch.setattr(routes_settings.requests, "get", fake_get)

    response = client.get("/api/settings/pixiv-auth/browser-service")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["running"] is False


def test_pixiv_browser_auth_callback_saves_token(tmp_path, monkeypatch):
    client = make_client(tmp_path)

    monkeypatch.setenv("PIXIV_AUTH_BROWSER_INTERNAL_URL", "http://auth-browser.test")
    monkeypatch.setenv("PIXIV_AUTH_BROWSER_TOKEN", "shared-secret")

    def fake_sidecar_post(_url, *, json: object, headers: object, timeout: object):
        _ = (json, headers, timeout)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(routes_settings.requests, "post", fake_sidecar_post)

    start_response = client.post("/api/settings/pixiv-auth/browser/start")
    flow_id = start_response.json()["flow_id"]

    def fake_complete(_service, *, flow_id, code_or_callback_url):
        assert flow_id == start_response.json()["flow_id"]
        assert code_or_callback_url.endswith("code=browser-code")
        return SimpleNamespace(refresh_token="browser-refresh-token")

    monkeypatch.setattr(routes_settings.PixivOAuthService, "complete", fake_complete)

    response = client.post(
        "/api/settings/pixiv-auth/browser/callback",
        headers={"X-Pixiv-Auth-Browser-Token": "shared-secret"},
        json={
            "flow_id": flow_id,
            "callback_url": (
                "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback?code=browser-code"
            ),
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "completed"
    settings_response = client.get("/api/settings")
    assert settings_response.json()["refresh_token_preview"] == "brow...oken"


def test_pixiv_browser_auth_callback_rejects_bad_token(tmp_path, monkeypatch):
    client = make_client(tmp_path)

    monkeypatch.setenv("PIXIV_AUTH_BROWSER_TOKEN", "shared-secret")

    response = client.post(
        "/api/settings/pixiv-auth/browser/callback",
        headers={"X-Pixiv-Auth-Browser-Token": "wrong"},
        json={"flow_id": "flow-1", "error": "failed"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "config_error"


def test_import_legacy_database_endpoint(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)
    legacy_db_path = tmp_path / "legacy-pixiv.db"
    create_legacy_database(legacy_db_path)

    with legacy_db_path.open("rb") as file:
        response = client.post(
            "/api/imports/legacy-database",
            files={"file": ("pixiv.db", file, "application/octet-stream")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_artists"] == 2
    assert body["skipped_rows"] == 0
    assert body["total_rows"] == 2
    assert body["hydration_job_id"]
    assert queue.wake_count == 1

    artist_response = client.get("/api/artists/100058387")
    assert artist_response.status_code == 200
    assert artist_response.json()["latest_downloaded_artwork_id"] == "113381074"
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["hydration_job_id"])
    finally:
        repository.close()
    assert job is not None
    assert job.type == "hydrate_legacy_import"
    assert job.total_files == 2
    assert job.workflow_run_id is not None
    assert job.workflow_item_id is not None
    assert job.workflow_source == "legacy_import"
    assert "workflow_source" not in job.options
    assert job.options["source"] == "legacy_database"
    assert job.options["artist_ids"] == ["100058387", "101013492"]
    assert job.options["legacy_latest_download_id_by_artist"]["100058387"] == "113381074"
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(str(job.workflow_run_id))
    finally:
        workflow_repository.close()
    assert run is not None
    assert run.source == "legacy_import"
    assert run.items[0].job_ids == [job.id]


def test_create_download_job(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)

    response = client.post(
        "/api/downloads",
        json={
            "user_id": "123",
            "artwork_id": None,
            "mode": "artist",
            "force_rescan": False,
            "retry_failed": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert queue.wake_count == 1
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_id"])
        assert job is not None
        assert job.type == "resolve_workflow_targets"
        assert job.options["artist_ids"] == ["123"]
        assert job.workflow_source == "advanced_workflow"
        assert "workflow_source" not in job.options
        run_id = job.workflow_run_id
    finally:
        repository.close()
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(str(run_id))
    finally:
        workflow_repository.close()
    assert run is not None
    assert run.source == "download_api"
    assert run.status == "running"
    assert [node.node_id for node in run.node_runs] == [
        "target",
        "sync",
        "collect",
        "filters",
        "actions",
    ]
    assert run.node_runs[0].job_ids == [body["job_id"]]


def test_create_download_job_persists_workflow_options(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/downloads",
        json={
            "user_id": "123",
            "artwork_id": None,
            "mode": "artist",
            "force_rescan": False,
            "retry_failed": False,
            "full_download": True,
            "max_artworks": 12,
            "min_artwork_id": "100",
            "max_artwork_id": "200",
        },
    )

    assert response.status_code == 200
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(response.json()["job_id"])
        assert job is not None
        assert job.type == "resolve_workflow_targets"
        assert job.options["activation_scope"] == "one_time"
        assert job.options["artist_ids"] == ["123"]
        assert "workflow_run_id" not in job.options
        assert "workflow_item_id" not in job.options
        assert "workflow_source" not in job.options
    finally:
        repository.close()
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(str(job.workflow_run_id))
    finally:
        workflow_repository.close()
    assert run is not None
    collect_node = next(node for node in run.node_runs if node.node_id == "collect")
    assert collect_node.input["config"] == {
        "mode": "all_synced",
        "max_artworks": 12,
        "min_artwork_id": "100",
        "max_artwork_id": "200",
    }


def test_create_download_job_rejects_low_disk_space(tmp_path, monkeypatch):
    client = make_client(tmp_path)

    monkeypatch.setattr(
        "backend.services.storage_service.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=1024, total=2048, used=1024),
    )

    response = client.post(
        "/api/downloads",
        json={
            "user_id": "123",
            "artwork_id": None,
            "mode": "artist",
            "force_rescan": False,
            "retry_failed": False,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_disk_space"


def test_one_time_download_jobs_respect_active_limit(tmp_path):
    client = make_client(tmp_path)

    first_response = client.post(
        "/api/downloads",
        json={
            "user_id": "123",
            "artwork_id": None,
            "mode": "artist",
            "force_rescan": False,
            "retry_failed": False,
        },
    )
    second_response = client.post(
        "/api/downloads",
        json={
            "user_id": "456",
            "artwork_id": None,
            "mode": "artist",
            "force_rescan": False,
            "retry_failed": False,
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["status"] == "queued"
    assert second_response.json()["status"] == "inactive"


def test_inactive_one_time_job_activates_when_capacity_opens(tmp_path):
    client = make_client(tmp_path)

    first_response = client.post(
        "/api/downloads",
        json={
            "user_id": "123",
            "artwork_id": None,
            "mode": "artist",
            "force_rescan": False,
            "retry_failed": False,
        },
    )
    second_response = client.post(
        "/api/downloads",
        json={
            "user_id": "456",
            "artwork_id": None,
            "mode": "artist",
            "force_rescan": False,
            "retry_failed": False,
        },
    )
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    service = None
    try:
        first = repository.get_by_id(first_response.json()["job_id"])
        assert first is not None
        repository.update(replace(first, status="completed"))
    finally:
        repository.close()

    service = JobService(
        tmp_path / "pixiv.sqlite3",
        settings_json_path=tmp_path / "config" / "settings.json",
    )
    try:
        activated = service.activate_inactive_one_time_jobs()
        assert [job.id for job in activated] == [second_response.json()["job_id"]]
        assert service.get_job(second_response.json()["job_id"]).status == "queued"
    finally:
        service.close()


def test_scheduled_task_create_and_run_queues_job(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Artist updates",
            "action": "download_artist",
            "target_artist_id": "123",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
        },
    )

    assert create_response.status_code == 200
    task = create_response.json()
    assert task["status"] == "active"
    assert queue.wake_count == 1

    run_response = client.post(f"/api/scheduled-tasks/{task['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    assert body["created"] is True
    assert body["job_id"]
    assert body["workflow_run_id"]
    assert body["task"]["last_job_id"] == body["job_id"]
    assert body["task"]["last_run_summary"]["workflow_run_id"] == body["workflow_run_id"]
    assert body["task"]["last_run_summary"]["workflow_run_source"] == "manual_schedule"
    assert queue.wake_count == 2
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_id"])
    finally:
        repository.close()
    assert job is not None
    assert job.type == "resolve_workflow_targets"
    assert job.workflow_run_id == body["workflow_run_id"]
    assert job.workflow_source == "advanced_workflow"
    assert "workflow_source" not in job.options
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(body["workflow_run_id"])
    finally:
        workflow_repository.close()
    assert run is not None
    assert run.source == "manual_schedule"
    assert [node.node_id for node in run.node_runs] == [
        "target",
        "sync",
        "collect",
        "filters",
        "actions",
    ]


def test_scheduled_task_creation_keeps_enabled_schedules_active(tmp_path):
    client = make_client(tmp_path)

    first_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "First",
            "action": "download_artist",
            "target_artist_id": "123",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
        },
    )
    second_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Second",
            "action": "download_artist",
            "target_artist_id": "456",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["status"] == "active"
    assert second_response.json()["status"] == "active"


def test_inactive_scheduled_task_activation_is_legacy_noop(tmp_path):
    client = make_client(tmp_path)

    first_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "First",
            "action": "download_artist",
            "target_artist_id": "123",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
        },
    )
    second_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Second",
            "action": "download_artist",
            "target_artist_id": "456",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
        },
    )
    service = scheduled_task_service.ScheduledTaskService(
        tmp_path / "pixiv.sqlite3",
        settings_json_path=tmp_path / "config" / "settings.json",
    )
    try:
        assert second_response.json()["status"] == "active"
        paused_response = client.put(
            f"/api/scheduled-tasks/{first_response.json()['id']}",
            json={"status": "paused"},
        )
        assert paused_response.status_code == 200

        activated = service.activate_inactive_tasks()

        assert activated == []
        assert service.get_task(second_response.json()["id"]).status == "active"
    finally:
        service.close()


def test_scheduled_task_can_be_archived(tmp_path):
    client = make_client(tmp_path)

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Archive me",
            "action": "download_artist",
            "target_artist_id": "123",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
        },
    )
    task_id = create_response.json()["id"]

    archive_response = client.put(f"/api/scheduled-tasks/{task_id}", json={"status": "archived"})

    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"


def test_scheduled_task_builder_runs_all_artists_with_filter(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(
            Artist(
                id="123",
                name="Stale",
                last_checked_at="2023-01-01T00:00:00Z",
            )
        )
        artist_repository.upsert(
            Artist(
                id="456",
                name="Fresh",
                last_checked_at="2999-01-01T00:00:00Z",
            )
        )
    finally:
        artist_repository.close()

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Stale sync",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "all_artists"},
                "filters": [{"type": "last_checked_before_days", "days": 30}],
                "actions": ["sync_artist"],
                "max_artists_per_run": 25,
            },
        },
    )

    assert create_response.status_code == 200
    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    assert body["created"] is True
    assert len(body["job_ids"]) == 1
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.type == "resolve_workflow_targets"
        assert job.options["artist_ids"] == ["123"]
    finally:
        repository.close()
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(body["workflow_run_id"])
    finally:
        workflow_repository.close()
    assert run is not None
    assert [node.node_id for node in run.node_runs] == ["target", "sync"]


def test_scheduled_task_builder_targets_single_artwork(tmp_path):
    client = make_client(tmp_path)

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Artwork workflow",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "single_artwork", "artwork_id": "999"},
                "filters": [],
                "actions": ["download_artist"],
                "download_options": {"full_download": True},
                "max_artists_per_run": 25,
            },
        },
    )

    assert create_response.status_code == 200
    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    assert body["created"] is True
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.type == "resolve_workflow_targets"
        assert job.options["artwork_ids"] == ["999"]
        assert job.workflow_run_id == body["workflow_run_id"]
        assert job.workflow_source == "advanced_workflow"
    finally:
        repository.close()
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(body["workflow_run_id"])
    finally:
        workflow_repository.close()
    assert run is not None
    assert run.node_runs[2].input["config"]["mode"] == "all_synced"


def test_scheduled_task_builder_accepts_empty_legacy_target_artist_id(tmp_path):
    client = make_client(tmp_path)

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "All artists",
            "action": "sync_artist",
            "target_artist_id": "",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "all_artists"},
                "filters": [],
                "actions": ["sync_artist"],
                "max_artists_per_run": 25,
                "artist_selection": "oldest_checked_first",
            },
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["target_artist_id"] == ""
    assert create_response.json()["config"]["target"]["type"] == "all_artists"


def test_scheduled_task_builder_uses_oldest_checked_artists_first(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(
            Artist(
                id="old",
                name="Old",
                last_checked_at="2023-01-01T00:00:00Z",
            )
        )
        artist_repository.upsert(
            Artist(
                id="new",
                name="New",
                last_checked_at="2024-01-01T00:00:00Z",
            )
        )
    finally:
        artist_repository.close()

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Oldest first",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "all_artists"},
                "filters": [],
                "actions": ["sync_artist"],
                "max_artists_per_run": 1,
                "artist_selection": "oldest_checked_first",
            },
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["config"]["artist_selection"] == "oldest_checked_first"
    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.options["artist_ids"] == ["old"]
    finally:
        repository.close()


def test_scheduled_task_builder_uses_newest_checked_artists_first(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(
            Artist(
                id="old",
                name="Old",
                last_checked_at="2023-01-01T00:00:00Z",
            )
        )
        artist_repository.upsert(
            Artist(
                id="new",
                name="New",
                last_checked_at="2024-01-01T00:00:00Z",
            )
        )
    finally:
        artist_repository.close()

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Newest first",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "all_artists"},
                "filters": [],
                "actions": ["sync_artist"],
                "max_artists_per_run": 1,
                "artist_selection": "newest_checked_first",
            },
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["config"]["artist_selection"] == "newest_checked_first"
    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.options["artist_ids"] == ["new"]
    finally:
        repository.close()


def test_scheduled_task_builder_can_randomly_select_artists(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="first", name="First"))
        artist_repository.upsert(Artist(id="second", name="Second"))
    finally:
        artist_repository.close()

    def reverse_id_sample(artists, *, k):
        assert k == len(artists)
        return sorted(artists, key=lambda artist: artist.id, reverse=True)

    monkeypatch.setattr(scheduled_task_service.random, "sample", reverse_id_sample)
    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Random",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "all_artists"},
                "filters": [],
                "actions": ["sync_artist"],
                "max_artists_per_run": 1,
                "artist_selection": "random",
            },
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["config"]["artist_selection"] == "random"
    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.options["artist_ids"] == ["second"]
    finally:
        repository.close()


def test_scheduled_task_builder_targets_local_tag(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    tag_repository = LocalTagRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="123", name="Tagged"))
        artist_repository.upsert(Artist(id="456", name="Other"))
        tag_repository.set_artist_tags("123", ["favorite"])
    finally:
        artist_repository.close()
        tag_repository.close()

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Tagged download",
            "interval_days": 7,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "artists_with_tag", "tag": "favorite"},
                "filters": [],
                "actions": ["download_artist", "retry_failed_artist"],
                "max_artists_per_run": 25,
            },
        },
    )
    assert create_response.status_code == 200

    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.options["artist_ids"] == ["123"]
    finally:
        repository.close()
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(body["workflow_run_id"])
    finally:
        workflow_repository.close()
    assert run is not None
    assert [node.node_id for node in run.node_runs] == [
        "target",
        "sync",
        "collect",
        "filters",
        "actions",
        "collect_retry",
        "filters_retry",
        "actions_retry",
    ]


def test_scheduled_task_builder_targets_multiple_local_tags(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    tag_repository = LocalTagRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="123", name="Tagged"))
        artist_repository.upsert(Artist(id="456", name="Other Tagged"))
        artist_repository.upsert(Artist(id="789", name="Untagged"))
        tag_repository.set_artist_tags("123", ["favorite"])
        tag_repository.set_artist_tags("456", ["reference"])
    finally:
        artist_repository.close()
        tag_repository.close()

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Multi-tag sync",
            "interval_days": 7,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {
                    "type": "artists_with_tag",
                    "tags": ["favorite", "reference"],
                },
                "filters": [],
                "actions": ["sync_artist"],
                "max_artists_per_run": 25,
            },
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["config"]["target"]["tags"] == [
        "favorite",
        "reference",
    ]

    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.options["artist_ids"] == ["123", "456"]
    finally:
        repository.close()


def test_scheduled_task_builder_skips_unavailable_artists_by_default(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="123", name="Open"))
        artist_repository.upsert(Artist(id="456", name="Closed", account_status="unavailable"))
    finally:
        artist_repository.close()

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Skip unavailable",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "all_artists"},
                "filters": [],
                "actions": ["sync_artist"],
                "max_artists_per_run": 25,
            },
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["config"]["skip_unavailable_artists"] is True

    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.options["artist_ids"] == ["123"]
    finally:
        repository.close()


def test_scheduled_task_builder_can_include_unavailable_artists(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="123", name="Open"))
        artist_repository.upsert(Artist(id="456", name="Closed", account_status="unavailable"))
    finally:
        artist_repository.close()

    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Include unavailable",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
            "config": {
                "target": {"type": "all_artists"},
                "filters": [],
                "actions": ["sync_artist"],
                "max_artists_per_run": 25,
                "skip_unavailable_artists": False,
            },
        },
    )
    assert create_response.status_code == 200

    run_response = client.post(f"/api/scheduled-tasks/{create_response.json()['id']}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_ids"][0])
        assert job is not None
        assert job.options["artist_ids"] == ["123", "456"]
    finally:
        repository.close()


def test_scheduled_download_blocks_on_low_disk_space(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    create_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Artist updates",
            "action": "download_artist",
            "target_artist_id": "123",
            "interval_days": 30,
            "enabled": True,
            "run_after_startup": True,
        },
    )
    task_id = create_response.json()["id"]

    monkeypatch.setattr(
        "backend.services.storage_service.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=1024, total=2048, used=1024),
    )

    run_response = client.post(f"/api/scheduled-tasks/{task_id}/run")

    assert run_response.status_code == 200
    body = run_response.json()
    assert body["created"] is False
    assert body["task"]["status"] == "blocked"
    assert body["task"]["last_error_code"] == "insufficient_disk_space"
    assert body["task"]["failure_reason"] == "disk"


def test_create_artist_queues_sync_job(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)

    response = client.post("/api/artists", json={"user_id": "123"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert queue.wake_count == 1
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        job = repository.get_by_id(body["job_id"])
        assert job is not None
        assert job.type == "resolve_workflow_targets"
        assert job.options["artist_ids"] == ["123"]
        assert job.workflow_source == "advanced_workflow"
        assert "workflow_source" not in job.options
        run_id = job.workflow_run_id
    finally:
        repository.close()
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(str(run_id))
    finally:
        workflow_repository.close()
    assert run is not None
    assert run.source == "library_shortcut"
    assert [node.node_id for node in run.node_runs] == ["target", "sync"]
    assert run.node_runs[0].job_ids == [body["job_id"]]


def test_workflow_run_reads_advanced_shortcut_node_totals(tmp_path):
    client = make_client(tmp_path)
    repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = WorkflowRun(
            id="advanced-shortcut-run",
            status="completed",
            total=2,
            completed=1,
            failed=0,
            skipped=0,
            concurrency=1,
            source="library_shortcut",
            created_at="2026-07-01T00:00:00Z",
        )
        repository.create_run(run)
        repository.create_item(
            WorkflowRunItem(
                id=None,
                run_id=run.id,
                draft_id="advanced:advanced-shortcut-run",
                title="Sync artist",
                status="completed",
                config={"nodes": []},
                request={"source": "library_shortcut"},
                created_at=run.created_at,
                finished_at="2026-07-01T00:00:01Z",
            )
        )
        for position, node_id in enumerate(("target", "sync")):
            repository.create_node_run(
                WorkflowNodeRun(
                    id=None,
                    workflow_run_id=run.id,
                    node_id=node_id,
                    node_type="sync_metadata" if node_id == "sync" else "artist_target",
                    title=node_id.title(),
                    position=position,
                    status="completed",
                    output={"completed_jobs": []},
                    created_at=run.created_at,
                    started_at=run.created_at,
                    finished_at="2026-07-01T00:00:01Z",
                )
            )
    finally:
        repository.close()

    list_response = client.get("/api/workflows/runs")
    detail_response = client.get(f"/api/workflows/runs/{run.id}")

    assert list_response.status_code == 200
    list_item = next(item for item in list_response.json()["items"] if item["id"] == run.id)
    assert list_item["status"] == "completed"
    assert list_item["completed"] == 2
    assert list_item["total"] == 2
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "completed"
    assert detail["completed"] == 2
    assert detail["total"] == 2


def test_artist_tags_and_filter_endpoint(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="123", name="Tagged Artist"))
        artist_repository.upsert(Artist(id="456", name="Other Artist"))
    finally:
        artist_repository.close()

    update_response = client.put("/api/artists/123/local-tags", json={"tags": ["favorite"]})
    list_response = client.get("/api/artists?local_tag=favorite")
    tags_response = client.get("/api/artists/-/local-tags")

    assert update_response.status_code == 200
    assert update_response.json()["items"][0]["name"] == "favorite"
    assert list_response.status_code == 200
    assert [artist["id"] for artist in list_response.json()["items"]] == ["123"]
    assert tags_response.json()["items"][0]["name"] == "favorite"


def test_artist_list_reports_status_flags_and_filters(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(
            Artist(
                id="123",
                name="Needs Update",
                last_download_id="100",
                account_status="available",
                remote_latest_artwork_id="200",
                remote_latest_checked_at="2023-01-01T00:00:00Z",
            )
        )
        artist_repository.upsert(
            Artist(
                id="456",
                name="Unavailable",
                account_status="unavailable",
                account_status_reason="Page not found",
                remote_latest_checked_at="2999-01-01T00:00:00Z",
            )
        )
    finally:
        artist_repository.close()

    update_response = client.get("/api/artists?update_state=available")
    unavailable_response = client.get("/api/artists?account_status=unavailable")

    assert update_response.status_code == 200
    update_artist = update_response.json()["items"][0]
    assert update_artist["id"] == "123"
    assert update_artist["has_remote_update"] is True
    assert update_artist["is_check_stale"] is True
    assert update_artist["check_stale_days"] == 30
    assert unavailable_response.status_code == 200
    unavailable_artist = unavailable_response.json()["items"][0]
    assert unavailable_artist["id"] == "456"
    assert unavailable_artist["account_status"] == "unavailable"


def test_artist_detail_includes_name_history(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    name_history_repository = ArtistNameHistoryRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="123", name="Current Name"))
        name_history_repository.record_name("123", "Old Name")
        name_history_repository.record_name("123", "Current Name")
    finally:
        artist_repository.close()
        name_history_repository.close()

    response = client.get("/api/artists/123")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["name_history"]}
    assert names == {"Old Name", "Current Name"}


def test_delete_artist_removes_database_records(tmp_path):
    client = make_client(tmp_path)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="123", name="Delete Me"))
    finally:
        artist_repository.close()
    tag_repository = LocalTagRepository(tmp_path / "pixiv.sqlite3")
    try:
        tag_repository.set_artist_tags("123", ["old"])
    finally:
        tag_repository.close()

    response = client.delete("/api/artists/123")

    assert response.status_code == 204
    assert client.get("/api/artists/123").status_code == 404


def test_cancel_queued_job_marks_terminal(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        repository.create(Job(id="job-1", type="download_artist", status="queued"))
    finally:
        repository.close()

    response = client.post("/api/jobs/job-1/cancel")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "job-1",
        "status": "cancelled",
        "cancel_requested": True,
    }
    assert queue.wake_count == 1


def test_cancel_completed_job_returns_consistent_error(tmp_path):
    client = make_client(tmp_path)
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        repository.create(Job(id="job-1", type="download_artist", status="completed"))
    finally:
        repository.close()

    response = client.post("/api/jobs/job-1/cancel")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "job_not_cancellable"


def test_job_queue_pause_and_resume_endpoints(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)

    pause_response = client.post("/api/jobs/queue/pause")
    state_response = client.get("/api/jobs/queue")
    resume_response = client.post("/api/jobs/queue/resume")

    assert pause_response.status_code == 200
    assert pause_response.json() == {"paused": True}
    assert state_response.json() == {"paused": True}
    assert resume_response.json() == {"paused": False}
    assert queue.wake_count == 1


def test_bulk_cancel_jobs_cancels_active_and_reports_terminal_errors(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        repository.create(Job(id="queued-job", type="download_artist", status="queued"))
        repository.create(Job(id="done-job", type="download_artist", status="completed"))
    finally:
        repository.close()

    response = client.post(
        "/api/jobs/bulk-cancel",
        json={"job_ids": ["queued-job", "done-job", "missing-job"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cancelled"][0]["job_id"] == "queued-job"
    assert body["cancelled"][0]["status"] == "cancelled"
    assert [error["job_id"] for error in body["errors"]] == ["done-job", "missing-job"]
    assert queue.wake_count == 1


def test_retry_legacy_hydration_job_queues_failed_artists_only(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        repository.create(
            Job(
                id="job-1",
                type="hydrate_legacy_import",
                status="failed",
                workflow_run_id="run-1",
                workflow_item_id=1,
                workflow_source="legacy_import",
                options={
                    "source": "legacy_database",
                    "artist_ids": ["111", "222"],
                    "legacy_latest_download_id_by_artist": {"111": "1000", "222": "2000"},
                    "activation_scope": "one_time",
                    "workflow_run_id": "run-1",
                    "workflow_item_id": 1,
                    "workflow_source": "legacy_import",
                },
            )
        )
        repository.add_event(
            JobEvent(
                job_id="job-1",
                level="error",
                message="Legacy import hydration artist 222: failed_retryable",
                payload={"artist_id": "222", "status": "failed_retryable", "reason": "Rate Limit"},
            )
        )
    finally:
        repository.close()

    response = client.post("/api/jobs/job-1/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["source_job_id"] == "job-1"
    assert body["action"] == "retry_failed_artists"
    assert queue.wake_count == 1
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        retry = repository.get_by_id(body["job_id"])
    finally:
        repository.close()
    assert retry is not None
    assert retry.type == "hydrate_legacy_import"
    assert retry.workflow_run_id is not None
    assert retry.workflow_run_id != "run-1"
    assert retry.workflow_item_id is not None
    assert retry.workflow_source == "job_retry"
    assert retry.options["artist_ids"] == ["222"]
    assert retry.options["legacy_latest_download_id_by_artist"] == {"222": "2000"}
    assert "workflow_source" not in retry.options
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(str(retry.workflow_run_id))
    finally:
        workflow_repository.close()
    assert run is not None
    assert run.source == "job_retry"
    assert run.items[0].job_ids == [retry.id]


def test_rerun_job_queues_copy_with_original_options(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        repository.create(
            Job(
                id="job-1",
                type="download_artist",
                status="failed",
                input_user_id="123",
                options={"activation_scope": "one_time", "max_artworks": 5},
            )
        )
    finally:
        repository.close()

    response = client.post("/api/jobs/job-1/rerun")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "rerun"
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        rerun = repository.get_by_id(body["job_id"])
    finally:
        repository.close()
    assert rerun is not None
    assert rerun.type == "download_artist"
    assert rerun.input_user_id == "123"
    assert rerun.options["max_artworks"] == 5
    assert rerun.options["source_job_id"] == "job-1"
    assert rerun.workflow_run_id is not None
    assert rerun.workflow_source == "job_rerun"
    assert "workflow_source" not in rerun.options
    workflow_repository = WorkflowRunRepository(tmp_path / "pixiv.sqlite3")
    try:
        run = workflow_repository.get_run(str(rerun.workflow_run_id))
    finally:
        workflow_repository.close()
    assert run is not None
    assert run.source == "job_rerun"
    assert run.items[0].job_ids == [rerun.id]


def test_job_detail_reports_related_retry_and_rerun_jobs(tmp_path):
    client = make_client(tmp_path)
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        repository.create(Job(id="job-1", type="download_artist", status="failed"))
        repository.create(
            Job(
                id="retry-job",
                type="download_artist",
                status="queued",
                options={"source_job_id": "job-1", "job_action": "retry"},
            )
        )
        repository.create(
            Job(
                id="rerun-job",
                type="download_artist",
                status="running",
                options={"source_job_id": "job-1", "job_action": "rerun"},
            )
        )
    finally:
        repository.close()

    response = client.get("/api/jobs/job-1")

    assert response.status_code == 200
    related = response.json()["related_jobs"]
    assert {job["id"]: job["action"] for job in related} == {
        "retry-job": "retry",
        "rerun-job": "rerun",
    }


def test_recent_logs_endpoint_returns_paginated_items(tmp_path):
    client = make_client(tmp_path)
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        repository.create(Job(id="job-1", type="download_artist", status="queued"))
        repository.add_event(JobEvent(job_id="job-1", level="info", message="First"))
        repository.add_event(JobEvent(job_id="job-1", level="error", message="Second"))
    finally:
        repository.close()

    response = client.get("/api/logs/recent?level=error&limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["level"] == "error"
    assert body["items"][0]["message"] == "Second"


def make_client(tmp_path, queue=None):
    db_path, settings_path = make_config(tmp_path)
    app = create_app(
        db_path=db_path,
        settings_json_path=settings_path,
        start_queue=False,
        job_queue=queue or NoopQueue(),
    )
    return TestClient(app)


def make_settings_service(tmp_path):
    db_path, settings_path = make_config(tmp_path)
    return AppSettingsService(db_path=db_path, settings_json_path=settings_path)


def make_config(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    settings_example_path = config_dir / "settings.example.json"
    settings_example_path.write_text(
        f"""
        {{
            "download_path": "{str(tmp_path / "default-downloads").replace("\\", "\\\\")}",
            "refresh_token": "",
            "request_base_delay_seconds": 0.1,
            "request_random_delay_seconds": 0.2,
            "file_download_base_delay_seconds": 1.0,
            "file_download_random_delay_seconds": 0.5,
            "max_concurrent_downloads": 1,
            "max_active_scheduled_tasks": 1,
            "max_active_run_jobs": 1,
            "min_free_space_gb": 10.0,
            "existing_file_behavior": "skip",
            "library_stale_check_days": 30
        }}
        """,
        encoding="utf-8",
    )
    settings_path = config_dir / "settings.json"
    settings_path.write_text(
        f"""
        {{
            "download_path": "{str(tmp_path / "downloads").replace("\\", "\\\\")}",
            "refresh_token": "secret-token"
        }}
        """,
        encoding="utf-8",
    )
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path, settings_json_path=settings_path)
    return db_path, settings_path


class FakeConnectionPixivApi:
    user_id = "123"

    def __init__(self, error_message=None):
        self.error_message = error_message
        self.calls = []

    def auth(self, *, refresh_token):
        self.calls.append(("auth", refresh_token))

    def user_detail(self, user_id):
        self.calls.append(("user_detail", user_id))
        if self.error_message:
            return SimpleNamespace(
                error=SimpleNamespace(
                    message=self.error_message,
                    user_message="",
                    reason="",
                )
            )
        return SimpleNamespace(user=SimpleNamespace(id=user_id, name="Artist"))


def create_legacy_database(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE pic (
                ID TEXT PRIMARY KEY,
                name TEXT,
                downloadedDate TEXT,
                lastDownloadID TEXT,
                url TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO pic(ID, name, downloadedDate, lastDownloadID, url)
            VALUES(?, ?, ?, ?, ?)
            """,
            [
                (
                    "100058387",
                    "Legacy Artist",
                    "2023-11-13 00:00:00",
                    "113381074",
                    "https://www.pixiv.net/users/100058387",
                ),
                (
                    "101013492",
                    "Second Artist",
                    "2025-01-05 23:52:11",
                    "125619677",
                    "https://www.pixiv.net/users/101013492",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()
