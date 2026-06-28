from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.domain.entities import ScheduledTaskConfig, ScheduledTaskTarget
from backend.domain.types import ScheduledTaskAction
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.tag_repository import LocalTagRepository
from backend.repositories.workflow_run_repository import WorkflowRun
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
from backend.services.avatar_cache_service import AvatarCacheService
from backend.services.settings_service import AppSettingsService
from backend.services.workflow_run_service import WorkflowRunService

router = APIRouter(prefix="/api/artists", tags=["artists"])


@router.get("", response_model=ArtistListResponse)
def list_artists(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    q: str | None = None,
    local_tag: str | None = None,
    file_state: str | None = None,
    tag_state: str | None = None,
    account_status: str | None = None,
    update_state: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: str = "updated_desc",
) -> ArtistListResponse:
    repository = ArtistRepository(db_path)
    tag_repository = LocalTagRepository(db_path)
    settings_service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        stale_days = settings_service.load().library_stale_check_days
        artists = repository.list(
            limit=limit,
            offset=offset,
            query=q,
            local_tag=local_tag,
            file_state=file_state,
            tag_state=tag_state,
            account_status=account_status,
            update_state=update_state,
            stale_days=stale_days,
            sort=sort,
        )
        return ArtistListResponse(
            items=[
                artist_summary_response(
                    artist,
                    repository.get_counts(artist.id),
                    tag_repository.list_for_artist(artist.id),
                    stale_days=stale_days,
                )
                for artist in artists
            ],
            total=repository.count(
                query=q,
                local_tag=local_tag,
                file_state=file_state,
                tag_state=tag_state,
                account_status=account_status,
                update_state=update_state,
                stale_days=stale_days,
            ),
        )
    finally:
        repository.close()
        tag_repository.close()
        settings_service.close()


@router.post("", response_model=DownloadCreateResponse)
def create_artist(
    request: ArtistCreateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    service = WorkflowRunService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_download_shortcut(
            source="library_shortcut",
            title="Sync artist",
            draft_id=f"library-sync:{request.user_id}",
            config=artist_action_config(request.user_id, "sync_artist"),
            user_id=request.user_id,
            artwork_id=None,
            sync_only=True,
        )
    finally:
        service.close()
    queue.wake()
    return download_response_from_run(db_path, run)


@router.get("/-/local-tags", response_model=LocalTagListResponse)
def list_local_tags(db_path: DbPath) -> LocalTagListResponse:
    repository = LocalTagRepository(db_path)
    try:
        return local_tag_list_response(repository.list())
    finally:
        repository.close()


@router.get("/{artist_id}", response_model=ArtistDetailResponse)
def get_artist(
    artist_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> ArtistDetailResponse:
    repository = ArtistRepository(db_path)
    tag_repository = LocalTagRepository(db_path)
    name_history_repository = ArtistNameHistoryRepository(db_path)
    settings_service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        artist = repository.get_by_id(artist_id)
        if artist is None:
            raise HTTPException(status_code=404, detail="artist not found")
        stale_days = settings_service.load().library_stale_check_days
        return artist_detail_response(
            artist,
            repository.get_counts(artist.id),
            tag_repository.list_for_artist(artist.id),
            name_history_repository.list_for_artist(artist.id),
            stale_days=stale_days,
        )
    finally:
        repository.close()
        tag_repository.close()
        name_history_repository.close()
        settings_service.close()


@router.get("/{artist_id}/avatar", include_in_schema=False)
def get_artist_avatar(artist_id: str, db_path: DbPath) -> FileResponse:
    repository = ArtistRepository(db_path)
    try:
        if repository.get_by_id(artist_id) is None:
            raise HTTPException(status_code=404, detail="artist not found")
        cached_avatar = AvatarCacheService().get_cached_avatar(artist_id)
        if cached_avatar is None:
            raise HTTPException(status_code=404, detail="artist avatar not cached")
        return FileResponse(
            cached_avatar.path,
            media_type=cached_avatar.media_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    finally:
        repository.close()


@router.delete("/{artist_id}", status_code=204)
def delete_artist(artist_id: str, db_path: DbPath) -> None:
    repository = ArtistRepository(db_path)
    try:
        if not repository.delete(artist_id):
            raise HTTPException(status_code=404, detail="artist not found")
        AvatarCacheService().remove_artist_avatar(artist_id)
    finally:
        repository.close()


@router.post("/{artist_id}/sync", response_model=DownloadCreateResponse)
def sync_artist(
    artist_id: str,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    service = WorkflowRunService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_download_shortcut(
            source="library_shortcut",
            title="Sync artist",
            draft_id=f"library-sync:{artist_id}",
            config=artist_action_config(artist_id, "sync_artist"),
            user_id=artist_id,
            artwork_id=None,
            sync_only=True,
        )
    finally:
        service.close()
    queue.wake()
    return download_response_from_run(db_path, run)


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

    service = WorkflowRunService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_download_shortcut(
            source="library_shortcut",
            title="Retry failed artist",
            draft_id=f"library-retry-failed:{artist_id}",
            config=artist_action_config(artist_id, "retry_failed_artist"),
            user_id=artist_id,
            artwork_id=None,
            retry_failed_artist=True,
        )
    finally:
        service.close()
    queue.wake()
    return download_response_from_run(db_path, run)


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


def artist_action_config(artist_id: str, action: ScheduledTaskAction) -> ScheduledTaskConfig:
    return ScheduledTaskConfig(
        target=ScheduledTaskTarget(type="single_artist", artist_id=artist_id),
        actions=(action,),
        max_artists_per_run=1,
    )


def download_response_from_run(
    db_path: Path | str | None,
    run: WorkflowRun,
) -> DownloadCreateResponse:
    job_id = run.items[0].job_ids[0]
    repository = JobRepository(db_path)
    try:
        job = repository.get_by_id(job_id)
    finally:
        repository.close()
    return DownloadCreateResponse(job_id=job_id, status=job.status if job else "queued")
