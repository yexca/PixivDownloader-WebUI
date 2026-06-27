import sqlite3
from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api import routes_settings
from backend.app import create_app
from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Job, JobEvent
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.tag_repository import LocalTagRepository
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
            "max_concurrent_downloads": 2,
            "max_active_scheduled_tasks": 3,
            "max_active_one_time_tasks": 4,
            "min_free_space_gb": 10.0,
            "library_stale_check_days": 14,
            "overwrite_existing_files": False,
            "skip_existing_files": True,
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["download_path"].endswith("new-downloads")
    assert body["download_path_editable"] is True
    assert body["runtime_mode"] == "local"
    assert body["max_active_scheduled_tasks"] == 3
    assert body["max_active_one_time_tasks"] == 4
    assert body["min_free_space_gb"] == 10.0
    assert body["library_stale_check_days"] == 14
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
    assert body["library_stale_check_days"] == 30
    assert body["skip_existing_files"] is True


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
            "max_concurrent_downloads": 2,
            "min_free_space_gb": 10.0,
            "library_stale_check_days": 30,
            "overwrite_existing_files": False,
            "skip_existing_files": True,
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["download_path"].replace("\\", "/").endswith("downloads")
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
    client = make_client(tmp_path)
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

    artist_response = client.get("/api/artists/100058387")
    assert artist_response.status_code == 200
    assert artist_response.json()["latest_downloaded_artwork_id"] == "113381074"


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
        assert job.input_user_id == "123"
    finally:
        repository.close()


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
        assert job.options == {
            "activation_scope": "one_time",
            "full_download": True,
            "max_artworks": 12,
            "min_artwork_id": "100",
            "max_artwork_id": "200",
        }
    finally:
        repository.close()


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
    assert body["task"]["last_job_id"] == body["job_id"]
    assert queue.wake_count == 2


def test_scheduled_task_creation_limits_active_schedules(tmp_path):
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
    assert second_response.json()["status"] == "inactive"


def test_inactive_scheduled_task_activates_when_capacity_opens(tmp_path):
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
        assert second_response.json()["status"] == "inactive"
        paused_response = client.put(
            f"/api/scheduled-tasks/{first_response.json()['id']}",
            json={"status": "paused"},
        )
        assert paused_response.status_code == 200

        activated = service.activate_inactive_tasks()

        assert [task.id for task in activated] == [second_response.json()["id"]]
        assert service.get_task(second_response.json()["id"]).status == "active"
    finally:
        service.close()


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
        assert job.type == "sync_artist"
        assert job.input_user_id == "123"
    finally:
        repository.close()


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
        assert job.type == "download_from_artwork"
        assert job.input_artwork_id == "999"
        assert job.options == {"full_download": True}
    finally:
        repository.close()


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
        assert job.input_user_id == "old"
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
        assert job.input_user_id == "new"
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
        assert job.input_user_id == "second"
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
    assert len(body["job_ids"]) == 2
    repository = JobRepository(tmp_path / "pixiv.sqlite3")
    try:
        jobs = [repository.get_by_id(job_id) for job_id in body["job_ids"]]
        assert [job.type for job in jobs if job is not None] == [
            "download_artist",
            "retry_failed_artist",
        ]
        assert {job.input_user_id for job in jobs if job is not None} == {"123"}
    finally:
        repository.close()


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
        jobs = [repository.get_by_id(job_id) for job_id in body["job_ids"]]
        assert {job.input_user_id for job in jobs if job is not None} == {"123", "456"}
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
        jobs = [repository.get_by_id(job_id) for job_id in body["job_ids"]]
        assert {job.input_user_id for job in jobs if job is not None} == {"123"}
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
        jobs = [repository.get_by_id(job_id) for job_id in body["job_ids"]]
        assert {job.input_user_id for job in jobs if job is not None} == {"123", "456"}
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


