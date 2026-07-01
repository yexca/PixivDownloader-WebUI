from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import (
    ScheduledTask,
    ScheduledTaskConfig,
    ScheduledTaskFilter,
    ScheduledTaskTarget,
)
from backend.repositories._time import utc_now


class ScheduledTaskRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def create(self, task: ScheduledTask) -> ScheduledTask:
        now = utc_now()
        created = replace(task, created_at=task.created_at or now, updated_at=now)
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO scheduled_tasks(
                        name,
                        action,
                        status,
                        target_artist_id,
                        interval_days,
                        run_after_startup,
                        last_run_at,
                        last_success_at,
                        next_run_at,
                        last_job_id,
                        last_error_code,
                        last_error_message,
                        config_json,
                        last_run_summary_json,
                        created_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    scheduled_task_values(created, include_id=False),
                )
        except sqlite3.Error as exc:
            raise DatabaseError("failed to create scheduled task") from exc
        return self.get_by_id(int(cursor.lastrowid)) or created

    def update(self, task: ScheduledTask) -> None:
        if task.id is None:
            raise DatabaseError("scheduled task id is required for update")
        updated = replace(task, updated_at=utc_now())
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE scheduled_tasks
                    SET name = ?,
                        action = ?,
                        status = ?,
                        target_artist_id = ?,
                        interval_days = ?,
                        run_after_startup = ?,
                        last_run_at = ?,
                        last_success_at = ?,
                        next_run_at = ?,
                        last_job_id = ?,
                        last_error_code = ?,
                        last_error_message = ?,
                        config_json = ?,
                        last_run_summary_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    scheduled_task_values(updated, include_id=True, include_created_at=False),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update scheduled task {task.id}") from exc

    def get_by_id(self, task_id: int) -> ScheduledTask | None:
        try:
            row = self.conn.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch scheduled task {task_id}") from exc
        return scheduled_task_from_row(row) if row is not None else None

    def list(self) -> list[ScheduledTask]:
        try:
            rows = self.conn.execute(
                "SELECT * FROM scheduled_tasks ORDER BY updated_at DESC"
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list scheduled tasks") from exc
        return [scheduled_task_from_row(row) for row in rows]

    def due(self, now: str) -> list[ScheduledTask]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM scheduled_tasks
                WHERE status = 'active'
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at, id
                """,
                (now,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list due scheduled tasks") from exc
        return [scheduled_task_from_row(row) for row in rows]

    def count_by_status(self, status: str) -> int:
        try:
            row = self.conn.execute(
                "SELECT COUNT(*) AS count FROM scheduled_tasks WHERE status = ?",
                (status,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to count {status} scheduled tasks") from exc
        return int(row["count"] if row is not None else 0)

    def list_inactive(self, *, limit: int) -> list[ScheduledTask]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM scheduled_tasks
                WHERE status = 'inactive'
                ORDER BY created_at, id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list inactive scheduled tasks") from exc
        return [scheduled_task_from_row(row) for row in rows]

    def delete(self, task_id: int) -> bool:
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "DELETE FROM scheduled_tasks WHERE id = ?",
                    (task_id,),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to delete scheduled task {task_id}") from exc
        return cursor.rowcount > 0

    def close(self) -> None:
        self.conn.close()


def scheduled_task_values(
    task: ScheduledTask,
    *,
    include_id: bool,
    include_created_at: bool = True,
) -> tuple[object, ...]:
    values: list[object] = [
        task.name,
        task.action,
        task.status,
        task.target_artist_id,
        task.interval_days,
        int(task.run_after_startup),
        task.last_run_at,
        task.last_success_at,
        task.next_run_at,
        task.last_job_id,
        task.last_error_code,
        task.last_error_message,
        task_config_json(task),
        json.dumps(task.last_run_summary) if task.last_run_summary is not None else None,
    ]
    if include_created_at:
        values.append(task.created_at)
    values.append(task.updated_at)
    if include_id:
        values.append(task.id)
    return tuple(values)


def scheduled_task_from_row(row: sqlite3.Row) -> ScheduledTask:
    return ScheduledTask(
        id=int(row["id"]),
        name=str(row["name"]),
        action=row["action"],
        status=row["status"],
        target_artist_id=str(row["target_artist_id"]),
        interval_days=int(row["interval_days"]),
        run_after_startup=bool(row["run_after_startup"]),
        last_run_at=str(row["last_run_at"]) if row["last_run_at"] else None,
        last_success_at=str(row["last_success_at"]) if row["last_success_at"] else None,
        next_run_at=str(row["next_run_at"]) if row["next_run_at"] else None,
        last_job_id=str(row["last_job_id"]) if row["last_job_id"] else None,
        last_error_code=str(row["last_error_code"]) if row["last_error_code"] else None,
        last_error_message=str(row["last_error_message"]) if row["last_error_message"] else None,
        config=task_config_from_row(row),
        last_run_summary=json.loads(row["last_run_summary_json"])
        if row["last_run_summary_json"]
        else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def task_config_json(task: ScheduledTask) -> str:
    config = task.config or legacy_task_config(task)
    return json.dumps(scheduled_task_config_to_dict(config), ensure_ascii=False)


def task_config_from_row(row: sqlite3.Row) -> ScheduledTaskConfig:
    try:
        config_json = row["config_json"]
    except IndexError:
        config_json = None
    if config_json:
        return scheduled_task_config_from_dict(json.loads(config_json))
    return legacy_task_config(
        ScheduledTask(
            id=int(row["id"]),
            name=str(row["name"]),
            action=row["action"],
            status=row["status"],
            target_artist_id=str(row["target_artist_id"]),
            interval_days=int(row["interval_days"]),
        )
    )


def legacy_task_config(task: ScheduledTask) -> ScheduledTaskConfig:
    return ScheduledTaskConfig(
        target=ScheduledTaskTarget(type="single_artist", artist_id=task.target_artist_id),
        actions=(task.action,),
    )


def scheduled_task_config_to_dict(config: ScheduledTaskConfig) -> dict[str, object]:
    return {
        "target": {
            "type": config.target.type,
            "artist_id": config.target.artist_id,
            "artwork_id": config.target.artwork_id,
            "tag": config.target.tag,
            "tags": list(config.target.tags),
            "days": config.target.days,
        },
        "filters": [
            {
                "type": item.type,
                "days": item.days,
            }
            for item in config.filters
        ],
        "actions": list(config.actions),
        "download_options": dict(config.download_options),
        "max_artists_per_run": config.max_artists_per_run,
        "artist_selection": config.artist_selection,
        "skip_unavailable_artists": config.skip_unavailable_artists,
    }


def scheduled_task_config_from_dict(data: dict[str, object]) -> ScheduledTaskConfig:
    target_data = data.get("target", {})
    if not isinstance(target_data, dict):
        target_data = {}
    filter_values = data.get("filters", [])
    filters: list[ScheduledTaskFilter] = []
    if isinstance(filter_values, list):
        for value in filter_values:
            if not isinstance(value, dict):
                continue
            filter_type = value.get("type")
            if filter_type not in {"last_checked_before_days", "has_failed_files"}:
                continue
            filters.append(
                ScheduledTaskFilter(
                    type=filter_type,
                    days=optional_int(value.get("days")),
                )
            )
    action_values = data.get("actions", ["download_artist"])
    actions = tuple(
        action
        for action in action_values
        if action in {"sync_artist", "download_artist", "retry_failed_artist"}
    )
    if not actions:
        actions = ("download_artist",)
    artist_selection = data.get("artist_selection", "oldest_checked_first")
    if artist_selection not in {
        "oldest_checked_first",
        "newest_checked_first",
        "random",
    }:
        artist_selection = "oldest_checked_first"
    target_type = target_data.get("type")
    if target_type not in {
        "artists",
        "artworks",
        "single_artist",
        "single_artwork",
        "all_artists",
        "artists_with_tag",
        "artists_not_checked",
    }:
        target_type = "single_artist"
    tag = optional_str(target_data.get("tag"))
    tags = tuple(normalize_tags(target_data.get("tags"), fallback=tag))
    artist_source = target_data.get("artist_source")
    if artist_source not in {"artist_ids", "artwork_ids"}:
        artist_source = "artist_ids"
    return ScheduledTaskConfig(
        target=ScheduledTaskTarget(
            type=target_type,
            artist_id=optional_str(target_data.get("artist_id")),
            artwork_id=optional_str(target_data.get("artwork_id")),
            artist_ids=tuple(normalize_ids(target_data.get("artist_ids"))),
            artwork_ids=tuple(normalize_ids(target_data.get("artwork_ids"))),
            artist_source=artist_source,
            tag=tag,
            tags=tags,
            days=optional_int(target_data.get("days")),
        ),
        filters=tuple(filters),
        actions=actions,
        download_options=clean_download_options(data.get("download_options")),
        max_artists_per_run=max(1, optional_int(data.get("max_artists_per_run")) or 25),
        artist_selection=artist_selection,
        skip_unavailable_artists=bool(data.get("skip_unavailable_artists", True)),
    )


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_id in value:
        item_id = str(raw_id).strip()
        if not item_id or item_id in seen:
            continue
        normalized.append(item_id)
        seen.add(item_id)
    return normalized


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def clean_download_options(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, object] = {}
    full_download = value.get("full_download")
    if isinstance(full_download, bool):
        cleaned["full_download"] = full_download
    for key in ("max_artworks", "min_artwork_id", "max_artwork_id", "tag_variant_action"):
        item = value.get(key)
        if item is None or item == "":
            continue
        cleaned[key] = item
    if value.get("only_new_artworks") is True:
        cleaned["only_new_artworks"] = True
    stop_if_artwork_count_above = value.get("stop_if_artwork_count_above")
    if stop_if_artwork_count_above is not None and stop_if_artwork_count_above != "":
        cleaned["stop_if_artwork_count_above"] = stop_if_artwork_count_above
    naming_rule = value.get("naming_rule")
    if isinstance(naming_rule, str) and naming_rule.strip():
        cleaned["naming_rule"] = naming_rule.strip()
    naming_tag_variants = value.get("naming_tag_variants")
    if isinstance(naming_tag_variants, list):
        cleaned["naming_tag_variants"] = naming_tag_variants
    tag_variants = value.get("tag_variants")
    if isinstance(tag_variants, list):
        cleaned["tag_variants"] = tag_variants
    elif isinstance(naming_tag_variants, list):
        cleaned["tag_variants"] = legacy_tag_variants(
            naming_tag_variants,
            value.get("tag_variant_action"),
        )
    return cleaned


def legacy_tag_variants(
    naming_variants: list[object],
    action: object,
) -> list[dict[str, str]]:
    behavior = legacy_action_to_behavior(action)
    result: list[dict[str, str]] = []
    for item in naming_variants:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag")
        naming_rule = item.get("naming_rule")
        if not isinstance(tag, str) or not tag.strip():
            continue
        variant = {"tag": tag.strip(), "behavior": behavior}
        if isinstance(naming_rule, str) and naming_rule.strip():
            variant["naming_rule"] = naming_rule.strip()
        result.append(variant)
    return result


def legacy_action_to_behavior(action: object) -> str:
    if action == "retry_failed_artist":
        return "retry_failed"
    if action == "sync_artist":
        return "skip"
    return "download"


def normalize_tags(value: object, *, fallback: str | None = None) -> list[str]:
    values: list[object] = []
    if isinstance(value, list):
        values.extend(value)
    if fallback:
        values.append(fallback)
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in values:
        tag = optional_str(raw_tag)
        if tag is None:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        tags.append(tag)
        seen.add(key)
    return tags
