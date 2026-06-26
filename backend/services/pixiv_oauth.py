from __future__ import annotations

import re
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any, Protocol
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests

from backend.core.errors import ConfigError, PixivAuthError

USER_AGENT = "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)"
REDIRECT_URI = "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback"
LOGIN_URL = "https://app-api.pixiv.net/web/v1/login"
AUTH_TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"
CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
FLOW_TTL_SECONDS = 300


class HttpClient(Protocol):
    def post(self, url: str, *, data: dict[str, str], headers: dict[str, str]) -> Any: ...


@dataclass(frozen=True)
class PixivOAuthFlow:
    flow_id: str
    login_url: str
    expires_at: datetime


@dataclass(frozen=True)
class PixivOAuthToken:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class _StoredFlow:
    code_verifier: str
    expires_at: datetime


class PixivOAuthFlowStore:
    def __init__(self) -> None:
        self._flows: dict[str, _StoredFlow] = {}

    def create(self) -> tuple[str, str, datetime]:
        self.cleanup()
        flow_id = token_urlsafe(24)
        code_verifier = token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=FLOW_TTL_SECONDS)
        self._flows[flow_id] = _StoredFlow(code_verifier=code_verifier, expires_at=expires_at)
        return flow_id, code_verifier, expires_at

    def pop(self, flow_id: str) -> str:
        self.cleanup()
        flow = self._flows.pop(flow_id, None)
        if flow is None:
            raise ConfigError("Pixiv authentication flow expired. Please start again.")
        return flow.code_verifier

    def cleanup(self) -> None:
        now = datetime.now(UTC)
        expired_ids = [
            flow_id for flow_id, flow in self._flows.items() if flow.expires_at <= now
        ]
        for flow_id in expired_ids:
            self._flows.pop(flow_id, None)


class PixivOAuthService:
    def __init__(
        self,
        *,
        store: PixivOAuthFlowStore,
        http_client: HttpClient | None = None,
    ) -> None:
        self.store = store
        self.http_client = http_client or requests

    def start(self) -> PixivOAuthFlow:
        flow_id, code_verifier, expires_at = self.store.create()
        login_params = {
            "code_challenge": _s256(code_verifier.encode("ascii")),
            "code_challenge_method": "S256",
            "client": "pixiv-android",
        }
        return PixivOAuthFlow(
            flow_id=flow_id,
            login_url=f"{LOGIN_URL}?{urlencode(login_params)}",
            expires_at=expires_at,
        )

    def complete(self, *, flow_id: str, code_or_callback_url: str) -> PixivOAuthToken:
        code = extract_code(code_or_callback_url)
        code_verifier = self.store.pop(flow_id)
        response = self.http_client.post(
            AUTH_TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "include_policy": "true",
                "redirect_uri": REDIRECT_URI,
            },
            headers={"User-Agent": USER_AGENT},
        )
        return _parse_token_response(response)

    def refresh(self, refresh_token: str) -> PixivOAuthToken:
        response = self.http_client.post(
            AUTH_TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "include_policy": "true",
                "refresh_token": refresh_token,
            },
            headers={"User-Agent": USER_AGENT},
        )
        return _parse_token_response(response)


def extract_code(code_or_callback_url: str) -> str:
    value = code_or_callback_url.strip()
    if not value:
        raise ConfigError("Pixiv authorization code is required.")

    embedded_code = extract_code_from_text(value)
    if embedded_code:
        return embedded_code

    if "://" not in value and _looks_like_raw_code(value):
        return value

    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    code_values = query.get("code", [])
    if not code_values or not code_values[0].strip():
        if extract_pixiv_intermediate_auth_url(value):
            raise ConfigError(
                "This is an intermediate Pixiv authentication URL, not the final callback URL. "
                "Copy the Pixiv callback URL that contains code= from the browser network log."
            )
        raise ConfigError("Callback URL does not contain a Pixiv authorization code.")
    return code_values[0].strip()


def _looks_like_raw_code(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._~-]+", value))


def extract_code_from_text(text: str) -> str | None:
    candidates = [text, unquote(text)]
    for candidate in candidates:
        match = re.search(
            r"https://app-api\.pixiv\.net/web/v1/users/auth/pixiv/callback\?[^\s'\"<>]+",
            candidate,
        )
        if match:
            parsed = urlparse(match.group(0))
            code = _first_query_value(parsed.query, "code")
            if code:
                return code

        code = _first_query_value(candidate, "code")
        if code:
            return code
    return None


def extract_post_redirect_return_to(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.netloc != "accounts.pixiv.net" or parsed.path != "/post-redirect":
        return None
    query = parse_qs(parsed.query)
    return_to_values = query.get("return_to", [])
    if not return_to_values or not return_to_values[0].strip():
        return None
    return return_to_values[0].strip()


def extract_pixiv_intermediate_auth_url(url: str) -> str | None:
    value = url.strip()
    return_to = extract_post_redirect_return_to(value)
    if return_to:
        return return_to
    if is_pixiv_auth_start_url(value):
        return value
    return None


def is_pixiv_auth_start_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return (
        parsed.netloc == "app-api.pixiv.net"
        and parsed.path == "/web/v1/users/auth/pixiv/start"
    )


def _first_query_value(query_or_text: str, key: str) -> str | None:
    query = query_or_text
    if "?" in query:
        query = query.split("?", 1)[1]
    values = parse_qs(query).get(key, [])
    if not values or not values[0].strip():
        return None
    return values[0].strip()


def _s256(data: bytes) -> str:
    return urlsafe_b64encode(sha256(data).digest()).rstrip(b"=").decode("ascii")


def _parse_token_response(response: Any) -> PixivOAuthToken:
    try:
        data = response.json()
    except ValueError as exc:
        raise PixivAuthError("Pixiv authentication failed: invalid token response.") from exc

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token or not refresh_token:
        message = _error_message(data)
        raise PixivAuthError(f"Pixiv authentication failed: {message}")

    return PixivOAuthToken(
        access_token=str(access_token),
        refresh_token=str(refresh_token),
        expires_in=int(data.get("expires_in") or 0),
    )


def _error_message(data: dict[str, Any]) -> str:
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("description") or error)
    if error:
        return str(error)
    return "token response did not include a refresh token."
