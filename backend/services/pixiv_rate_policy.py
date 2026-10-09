from __future__ import annotations

import logging
import random
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TypeVar

from backend.core.errors import JobCancelledError

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RateLimitRule:
    min_interval_seconds: float
    random_delay_seconds: float = 0.0


@dataclass
class RateLimiter:
    rule: RateLimitRule
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    random_value: Callable[[], float] = random.random
    _next_allowed_at: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self, cancel_callback: Callable[[], bool] | None = None) -> None:
        delay = self._reserve_delay()
        if delay <= 0:
            return
        logger.info("Pixiv rate limit sleep: %.3f seconds", delay)
        cancellable_sleep(delay, self.sleep, cancel_callback)

    def _reserve_delay(self) -> float:
        with self._lock:
            now = self.monotonic()
            delay = max(0.0, self._next_allowed_at - now)
            interval = self.rule.min_interval_seconds + (
                self.rule.random_delay_seconds * self.random_value()
            )
            self._next_allowed_at = max(now, self._next_allowed_at) + interval
            return delay


@dataclass(frozen=True)
class RetryRule:
    status_delays_seconds: dict[int, tuple[float, ...]]
    transient_error_delays_seconds: tuple[float, ...] = ()


@dataclass(frozen=True)
class PixivRequestPolicy:
    rate_limiter: RateLimiter
    retry_rule: RetryRule
    sleep: Callable[[float], None] = time.sleep
    cancel_callback: Callable[[], bool] | None = None

    def run(
        self,
        operation: str,
        request: Callable[[], T],
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> T:
        cancel_callback = cancel_callback or self.cancel_callback
        attempt = 0
        while True:
            raise_if_cancelled(cancel_callback)
            self.rate_limiter.wait(cancel_callback)
            try:
                return request()
            except Exception as exc:
                retry_delay = self._retry_delay(exc, attempt)
                if retry_delay is None:
                    raise
                attempt += 1
                logger.warning(
                    "Pixiv %s failed with retryable error; retrying in %.1f seconds",
                    operation,
                    retry_delay,
                    exc_info=True,
                )
                cancellable_sleep(retry_delay, self.sleep, cancel_callback)

    def _retry_delay(self, exc: Exception, attempt: int) -> float | None:
        status = http_status_from_exception(exc)
        if status is not None:
            delays = self.retry_rule.status_delays_seconds.get(status, ())
            if attempt < len(delays):
                return delays[attempt]
            return None
        if is_transient_network_error(exc) and attempt < len(
            self.retry_rule.transient_error_delays_seconds
        ):
            return self.retry_rule.transient_error_delays_seconds[attempt]
        return None


def metadata_request_policy(
    *,
    min_interval_seconds: float,
    random_delay_seconds: float,
    cancel_callback: Callable[[], bool] | None = None,
) -> PixivRequestPolicy:
    return PixivRequestPolicy(
        rate_limiter=shared_limiter("metadata", min_interval_seconds, random_delay_seconds),
        cancel_callback=cancel_callback,
        retry_rule=RetryRule(
            status_delays_seconds={
                429: (30.0, 60.0, 120.0, 200.0, 300.0, 600.0),
                502: (10.0, 10.0, 10.0),
                503: (10.0, 30.0, 60.0),
                504: (10.0, 30.0, 60.0),
            },
            transient_error_delays_seconds=(5.0, 15.0, 30.0),
        ),
    )


def file_download_request_policy(
    *,
    min_interval_seconds: float,
    random_delay_seconds: float,
) -> PixivRequestPolicy:
    return PixivRequestPolicy(
        rate_limiter=shared_limiter("files", min_interval_seconds, random_delay_seconds),
        retry_rule=RetryRule(
            status_delays_seconds={
                429: (30.0, 60.0, 120.0, 200.0, 300.0),
                502: (10.0, 10.0, 10.0),
                503: (10.0, 30.0, 60.0),
                504: (10.0, 30.0, 60.0),
            },
            transient_error_delays_seconds=(5.0, 15.0, 30.0),
        ),
    )


def http_status_from_exception(exc: Exception) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value

    response = getattr(exc, "response", None)
    for attr in ("status_code", "status"):
        value = getattr(response, attr, None)
        if isinstance(value, int):
            return value

    match = re.search(r"\b(429|50[234])\b", str(exc))
    return int(match.group(1)) if match else None


def is_transient_network_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).casefold()
    transient_names = ("timeout", "connectionerror", "connecttimeout", "readtimeout")
    transient_messages = ("timed out", "connection aborted", "connection reset")
    return any(token in name for token in transient_names) or any(
        token in message for token in transient_messages
    )


@lru_cache(maxsize=64)
def shared_limiter(kind: str, interval: float, jitter: float) -> RateLimiter:
    del kind
    return RateLimiter(RateLimitRule(interval, jitter))


def raise_if_cancelled(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise JobCancelledError("Job cancelled")


def cancellable_sleep(
    seconds: float,
    sleep: Callable[[float], None],
    callback: Callable[[], bool] | None,
) -> None:
    if callback is None:
        sleep(seconds)
        return
    while seconds > 0:
        raise_if_cancelled(callback)
        step = min(seconds, 0.2)
        sleep(step)
        seconds -= step
    raise_if_cancelled(callback)
