from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.domain.entities import (
    ScheduledTask,
    ScheduledTaskConfig,
    ScheduledTaskFilter,
    ScheduledTaskTarget,
)
from backend.domain.types import (
    FailureReason,
    ScheduledTaskAction,
    ScheduledTaskArtistSelection,
    ScheduledTaskFilterType,
    ScheduledTaskStatus,
    ScheduledTaskTargetType,
)
from backend.schemas.failure_reasons import classify_failure_reason


class ScheduledTaskTargetRequest(BaseModel):
    type: ScheduledTaskTargetType
    artist_id: str | None = None
    artwork_id: str | None = None
    artist_ids: list[str] = Field(default_factory=list)
    artwork_ids: list[str] = Field(default_factory=list)
    artist_source: str = "artist_ids"
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
    download_options: dict[str, object] = Field(default_factory=dict)
    max_artists_per_run: int = Field(default=25, ge=1, le=500)
    artist_selection: ScheduledTaskArtistSelection = "oldest_checked_first"
    skip_unavailable_artists: bool = True

    @model_validator(mode="after")
    def validate_target_actions(self) -> ScheduledTaskConfigRequest:
        if self.target.type in {"single_artwork", "artworks"} and any(
            action != "download_artist" for action in self.actions
        ):
            raise ValueError("artwork target only supports download_artist")
        if (
            self.target.type == "artists"
            and self.target.artwork_ids
            and any(action != "download_artist" for action in self.actions)
        ):
            raise ValueError("artists target with artwork IDs only supports download_artist")
        return self


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
    failure_reason: FailureReason
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
    workflow_run_id: str | None
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
        failure_reason=classify_failure_reason(task.last_error_code, task.last_error_message),
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
            artwork_id=request.target.artwork_id,
            artist_ids=tuple(normalize_ids(request.target.artist_ids)),
            artwork_ids=tuple(normalize_ids(request.target.artwork_ids)),
            artist_source=normalize_artist_source(request.target.artist_source),
            tag=request.target.tag,
            tags=tuple(normalize_tags(request.target.tags)),
            days=request.target.days,
        ),
        filters=tuple(
            ScheduledTaskFilter(type=item.type, days=item.days) for item in request.filters
        ),
        actions=tuple(request.actions) or ("download_artist",),
        download_options=clean_download_options(request.download_options),
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
            "artwork_id": config.target.artwork_id,
            "artist_ids": list(config.target.artist_ids),
            "artwork_ids": list(config.target.artwork_ids),
            "artist_source": config.target.artist_source,
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


def normalize_ids(ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_id in ids:
        item_id = str(raw_id).strip()
        if not item_id or item_id in seen:
            continue
        normalized.append(item_id)
        seen.add(item_id)
    return normalized


def normalize_artist_source(value: object) -> str:
    return "artwork_ids" if value == "artwork_ids" else "artist_ids"


def clean_download_options(options: dict[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    full_download = options.get("full_download")
    if isinstance(full_download, bool):
        cleaned["full_download"] = full_download
    for key in ("max_artworks", "min_artwork_id", "max_artwork_id"):
        value = options.get(key)
        if value is None or value == "":
            continue
        cleaned[key] = value
    if options.get("only_new_artworks") is True:
        cleaned["only_new_artworks"] = True
    stop_if_artwork_count_above = options.get("stop_if_artwork_count_above")
    if stop_if_artwork_count_above is not None and stop_if_artwork_count_above != "":
        cleaned["stop_if_artwork_count_above"] = stop_if_artwork_count_above
    naming_rule = options.get("naming_rule")
    if isinstance(naming_rule, str) and naming_rule.strip():
        cleaned["naming_rule"] = naming_rule.strip()
    naming_tag_variants = options.get("naming_tag_variants")
    if isinstance(naming_tag_variants, list):
        cleaned_variants: list[dict[str, str]] = []
        for item in naming_tag_variants:
            if not isinstance(item, dict):
                continue
            tag = item.get("tag")
            variant_rule = item.get("naming_rule")
            if (
                isinstance(tag, str)
                and isinstance(variant_rule, str)
                and tag.strip()
                and variant_rule.strip()
            ):
                cleaned_variants.append({"tag": tag.strip(), "naming_rule": variant_rule.strip()})
        if cleaned_variants:
            cleaned["naming_tag_variants"] = cleaned_variants
    tag_variants = clean_tag_variants(options.get("tag_variants"))
    if not tag_variants:
        tag_variants = legacy_tag_variants(options)
    if tag_variants:
        cleaned["tag_variants"] = tag_variants
    return cleaned


def clean_tag_variants(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag")
        behavior = item.get("behavior")
        naming_rule = item.get("naming_rule")
        if not isinstance(tag, str) or not tag.strip():
            continue
        variant: dict[str, str] = {"tag": tag.strip()}
        if isinstance(behavior, str) and behavior in {"download", "skip", "retry_failed"}:
            variant["behavior"] = behavior
        if isinstance(naming_rule, str) and naming_rule.strip():
            variant["naming_rule"] = naming_rule.strip()
        if len(variant) > 1:
            cleaned.append(variant)
    return cleaned


def legacy_tag_variants(options: dict[str, object]) -> list[dict[str, str]]:
    naming_variants = options.get("naming_tag_variants")
    if not isinstance(naming_variants, list):
        return []
    behavior = legacy_action_to_behavior(options.get("tag_variant_action"))
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


def legacy_action_to_behavior(value: object) -> str:
    if value == "retry_failed_artist":
        return "retry_failed"
    if value == "sync_artist":
        return "skip"
    return "download"