def test_workflow_batch_run_persists_items_and_jobs(tmp_path):
    queue = NoopQueue()
    client = make_client(tmp_path, queue=queue)
    artist_repository = ArtistRepository(tmp_path / "pixiv.sqlite3")
    try:
        artist_repository.upsert(Artist(id="123", name="Artist"))
    finally:
        artist_repository.close()

    response = client.post(
        "/api/workflows/runs",
        json={
            "concurrency": 2,
            "items": [
                {
                    "draft_id": "draft-1",
                    "title": "Sync artist",
                    "config": {
                        "target": {"type": "single_artist", "artist_id": "123"},
                        "filters": [],
                        "actions": ["sync_artist"],
                        "max_artists_per_run": 25,
                    },
                },
                {
                    "draft_id": "draft-2",
                    "title": "Download missing artist",
                    "config": {
                        "target": {"type": "single_artist", "artist_id": "404"},
                        "filters": [],
                        "actions": ["download_artist"],
                        "max_artists_per_run": 25,
                    },
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["total"] == 2
    assert body["completed"] == 2
    assert body["concurrency"] == 2
    assert [item["draft_id"] for item in body["items"]] == ["draft-1", "draft-2"]
    assert all(item["status"] == "completed" for item in body["items"])
    assert len(body["items"][0]["job_ids"]) == 1
    assert queue.wake_count == 1

    list_response = client.get("/api/workflows/runs")

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["total"] == 1
    assert list_body["items"][0]["id"] == body["id"]
    assert list_body["items"][0]["items"][0]["title"] == "Sync artist"


def test_workflow_batch_schedules_respect_active_limit(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/workflows/runs",
        json={
            "concurrency": 2,
            "items": [
                {
                    "draft_id": "draft-1",
                    "title": "First schedule",
                    "schedule": True,
                    "name": "First schedule",
                    "interval_days": 30,
                    "enabled": True,
                    "run_after_startup": True,
                    "config": {
                        "target": {"type": "single_artist", "artist_id": "123"},
                        "filters": [],
                        "actions": ["download_artist"],
                        "max_artists_per_run": 25,
                    },
                },
                {
                    "draft_id": "draft-2",
                    "title": "Second schedule",
                    "schedule": True,
                    "name": "Second schedule",
                    "interval_days": 30,
                    "enabled": True,
                    "run_after_startup": True,
                    "config": {
                        "target": {"type": "single_artist", "artist_id": "456"},
                        "filters": [],
                        "actions": ["download_artist"],
                        "max_artists_per_run": 25,
                    },
                },
            ],
        },
    )

    assert response.status_code == 200
    schedules_response = client.get("/api/scheduled-tasks")

    assert schedules_response.status_code == 200
    tasks = sorted(schedules_response.json()["items"], key=lambda task: task["name"])
    assert [(task["name"], task["status"]) for task in tasks] == [
        ("First schedule", "active"),
        ("Second schedule", "inactive"),
    ]


def test_workflow_batch_one_time_jobs_respect_active_limit(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/workflows/runs",
        json={
            "concurrency": 2,
            "items": [
                {
                    "draft_id": "draft-1",
                    "title": "First one-time",
                    "config": {
                        "target": {"type": "single_artist", "artist_id": "123"},
                        "filters": [],
                        "actions": ["download_artist"],
                        "max_artists_per_run": 25,
                    },
                },
                {
                    "draft_id": "draft-2",
                    "title": "Second one-time",
                    "config": {
                        "target": {"type": "single_artist", "artist_id": "456"},
                        "filters": [],
                        "actions": ["download_artist"],
                        "max_artists_per_run": 25,
                    },
                },
            ],
        },
    )

    assert response.status_code == 200
    jobs_response = client.get("/api/jobs")

    assert jobs_response.status_code == 200
    jobs = sorted(jobs_response.json()["items"], key=lambda job: job["input_user_id"])
    assert [(job["input_user_id"], job["status"]) for job in jobs] == [
        ("123", "queued"),
        ("456", "inactive"),
    ]


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
        assert job.type == "sync_artist"
        assert job.input_user_id == "123"
    finally:
        repository.close()


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
            "max_concurrent_downloads": 1,
            "max_active_scheduled_tasks": 1,
            "max_active_one_time_tasks": 1,
            "min_free_space_gb": 10.0,
            "library_stale_check_days": 30,
            "overwrite_existing_files": false,
            "skip_existing_files": true
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
    migrate_database(tmp_path / "pixiv.sqlite3", settings_json_path=settings_path)
    app = create_app(
        db_path=tmp_path / "pixiv.sqlite3",
        settings_json_path=settings_path,
        start_queue=False,
        job_queue=queue or NoopQueue(),
    )
    return TestClient(app)


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
