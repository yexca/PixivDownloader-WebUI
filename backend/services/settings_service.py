from __future__ import annotations

import os
from pathlib import Path

from backend.core.config import Settings
from backend.core.config import SettingsService as JsonSettingsService
from backend.core.errors import PixivAuthError
from backend.core.paths import downloads_dir
from backend.repositories.settings_repository import SettingsRepository
from backend.services.pixiv_client import PixivApi, PixivClient


class AppSettingsService:
    def __init__(
        self,
        *,
        db_path: Path | str | None = None,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.repository = SettingsRepository(db_path)
        settings_path = Path(settings_json_path) if settings_json_path is not None else None
        example_path = settings_path.with_name("settings.example.json") if settings_path else None
        self.json_settings = JsonSettingsService(settings_path, example_path=example_path)

    def get_masked(self) -> dict[str, object]:
        settings = self.load()
        return masked_settings(settings)

    def load(self) -> Settings:
        settings = self.json_settings.load()
        settings = enforce_runtime_settings(settings)
        self._sync_repository(settings)
        return settings

    def update(self, values: dict[str, object]) -> Settings:
        current = self.load().to_dict()
        refresh_token_value = values.get("refresh_token", "")
        refresh_token = refresh_token_value.strip() if isinstance(refresh_token_value, str) else ""
        update_values = {key: value for key, value in values.items() if key != "refresh_token"}
        if is_docker_runtime():
            update_values.pop("download_path", None)
        merged = {
            **current,
            **update_values,
        }
        if refresh_token:
            merged["refresh_token"] = refresh_token
        settings = enforce_runtime_settings(Settings.from_dict(merged))
        self.save(settings)
        return settings

    def validate_pixiv_auth(self, *, api: PixivApi | None = None) -> None:
        settings = self.load()
        if not settings.refresh_token:
            raise PixivAuthError("Pixiv refresh token is not configured")
        PixivClient(refresh_token=settings.refresh_token, api=api)

    def save(self, settings: Settings) -> None:
        self.json_settings.save(settings)
        self._sync_repository(settings)

    def _sync_repository(self, settings: Settings) -> None:
        values = settings.to_dict()
        for key, value in values.items():
            self.repository.set(key, value)

    def close(self) -> None:
        self.repository.close()


def masked_settings(settings: Settings) -> dict[str, object]:
    token = settings.refresh_token
    preview = ""
    if token:
        preview = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "*" * len(token)
    return {
        "download_path": settings.download_path,
        "download_path_editable": not is_docker_runtime(),
        "runtime_mode": runtime_mode(),
        "refresh_token_configured": bool(token),
        "refresh_token_preview": preview,
        "request_base_delay_seconds": settings.request_base_delay_seconds,
        "request_random_delay_seconds": settings.request_random_delay_seconds,
        "max_concurrent_downloads": settings.max_concurrent_downloads,
        "max_active_scheduled_tasks": settings.max_active_scheduled_tasks,
        "max_active_one_time_tasks": settings.max_active_one_time_tasks,
        "min_free_space_gb": settings.min_free_space_gb,
        "overwrite_existing_files": settings.overwrite_existing_files,
        "skip_existing_files": settings.skip_existing_files,
        "library_stale_check_days": settings.library_stale_check_days,
    }


def runtime_mode() -> str:
    value = os.environ.get("PIXIVDOWNLOADER_RUNTIME", "").strip().lower()
    return value or "local"


def is_docker_runtime() -> bool:
    return runtime_mode() == "docker"


def enforce_runtime_settings(settings: Settings) -> Settings:
    if not is_docker_runtime():
        return settings
    return Settings.from_dict(
        {
            **settings.to_dict(),
            "download_path": str(downloads_dir()),
        }
    )
