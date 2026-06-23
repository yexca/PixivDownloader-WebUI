from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

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
    ) -> None:
        if download_path is None:
            settings = SettingsService().load()
            self.download_path = Path(settings.download_path)
            self.skip_existing = settings.skip_existing_files
        else:
            self.download_path = Path(download_path)
            self.skip_existing = skip_existing
        self.http_client = http_client or requests
        self.download_path.mkdir(parents=True, exist_ok=True)

    def download(self, artist_name: str, artist_id: str, url: str) -> FileDownloadResult:
        artist_dir = self.download_path / f"{clean_path(artist_name)} - {artist_id}"
        artist_dir.mkdir(parents=True, exist_ok=True)

        file_name = url.split("/")[-1]
        local_path = artist_dir / file_name
        if self.skip_existing and local_path.exists():
            return FileDownloadResult(
                url=url,
                file_name=file_name,
                local_path=local_path,
                size_bytes=local_path.stat().st_size,
                skipped=True,
            )

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
