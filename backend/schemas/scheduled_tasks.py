from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from backend.domain.entities import (
    ScheduledTask,
    ScheduledTaskConfig,
    ScheduledTaskFilter,
    ScheduledTaskTarget,
)
from backend.domain.types import (
    ScheduledTaskAction,
    ScheduledTaskArtistSelection,
    ScheduledTaskFilterType,
    ScheduledTaskStatus,
    ScheduledTaskTargetType,
)


class ScheduledTaskTargetRequest(BaseModel):
    type: ScheduledTaskTargetType
    artist_id: str | None = None
    tag: str | None = None
    tags: list[str] = Field(default_factory=list)
    days: int | None = Field(default=None, ge=1)


class ScheduledTaskFilterRequest(BaseModel):
    type: ScheduledTaskFilterType
    days: int | None = Field(default=None, ge=1)


class ScheduledTaskConfigRequest(BaseModel):
    target: ScheduledTaskTargetRequest
    filters: list[ScheduledTaskFilterRequest] = Field(default_factory=list)
    actions: list[ScheduledTaskAction] = Field(default_factory=lambda: ["download_artist"])
    max_artists_per_run: int = Field(default=25, ge=1, le=500)
    artist_selection: ScheduledTaskArtistSelection = "oldest_checked_first"
    skip_unavailable_artists: bool = True


class ScheduledTaskCreateRequest(BaseModel):
    name: str = ""
    action: ScheduledTaskAction | None = None
    target_artist_id: str | None = Field(default=None, min_length=1)
    interval_days: int = Field(ge=1)
    enabled: bool = True
    run_after_startup: bool = True
    config: ScheduledTaskConfigRequest | None = None

    @field_validator("target_artist_id", mode="before")
    @classmethod
    def empty_target_artist_id_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ScheduledTaskUpdateRequest(BaseModel):
    name: str | None = None
    action: ScheduledTaskAction | None = None
    status: ScheduledTaskStatus | None = None
    target_artist_id: str | None = Field(default=None, min_length=1)
    interval_days: int | None = Field(default=None, ge=1)
    run_after_startup: bool | None = None
    config: ScheduledTaskConfigRequest | None = None

    @field_validator("target_artist_id", mode="before")
    @classmethod
    def empty_target_artist_id_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ScheduledTaskResponse(BaseModel):
    id: int
    name: str
    action: str
    status: str
    target_artist_id: str
    interval_days: int
    run_after_startup: bool
    last_run_at: str | None
    last_success_at: str | None
    next_run_at: str | None
    last_job_id: str | None
    last_error_code: str | None
    last_error_message: str | None
    config: dict[str, object]
    last_run_summary: dict[str, object] | None
    created_at: str | None
    updated_at: str | None


class ScheduledTaskListResponse(BaseModel):
    items: list[ScheduledTaskResponse]
    total: int


class ScheduledTaskRunResponse(BaseModel):
    task: ScheduledTaskResponse
    job_id: str | None
    job_ids: list[str]
    created: bool
    skipped: bool


def scheduled_task_response(task: ScheduledTask) -> ScheduledTaskResponse:
    if task.id is None:
        raise ValueError("scheduled task id is required")
    return ScheduledTaskResponse(
        id=task.id,
        name=task.name,
        action=task.action,
        status=task.status,
        target_artist_id=task.target_artist_id,
        interval_days=task.interval_days,
        run_after_startup=task.run_after_startup,
        last_run_at=task.last_run_at,
        last_success_at=task.last_success_at,
        next_run_at=task.next_run_at,
        last_job_id=task.last_job_id,
        last_error_code=task.last_error_code,
        last_error_message=task.last_error_message,
        config=scheduled_task_config_to_dict(task.config),
        last_run_summary=task.last_run_summary,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def scheduled_task_config_from_request(
    request: ScheduledTaskConfigRequest,
) -> ScheduledTaskConfig:
    return ScheduledTaskConfig(
        target=ScheduledTaskTarget(
            type=request.target.type,
            artist_id=request.target.artist_id,
            tag=request.target.tag,
            tags=tuple(normalize_tags(request.target.tags)),
            days=request.target.days,
        ),
        filters=tuple(
            ScheduledTaskFilter(type=item.type, days=item.days) for item in request.filters
        ),
        actions=tuple(request.actions) or ("download_artist",),
        max_artists_per_run=request.max_artists_per_run,
        artist_selection=request.artist_selection,
        skip_unavailable_artists=request.skip_unavailable_artists,
    )


def scheduled_task_config_to_dict(config: ScheduledTaskConfig | None) -> dict[str, object]:
    if config is None:
        return {}
    return {
        "target": {
            "type": config.target.type,
            "artist_id": config.target.artist_id,
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
        "max_artists_per_run": config.max_artists_per_run,
        "artist_selection": config.artist_selection,
        "skip_unavailable_artists": config.skip_unavailable_artists,
    }


def normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tag in tags:
        tag = raw_tag.strip()
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        normalized.append(tag)
        seen.add(key)
    return normalized
