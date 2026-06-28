from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from backend.core.config import ExistingFileBehavior
from backend.core.config import SettingsService
from backend.core.errors import DownloadError


class HttpResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def iter_content(self, chunk_size: int) -> object: ...


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        stream: bool,
        timeout: int,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class FileDownloadResult:
    url: str
    file_name: str
    local_path: Path
    size_bytes: int
    skipped: bool = False


class FileDownloader:
    def __init__(
        self,
        download_path: Path | str | None = None,
        *,
        http_client: HttpClient | None = None,
        skip_existing: bool = False,
        existing_file_behavior: ExistingFileBehavior | None = None,
    ) -> None:
        if download_path is None:
            settings = SettingsService().load()
            self.download_path = Path(settings.download_path)
            self.existing_file_behavior = settings.existing_file_behavior
        else:
            self.download_path = Path(download_path)
            self.existing_file_behavior = existing_file_behavior or (
                "skip" if skip_existing else "overwrite"
            )
        self.http_client = http_client or requests
        try:
            self.download_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DownloadError(f"download path is not writable: {self.download_path}") from exc

    def download(
        self,
        artist_name: str,
        artist_id: str,
        url: str,
        *,
        relative_path: str | None = None,
    ) -> FileDownloadResult:
        if relative_path:
            local_path = safe_download_path(self.download_path, relative_path)
            file_name = local_path.name
            parent_dir = local_path.parent
        else:
            parent_dir = self.download_path / f"{clean_path(artist_name)} - {artist_id}"
            file_name = url.split("/")[-1]
            local_path = parent_dir / file_name
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DownloadError(f"download path is not writable: {parent_dir}") from exc

        if self.existing_file_behavior == "skip" and local_path.exists():
            return FileDownloadResult(
                url=url,
                file_name=file_name,
                local_path=local_path,
                size_bytes=local_path.stat().st_size,
                skipped=True,
            )
        if self.existing_file_behavior == "save_duplicate":
            local_path = unique_download_path(local_path)
            file_name = local_path.name

        headers = {
            "Referer": "https://www.pixiv.net/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            ),
        }

        try:
            response = self.http_client.get(url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            size_bytes = 0
            with local_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
                        size_bytes += len(chunk)
        except requests.exceptions.RequestException as exc:
            raise DownloadError(f"failed to download {url}") from exc
        except OSError as exc:
            raise DownloadError(f"failed to write {local_path}") from exc

        return FileDownloadResult(
            url=url,
            file_name=file_name,
            local_path=local_path,
            size_bytes=size_bytes,
        )


def clean_path(path: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", path)


def safe_download_path(base_path: Path, relative_path: str) -> Path:
    parts = [clean_path(part).strip() for part in re.split(r"[/\\]+", relative_path)]
    cleaned_parts = [part for part in parts if part and part not in {".", ".."}]
    if not cleaned_parts:
        raise DownloadError("download file name is empty")
    return base_path.joinpath(*cleaned_parts)


def unique_download_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
