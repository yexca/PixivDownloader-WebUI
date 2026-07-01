from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from backend.domain.entities import Job
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import WorkflowNodeRun
from backend.services.job_service import JobService, WorkflowJobLink
from backend.services.workflow_nodes.base import (
    WorkflowNodeContext,
    WorkflowNodeExecutorBase,
    WorkflowNodeResult,
)
from backend.services.workflow_nodes.utils import positive_int, string_list


class ArtistTargetNodeExecutor(WorkflowNodeExecutorBase):
    node_type = "artist_target"

    def execute(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        artist_ids = tuple(resolve_artist_ids(config, context.db_path))
        artwork_ids = tuple(resolve_artwork_ids(config))
        max_artists = positive_int(config.get("max_artists")) or max(
            1,
            len(artist_ids) + len(artwork_ids),
        )
        output = {
            "target_scope": str(config.get("scope") or "selected"),
            "max_artists": max_artists,
            "input_artist_ids": list(artist_ids),
            "input_artwork_ids": list(artwork_ids),
        }
        if not artist_ids and not artwork_ids:
            return WorkflowNodeResult(output={**output, "artist_ids": [], "resolved_count": 0})

        service = JobService(
            context.db_path,
            settings_json_path=context.settings_json_path,
        )
        try:
            job = service.create_resolve_workflow_targets_job(
                artist_ids=artist_ids,
                artwork_ids=artwork_ids,
                max_targets_per_run=max_artists,
                options={"target_scope": output["target_scope"]},
                workflow_link=WorkflowJobLink(
                    run_id=node_run.workflow_run_id,
                    item_id=context.workflow_item_id,
                    source="advanced_workflow",
                ),
            )
        finally:
            service.close()

        job_ids = [] if job is None else [job.id]
        return WorkflowNodeResult(
            output={**output, "resolver_job_ids": job_ids},
            job_ids=job_ids,
        )

    def complete_from_jobs(
        self,
        node_run: WorkflowNodeRun,
        jobs: list[Job],
        context: WorkflowNodeContext,
    ) -> WorkflowNodeResult:
        payload = latest_resolver_payload(context.db_path, node_run.job_ids)
        artist_ids = string_list(payload.get("resolved_artist_ids") or payload.get("artist_ids"))
        resolved_from_artworks = payload.get("resolved_from_artworks")
        if not isinstance(resolved_from_artworks, list):
            resolved_from_artworks = []
        return WorkflowNodeResult(
            output={
                **node_run.output,
                "artist_ids": artist_ids,
                "resolved_from_artworks": resolved_from_artworks,
                "resolved_count": len(artist_ids),
                "skipped_count": sum(job.skipped_files for job in jobs),
                "completed_jobs": [job.id for job in jobs],
            }
        )


def latest_resolver_payload(db_path: object, job_ids: list[str]) -> dict[str, object]:
    if not job_ids:
        return {}
    repository = JobRepository(db_path)
    try:
        for job_id in reversed(job_ids):
            for event in reversed(repository.list_events(job_id, limit=100)):
                payload = event.payload
                if not isinstance(payload, dict):
                    continue
                if "resolved_artist_ids" in payload or "artist_ids" in payload:
                    return payload
    finally:
        repository.close()
    return {}


def resolve_artist_ids(config: dict[str, object], db_path: object) -> list[str]:
    explicit_ids = string_list(config.get("artist_ids"))
    scope = str(config.get("scope") or "selected")
    single_artist = config.get("artist_id")
    if isinstance(single_artist, str) and single_artist.strip():
        explicit_ids = [single_artist.strip(), *explicit_ids]
    if explicit_ids and scope in {"selected", "artists", "single_artist"}:
        return explicit_ids[: max_targets(config, len(explicit_ids))]
    if scope == "artists":
        return explicit_ids[: max_targets(config, len(explicit_ids))]
    if scope not in {"all_artists", "artists_with_tag", "artists_not_checked"}:
        return explicit_ids[: max_targets(config, len(explicit_ids))]

    repository = ArtistRepository(db_path)
    try:
        artists = repository.list(limit=1000)
    finally:
        repository.close()
    if scope == "artists_with_tag":
        tags = string_list(config.get("tags"))
        tag = config.get("tag")
        if isinstance(tag, str) and tag.strip():
            tags = [*tags, tag.strip()]
        if tags:
            repository = ArtistRepository(db_path)
            try:
                artists = []
                seen: set[str] = set()
                for item in tags:
                    for artist in repository.list(limit=1000, local_tag=item):
                        if artist.id in seen:
                            continue
                        artists.append(artist)
                        seen.add(artist.id)
            finally:
                repository.close()
    if scope == "artists_not_checked":
        days = positive_int(config.get("days")) or 30
        artists = [artist for artist in artists if artist_is_stale(artist, days)]
    filters = config.get("filters")
    if isinstance(filters, list):
        for item in filters:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "last_checked_before_days":
                days = positive_int(item.get("days")) or 30
                artists = [artist for artist in artists if artist_is_stale(artist, days)]
    scheduled_config = scheduled_config_for_selection(config)
    return [
        artist.id
        for artist in select_artists(artists, scheduled_config)[: scheduled_config["max_artists"]]
    ]


def resolve_artwork_ids(config: dict[str, object]) -> list[str]:
    artwork_ids = string_list(config.get("artwork_ids"))
    artwork_id = config.get("artwork_id")
    if isinstance(artwork_id, str) and artwork_id.strip():
        return [artwork_id.strip(), *artwork_ids]
    return artwork_ids


def max_targets(config: dict[str, object], default: int) -> int:
    return positive_int(config.get("max_artists")) or max(1, default)


def scheduled_config_for_selection(config: dict[str, object]):
    selection = config.get("artist_selection")
    if selection not in {"oldest_checked_first", "newest_checked_first", "random"}:
        selection = "oldest_checked_first"
    return {
        "max_artists": max_targets(config, 25),
        "artist_selection": selection,
        "skip_unavailable_artists": bool(config.get("skip_unavailable_artists", True)),
    }


def select_artists(artists, config: dict[str, object]):
    if config["skip_unavailable_artists"]:
        artists = [artist for artist in artists if artist.account_status != "unavailable"]
    if config["artist_selection"] == "random":
        return random.sample(artists, k=len(artists))
    reverse = config["artist_selection"] == "newest_checked_first"
    return sorted(artists, key=artist_checked_sort_key, reverse=reverse)


def artist_is_stale(artist, days: int) -> bool:
    if artist.last_checked_at is None:
        return True
    return parse_time(artist.last_checked_at) <= datetime.now(UTC) - timedelta(days=days)


def artist_checked_sort_key(artist) -> datetime:
    if artist.last_checked_at is None:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return parse_time(artist.last_checked_at)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
