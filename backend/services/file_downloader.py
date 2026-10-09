from __future__ import annotations

import os
import re
import tempfile
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from backend.core.config import ExistingFileBehavior, SettingsService
from backend.core.errors import DownloadError, JobCancelledError
from backend.services.pixiv_rate_policy import PixivRequestPolicy, file_download_request_policy


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
    # Serialize path allocation and replacement, including save_duplicate.
    _path_locks = tuple(threading.RLock() for _ in range(64))

    def __init__(
        self,
        download_path: Path | str | None = None,
        *,
        http_client: HttpClient | None = None,
        skip_existing: bool = False,
        existing_file_behavior: ExistingFileBehavior | None = None,
        request_policy: PixivRequestPolicy | None = None,
    ) -> None:
        if download_path is None:
            settings = SettingsService().load()
            self.download_path = Path(settings.download_path)
            self.existing_file_behavior = settings.existing_file_behavior
            if request_policy is None:
                request_policy = file_download_request_policy(
                    min_interval_seconds=settings.file_download_base_delay_seconds,
                    random_delay_seconds=settings.file_download_random_delay_seconds,
                )
        else:
            self.download_path = Path(download_path)
            self.existing_file_behavior = existing_file_behavior or (
                "skip" if skip_existing else "overwrite"
            )
        self.http_client = http_client or requests
        self.request_policy = request_policy
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
        cancel_callback: Callable[[], bool] | None = None,
        retry_incomplete: bool = False,
    ) -> FileDownloadResult:
        path = (
            safe_download_path(self.download_path, relative_path)
            if relative_path
            else self.download_path
            / f"{clean_path(artist_name)} - {artist_id}"
            / url.split("/")[-1]
        )
        lock = self._path_locks[hash(str(path.resolve()).casefold()) % 64]
        while not lock.acquire(timeout=0.2):
            check_cancel(cancel_callback)
        try:
            return self._download(
                artist_name,
                artist_id,
                url,
                relative_path=relative_path,
                cancel_callback=cancel_callback,
                retry_incomplete=retry_incomplete,
            )
        finally:
            lock.release()

    def _download(
        self,
        artist_name: str,
        artist_id: str,
        url: str,
        *,
        relative_path: str | None,
        cancel_callback: Callable[[], bool] | None,
        retry_incomplete: bool,
    ) -> FileDownloadResult:
        check_cancel(cancel_callback)
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

        if self.existing_file_behavior == "skip" and local_path.exists() and not retry_incomplete:
            return FileDownloadResult(
                url=url,
                file_name=file_name,
                local_path=local_path,
                size_bytes=local_path.stat().st_size,
                skipped=True,
            )
        if self.existing_file_behavior == "save_duplicate" and not retry_incomplete:
            local_path = unique_download_path(local_path)
            file_name = local_path.name

        headers = {
            "Referer": "https://www.pixiv.net/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            ),
        }

        response = None
        temporary_path = None
        try:
            response = self._get(url, headers=headers, cancel_callback=cancel_callback)
            size_bytes = 0
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=parent_dir, prefix=f".{file_name}.", suffix=".part", delete=False
            ) as file:
                temporary_path = Path(file.name)
                for chunk in response.iter_content(chunk_size=8192):
                    check_cancel(cancel_callback)
                    if chunk:
                        file.write(chunk)
                        size_bytes += len(chunk)
                file.flush()
                os.fsync(file.fileno())
            check_cancel(cancel_callback)
            length = getattr(response, "headers", {}).get("Content-Length")
            if size_bytes == 0 or (length is not None and size_bytes != int(length)):
                raise DownloadError(f"incomplete response for {url}")
            temporary_path.replace(local_path)
        except requests.exceptions.RequestException as exc:
            raise DownloadError(f"failed to download {url}") from exc
        except OSError as exc:
            raise DownloadError(f"failed to write {local_path}") from exc
        finally:
            if response is not None:
                close = getattr(response, "close", None)
                if close is not None:
                    with suppress(Exception):
                        close()
            if temporary_path is not None:
                with suppress(FileNotFoundError):
                    temporary_path.unlink()

        return FileDownloadResult(
            url=url,
            file_name=file_name,
            local_path=local_path,
            size_bytes=size_bytes,
        )

    def _get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        cancel_callback: Callable[[], bool] | None = None,
    ) -> HttpResponse:
        def request() -> HttpResponse:
            response = self.http_client.get(url, headers=headers, stream=True, timeout=60)
            try:
                response.raise_for_status()
            except Exception:
                close = getattr(response, "close", None)
                if close is not None:
                    close()
                raise
            return response

        if self.request_policy is None:
            return request()
        return self.request_policy.run("file download", request, cancel_callback=cancel_callback)


def check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise JobCancelledError("Job cancelled")


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
