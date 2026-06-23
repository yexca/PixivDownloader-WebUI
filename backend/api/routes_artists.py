from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.api.dependencies import DbPath
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.schemas.artists import (
    ArtistDetailResponse,
    ArtistListResponse,
    ArtworkListResponse,
    artist_detail_response,
    artist_summary_response,
    artwork_summary_response,
)

router = APIRouter(prefix="/api/artists", tags=["artists"])


@router.get("", response_model=ArtistListResponse)
def list_artists(
    db_path: DbPath,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: str = "updated_desc",
) -> ArtistListResponse:
    repository = ArtistRepository(db_path)
    try:
        artists = repository.list(limit=limit, offset=offset, query=q)
        if sort == "name_asc":
            artists = sorted(artists, key=lambda artist: artist.name.lower())
        if sort == "id_asc":
            artists = sorted(artists, key=lambda artist: artist.id)
        return ArtistListResponse(
            items=[
                artist_summary_response(artist, repository.get_counts(artist.id))
                for artist in artists
            ],
            total=repository.count(query=q),
        )
    finally:
        repository.close()


@router.get("/{artist_id}", response_model=ArtistDetailResponse)
def get_artist(artist_id: str, db_path: DbPath) -> ArtistDetailResponse:
    repository = ArtistRepository(db_path)
    try:
        artist = repository.get_by_id(artist_id)
        if artist is None:
            raise HTTPException(status_code=404, detail="artist not found")
        return artist_detail_response(artist, repository.get_counts(artist.id))
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
