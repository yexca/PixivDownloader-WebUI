import json

import pytest
import requests

from backend.core import paths


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    """Even callers using default paths must never touch the user's runtime data."""
    for name in (
        "PIXIV_AUTH_BROWSER_TOKEN",
        "PIXIV_AUTH_BROWSER_VNC_PASSWORD",
        "PIXIV_AUTH_BROWSER_INTERNAL_URL",
        "PIXIV_AUTH_BROWSER_PUBLIC_URL",
        "PIXIV_AUTH_BROWSER_CALLBACK_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    runtime = tmp_path / "runtime"
    config = runtime / "config"
    config.mkdir(parents=True)
    (config / "settings.example.json").write_text(
        json.dumps(
            {
                "download_path": str(runtime / "downloads"),
                "min_free_space_gb": 0,
                "request_random_delay_seconds": 0,
                "file_download_base_delay_seconds": 0,
                "file_download_random_delay_seconds": 0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "project_root", lambda: runtime)

    def reject_network(*_args, **_kwargs):
        raise AssertionError("Tests must use a mocked HTTP boundary")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_network)
