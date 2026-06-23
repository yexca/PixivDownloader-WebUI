from __future__ import annotations

from pathlib import Path

from backend.core.config import Settings
from backend.core.config import SettingsService as JsonSettingsService
from backend.core.errors import PixivAuthError
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
        self.json_settings = JsonSettingsService(settings_json_path)

    def get_masked(self) -> dict[str, object]:
        settings = self.load()
        return masked_settings(settings)

    def load(self) -> Settings:
        values = self.repository.all()
        if not values:
            settings = self.json_settings.load()
            self.save(settings)
            return settings
        return Settings.from_dict(values)

    def update(self, values: dict[str, object]) -> Settings:
        current = self.load().to_dict()
        refresh_token = str(values.get("refresh_token", "")).strip()
        merged = {
            **current,
            **{key: value for key, value in values.items() if key != "refresh_token"},
        }
        if refresh_token:
            merged["refresh_token"] = refresh_token
        settings = Settings.from_dict(merged)
        self.save(settings)
        return settings

    def validate_pixiv_auth(self, *, api: PixivApi | None = None) -> None:
        settings = self.load()
        if not settings.refresh_token:
            raise PixivAuthError("Pixiv refresh token is not configured")
        PixivClient(refresh_token=settings.refresh_token, api=api)

    def save(self, settings: Settings) -> None:
        values = settings.to_dict()
        for key, value in values.items():
            self.repository.set(key, value)
        self.json_settings.save(settings)

    def close(self) -> None:
        self.repository.close()


def masked_settings(settings: Settings) -> dict[str, object]:
    token = settings.refresh_token
    preview = ""
    if token:
        preview = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "*" * len(token)
    return {
        "download_path": settings.download_path,
        "refresh_token_configured": bool(token),
        "refresh_token_preview": preview,
        "request_base_delay_seconds": settings.request_base_delay_seconds,
        "request_random_delay_seconds": settings.request_random_delay_seconds,
        "max_concurrent_downloads": settings.max_concurrent_downloads,
        "overwrite_existing_files": settings.overwrite_existing_files,
        "skip_existing_files": settings.skip_existing_files,
    }
