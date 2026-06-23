from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, SettingsJsonPath
from backend.schemas.settings import SettingsResponse, SettingsUpdateRequest
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
        settings = service.update(request.model_dump())
        return masked_settings(settings)
    finally:
        service.close()
