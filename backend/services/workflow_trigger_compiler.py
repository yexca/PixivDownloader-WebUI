from __future__ import annotations

from backend.domain.entities import (
    WorkflowTriggerConfig,
    WorkflowTriggerRuntime,
    WorkflowTriggerTarget,
)
from backend.domain.types import WorkflowTriggerAction
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest


def workflow_trigger_definition(
    task: WorkflowTriggerRuntime,
    config: WorkflowTriggerConfig,
    *,
    artist_ids: list[str] | None = None,
    artwork_ids: list[str] | None = None,
) -> AdvancedWorkflowDefinitionRequest:
    actions = tuple(config.actions) or ("download_artist",)
    nodes: list[dict[str, object]] = [
        {
            "id": "target",
            "type": "artist_target",
            "title": "Target artists",
                "config": workflow_trigger_target_config(
                config,
                artist_ids=artist_ids,
                artwork_ids=artwork_ids,
            ),
        }
    ]
    if any(
        action in {"sync_artist", "download_artist", "retry_failed_artist"}
        for action in actions
    ):
        nodes.append(
            {
                "id": "sync",
                "type": "sync_metadata",
                "title": "Sync metadata",
                "config": {
                    "mode": "full"
                    if config.download_options.get("full_download")
                    else "incremental"
                },
            }
        )
    if actions == ("sync_artist",):
        return AdvancedWorkflowDefinitionRequest.model_validate(
            {
                "name": task.name
                or default_workflow_trigger_name("sync_artist", task.target_artist_id, config),
                "nodes": nodes,
            }
        )

    download_options = dict(config.download_options)
    if "download_artist" in actions:
        nodes.extend(
            workflow_trigger_download_nodes(
                download_options,
                suffix="",
                collect_mode=workflow_trigger_download_collect_mode(download_options),
                title="Download files",
            )
        )
    if "retry_failed_artist" in actions:
        nodes.extend(
            workflow_trigger_download_nodes(
                download_options,
                suffix="_retry",
                collect_mode="failed_files",
                title="Retry failed files",
            )
        )
    return AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": task.name
            or default_workflow_trigger_name(actions[0], task.target_artist_id, config),
            "nodes": nodes,
        }
    )


def workflow_trigger_target_config(
    config: WorkflowTriggerConfig,
    *,
    artist_ids: list[str] | None = None,
    artwork_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "scope": config.target.type,
        "artist_ids": artist_ids if artist_ids is not None else list(config.target.artist_ids),
        "artwork_ids": artwork_ids if artwork_ids is not None else list(config.target.artwork_ids),
        "artist_id": config.target.artist_id,
        "artwork_id": config.target.artwork_id,
        "artist_source": config.target.artist_source,
        "tag": config.target.tag,
        "tags": list(config.target.tags),
        "days": config.target.days,
        "filters": [
            {"type": item.type, "days": item.days}
            for item in config.filters
        ],
        "artist_selection": config.artist_selection,
        "skip_unavailable_artists": config.skip_unavailable_artists,
        "max_artists": config.max_artists_per_run,
    }


def legacy_config(task: WorkflowTriggerRuntime) -> WorkflowTriggerConfig:
    return WorkflowTriggerConfig(
        target=WorkflowTriggerTarget(type="single_artist", artist_id=task.target_artist_id),
        actions=(task.action,),
    )


def workflow_trigger_downloads(config: WorkflowTriggerConfig) -> bool:
    return any(action in {"download_artist", "retry_failed_artist"} for action in config.actions)


def workflow_trigger_download_collect_mode(download_options: dict[str, object]) -> str:
    if download_options.get("full_download"):
        return "all_synced"
    if download_options.get("pending_only"):
        return "pending_files"
    return "new_since_last_download"


def workflow_trigger_download_nodes(
    download_options: dict[str, object],
    *,
    suffix: str,
    collect_mode: str,
    title: str,
) -> list[dict[str, object]]:
    return [
        {
            "id": f"collect{suffix}",
            "type": "collect_artworks",
            "title": "Collect artworks" if not suffix else "Collect failed files",
            "config": {
                "mode": collect_mode,
                "max_artworks": download_options.get("max_artworks"),
                "min_artwork_id": download_options.get("min_artwork_id"),
                "max_artwork_id": download_options.get("max_artwork_id"),
            },
        },
        {
            "id": f"filters{suffix}",
            "type": "filter_artworks",
            "title": "Filter artworks",
            "config": {
                "stop_above_limit": download_options.get("stop_if_artwork_count_above"),
            },
        },
        {
            "id": f"actions{suffix}",
            "type": "execute_actions",
            "title": title,
            "config": {
                "download": True,
                "execution_unit": "artist",
                "naming_rule": download_options.get("naming_rule"),
            },
        },
    ]


def default_workflow_trigger_name(
    action: WorkflowTriggerAction,
    artist_id: str,
    config: WorkflowTriggerConfig | None = None,
) -> str:
    labels = {
        "sync_artist": "Sync artist",
        "download_artist": "Download artist",
        "retry_failed_artist": "Retry failed artist",
    }
    if config is not None:
        target = config.target
        if target.type == "artists":
            if target.artist_source == "artwork_ids":
                return "Download artists from artworks"
            return "Download artists"
        if target.type == "artworks":
            return "Download artworks"
        if target.type == "single_artwork" and target.artwork_id:
            return f"Download artwork {target.artwork_id}"
        if target.type == "all_artists":
            return f"{labels[action]} all artists"
        if target.type == "artists_with_tag":
            tag_label = ", ".join(target.tags) if target.tags else target.tag or "tag"
            return f"{labels[action]} artists tagged {tag_label}"
        if target.type == "artists_not_checked":
            return f"{labels[action]} unchecked artists"
    return f"{labels[action]} {artist_id}"
