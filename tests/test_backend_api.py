import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api import routes_settings
from backend.app import create_app
from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Job
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.tag_repository import LocalTagRepository
from backend.services import scheduled_task_service
from backend.services.settings_service import AppSettingsService


class NoopQueue:
    def __init__(self):
        self.wake_count = 0

    def wake(self):
        self.wake_count += 1


def test_health_endpoint(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.2.0"}


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
            "min_free_space_gb": 10.0,
            "overwrite_existing_files": False,
            "skip_existing_files": True,
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["download_path"].endswith("new-downloads")
    assert body["download_path_editable"] is True
    assert body["runtime_mode"] == "local"
    assert body["min_free_space_gb"] == 10.0
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
            "min_free_space_gb": 10.0,
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
