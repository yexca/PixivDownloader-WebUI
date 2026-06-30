from __future__ import annotations


def dict_option(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def action_list(value: object) -> list[str]:
    valid_actions = {"download_artist", "sync_artist", "retry_failed_artist"}
    actions = [action for action in string_list(value) if action in valid_actions]
    return actions or ["download_artist"]


def string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
