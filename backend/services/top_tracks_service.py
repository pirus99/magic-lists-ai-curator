"""Navidrome-only artist top-track enrichment."""
import os
from typing import Any, Dict, Iterable, List, Optional

from ..core.server_router import get_server_client


def top_tracks_settings(
    enabled: Optional[bool],
    count: Optional[int],
    max_count: int = 10,
) -> Dict[str, Any]:
    """Return safe, normalized top-track settings for the active server type."""
    if os.getenv("SERVER_TYPE", "navidrome").lower() != "navidrome":
        return {"top_tracks_enabled": False, "top_tracks_count": 0}

    normalized_count = max(0, min(max_count, int(count or 0)))
    return {
        "top_tracks_enabled": bool(enabled) and normalized_count > 0,
        "top_tracks_count": normalized_count,
    }


async def fetch_top_tracks(
    artist_ids: Iterable[str],
    library_ids: Optional[List[str]],
    count: int,
) -> List[Dict[str, Any]]:
    """Fetch up to ``count`` top songs for each artist when Navidrome is active."""
    if count <= 0 or os.getenv("SERVER_TYPE", "navidrome").lower() != "navidrome":
        return []

    unique_ids = list(dict.fromkeys(artist_id for artist_id in artist_ids if artist_id))
    if not unique_ids:
        return []

    client = get_server_client()
    artists = await client.get_artists(library_ids) or []
    names_by_id = {artist.get("id"): artist.get("name") for artist in artists}
    tracks: List[Dict[str, Any]] = []
    for artist_id in unique_ids:
        artist_name = names_by_id.get(artist_id)
        if not artist_name:
            continue
        tracks.extend(
            await client.get_top_songs_by_artist(artist_name, count, library_ids) or []
        )
    return tracks
