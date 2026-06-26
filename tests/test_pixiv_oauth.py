from datetime import UTC, datetime, timedelta

import pytest

from backend.core.errors import ConfigError, PixivAuthError
from backend.services.pixiv_oauth import (
    PixivOAuthFlowStore,
    PixivOAuthService,
    extract_code,
    extract_code_from_text,
    extract_post_redirect_return_to,
    is_pixiv_auth_start_url,
)


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class FakeHttpClient:
    def __init__(self, data):
        self.data = data
        self.posts = []

    def post(self, url, *, data, headers):
        self.posts.append({"url": url, "data": data, "headers": headers})
        return FakeResponse(self.data)


def test_start_creates_login_url_with_pkce_params():
    service = PixivOAuthService(store=PixivOAuthFlowStore())

    flow = service.start()

    assert flow.flow_id
    assert flow.login_url.startswith("https://app-api.pixiv.net/web/v1/login?")
    assert "code_challenge=" in flow.login_url
    assert "code_challenge_method=S256" in flow.login_url
    assert "client=pixiv-android" in flow.login_url


def test_complete_exchanges_code_for_refresh_token():
    http_client = FakeHttpClient(
        {"access_token": "access-token", "refresh_token": "refresh-token", "expires_in": 3600}
    )
    service = PixivOAuthService(store=PixivOAuthFlowStore(), http_client=http_client)
    flow = service.start()

    token = service.complete(
        flow_id=flow.flow_id,
        code_or_callback_url="https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback?code=abc",
    )

    assert token.refresh_token == "refresh-token"
    assert http_client.posts[0]["data"]["code"] == "abc"
    assert http_client.posts[0]["data"]["grant_type"] == "authorization_code"
    assert http_client.posts[0]["data"]["code_verifier"]


def test_complete_rejects_expired_flow():
    store = PixivOAuthFlowStore()
    flow_id, _code_verifier, _expires_at = store.create()
    store._flows[flow_id] = store._flows[flow_id].__class__(
        code_verifier="expired",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    with pytest.raises(ConfigError):
        store.pop(flow_id)


def test_extract_code_accepts_raw_code_and_callback_url():
    assert extract_code("abc123") == "abc123"
    assert extract_code("https://example.test/callback?state=x&code=abc123") == "abc123"


def test_extract_code_finds_callback_url_inside_copied_request_text():
    curl = (
        "curl 'https://app-api.pixiv.net/web/v1/users/auth/pixiv/"
        "callback?state=xyz&code=abc123' -H 'user-agent: test'"
    )
    har_snippet = (
        '{"url":"https%3A%2F%2Fapp-api.pixiv.net%2Fweb%2Fv1%2Fusers%2Fauth'
        '%2Fpixiv%2Fcallback%3Fstate%3Dxyz%26code%3Ddef456"}'
    )

    assert extract_code_from_text(curl) == "abc123"
    assert extract_code(har_snippet) == "def456"


def test_extract_code_rejects_pixiv_post_redirect_with_clear_error():
    url = (
        "https://accounts.pixiv.net/post-redirect?"
        "return_to=https%3A%2F%2Fapp-api.pixiv.net%2Fweb%2Fv1%2Fusers%2Fauth"
        "%2Fpixiv%2Fstart%3Fcode_challenge%3Dabc%26code_challenge_method%3DS256"
        "%26client%3Dpixiv-android%26via%3Dlogin"
    )

    assert extract_post_redirect_return_to(url).startswith("https://app-api.pixiv.net/")
    with pytest.raises(ConfigError, match="intermediate Pixiv authentication URL"):
        extract_code(url)


def test_extract_code_rejects_pixiv_auth_start_url_with_clear_error():
    url = (
        "https://app-api.pixiv.net/web/v1/users/auth/pixiv/start?"
        "code_challenge=abc&code_challenge_method=S256&client=pixiv-android&via=login"
    )

    assert is_pixiv_auth_start_url(url) is True
    with pytest.raises(ConfigError, match="intermediate Pixiv authentication URL"):
        extract_code(url)


def test_parse_token_response_rejects_error_payload():
    http_client = FakeHttpClient({"error": {"message": "invalid_grant"}})
    service = PixivOAuthService(store=PixivOAuthFlowStore(), http_client=http_client)
    flow = service.start()

    with pytest.raises(PixivAuthError):
        service.complete(flow_id=flow.flow_id, code_or_callback_url="abc")
