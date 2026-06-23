from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class DownloadCreateRequest(BaseModel):
    user_id: str | None = None
    artwork_id: str | None = None
    mode: Literal["artist", "artwork"] = "artist"
    force_rescan: bool = False
    retry_failed: bool = False

    @model_validator(mode="after")
    def validate_input(self) -> DownloadCreateRequest:
        if bool(self.user_id) == bool(self.artwork_id):
            raise ValueError("exactly one of user_id or artwork_id must be provided")
        return self


class DownloadCreateResponse(BaseModel):
    job_id: str
    status: str
