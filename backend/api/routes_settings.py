from __future__ import annotations

import os
from dataclasses import replace

import requests
from fastapi import APIRouter, Header, status

from backend.api.dependencies import (
    DbPath,
    PixivBrowserAuthStoreDep,
    PixivOAuthStore,
    SettingsJsonPath,
)
from backend.core.errors import ConfigError, PixivAuthError
from backend.schemas.settings import (
    AuthValidationResponse,
    PixivAuthCompleteRequest,
    PixivAuthCompleteResponse,
    PixivAuthRefreshResponse,
    PixivAuthStartResponse,
    PixivBrowserAuthCallbackRequest,
    PixivBrowserAuthServiceStatusResponse,
    PixivBrowserAuthStartResponse,
    PixivBrowserAuthStatusResponse,
    PixivConnectionTestResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)
from backend.services.pixiv_oauth import PixivOAuthService
from backend.services.settings_service import AppSettingsService, masked_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(db_path: DbPath, settings_json_path: SettingsJsonPath) -> dict[str, object]:
    service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        return service.get_masked()
    finally:
        service.close()


@router.put("", response_model=SettingsResponse)
def update_settings(
    request: SettingsUpdateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> dict[str, object]:
    service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        settings = service.update(request.model_dump(exclude_unset=True))
        return masked_settings(settings)
    finally:
        service.close()


@router.post("/validate-auth", response_model=AuthValidationResponse)
def validate_pixiv_auth(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> AuthValidationResponse:
    service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        service.validate_pixiv_auth()
    finally:
        service.close()
    return AuthValidationResponse(ok=True, message="Pixiv authentication succeeded.")


@router.post("/test-connection", response_model=PixivConnectionTestResponse)
def test_pixiv_connection(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
) -> PixivConnectionTestResponse:
    service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        user = service.test_pixiv_connection()
    finally:
        service.close()
    user_name = user["user_name"]
    user_id = user["user_id"]
    message = (
        f"Pixiv API connection succeeded for {user_name} ({user_id})."
        if user_name
        else f"Pixiv API connection succeeded for user {user_id}."
    )
    return PixivConnectionTestResponse(
        ok=True,
        message=message,
        user_id=user_id,
        user_name=user_name,
    )


@router.post("/pixiv-auth/start", response_model=PixivAuthStartResponse)
def start_pixiv_auth(
    flow_store: PixivOAuthStore,
) -> PixivAuthStartResponse:
    flow = PixivOAuthService(store=flow_store).start()
    return PixivAuthStartResponse(
        flow_id=flow.flow_id,
        login_url=flow.login_url,
        expires_at=flow.expires_at.isoformat(),
    )


@router.post("/pixiv-auth/browser/start", response_model=PixivBrowserAuthStartResponse)
def start_pixiv_browser_auth(
    flow_store: PixivOAuthStore,
    browser_store: PixivBrowserAuthStoreDep,
) -> PixivBrowserAuthStartResponse:
    flow = PixivOAuthService(store=flow_store).start()
    session = browser_store.create(
        flow_id=flow.flow_id,
        login_url=flow.login_url,
        expires_at=flow.expires_at,
    )
    _start_auth_browser(flow_id=session.flow_id, login_url=session.login_url)
    return PixivBrowserAuthStartResponse(
        flow_id=session.flow_id,
        login_url=session.login_url,
        expires_at=session.expires_at.isoformat(),
        novnc_url=_auth_browser_public_url(),
    )


@router.get("/pixiv-auth/browser/{flow_id}", response_model=PixivBrowserAuthStatusResponse)
def get_pixiv_browser_auth_status(
    flow_id: str,
    browser_store: PixivBrowserAuthStoreDep,
) -> PixivBrowserAuthStatusResponse:
    session = browser_store.get(flow_id)
    return PixivBrowserAuthStatusResponse(
        flow_id=session.flow_id,
        status=session.status,
        expires_at=session.expires_at.isoformat(),
        error=session.error,
    )


@router.get(
    "/pixiv-auth/browser-service",
    response_model=PixivBrowserAuthServiceStatusResponse,
)
def get_pixiv_browser_auth_service_status() -> PixivBrowserAuthServiceStatusResponse:
    internal_url = _auth_browser_internal_url_or_none()
    running = False
    configured = internal_url is not None
    if internal_url:
        try:
            response = requests.get(f"{internal_url}/health", timeout=2)
            running = response.status_code < 400
        except requests.RequestException:
            running = False
    message = (
        "Pixiv browser authentication service is running."
        if running
        else "Pixiv browser authentication service is not running."
    )
    return PixivBrowserAuthServiceStatusResponse(
        configured=configured,
        running=running,
        novnc_url=_auth_browser_public_url(),
        start_command="docker compose --profile auth up -d pixiv-auth-browser",
        stop_command="docker compose stop pixiv-auth-browser",
        message=message,
    )


@router.post(
    "/pixiv-auth/browser/callback",
    response_model=PixivBrowserAuthStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def receive_pixiv_browser_auth_callback(
    request: PixivBrowserAuthCallbackRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    flow_store: PixivOAuthStore,
    browser_store: PixivBrowserAuthStoreDep,
    x_pixiv_auth_browser_token: str | None = Header(default=None),
) -> PixivBrowserAuthStatusResponse:
    _verify_auth_browser_token(x_pixiv_auth_browser_token)
    if request.error:
        session = browser_store.set_failed(flow_id=request.flow_id, error=request.error)
    elif request.callback_url:
        browser_store.set_callback(flow_id=request.flow_id, callback_url=request.callback_url)
        try:
            _save_callback_refresh_token(
                db_path=db_path,
                settings_json_path=settings_json_path,
                flow_store=flow_store,
                flow_id=request.flow_id,
                callback_url=request.callback_url,
            )
        except Exception as exc:
            browser_store.set_failed(flow_id=request.flow_id, error=str(exc))
            raise
        session = browser_store.set_completed(flow_id=request.flow_id)
    else:
        raise ConfigError("Pixiv browser authentication callback or error is required.")
    return PixivBrowserAuthStatusResponse(
        flow_id=session.flow_id,
        status=session.status,
        expires_at=session.expires_at.isoformat(),
        error=session.error,
    )


@router.post("/pixiv-auth/complete", response_model=PixivAuthCompleteResponse)
def complete_pixiv_auth(
    request: PixivAuthCompleteRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    flow_store: PixivOAuthStore,
) -> dict[str, object]:
    settings_service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        token = PixivOAuthService(store=flow_store).complete(
            flow_id=request.flow_id,
            code_or_callback_url=request.code_or_callback_url,
        )
        settings = settings_service.load()
        settings_service.save(replace(settings, refresh_token=token.refresh_token))
        return {
            **settings_service.get_masked(),
            "message": "Pixiv refresh token saved.",
        }
    finally:
        settings_service.close()


def _save_callback_refresh_token(
    *,
    db_path,
    settings_json_path,
    flow_store: PixivOAuthStore,
    flow_id: str,
    callback_url: str,
) -> None:
    settings_service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        token = PixivOAuthService(store=flow_store).complete(
            flow_id=flow_id,
            code_or_callback_url=callback_url,
        )
        settings = settings_service.load()
        settings_service.save(replace(settings, refresh_token=token.refresh_token))
    finally:
        settings_service.close()


def _auth_browser_internal_url() -> str:
    value = _auth_browser_internal_url_or_none()
    if not value:
        raise ConfigError("Pixiv browser authentication sidecar is not configured.")
    return value


def _auth_browser_internal_url_or_none() -> str | None:
    value = os.environ.get("PIXIV_AUTH_BROWSER_INTERNAL_URL", "").strip().rstrip("/")
    return value or None


def _auth_browser_public_url() -> str:
    value = os.environ.get("PIXIV_AUTH_BROWSER_PUBLIC_URL", "").strip()
    if value:
        return value
    return "http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale"


def _auth_browser_token() -> str:
    return os.environ.get("PIXIV_AUTH_BROWSER_TOKEN", "").strip()


def _start_auth_browser(*, flow_id: str, login_url: str) -> None:
    token = _auth_browser_token()
    headers = {"X-Pixiv-Auth-Browser-Token": token} if token else {}
    try:
        response = requests.post(
            f"{_auth_browser_internal_url()}/api/auth/start",
            json={
                "flow_id": flow_id,
                "login_url": login_url,
                "callback_url": _auth_browser_callback_url(),
            },
            headers=headers,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise PixivAuthError("Pixiv browser authentication sidecar could not be reached.") from exc
    if response.status_code >= 400:
        raise PixivAuthError("Pixiv browser authentication sidecar rejected the login request.")


def _verify_auth_browser_token(received_token: str | None) -> None:
    expected_token = _auth_browser_token()
    if expected_token and received_token != expected_token:
        raise ConfigError("Pixiv browser authentication callback token is invalid.")


def _auth_browser_callback_url() -> str:
    return os.environ.get(
        "PIXIV_AUTH_BROWSER_CALLBACK_URL",
        "http://pixivdownloader:7653/api/settings/pixiv-auth/browser/callback",
    ).strip()


@router.post("/pixiv-auth/refresh", response_model=PixivAuthRefreshResponse)
def refresh_pixiv_auth(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    flow_store: PixivOAuthStore,
) -> dict[str, object]:
    settings_service = AppSettingsService(db_path=db_path, settings_json_path=settings_json_path)
    try:
        settings = settings_service.load()
        token = PixivOAuthService(store=flow_store).refresh(settings.refresh_token)
        settings_service.save(replace(settings, refresh_token=token.refresh_token))
        return {
            **settings_service.get_masked(),
            "message": "Pixiv refresh token refreshed.",
        }
    finally:
        settings_service.close()
