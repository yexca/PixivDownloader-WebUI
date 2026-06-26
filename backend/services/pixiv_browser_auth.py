from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from backend.core.errors import ConfigError

BrowserAuthStatus = Literal["pending", "callback_received", "completed", "failed"]


@dataclass
class PixivBrowserAuthSession:
    flow_id: str
    login_url: str
    expires_at: datetime
    status: BrowserAuthStatus = "pending"
    callback_url: str | None = None
    error: str | None = None


class PixivBrowserAuthStore:
    def __init__(self) -> None:
        self._sessions: dict[str, PixivBrowserAuthSession] = {}

    def create(
        self,
        *,
        flow_id: str,
        login_url: str,
        expires_at: datetime,
    ) -> PixivBrowserAuthSession:
        self.cleanup()
        session = PixivBrowserAuthSession(
            flow_id=flow_id,
            login_url=login_url,
            expires_at=expires_at,
        )
        self._sessions[flow_id] = session
        return session

    def get(self, flow_id: str) -> PixivBrowserAuthSession:
        self.cleanup()
        session = self._sessions.get(flow_id)
        if session is None:
            raise ConfigError("Pixiv browser authentication session expired. Please start again.")
        return session

    def set_callback(self, *, flow_id: str, callback_url: str) -> PixivBrowserAuthSession:
        session = self.get(flow_id)
        if session.status == "completed":
            return session
        session.callback_url = callback_url
        session.error = None
        session.status = "callback_received"
        return session

    def set_failed(self, *, flow_id: str, error: str) -> PixivBrowserAuthSession:
        session = self.get(flow_id)
        if session.status == "completed":
            return session
        session.error = error
        session.status = "failed"
        return session

    def set_completed(self, *, flow_id: str) -> PixivBrowserAuthSession:
        session = self.get(flow_id)
        session.status = "completed"
        return session

    def cleanup(self) -> None:
        now = datetime.now(UTC)
        expired_ids = [
            flow_id for flow_id, session in self._sessions.items() if session.expires_at <= now
        ]
        for flow_id in expired_ids:
            self._sessions.pop(flow_id, None)
