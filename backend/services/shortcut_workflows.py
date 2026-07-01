from __future__ import annotations

from pathlib import Path

from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import WorkflowRun, WorkflowRunRepository
from backend.schemas.downloads import DownloadCreateRequest, download_request_options
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner
from backend.services.settings_service import AppSettingsService
from backend.services.storage_service import check_free_space


def run_artist_sync_shortcut(
    *,
    artist_id: str,
    db_path: Path | str | None = None,
    settings_json_path: Path | str | None = None,
    source: str = "library_shortcut",
) -> WorkflowRun:
    return run_shortcut_definition(
        sync_artist_definition(artist_id),
        db_path=db_path,
        settings_json_path=settings_json_path,
        source=source,
    )


def run_artist_retry_failed_shortcut(
    *,
    artist_id: str,
    db_path: Path | str | None = None,
    settings_json_path: Path | str | None = None,
    source: str = "library_shortcut",
) -> WorkflowRun:
    ensure_download_space(db_path=db_path, settings_json_path=settings_json_path)
    return run_shortcut_definition(
        download_artist_definition(
            name=f"Retry failed artist {artist_id}",
            artist_ids=[artist_id],
            artwork_ids=[],
            options={},
            collect_mode="failed_files",
        ),
        db_path=db_path,
        settings_json_path=settings_json_path,
        source=source,
    )


def run_download_shortcut(
    request: DownloadCreateRequest,
    *,
    db_path: Path | str | None = None,
    settings_json_path: Path | str | None = None,
    source: str = "download_api",
) -> WorkflowRun:
    ensure_download_space(db_path=db_path, settings_json_path=settings_json_path)
    name = download_shortcut_name(request)
    return run_shortcut_definition(
        download_artist_definition(
            name=name,
            artist_ids=[] if request.user_id is None else [request.user_id],
            artwork_ids=[] if request.artwork_id is None else [request.artwork_id],
            options=download_request_options(request),
            collect_mode=download_collect_mode(request),
        ),
        db_path=db_path,
        settings_json_path=settings_json_path,
        source=source,
    )


def run_shortcut_definition(
    definition: AdvancedWorkflowDefinitionRequest,
    *,
    db_path: Path | str | None,
    settings_json_path: Path | str | None,
    source: str,
) -> WorkflowRun:
    runner = AdvancedWorkflowRunner(db_path, settings_json_path=settings_json_path)
    try:
        return runner.create_run(definition, source=source)
    finally:
        runner.close()


def sync_artist_definition(artist_id: str) -> AdvancedWorkflowDefinitionRequest:
    return AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": f"Sync artist {artist_id}",
            "nodes": [
                target_node(artist_ids=[artist_id], artwork_ids=[], max_artists=1),
                {
                    "id": "sync",
                    "type": "sync_metadata",
                    "title": "Sync metadata",
                    "config": {"mode": "incremental"},
                },
            ],
        }
    )


def download_artist_definition(
    *,
    name: str,
    artist_ids: list[str],
    artwork_ids: list[str],
    options: dict[str, object],
    collect_mode: str,
) -> AdvancedWorkflowDefinitionRequest:
    return AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": name,
            "nodes": [
                target_node(
                    artist_ids=artist_ids,
                    artwork_ids=artwork_ids,
                    max_artists=max(1, len(artist_ids) + len(artwork_ids)),
                ),
                {
                    "id": "sync",
                    "type": "sync_metadata",
                    "title": "Sync metadata",
                    "config": {"mode": "full" if options.get("full_download") else "incremental"},
                },
                {
                    "id": "collect",
                    "type": "collect_artworks",
                    "title": "Collect artworks",
                    "config": {
                        "mode": collect_mode,
                        "max_artworks": options.get("max_artworks"),
                        "min_artwork_id": options.get("min_artwork_id"),
                        "max_artwork_id": options.get("max_artwork_id"),
                    },
                },
                {
                    "id": "filters",
                    "type": "filter_artworks",
                    "title": "Filter artworks",
                    "config": {
                        "stop_above_limit": options.get("stop_if_artwork_count_above"),
                    },
                },
                {
                    "id": "actions",
                    "type": "execute_actions",
                    "title": "Download files",
                    "config": {
                        "download": True,
                        "execution_unit": "artist",
                        "naming_rule": options.get("naming_rule"),
                    },
                },
            ],
        }
    )


def target_node(
    *,
    artist_ids: list[str],
    artwork_ids: list[str],
    max_artists: int,
) -> dict[str, object]:
    return {
        "id": "target",
        "type": "artist_target",
        "title": "Target artists",
        "config": {
            "scope": "selected",
            "artist_ids": artist_ids,
            "artwork_ids": artwork_ids,
            "max_artists": max_artists,
        },
    }


def download_collect_mode(request: DownloadCreateRequest) -> str:
    if request.retry_failed:
        return "failed_files"
    if request.full_download:
        return "all_synced"
    if request.pending_only:
        return "pending_files"
    return "new_since_last_download"


def download_shortcut_name(request: DownloadCreateRequest) -> str:
    action = "Retry failed" if request.retry_failed else "Download"
    if request.artwork_id:
        target = f"artwork {request.artwork_id}"
        if request.full_download:
            return f"Full download {target}"
        if request.pending_only:
            return f"Download pending files for {target}"
        return f"{action} {target}"
    target = f"artist {request.user_id}" if request.user_id else "artist"
    if request.full_download:
        return f"Full download {target}"
    if request.pending_only:
        return f"Download pending files for {target}"
    return f"{action} {target}"


def first_run_job_id(run: WorkflowRun, *, db_path: Path | str | None = None) -> str | None:
    refreshed = refresh_run(run, db_path=db_path)
    for node in refreshed.node_runs:
        if node.job_ids:
            return node.job_ids[0]
    return None


def refresh_run(run: WorkflowRun, *, db_path: Path | str | None = None) -> WorkflowRun:
    repository = WorkflowRunRepository(db_path)
    try:
        return repository.get_run(run.id) or run
    finally:
        repository.close()


def job_status(db_path: Path | str | None, job_id: str | None) -> str:
    if job_id is None:
        return "completed"
    repository = JobRepository(db_path)
    try:
        job = repository.get_by_id(job_id)
    finally:
        repository.close()
    return job.status if job is not None else "queued"


def ensure_download_space(
    *,
    db_path: Path | str | None = None,
    settings_json_path: Path | str | None = None,
) -> None:
    settings_service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        settings = settings_service.load()
    finally:
        settings_service.close()
    check_free_space(settings.download_path, settings.min_free_space_gb)
