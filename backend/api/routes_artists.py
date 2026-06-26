from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.tag_repository import LocalTagRepository
from backend.schemas.artists import (
    ArtistCreateRequest,
    ArtistDetailResponse,
    ArtistListResponse,
    ArtistTagUpdateRequest,
    ArtworkListResponse,
    LocalTagListResponse,
    artist_detail_response,
    artist_summary_response,
    artwork_summary_response,
    local_tag_list_response,
)
from backend.schemas.downloads import DownloadCreateResponse
from backend.services.job_service import JobService

router = APIRouter(prefix="/api/artists", tags=["artists"])


@router.get("", response_model=ArtistListResponse)
def list_artists(
    db_path: DbPath,
    q: str | None = None,
    local_tag: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: str = "updated_desc",
) -> ArtistListResponse:
    repository = ArtistRepository(db_path)
    tag_repository = LocalTagRepository(db_path)
    try:
        artists = repository.list(limit=limit, offset=offset, query=q, local_tag=local_tag)
        if sort == "name_asc":
            artists = sorted(artists, key=lambda artist: artist.name.lower())
        if sort == "id_asc":
            artists = sorted(artists, key=lambda artist: artist.id)
        return ArtistListResponse(
            items=[
                artist_summary_response(
                    artist,
                    repository.get_counts(artist.id),
                    tag_repository.list_for_artist(artist.id),
                )
                for artist in artists
            ],
            total=repository.count(query=q, local_tag=local_tag),
        )
    finally:
        repository.close()
        tag_repository.close()


@router.post("", response_model=DownloadCreateResponse)
def create_artist(
    request: ArtistCreateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    service = JobService(db_path, settings_json_path=settings_json_path)
    try:
        job = service.create_download_job(
            user_id=request.user_id,
            artwork_id=None,
            sync_only=True,
        )
    finally:
        service.close()
    queue.wake()
    return DownloadCreateResponse(job_id=job.id, status=job.status)


@router.get("/-/local-tags", response_model=LocalTagListResponse)
def list_local_tags(db_path: DbPath) -> LocalTagListResponse:
    repository = LocalTagRepository(db_path)
    try:
        return local_tag_list_response(repository.list())
    finally:
        repository.close()


@router.get("/{artist_id}", response_model=ArtistDetailResponse)
def get_artist(artist_id: str, db_path: DbPath) -> ArtistDetailResponse:
    repository = ArtistRepository(db_path)
    tag_repository = LocalTagRepository(db_path)
    try:
        artist = repository.get_by_id(artist_id)
        if artist is None:
            raise HTTPException(status_code=404, detail="artist not found")
        return artist_detail_response(
            artist,
            repository.get_counts(artist.id),
            tag_repository.list_for_artist(artist.id),
        )
    finally:
        repository.close()
        tag_repository.close()


@router.delete("/{artist_id}", status_code=204)
def delete_artist(artist_id: str, db_path: DbPath) -> None:
    repository = ArtistRepository(db_path)
    try:
        if not repository.delete(artist_id):
            raise HTTPException(status_code=404, detail="artist not found")
    finally:
        repository.close()


@router.post("/{artist_id}/sync", response_model=DownloadCreateResponse)
def sync_artist(
    artist_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    service = JobService(db_path, settings_json_path=settings_json_path)
    try:
        job = service.create_download_job(
            user_id=artist_id,
            artwork_id=None,
            sync_only=True,
        )
    finally:
        service.close()
    queue.wake()
    return DownloadCreateResponse(job_id=job.id, status=job.status)


@router.post("/{artist_id}/retry-failed", response_model=DownloadCreateResponse)
def retry_failed_artist(
    artist_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    artist_repository = ArtistRepository(db_path)
    try:
        if artist_repository.get_by_id(artist_id) is None:
            raise HTTPException(status_code=404, detail="artist not found")
    finally:
        artist_repository.close()

    service = JobService(db_path, settings_json_path=settings_json_path)
    try:
        job = service.create_download_job(
            user_id=artist_id,
            artwork_id=None,
            retry_failed_artist=True,
        )
    finally:
        service.close()
    queue.wake()
    return DownloadCreateResponse(job_id=job.id, status=job.status)


@router.put("/{artist_id}/local-tags", response_model=LocalTagListResponse)
def set_artist_local_tags(
    artist_id: str,
    request: ArtistTagUpdateRequest,
    db_path: DbPath,
) -> LocalTagListResponse:
    repository = LocalTagRepository(db_path)
    try:
        tags = repository.set_artist_tags(artist_id, request.tags)
        return local_tag_list_response(tags)
    finally:
        repository.close()


@router.get("/{artist_id}/artworks", response_model=ArtworkListResponse)
def list_artist_artworks(
    artist_id: str,
    db_path: DbPath,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ArtworkListResponse:
    artist_repository = ArtistRepository(db_path)
    artwork_repository = ArtworkRepository(db_path)
    try:
        if artist_repository.get_by_id(artist_id) is None:
            raise HTTPException(status_code=404, detail="artist not found")
        artworks = artwork_repository.list_by_artist(artist_id, limit=limit, offset=offset)
        return ArtworkListResponse(
            items=[
                artwork_summary_response(
                    artwork,
                    artwork_repository.get_file_counts(artwork.id),
                )
                for artwork in artworks
            ],
            total=artwork_repository.count_by_artist(artist_id),
        )
    finally:
        artist_repository.close()
        artwork_repository.close()
