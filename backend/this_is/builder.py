"""Builder and refresh logic for 'This Is' (single-artist) playlists."""
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..database import DatabaseManager
from ..core.dependencies import get_ai_client
from ..core.server_router import get_server_client
from ..core.playlist_builder import PlaylistTypeConfig
from .curation import curate_this_is


scheduler_logger = logging.getLogger("scheduler")


# ---------------------------------------------------------------------------
# Type-specific steps
# ---------------------------------------------------------------------------
async def fetch_this_is_tracks(
    request: Any = None,
    library_ids: Optional[List[str]] = None,
    playlist_length: int = 25,
    playlist: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Fetch tracks for a This Is playlist (creation or refresh)."""
    server_client = get_server_client()

    if playlist is not None:
        # Refresh path: re-fetch fresh data for the saved artist.
        artist_id = (settings or {}).get("artist_id") or playlist["artist_id"]
        return await server_client.get_tracks_by_artist(artist_id, library_ids)

    # Creation path.
    if not request or not getattr(request, "artist_ids", None):
        raise ValueError("At least one artist must be selected")
    first_artist_id = request.artist_ids[0]
    tracks = await server_client.get_tracks_by_artist(first_artist_id, library_ids)
    return tracks or []


async def curate_this_is_wrapper(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    request: Any = None,
    ai_client=None,
    playlist: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    artist_name: Optional[str] = None,
    **kwargs,
) -> Tuple[List[str], str]:
    """Wrap the curation call, injecting variety context on refresh."""
    artist_name = _artist_name_for(
        request=request,
        playlist=playlist,
        settings=settings,
        artist_name=artist_name,
    )
    variety_context = None
    if playlist is not None:
        previous_songs = playlist.get("songs", [])
        variety_context = (
            f"REFRESH CONSTRAINT: This is a REFRESH, not a copy. Previous playlist had these "
            f"tracks: {', '.join(previous_songs[:10])}. Create a completely different track "
            f"selection and arrangement. Prioritize tracks NOT in the previous list. Tell a "
            f"fresh musical story. Avoid identical opening sequences."
            if previous_songs
            else "Create a fresh, engaging playlist arrangement."
        )
    return await curate_this_is(
        ai_client=ai_client,
        artist_name=artist_name,
        candidate_tracks=candidate_tracks,
        num_tracks=num_tracks,
        include_description=True,
        variety_context=variety_context,
    )


def build_this_is_name(
    request: Any = None,
    candidate_tracks: Optional[List[Dict[str, Any]]] = None,
    description: str = "",
    **kwargs,
) -> str:
    """Generate the playlist name for a This Is playlist."""
    if request is not None and getattr(request, "playlist_name", None):
        return request.playlist_name
    artist_name = _artist_name_for(
        request=request,
        artist_name=kwargs.get("artist_name"),
    )
    return f"This Is: {artist_name}"


def _artist_name_for(
    request: Any = None,
    playlist: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    artist_name: Optional[str] = None,
) -> str:
    """Resolve the artist name without blocking the async event loop."""
    if artist_name:
        return artist_name

    if request is not None and getattr(request, "artist_ids", None):
        return request.artist_ids[0]

    if playlist is not None:
        artist_id = (settings or {}).get("artist_id") or playlist["artist_id"]
        return (settings or {}).get("artist_name") or playlist.get("artist_name") or artist_id

    return "Unknown Artist"


def extra_this_is_settings(
    request: Any = None,
    playlist_length: int = 25,
    artist_name: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Persist the artist id/name for later refreshes."""
    if request is None or not getattr(request, "artist_ids", None):
        return {}
    return {
        "artist_id": request.artist_ids[0],
        "artist_name": _artist_name_for(request=request, artist_name=artist_name),
    }


# ---------------------------------------------------------------------------
# Config + refresh entry points
# ---------------------------------------------------------------------------
THIS_IS_CONFIG = PlaylistTypeConfig(
    type_key="this_is",
    fetch_tracks=fetch_this_is_tracks,
    curate=curate_this_is_wrapper,
    build_playlist_name=build_this_is_name,
    default_refresh_frequency="none",
    schedule_on_create=True,
    extra_curation_settings=extra_this_is_settings,
)


async def refresh_this_is_playlist(scheduled_playlist, db: DatabaseManager) -> None:
    """Refresh a specific This Is playlist (scheduler dispatch entry point)."""
    try:
        scheduler_logger.info(
            f"🔄 Starting refresh for This Is playlist ID: {scheduled_playlist.navidrome_playlist_id} "
            f"(frequency: {scheduled_playlist.refresh_frequency})"
        )
        nav_client = get_server_client()
        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next(
            (p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id),
            None,
        )
        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return

        settings = original_playlist.get("curation_settings") or {}
        artist_id = settings.get("artist_id") or original_playlist["artist_id"]
        library_ids = settings.get("library_ids") or []
        original_length = settings.get("playlist_length") or original_playlist.get("playlist_length", 25)
        scheduler_logger.info(f"🎯 ENFORCING original playlist length: {original_length}")

        tracks = await nav_client.get_tracks_by_artist(artist_id, library_ids)
        if not tracks:
            scheduler_logger.warning(f"⚠️ No tracks found for artist in playlist {scheduled_playlist.navidrome_playlist_id}")
            return
        if len(tracks) < original_length:
            scheduler_logger.warning(
                f"⚠️ Artist only has {len(tracks)} tracks, but user requested {original_length}. Using all available tracks."
            )
            original_length = len(tracks)

        curated_track_ids, description = await curate_this_is_wrapper(
            candidate_tracks=tracks,
            num_tracks=original_length,
            ai_client=get_ai_client(),
            playlist=original_playlist,
            settings=settings,
        )

        if curated_track_ids:
            if len(curated_track_ids) < original_length and len(tracks) >= original_length:
                scheduler_logger.warning(
                    f"⚠️ AI returned only {len(curated_track_ids)} tracks but user requested {original_length}. Using fallback to fill gap."
                )
                used_ids = set(curated_track_ids)
                remaining_tracks = [t for t in tracks if t["id"] not in used_ids]
                additional_needed = original_length - len(curated_track_ids)
                curated_track_ids.extend([t["id"] for t in remaining_tracks[:additional_needed]])

            scheduler_logger.info(f"🎯 Final track count: {len(curated_track_ids)} (requested: {original_length})")

            refresh_description = _resolve_description(original_playlist, description)
            await nav_client.update_playlist(
                playlist_id=scheduled_playlist.navidrome_playlist_id,
                track_ids=curated_track_ids,
                comment=refresh_description,
            )

            track_titles = []
            track_id_to_title = {track["id"]: track["title"] for track in tracks}
            for track_id in curated_track_ids:
                if track_id in track_id_to_title:
                    track_titles.append(track_id_to_title[track_id])

            await db.update_playlist_content(
                navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id,
                songs=track_titles,
                description=refresh_description,
            )

            from ..core.scheduler import calculate_next_refresh

            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, next_refresh)
            scheduler_logger.info(
                f"✅ Successfully refreshed This Is playlist {scheduled_playlist.navidrome_playlist_id}. "
                f"Next refresh: {next_refresh.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            scheduler_logger.warning(f"⚠️ No curated tracks generated for This Is playlist {scheduled_playlist.navidrome_playlist_id}")
    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing This Is playlist {scheduled_playlist.navidrome_playlist_id}: {e}")


def _resolve_description(original_playlist: Dict[str, Any], generated_description: str) -> str:
    """Resolve the refresh description using the shared metadata helper."""
    from ..playlist_metadata import resolve_refresh_description

    return resolve_refresh_description(
        existing_description=original_playlist.get("description"),
        generated_description=generated_description,
        metadata_overrides={"description": bool(original_playlist.get("description"))},
    )
