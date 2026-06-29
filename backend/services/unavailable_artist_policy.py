from __future__ import annotations

from backend.core.errors import UnconfirmedUnavailableArtistError
from backend.domain.entities import Artist

AUTO_ACCEPT_UNAVAILABLE_SOURCES = {
    "legacy_database",
    "library_shortcut",
}


def confirm_unavailable_artist(
    *,
    existing_artist: Artist | None,
    fetched_artist: Artist,
    source: str | None,
) -> None:
    if fetched_artist.account_status != "unavailable":
        return
    if existing_artist is not None:
        return
    if source in AUTO_ACCEPT_UNAVAILABLE_SOURCES:
        return
    reason = fetched_artist.account_status_reason or "Pixiv user is unavailable"
    raise UnconfirmedUnavailableArtistError(
        "Pixiv user is unavailable and was not added automatically. "
        f"Confirm the artist ID before adding it as unavailable. Reason: {reason}"
    )
