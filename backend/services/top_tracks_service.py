"""Artist top-track enrichment for both Navidrome and Jellyfin.

The active source is chosen automatically from the server type: Navidrome uses its
native ``getTopSongs`` endpoint, while Jellyfin (which has no equivalent) resolves
top tracks through Last.fm. Short display labels live in ``lastfm_service`` so the
backend, the template context and the frontend all agree on them.
"""
import logging
import os
from typing import Any, Dict, Iterable, List, Optional

from ..core.server_router import get_server_client
from .lastfm_service import TOP_TRACK_STRATEGY_LABELS, top_tracks_strategy_label

logger = logging.getLogger(__name__)

# Re-exported so callers can label a strategy without importing lastfm_service.
STRATEGY_LABELS = TOP_TRACK_STRATEGY_LABELS


def top_tracks_strategy() -> str:
    """Return the top-track strategy key for the active configuration.

    Returns:
        ``"native"`` for Navidrome, ``"lastfm"`` for Jellyfin when ``LASTFM_API_KEY``
        is configured, otherwise ``"off"``.
    """
    server_type = os.getenv("SERVER_TYPE", "navidrome").lower()
    if server_type == "navidrome":
        return "native"
    if server_type == "jellyfin":
        return "lastfm" if os.getenv("LASTFM_API_KEY") else "off"
    return "off"


def top_tracks_supported() -> bool:
    """Return True when a top-track source is available for the active server type."""
    return top_tracks_strategy() != "off"


def top_tracks_strategy_label_for_current_server() -> str:
    """Return the short label for the active top-track strategy."""
    return top_tracks_strategy_label(top_tracks_strategy())


def top_tracks_settings(
    enabled: Optional[bool],
    count: Optional[int],
    max_count: int = 10,
) -> Dict[str, Any]:
    """Return safe, normalized top-track settings for the active server type.

    Unlike the previous Navidrome-only version, settings are preserved for Jellyfin.
    When no source is available the feature is reported as disabled so the UI can
    explain why the control does nothing.
    """
    normalized_count = max(0, min(max_count, int(count or 0)))
    supported = top_tracks_supported()
    return {
        "top_tracks_enabled": bool(supported and enabled) and normalized_count > 0,
        "top_tracks_count": normalized_count if supported else 0,
    }


async def fetch_top_tracks(
    artist_ids: Iterable[str],
    library_ids: Optional[List[str]],
    count: int,
) -> List[Dict[str, Any]]:
    """Fetch up to ``count`` top songs for each artist from the active source.

    Never raises: a provider failure degrades to no top tracks, leaving the playlist
    to be ordered by local play count instead.
    """
    if count <= 0 or not top_tracks_supported():
        return []

    unique_ids = list(dict.fromkeys(artist_id for artist_id in artist_ids if artist_id))
    if not unique_ids:
        return []

    try:
        client = get_server_client()
        artists = await client.get_artists(library_ids) or []
        names_by_id = {artist.get("id"): artist.get("name") for artist in artists}
        tracks: List[Dict[str, Any]] = []
        for artist_id in unique_ids:
            artist_name = names_by_id.get(artist_id)
            if not artist_name:
                continue
            try:
                artist_top_tracks = await client.get_top_songs_by_artist(
                    artist_name, count, library_ids
                ) or []
            except Exception as exc:  # noqa: BLE001 - one artist must not break the batch
                logger.warning(
                    f"⚠️ Top tracks unavailable for '{artist_name}' "
                    f"({top_tracks_strategy()}): {exc}"
                )
                continue
            for track in artist_top_tracks:
                track["is_top_track"] = True
            tracks.extend(artist_top_tracks)
        return tracks
    except Exception as exc:  # noqa: BLE001 - never fail a playlist build
        logger.warning(f"⚠️ Top track enrichment failed ({top_tracks_strategy()}): {exc}")
        return []
