"""Artist Radio playlist builder and persistence settings."""
from typing import Any, Dict, List, Optional

from ..core.playlist_builder import PlaylistTypeConfig
from ..core.server_router import get_server_client
from ..services.top_tracks_service import fetch_top_tracks, top_tracks_settings
from .curation import curate_radio, filter_radio_tracks


async def fetch_radio_tracks(
    request: Any = None,
    library_ids: Optional[List[str]] = None,
    playlist: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Fetch and deduplicate tracks from the source and selected radio artists."""
    if request is not None:
        source_id = request.artist_id
        artist_ids = [source_id, *request.recommendation_ids, *request.manual_artist_ids]
        year_start, year_end = request.year_start, request.year_end
        album_cap, artist_cap = request.max_tracks_per_album, request.max_tracks_per_artist
        min_bitrate = request.min_bitrate
        min_format = request.min_format
        min_bit_depth = request.min_bit_depth
        top_settings = top_tracks_settings(request.top_tracks_enabled, request.top_tracks_count)
    else:
        saved = settings or {}
        source_id = saved.get("artist_id") or playlist["artist_id"]
        artist_ids = [source_id, *saved.get("selected_artist_ids", [])]
        year_start, year_end = saved.get("year_start"), saved.get("year_end")
        album_cap, artist_cap = saved.get("max_tracks_per_album", 4), saved.get("max_tracks_per_artist", 8)
        min_bitrate = saved.get("min_bitrate")
        min_format = saved.get("min_format")
        min_bit_depth = saved.get("min_bit_depth")
        top_settings = top_tracks_settings(
            saved.get("top_tracks_enabled"),
            saved.get("top_tracks_count"),
        )

    client = get_server_client()
    tracks: List[Dict[str, Any]] = []
    seen = set()
    unique_artist_ids = list(dict.fromkeys(artist_ids))
    for artist_id in unique_artist_ids:
        for track in await client.get_tracks_by_artist(artist_id, library_ids) or []:
            if track.get("id") not in seen:
                seen.add(track["id"])
                tracks.append(track)

    top_tracks = await fetch_top_tracks(
        unique_artist_ids,
        library_ids,
        top_settings["top_tracks_count"],
    )
    protected_track_ids = set()
    tracks_by_id = {track.get("id"): track for track in tracks if track.get("id")}
    for track in top_tracks:
        track_id = track.get("id")
        if not track_id:
            continue
        protected_track_ids.add(track_id)
        if track_id in tracks_by_id:
            tracks_by_id[track_id]["is_top_track"] = True
        else:
            seen.add(track_id)
            tracks.append(track)
            tracks_by_id[track_id] = track

    if request is not None and not request.diversity_enabled:
        album_cap = artist_cap = 0
    elif request is None and not saved.get("diversity_enabled", True):
        album_cap = artist_cap = 0
    return filter_radio_tracks(
        tracks, year_start, year_end, album_cap, artist_cap,
        min_bitrate, min_format, min_bit_depth,
        protected_track_ids=protected_track_ids,
    )


async def curate_radio_wrapper(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    request: Any = None,
    ai_client=None,
    artist_name: Optional[str] = None,
    **kwargs,
):
    return await curate_radio(candidate_tracks, num_tracks, ai_client, artist_name or "Artist Radio")


def build_radio_name(request: Any = None, artist_name: Optional[str] = None, **kwargs) -> str:
    if request is not None and request.playlist_name:
        return request.playlist_name
    return f"Artist Radio: {artist_name or 'Mix'}"


def extra_radio_settings(request: Any = None, artist_name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    if request is None:
        return {}
    return {
        "artist_id": request.artist_id,
        "artist_name": artist_name or request.artist_name,
        "source_mbid": request.source_mbid,
        "listenbrainz_enabled": request.listenbrainz_enabled,
        "algorithm": request.algorithm,
        "minimum_score": request.minimum_score,
        "recommendation_snapshot": [],
        "recommendation_ids": list(dict.fromkeys(request.recommendation_ids)),
        "selected_artist_ids": list(dict.fromkeys([request.artist_id, *request.recommendation_ids, *request.manual_artist_ids])),
        "manual_artist_ids": list(dict.fromkeys(request.manual_artist_ids)),
        "refetch_listenbrainz": request.refetch_listenbrainz,
        "year_start": request.year_start,
        "year_end": request.year_end,
        "diversity_enabled": request.diversity_enabled,
        "max_tracks_per_album": request.max_tracks_per_album,
        "max_tracks_per_artist": request.max_tracks_per_artist,
        "min_bitrate": request.min_bitrate,
        "min_format": request.min_format,
        "min_bit_depth": request.min_bit_depth,
        **top_tracks_settings(request.top_tracks_enabled, request.top_tracks_count),
    }


async def refresh_artist_radio_playlist(playlist_or_scheduled, db) -> None:
    """Refresh an Artist Radio playlist using its stored artist selection."""
    from ..core.scheduler import calculate_next_refresh
    from ..database import DatabaseManager

    if isinstance(playlist_or_scheduled, dict):
        playlist = playlist_or_scheduled
        scheduled = None
    else:
        scheduled = playlist_or_scheduled
        rows = await db.get_all_playlists_with_schedule_info()
        playlist = next(
            (row for row in rows if row.get("navidrome_playlist_id") == scheduled.navidrome_playlist_id),
            None,
        )
    if not playlist:
        return

    settings = playlist.get("curation_settings") or {}
    library_ids = settings.get("library_ids") or playlist.get("library_ids") or []
    target_length = settings.get("playlist_length") or playlist.get("playlist_length", 25)
    tracks = await fetch_radio_tracks(
        library_ids=library_ids,
        playlist=playlist,
        settings=settings,
    )
    if not tracks:
        return
    selected_ids, description = await curate_radio_wrapper(
        candidate_tracks=tracks,
        num_tracks=target_length,
        ai_client=None,
        artist_name=settings.get("artist_name"),
    )
    if not selected_ids:
        return
    server_client = get_server_client()
    await server_client.update_playlist(
        playlist_id=playlist["navidrome_playlist_id"],
        track_ids=selected_ids,
        comment=description,
    )
    titles = {track["id"]: track.get("title", "") for track in tracks}
    await db.update_playlist_content(
        navidrome_playlist_id=playlist["navidrome_playlist_id"],
        songs=[titles[track_id] for track_id in selected_ids if track_id in titles],
        description=description,
    )
    if scheduled is not None and scheduled.refresh_frequency not in ("none", "never"):
        await db.update_scheduled_playlist_next_refresh(
            scheduled.id,
            calculate_next_refresh(scheduled.refresh_frequency),
        )


ARTIST_RADIO_CONFIG = PlaylistTypeConfig(
    type_key="artist_radio",
    fetch_tracks=fetch_radio_tracks,
    curate=curate_radio_wrapper,
    build_playlist_name=build_radio_name,
    default_refresh_frequency="none",
    schedule_on_create=True,
    extra_curation_settings=extra_radio_settings,
    artist_id_resolver=lambda request, playlist_name: request.artist_id,
)
