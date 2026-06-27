from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from backend.domain.entities import Artist, ArtistNameHistory, Artwork, LocalTag
from backend.domain.types import ArtistAccountStatus


class LocalTagResponse(BaseModel):
    id: int
    name: str


class LocalTagListResponse(BaseModel):
    items: list[LocalTagResponse]
    total: int


class ArtistNameHistoryResponse(BaseModel):
    id: int
    name: str
    source: str
    first_seen_at: str | None
    last_seen_at: str | None


class ArtistSummaryResponse(BaseModel):
    id: str
    name: str
    profile_url: str
    avatar_url: str | None
    artwork_count: int
    downloaded_file_count: int
    remote_file_count: int
    pending_file_count: int
    failed_file_count: int
    latest_downloaded_artwork_id: str | None
    last_checked_at: str | None
    account_status: ArtistAccountStatus
    account_status_checked_at: str | None
    account_status_reason: str | None
    remote_latest_artwork_id: str | None
    remote_latest_checked_at: str | None
    has_remote_update: bool
    is_check_stale: bool
    check_stale_days: int
    local_tags: list[LocalTagResponse] = []


class ArtistListResponse(BaseModel):
    items: list[ArtistSummaryResponse]
    total: int


class ArtistDetailResponse(ArtistSummaryResponse):
    account: str | None
    comment: str | None
    name_history: list[ArtistNameHistoryResponse] = []


class ArtworkSummaryResponse(BaseModel):
    id: str
    artist_id: str
    title: str
    type: str | None
    page_count: int
    pixiv_created_at: str | None
    total_files: int
    downloaded_files: int
    skipped_files: int
    failed_files: int


class ArtworkListResponse(BaseModel):
    items: list[ArtworkSummaryResponse]
    total: int


class ArtistCreateRequest(BaseModel):
    user_id: str


class ArtistTagUpdateRequest(BaseModel):
    tags: list[str]


def artist_summary_response(
    artist: Artist,
    counts: dict[str, int],
    local_tags: list[LocalTag] | None = None,
    *,
    stale_days: int = 30,
) -> ArtistSummaryResponse:
    return ArtistSummaryResponse(
        id=artist.id,
        name=artist.name,
        profile_url=artist.profile_url,
        avatar_url=artist.avatar_url,
        artwork_count=counts["artwork_count"],
        downloaded_file_count=counts["downloaded_file_count"],
        remote_file_count=counts["remote_file_count"],
        pending_file_count=counts["pending_file_count"],
        failed_file_count=counts["failed_file_count"],
        latest_downloaded_artwork_id=artist.last_download_id,
        last_checked_at=artist.last_checked_at,
        account_status=artist.account_status,
        account_status_checked_at=artist.account_status_checked_at,
        account_status_reason=artist.account_status_reason,
        remote_latest_artwork_id=artist.remote_latest_artwork_id,
        remote_latest_checked_at=artist.remote_latest_checked_at,
        has_remote_update=has_remote_update(artist),
        is_check_stale=is_check_stale(artist, stale_days),
        check_stale_days=stale_days,
        local_tags=local_tag_list_response(local_tags or []).items,
    )


def artist_detail_response(
    artist: Artist,
    counts: dict[str, int],
    local_tags: list[LocalTag] | None = None,
    name_history: list[ArtistNameHistory] | None = None,
    *,
    stale_days: int = 30,
) -> ArtistDetailResponse:
    return ArtistDetailResponse(
        **artist_summary_response(artist, counts, local_tags, stale_days=stale_days).model_dump(),
        account=artist.account,
        comment=artist.comment,
        name_history=artist_name_history_list_response(name_history or []),
    )


def artwork_summary_response(
    artwork: Artwork,
    counts: dict[str, int],
) -> ArtworkSummaryResponse:
    return ArtworkSummaryResponse(
        id=artwork.id,
        artist_id=artwork.artist_id,
        title=artwork.title,
        type=artwork.type,
        page_count=artwork.page_count,
        pixiv_created_at=artwork.pixiv_created_at,
        total_files=counts["total_files"],
        downloaded_files=counts["downloaded_files"],
        skipped_files=counts["skipped_files"],
        failed_files=counts["failed_files"],
    )


def local_tag_list_response(tags: list[LocalTag]) -> LocalTagListResponse:
    return LocalTagListResponse(
        items=[LocalTagResponse(id=tag.id, name=tag.name) for tag in tags],
        total=len(tags),
    )


def artist_name_history_list_response(
    items: list[ArtistNameHistory],
) -> list[ArtistNameHistoryResponse]:
    return [
        ArtistNameHistoryResponse(
            id=item.id or 0,
            name=item.name,
            source=item.source,
            first_seen_at=item.first_seen_at,
            last_seen_at=item.last_seen_at,
        )
        for item in items
    ]


def has_remote_update(artist: Artist) -> bool:
    if not artist.remote_latest_artwork_id:
        return False
    try:
        remote_latest = int(artist.remote_latest_artwork_id)
        latest_downloaded = int(artist.last_download_id or 0)
    except ValueError:
        return artist.remote_latest_artwork_id != artist.last_download_id
    return remote_latest > latest_downloaded


def is_check_stale(artist: Artist, stale_days: int) -> bool:
    checked_at = artist.remote_latest_checked_at or artist.last_checked_at
    if checked_at is None:
        return True
    try:
        checked_time = datetime.fromisoformat(checked_at.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return True
    return checked_time <= datetime.now(UTC) - timedelta(days=max(1, stale_days))
