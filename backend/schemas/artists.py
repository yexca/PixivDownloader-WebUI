from __future__ import annotations

from pydantic import BaseModel

from backend.domain.entities import Artist, Artwork


class ArtistSummaryResponse(BaseModel):
    id: str
    name: str
    profile_url: str
    avatar_url: str | None
    artwork_count: int
    downloaded_file_count: int
    failed_file_count: int
    last_checked_at: str | None


class ArtistListResponse(BaseModel):
    items: list[ArtistSummaryResponse]
    total: int


class ArtistDetailResponse(ArtistSummaryResponse):
    account: str | None
    comment: str | None
    legacy_last_download_id: str | None


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


def artist_summary_response(
    artist: Artist,
    counts: dict[str, int],
) -> ArtistSummaryResponse:
    return ArtistSummaryResponse(
        id=artist.id,
        name=artist.name,
        profile_url=artist.profile_url,
        avatar_url=artist.avatar_url,
        artwork_count=counts["artwork_count"],
        downloaded_file_count=counts["downloaded_file_count"],
        failed_file_count=counts["failed_file_count"],
        last_checked_at=artist.last_checked_at,
    )


def artist_detail_response(artist: Artist, counts: dict[str, int]) -> ArtistDetailResponse:
    return ArtistDetailResponse(
        **artist_summary_response(artist, counts).model_dump(),
        account=artist.account,
        comment=artist.comment,
        legacy_last_download_id=artist.last_download_id,
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
