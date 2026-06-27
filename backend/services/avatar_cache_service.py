from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from backend.core.paths import resources_dir
from backend.domain.entities import Artist


class HttpResponse(Protocol):
    headers: dict[str, str]

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
class CachedAvatar:
    path: Path
    media_type: str


class AvatarCacheService:
    max_size_bytes = 5 * 1024 * 1024

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        *,
        http_client: HttpClient | None = None,
    ) -> None:
        self.cache_dir = (
            Path(cache_dir) if cache_dir is not None else resources_dir() / "cache" / "avatars"
        )
        self.http_client = http_client or requests

    def cache_artist_avatar(self, artist: Artist) -> bool:
        if not artist.avatar_url:
            return False
        cached = self.get_cached_avatar(artist.id)
        if cached is not None:
            return True

        media_type = media_type_from_url(artist.avatar_url)
        if media_type is None:
            return False
        target_path = avatar_path(
            self.cache_dir,
            artist.id,
            media_type,
        )
        temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
        headers = {
            "Referer": "https://www.pixiv.net/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            ),
        }

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            response = self.http_client.get(
                artist.avatar_url,
                headers=headers,
                stream=True,
                timeout=30,
            )
            response.raise_for_status()
            response_media_type = normalized_media_type(response.headers.get("content-type", ""))
            if response_media_type is not None:
                media_type = response_media_type
                target_path = avatar_path(
                    self.cache_dir,
                    artist.id,
                    media_type,
                )
                temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")

            size_bytes = 0
            with temp_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    size_bytes += len(chunk)  # type: ignore[arg-type]
                    if size_bytes > self.max_size_bytes:
                        raise ValueError("avatar image is too large")
                    file.write(chunk)  # type: ignore[arg-type]
            if size_bytes == 0:
                raise ValueError("avatar image is empty")
            self.remove_artist_avatar(artist.id)
            temp_path.replace(target_path)
            return True
        except Exception:
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)
            return False

    def get_cached_avatar(self, artist_id: str) -> CachedAvatar | None:
        safe_id = safe_artist_id(artist_id)
        for suffix, media_type in supported_media_types().items():
            path = self.cache_dir / f"{safe_id}{suffix}"
            if path.is_file():
                return CachedAvatar(path=path, media_type=media_type)
        return None

    def has_cached_avatar(self, artist_id: str) -> bool:
        return self.get_cached_avatar(artist_id) is not None

    def remove_artist_avatar(self, artist_id: str) -> None:
        safe_id = safe_artist_id(artist_id)
        for suffix in supported_media_types():
            with suppress(OSError):
                (self.cache_dir / f"{safe_id}{suffix}").unlink(missing_ok=True)


def safe_artist_id(artist_id: str) -> str:
    return (
        "".join(
            character
            for character in artist_id
            if character.isalnum() or character in {"-", "_"}
        )
        or "unknown"
    )


def avatar_path(cache_dir: Path, artist_id: str, media_type: str) -> Path:
    return cache_dir / f"{safe_artist_id(artist_id)}{extension_for_media_type(media_type)}"


def supported_media_types() -> dict[str, str]:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }


def normalized_media_type(value: str) -> str | None:
    media_type = value.split(";", 1)[0].strip().lower()
    if media_type in set(supported_media_types().values()):
        return media_type
    return None


def media_type_from_url(url: str) -> str | None:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    return supported_media_types().get(suffix)


def extension_for_media_type(media_type: str) -> str:
    if media_type == "image/jpeg":
        return ".jpg"
    for suffix, candidate in supported_media_types().items():
        if candidate == media_type:
            return suffix
    return ".jpg"
