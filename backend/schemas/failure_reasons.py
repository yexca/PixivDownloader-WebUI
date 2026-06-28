from __future__ import annotations

from backend.domain.types import FailureReason


def classify_failure_reason(*values: object) -> FailureReason:
    text = " ".join(str(value) for value in values if value).casefold()
    if not text:
        return "unknown"
    if any(token in text for token in ("auth", "token", "login", "permission", "401", "forbidden")):
        return "auth"
    if any(token in text for token in ("disk", "space", "storage", "insufficient_disk_space")):
        return "disk"
    if any(
        token in text
        for token in ("network", "timeout", "connection", "http", "rate limit", "429")
    ):
        return "network"
    if "cancel" in text:
        return "cancelled"
    if any(
        token in text
        for token in ("target", "artist", "artwork", "unavailable", "not found", "404")
    ):
        return "target"
    if any(token in text for token in ("skip", "rule", "filter", "validation")):
        return "rule"
    return "unknown"
