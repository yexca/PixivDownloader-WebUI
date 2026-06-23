from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from backend.core.config import SettingsService
from backend.core.errors import PixivApiError, PixivAuthError
from backend.domain.entities import Artist, Artwork, ArtworkFile


class PixivApi(Protocol):
    def auth(self, *, refresh_token: str) -> None: ...

    def illust_detail(self, illust_id: str) -> Any: ...

    def user_detail(self, user_id: str) -> Any: ...

    def user_illusts(self, *args: Any, **kwargs: Any) -> Any: ...

    def parse_qs(self, next_url: str | None) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class PixivArtworkPage:
    artwork_id: str
    page_index: int
    original_url: str


class PixivClient:
    def __init__(
        self,
        refresh_token: str | None = None,
        *,
        api: PixivApi | None = None,
        sleeper: object | None = None,
    ) -> None:
        self.refresh_token = refresh_token
        if self.refresh_token is None:
            self.refresh_token = SettingsService().load().refresh_token
        if not self.refresh_token:
            raise PixivAuthError("Pixiv refresh token is not configured")

        if api is None:
            from pixivpy3 import AppPixivAPI

            api = AppPixivAPI()
        self.api = api
        self.sleeper = sleeper
        try:
            self.api.auth(refresh_token=self.refresh_token)
        except Exception as exc:
            message = "Pixiv authentication failed. Please update refresh token."
            raise PixivAuthError(message) from exc

    def get_artist_by_user_id(self, user_id: str) -> Artist:
        try:
            user = self.api.user_detail(user_id).user
        except Exception as exc:
            raise PixivApiError(f"failed to fetch Pixiv user {user_id}") from exc
        return artist_from_pixiv_user(user, fallback_id=user_id)

    def get_artist_by_artwork_id(self, artwork_id: str) -> Artist:
        try:
            illust = self.api.illust_detail(artwork_id).illust
        except Exception as exc:
            raise PixivApiError(f"failed to fetch Pixiv artwork {artwork_id}") from exc
        return artist_from_pixiv_user(illust.user)

    def get_artworks_by_user_id(self, user_id: str) -> list[Artwork]:
        illusts: list[Any] = []
        next_qs: dict[str, Any] | None = {}

        while next_qs is not None:
            try:
                if next_qs == {}:
                    json_result = self.api.user_illusts(user_id)
                else:
                    json_result = self.api.user_illusts(**next_qs)
            except Exception as exc:
                raise PixivApiError(f"failed to fetch artworks for Pixiv user {user_id}") from exc

            if _is_invalid_grant(json_result):
                self.api.auth(refresh_token=self.refresh_token)
                continue

            illusts.extend(_get_value(json_result, "illusts", []))
            next_url = _get_value(json_result, "next_url", None)
            next_qs = self.api.parse_qs(next_url)
            if self.sleeper is not None:
                self.sleeper()

        return [artwork_from_pixiv_illust(illust) for illust in illusts]


def artist_from_pixiv_user(user: Any, fallback_id: str | None = None) -> Artist:
    artist_id = str(_get_value(user, "id", fallback_id or ""))
    return Artist(
        id=artist_id,
        name=str(_get_value(user, "name", "")),
        profile_url=f"https://www.pixiv.net/users/{artist_id}",
    )


def artwork_from_pixiv_illust(illust: Any) -> Artwork:
    artwork_id = str(_get_value(illust, "id", ""))
    artist = _get_value(illust, "user", None)
    artist_id = str(_get_value(artist, "id", ""))
    pages = tuple(
        ArtworkFile(
            artwork_id=page.artwork_id,
            page_index=page.page_index,
            original_url=page.original_url,
            file_name=page.original_url.split("/")[-1],
        )
        for page in artwork_pages_from_pixiv_illust(illust)
    )
    return Artwork(
        id=artwork_id,
        artist_id=artist_id,
        title=str(_get_value(illust, "title", "")),
        files=pages,
    )


def artwork_pages_from_pixiv_illust(illust: Any) -> list[PixivArtworkPage]:
    artwork_id = str(_get_value(illust, "id", ""))
    pages: list[PixivArtworkPage] = []

    single_page = _get_value(illust, "meta_single_page", None)
    original_url = _get_value(single_page, "original_image_url", None)
    if original_url:
        pages.append(
            PixivArtworkPage(
                artwork_id=artwork_id,
                page_index=0,
                original_url=str(original_url),
            )
        )
        return pages

    meta_pages = _get_value(illust, "meta_pages", [])
    for index, page in enumerate(meta_pages):
        image_urls = _get_value(page, "image_urls", None)
        original_url = _get_value(image_urls, "original", None)
        if original_url:
            pages.append(
                PixivArtworkPage(
                    artwork_id=artwork_id,
                    page_index=index,
                    original_url=str(original_url),
                )
            )
    return pages


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _is_invalid_grant(result: Any) -> bool:
    error = _get_value(result, "error", None)
    message = _get_value(error, "message", "")
    return "invalid_grant" in str(message)


class PixivClientProtocol(Protocol):
    def get_artist_by_user_id(self, user_id: str) -> Artist: ...

    def get_artist_by_artwork_id(self, artwork_id: str) -> Artist: ...

    def get_artworks_by_user_id(self, user_id: str) -> Iterable[Artwork]: ...
