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
    assert response.json() == {"status": "ok", "version": "1.0.0"}


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
            "overwrite_existing_files": False,
            "skip_existing_files": True,
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["download_path"].endswith("new-downloads")
    assert body["download_path_editable"] is True
    assert body["runtime_mode"] == "local"
    assert body["refresh_token_configured"] is True
    assert body["refresh_token_preview"] == "secr...oken"


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
