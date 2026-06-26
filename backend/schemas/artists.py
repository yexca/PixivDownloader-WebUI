from __future__ import annotations

from pydantic import BaseModel

from backend.domain.entities import Artist, Artwork, LocalTag


class LocalTagResponse(BaseModel):
    id: int
    name: str


class LocalTagListResponse(BaseModel):
    items: list[LocalTagResponse]
    total: int


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
    local_tags: list[LocalTagResponse] = []


class ArtistListResponse(BaseModel):
    items: list[ArtistSummaryResponse]
    total: int


class ArtistDetailResponse(ArtistSummaryResponse):
    account: str | None
    comment: str | None


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
        local_tags=local_tag_list_response(local_tags or []).items,
    )


def artist_detail_response(
    artist: Artist,
    counts: dict[str, int],
    local_tags: list[LocalTag] | None = None,
) -> ArtistDetailResponse:
    return ArtistDetailResponse(
        **artist_summary_response(artist, counts, local_tags).model_dump(),
        account=artist.account,
        comment=artist.comment,
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
