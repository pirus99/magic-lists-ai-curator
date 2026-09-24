"""Builder and refresh logic for 'Genre Mix' playlists."""
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from ..database import DatabaseManager
from ..core.dependencies import get_ai_client
from ..core.server_router import get_server_client
from ..core.playlist_builder import PlaylistTypeConfig
from ..track_scoring import filter_tracks_for_this_is_playlist
from ..recipe_manager import recipe_manager
from .curation import curate_genre_mix


scheduler_logger = logging.getLogger("scheduler")

DEFAULT_MAX_TRACKS_PER_ALBUM = 2
DEFAULT_MAX_TRACKS_PER_ARTIST = 3


# ---------------------------------------------------------------------------
# Type-specific steps
# ---------------------------------------------------------------------------
async def fetch_genre_mix_tracks(
    request: Any = None,
    library_ids: Optional[List[str]] = None,
    playlist_length: int = 25,
    playlist: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Fetch tracks for a Genre Mix playlist (creation or refresh)."""
    server_client = get_server_client()
    if playlist is not None:
        genres = (settings or {}).get("genres") or [g.strip() for g in playlist.get("artist_id", "").split(",") if g.strip()]
        if not genres:
            scheduler_logger.error("❌ No genres found for Genre Mix refresh")
            return []
        return await server_client.get_tracks_by_genres(genres, library_ids)
    if request is None or not getattr(request, "genres", None):
        return []
    return await server_client.get_tracks_by_genres(request.genres, library_ids)


async def apply_genre_mix_filter(
    source_tracks: List[Dict[str, Any]],
    target_playlist_size: int,
    request: Any = None,
    nav_client=None,
    ai_client=None,
    settings: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Apply smart filtering + diversity caps for Genre Mix playlists."""
    library_stats = await nav_client.get_library_stats()
    genre_recipe = recipe_manager.get_recipe("genre_mix")
    diversity_config = genre_recipe.get("source_filtering", {})

    ollama_max_tracks = None
    if ai_client.provider.provider_type == "ollama":
        ollama_max_tracks = int(os.getenv("OLLAMA_MAX_TRACKS", "0")) or None

    # Resolve caps / filters from request (creation) or settings (refresh).
    if request is not None:
        max_tracks_per_album = request.max_tracks_per_album if request.max_tracks_per_album is not None else DEFAULT_MAX_TRACKS_PER_ALBUM
        max_tracks_per_artist = request.max_tracks_per_artist if request.max_tracks_per_artist is not None else DEFAULT_MAX_TRACKS_PER_ARTIST
        year_start = request.year_start
        year_end = request.year_end
        blacklisted_artists = request.blacklisted_artists
        min_bitrate = request.min_bitrate
        min_format = request.min_format
        min_bit_depth = request.min_bit_depth
    else:
        max_tracks_per_album = (settings or {}).get("max_tracks_per_album", DEFAULT_MAX_TRACKS_PER_ALBUM)
        max_tracks_per_artist = (settings or {}).get("max_tracks_per_artist", DEFAULT_MAX_TRACKS_PER_ARTIST)
        year_start = (settings or {}).get("year_start")
        year_end = (settings or {}).get("year_end")
        blacklisted_artists = (settings or {}).get("blacklisted_artists") or []
        min_bitrate = (settings or {}).get("min_bitrate")
        min_format = (settings or {}).get("min_format")
        min_bit_depth = (settings or {}).get("min_bit_depth")

    return filter_tracks_for_this_is_playlist(
        source_tracks=source_tracks,
        target_playlist_size=target_playlist_size,
        library_stats=library_stats,
        playlist_type="genre",
        diversity_config=diversity_config,
        ollama_max_tracks=ollama_max_tracks,
        exploration_ratio=diversity_config.get("exploration_ratio", 0.0),
        high_tier_ratio=diversity_config.get("high_tier_ratio", 0.4),
        high_tier_multiplier=diversity_config.get("high_tier_multiplier", 3.0),
        year_start=year_start,
        year_end=year_end,
        blacklisted_artists=blacklisted_artists,
        min_bitrate=min_bitrate,
        min_format=min_format,
        min_bit_depth=min_bit_depth,
        max_tracks_per_album=max_tracks_per_album,
        max_tracks_per_artist=max_tracks_per_artist,
    )


async def curate_genre_mix_wrapper(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    request: Any = None,
    ai_client=None,
    playlist: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Tuple[List[str], str]:
    """Wrap genre-mix curation, resolving genres from request or settings."""
    if request is not None and getattr(request, "genres", None):
        genres = request.genres
    else:
        genres = (settings or {}).get("genres") or [g.strip() for g in (playlist or {}).get("artist_id", "").split(",") if g.strip()]
    return await curate_genre_mix(
        ai_client=ai_client,
        genres=genres,
        candidate_tracks=candidate_tracks,
        num_tracks=num_tracks,
        include_description=True,
    )


def build_genre_mix_name(
    request: Any = None,
    candidate_tracks: Optional[List[Dict[str, Any]]] = None,
    description: str = "",
    **kwargs,
) -> str:
    """Generate the playlist name for a Genre Mix playlist."""
    if request is not None and getattr(request, "playlist_name", None):
        return request.playlist_name
    if request is not None and getattr(request, "genres", None):
        return f"Genre Mix: {', '.join(request.genres)}"
    return "Genre Mix"


def extra_genre_mix_settings(request: Any = None, playlist_length: int = 25, **kwargs) -> Dict[str, Any]:
    """Persist genre-specific curation settings for later refreshes."""
    if request is None or not getattr(request, "genres", None):
        return {}
    return {
        "genres": request.genres,
        "year_start": request.year_start,
        "year_end": request.year_end,
        "blacklisted_artists": request.blacklisted_artists,
        "min_bitrate": request.min_bitrate,
        "min_format": request.min_format,
        "min_bit_depth": request.min_bit_depth,
        "max_tracks_per_album": request.max_tracks_per_album if request.max_tracks_per_album is not None else DEFAULT_MAX_TRACKS_PER_ALBUM,
        "max_tracks_per_artist": request.max_tracks_per_artist if request.max_tracks_per_artist is not None else DEFAULT_MAX_TRACKS_PER_ARTIST,
    }


def artist_id_for_genre_mix(request: Any = None, **kwargs) -> str:
    """Genre playlists use the joined genre list as the stored artist_id."""
    if request is not None and getattr(request, "genres", None):
        return ", ".join(request.genres)
    return "genre_mix"


# ---------------------------------------------------------------------------
# Config + refresh entry points
# ---------------------------------------------------------------------------
GENRE_MIX_CONFIG = PlaylistTypeConfig(
    type_key="genre_mix",
    fetch_tracks=fetch_genre_mix_tracks,
    curate=curate_genre_mix_wrapper,
    build_playlist_name=build_genre_mix_name,
    default_refresh_frequency="none",
    schedule_on_create=True,
    extra_curation_settings=extra_genre_mix_settings,
    apply_smart_filter=apply_genre_mix_filter,
    artist_id_resolver=artist_id_for_genre_mix,
)


async def refresh_genre_playlist(playlist: Dict[str, Any], db: DatabaseManager) -> None:
    """Refresh a Genre Mix playlist using its saved curation settings."""
    try:
        scheduler_logger.info(f"🔄 Starting refresh for Genre Mix playlist ID: {playlist.get('navidrome_playlist_id')}")
        nav_client = get_server_client()
        ai_client = get_ai_client()

        settings = playlist.get("curation_settings") or {}
        genres = settings.get("genres") or [g.strip() for g in playlist.get("artist_id", "").split(",") if g.strip()]
        if not genres:
            scheduler_logger.error("❌ No genres found for Genre Mix refresh")
            return

        library_ids = settings.get("library_ids") or []
        playlist_length = settings.get("playlist_length") or playlist.get("playlist_length") or 25

        all_tracks = await nav_client.get_tracks_by_genres(genres, library_ids)
        scheduler_logger.info(f"🎵 Found {len(all_tracks)} total tracks for genres '{', '.join(genres)}'")
        if not all_tracks:
            scheduler_logger.warning(f"⚠️ No tracks found for genres: {', '.join(genres)}")
            return

        filtered_tracks, filter_metadata = await apply_genre_mix_filter(
            source_tracks=all_tracks,
            target_playlist_size=playlist_length,
            nav_client=nav_client,
            ai_client=ai_client,
            settings=settings,
        )

        curated_track_ids, description = await curate_genre_mix_wrapper(
            candidate_tracks=filtered_tracks,
            num_tracks=playlist_length,
            ai_client=ai_client,
            playlist=playlist,
            settings=settings,
        )

        if not curated_track_ids:
            scheduler_logger.warning(f"⚠️ No curated tracks generated for Genre Mix {playlist.get('navidrome_playlist_id')}")
            return

        from ..playlist_metadata import resolve_refresh_description

        comment_to_use = resolve_refresh_description(
            existing_description=playlist.get("description"),
            generated_description=description,
            metadata_overrides={"description": bool(playlist.get("description"))},
        )
        await nav_client.update_playlist(
            playlist_id=playlist.get("navidrome_playlist_id"),
            track_ids=curated_track_ids,
            comment=comment_to_use,
        )

        track_titles = []
        track_id_to_title = {track["id"]: track["title"] for track in all_tracks}
        for track_id in curated_track_ids:
            if track_id in track_id_to_title:
                track_titles.append(track_id_to_title[track_id])

        await db.update_playlist_content(
            navidrome_playlist_id=playlist.get("navidrome_playlist_id"),
            songs=track_titles,
            description=comment_to_use,
        )
        scheduler_logger.info(f"✅ Successfully refreshed Genre Mix playlist {playlist.get('navidrome_playlist_id')}")
    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing Genre Mix playlist {playlist.get('navidrome_playlist_id')}: {e}")
