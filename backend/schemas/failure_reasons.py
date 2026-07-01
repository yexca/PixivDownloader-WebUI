from __future__ import annotations

from pydantic import BaseModel

from backend.core.errors import (
    ConfigError,
    DatabaseError,
    DownloadError,
    DownloadSkippedError,
    InsufficientDiskSpaceError,
    JobCancelledError,
    JobNotCancellableError,
    JobNotFoundError,
    PixivApiError,
    PixivAuthError,
    UnconfirmedUnavailableArtistError,
)
from backend.domain.types import FailureReason

RETRYABLE_FAILURE_CODES = {
    "network_error",
    "pixiv_api_error",
    "pixiv_rate_limited",
}


class FailureDetail(BaseModel):
    code: str
    reason: FailureReason
    retryable: bool
    message: str | None = None


EXCEPTION_FAILURE_CODES: dict[type[Exception], str] = {
    ConfigError: "config_error",
    DatabaseError: "database_error",
    DownloadError: "download_error",
    DownloadSkippedError: "rule_skipped",
    InsufficientDiskSpaceError: "insufficient_disk_space",
    JobCancelledError: "cancelled",
    JobNotCancellableError: "job_not_cancellable",
    JobNotFoundError: "job_not_found",
    PixivApiError: "pixiv_api_error",
    PixivAuthError: "pixiv_auth_failed",
    UnconfirmedUnavailableArtistError: "pixiv_target_unavailable",
}


def classify_failure_reason(*values: object) -> FailureReason:
    text = " ".join(str(value) for value in values if value).casefold()
    if not text:
        return "unknown"
    if any(token in text for token in ("auth", "token", "login", "permission", "401", "forbidden")):
        return "auth"
    if any(token in text for token in ("disk", "space", "storage", "insufficient_disk_space")):
        return "disk"
    if any(
        token in text for token in ("network", "timeout", "connection", "http", "rate limit", "429")
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


def failure_detail(
    *values: object,
    code: str | None = None,
    message: str | None = None,
    status: str | None = None,
    retryable: bool | None = None,
) -> FailureDetail:
    resolved_code = normalize_failure_code(code, *values, status)
    resolved_message = message or first_string(*values)
    return FailureDetail(
        code=resolved_code,
        reason=classify_failure_reason(resolved_code, resolved_message, *values),
        retryable=retryable if retryable is not None else resolved_code in RETRYABLE_FAILURE_CODES,
        message=resolved_message,
    )


def failure_detail_from_exception(exc: Exception) -> FailureDetail:
    message = str(exc).strip() or type(exc).__name__
    return failure_detail(
        type(exc).__name__,
        message,
        code=failure_code_from_exception(exc),
        message=message,
    )


def failure_code_from_exception(exc: Exception) -> str:
    for error_type, code in EXCEPTION_FAILURE_CODES.items():
        if isinstance(exc, error_type):
            return code
    return normalize_failure_code(None, type(exc).__name__, str(exc))


def normalize_failure_code(
    code: str | None,
    *values: object,
    status: str | None = None,
) -> str:
    explicit = normalize_code(code)
    if explicit:
        return explicit
    text = " ".join(str(value) for value in values if value).casefold()
    if status == "cancelled" or "cancel" in text:
        return "cancelled"
    if "insufficient_disk_space" in text or "disk" in text or "free space" in text:
        return "insufficient_disk_space"
    if "pixivautherror" in text or "pixiv_auth_failed" in text or "refresh token" in text:
        return "pixiv_auth_failed"
    if "unconfirmedunavailableartisterror" in text or "unavailable" in text:
        return "pixiv_target_unavailable"
    if "rate limit" in text or "429" in text:
        return "pixiv_rate_limited"
    if "404" in text or "not found" in text or "does not exist" in text:
        if "artwork" in text or "illust" in text:
            return "pixiv_artwork_not_found"
        if "artist" in text or "user" in text:
            return "pixiv_artist_not_found"
        return "target_not_found"
    if "failed to fetch pixiv artwork" in text:
        return "pixiv_artwork_fetch_failed"
    if "failed to fetch pixiv user" in text or "failed to fetch artworks for pixiv user" in text:
        return "pixiv_artist_fetch_failed"
    if "pixivapierror" in text or "pixiv_api_error" in text:
        return "pixiv_api_error"
    if any(token in text for token in ("network", "timeout", "connection", "http")):
        return "network_error"
    if "downloadskippederror" in text or "skip" in text or "rule" in text or "filter" in text:
        return "rule_skipped"
    if "validation" in text:
        return "validation_error"
    if text:
        return "unknown_error"
    return "none"


def normalize_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    result = []
    for char in normalized:
        if char.isalnum():
            result.append(char.lower())
        else:
            result.append("_")
    return "_".join(part for part in "".join(result).split("_") if part)


def first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
