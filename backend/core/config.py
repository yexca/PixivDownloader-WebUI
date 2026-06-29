from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from backend.core.errors import ConfigError
from backend.core.paths import settings_example_path as default_settings_example_path
from backend.core.paths import settings_path as default_settings_path

ExistingFileBehavior = Literal["skip", "overwrite", "save_duplicate"]


@dataclass(frozen=True)
class Settings:
    download_path: str
    refresh_token: str = ""
    request_base_delay_seconds: float = 0.0
    request_random_delay_seconds: float = 2.0
    file_download_base_delay_seconds: float = 1.0
    file_download_random_delay_seconds: float = 0.5
    max_concurrent_downloads: int = 1
    max_active_scheduled_tasks: int = 1
    max_active_one_time_tasks: int = 1
    min_free_space_gb: float = 10.0
    existing_file_behavior: ExistingFileBehavior = "skip"
    library_stale_check_days: int = 30

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        download_path = str(data.get("download_path", "")).strip()
        if not download_path:
            raise ConfigError("download_path is required")

        max_concurrent_downloads = int(data.get("max_concurrent_downloads", 1))
        if max_concurrent_downloads < 1:
            raise ConfigError("max_concurrent_downloads must be at least 1")

        max_active_scheduled_tasks = int(data.get("max_active_scheduled_tasks", 1))
        if max_active_scheduled_tasks < 1:
            raise ConfigError("max_active_scheduled_tasks must be at least 1")

        max_active_one_time_tasks = int(data.get("max_active_one_time_tasks", 1))
        if max_active_one_time_tasks < 1:
            raise ConfigError("max_active_one_time_tasks must be at least 1")

        request_base_delay_seconds = float(data.get("request_base_delay_seconds", 0.0))
        request_random_delay_seconds = float(data.get("request_random_delay_seconds", 2.0))
        if request_base_delay_seconds < 0 or request_random_delay_seconds < 0:
            raise ConfigError("request delays must be non-negative")

        file_download_base_delay_seconds = float(data.get("file_download_base_delay_seconds", 1.0))
        file_download_random_delay_seconds = float(
            data.get("file_download_random_delay_seconds", 0.5)
        )
        if file_download_base_delay_seconds < 0 or file_download_random_delay_seconds < 0:
            raise ConfigError("file download delays must be non-negative")

        min_free_space_gb = float(data.get("min_free_space_gb", 10.0))
        if min_free_space_gb < 0:
            raise ConfigError("minimum free space must be non-negative")

        library_stale_check_days = int(data.get("library_stale_check_days", 30))
        if library_stale_check_days < 1:
            raise ConfigError("library stale check days must be at least 1")

        existing_file_behavior = str(
            data.get(
                "existing_file_behavior",
                legacy_existing_file_behavior(data),
            )
        )
        if existing_file_behavior not in {"skip", "overwrite", "save_duplicate"}:
            raise ConfigError("existing_file_behavior must be skip, overwrite, or save_duplicate")

        return cls(
            download_path=download_path,
            refresh_token=str(data.get("refresh_token", "")),
            request_base_delay_seconds=request_base_delay_seconds,
            request_random_delay_seconds=request_random_delay_seconds,
            file_download_base_delay_seconds=file_download_base_delay_seconds,
            file_download_random_delay_seconds=file_download_random_delay_seconds,
            max_concurrent_downloads=max_concurrent_downloads,
            max_active_scheduled_tasks=max_active_scheduled_tasks,
            max_active_one_time_tasks=max_active_one_time_tasks,
            min_free_space_gb=min_free_space_gb,
            existing_file_behavior=existing_file_behavior,
            library_stale_check_days=library_stale_check_days,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "download_path": self.download_path,
            "refresh_token": self.refresh_token,
            "request_base_delay_seconds": self.request_base_delay_seconds,
            "request_random_delay_seconds": self.request_random_delay_seconds,
            "file_download_base_delay_seconds": self.file_download_base_delay_seconds,
            "file_download_random_delay_seconds": self.file_download_random_delay_seconds,
            "max_concurrent_downloads": self.max_concurrent_downloads,
            "max_active_scheduled_tasks": self.max_active_scheduled_tasks,
            "max_active_one_time_tasks": self.max_active_one_time_tasks,
            "min_free_space_gb": self.min_free_space_gb,
            "existing_file_behavior": self.existing_file_behavior,
            "overwrite_existing_files": self.existing_file_behavior == "overwrite",
            "skip_existing_files": self.existing_file_behavior == "skip",
            "library_stale_check_days": self.library_stale_check_days,
        }


class SettingsService:
    def __init__(
        self,
        path: Path | str | None = None,
        *,
        example_path: Path | str | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else default_settings_path()
        self.example_path = (
            Path(example_path) if example_path is not None else default_settings_example_path()
        )

    def load_raw(self) -> dict[str, Any]:
        defaults = self._load_file(self.example_path, required=True)
        overrides = self._load_file(self.path, required=False)
        return {**defaults, **overrides}

    def _load_file(self, path: Path, *, required: bool) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            if required:
                raise ConfigError(f"settings example file not found: {path}") from exc
            return {}
        except json.JSONDecodeError as exc:
            raise ConfigError(f"settings file is invalid JSON: {path}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"settings file must contain a JSON object: {path}")
        return data

    def load(self) -> Settings:
        return Settings.from_dict(self.load_raw())

    def save_raw(self, settings: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(settings, indent=4, ensure_ascii=False)

        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                delete=False,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            ) as temp_file:
                temp_file.write(content)
                temp_path = Path(temp_file.name)
            temp_path.replace(self.path)
        except OSError as exc:
            raise ConfigError(f"failed to save settings: {self.path}") from exc

    def save(self, settings: Settings) -> None:
        self.save_raw(settings.to_dict())

    def masked_for_display(self) -> dict[str, Any]:
        settings = self.load()
        token = settings.refresh_token
        return {
            "download_path": settings.download_path,
            "refresh_token_configured": bool(token),
            "refresh_token_preview": mask_token(token),
            "request_base_delay_seconds": settings.request_base_delay_seconds,
            "request_random_delay_seconds": settings.request_random_delay_seconds,
            "file_download_base_delay_seconds": settings.file_download_base_delay_seconds,
            "file_download_random_delay_seconds": settings.file_download_random_delay_seconds,
            "max_concurrent_downloads": settings.max_concurrent_downloads,
            "max_active_scheduled_tasks": settings.max_active_scheduled_tasks,
            "max_active_one_time_tasks": settings.max_active_one_time_tasks,
            "min_free_space_gb": settings.min_free_space_gb,
            "existing_file_behavior": settings.existing_file_behavior,
            "overwrite_existing_files": settings.existing_file_behavior == "overwrite",
            "skip_existing_files": settings.existing_file_behavior == "skip",
            "library_stale_check_days": settings.library_stale_check_days,
        }


def legacy_existing_file_behavior(data: dict[str, Any]) -> ExistingFileBehavior:
    if bool(data.get("overwrite_existing_files", False)):
        return "overwrite"
    if bool(data.get("skip_existing_files", True)):
        return "skip"
    return "save_duplicate"


def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}...{token[-4:]}"
