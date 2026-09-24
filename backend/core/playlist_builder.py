"""Generic playlist build & refresh pipeline.

Every playlist type shares the same high-level flow:

    fetch candidate tracks -> (optional) smart-filter -> AI curate ->
    create/update Navidrome playlist -> persist to local DB -> schedule refresh

This module captures that flow once. Each type supplies a small
``PlaylistTypeConfig`` describing how to perform the type-specific steps, so the
per-type ``builder`` modules stay tiny and the duplicated ~3x pipelines that used
to live in ``main.py`` disappear.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Dict, List, Optional, Tuple

from ..database import DatabaseManager
from ..core.dependencies import get_ai_client
from ..core.server_router import get_server_client
from ..playlist_metadata import resolve_refresh_description


scheduler_logger = logging.getLogger("scheduler")


@dataclass
class PlaylistTypeConfig:
    """Describes how to build/refresh one playlist type.

    Attributes:
        type_key: The ``playlist_type`` stored in the database (e.g. ``"this_is"``).
        fetch_tracks: Async callable returning candidate tracks for a build/refresh.
        curate: Async callable that takes the (filtered) candidate tracks and returns
            ``(track_ids, description)``.
        build_playlist_name: Returns the playlist name (used on creation).
        default_refresh_frequency: Frequency used when the request does not specify one.
        schedule_on_create: Whether to register a scheduled refresh on creation.
        extra_curation_settings: Optional callable returning extra fields to persist
            in ``curation_settings`` (e.g. genre-specific filters).
        apply_smart_filter: Optional callable that filters candidate tracks before
            curation. Receives the source tracks and returns ``(tracks, metadata)``.
    """

    type_key: str
    fetch_tracks: Callable[..., Awaitable[List[Dict[str, Any]]]]
    curate: Callable[..., Awaitable[Tuple[List[str], str]]]
    build_playlist_name: Callable[..., str]
    default_refresh_frequency: str = "none"
    schedule_on_create: bool = True
    extra_curation_settings: Optional[Callable[..., Dict[str, Any]]] = None
    apply_smart_filter: Optional[Callable[..., Awaitable[Tuple[List[Dict[str, Any]], Dict[str, Any]]]]] = None
    artist_id_resolver: Optional[Callable[..., str]] = None


async def build_playlist(
    config: PlaylistTypeConfig,
    db: DatabaseManager,
    *,
    playlist_length: int,
    library_ids: List[str],
    refresh_frequency: Optional[str] = None,
    request: Optional[Any] = None,
    artist_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new playlist of the given type end-to-end.

    Returns a dict suitable for the API response (includes ``navidrome_playlist_id``
    and ``refresh_frequency``). ``artist_name`` is resolved by the API route before
    starting the asynchronous build pipeline.
    """
    nav_client = get_server_client()
    ai_client = get_ai_client()

    # 1. Fetch candidate tracks (type-specific).
    source_tracks = await config.fetch_tracks(
        request=request, library_ids=library_ids, playlist_length=playlist_length
    )
    if not source_tracks:
        raise ValueError(f"No tracks found for playlist type '{config.type_key}'")

    # 2. Optional smart filtering (type-specific).
    if config.apply_smart_filter is not None:
        candidate_tracks, filter_metadata = await config.apply_smart_filter(
            source_tracks=source_tracks,
            target_playlist_size=playlist_length,
            request=request,
            nav_client=nav_client,
            ai_client=ai_client,
        )
        _log_filter_metadata(config.type_key, filter_metadata)
    else:
        candidate_tracks = source_tracks

    # 3. AI curation (type-specific).
    curated_track_ids, description = await config.curate(
        candidate_tracks=candidate_tracks,
        num_tracks=playlist_length,
        request=request,
        ai_client=ai_client,
        artist_name=artist_name,
    )

    if not curated_track_ids:
        if description and "Playlist generation failed" in description:
            raise ValueError(f"Playlist generation failed: {description}")
        raise ValueError("AI curation failed to return any tracks")

    # 4. Build the playlist name.
    playlist_name = config.build_playlist_name(
        request=request,
        candidate_tracks=candidate_tracks,
        description=description,
        artist_name=artist_name,
    )

    # 5. Create the playlist in Navidrome.
    navidrome_playlist_id = await nav_client.create_playlist(
        name=playlist_name,
        track_ids=curated_track_ids,
        comment=description if description else None,
    )

    # 6. Persist to the local database.
    track_titles = _titles_for_ids(curated_track_ids, source_tracks)
    curation_settings: Dict[str, Any] = {
        "playlist_length": playlist_length,
        "library_ids": library_ids,
        "refresh_frequency": refresh_frequency or config.default_refresh_frequency,
    }
    if config.extra_curation_settings is not None:
        curation_settings.update(
            config.extra_curation_settings(
                request=request,
                playlist_length=playlist_length,
                artist_name=artist_name,
            )
        )

    playlist = await db.create_playlist(
        artist_id=_artist_id_for(config, request, playlist_name),
        playlist_name=playlist_name,
        songs=track_titles,
        description=description,
        navidrome_playlist_id=navidrome_playlist_id,
        playlist_length=playlist_length,
        library_ids=library_ids,
        curation_settings=curation_settings,
        playlist_type=config.type_key,
    )

    # 7. Optionally schedule a refresh.
    frequency = refresh_frequency or config.default_refresh_frequency
    if config.schedule_on_create and frequency not in ("none", "never"):
        from ..core.scheduler import calculate_next_refresh, schedule_playlist_refresh

        next_refresh = calculate_next_refresh(frequency)
        await db.create_scheduled_playlist(
            playlist_type=config.type_key,
            navidrome_playlist_id=navidrome_playlist_id,
            refresh_frequency=frequency,
            next_refresh=next_refresh,
        )
        schedule_playlist_refresh()
        scheduler_logger.info(f"📅 Scheduled {frequency} refresh for {config.type_key} playlist: {playlist_name}")

    # 8. Build the response dict.
    playlist_dict = playlist.dict() if hasattr(playlist, "dict") else playlist.__dict__
    playlist_dict["navidrome_playlist_id"] = navidrome_playlist_id
    playlist_dict["refresh_frequency"] = frequency
    if frequency != "none":
        playlist_dict["next_refresh"] = calculate_next_refresh(frequency).isoformat()
    return playlist_dict


async def refresh_playlist(
    config: PlaylistTypeConfig,
    playlist: Dict[str, Any],
    db: DatabaseManager,
) -> None:
    """Refresh an existing playlist of the given type using its saved settings."""
    nav_client = get_server_client()
    ai_client = get_ai_client()

    settings = playlist.get("curation_settings") or {}
    library_ids = settings.get("library_ids") or []
    playlist_length = settings.get("playlist_length") or playlist.get("playlist_length") or 25

    # 1. Re-fetch candidate tracks (type-specific; refresh variant).
    source_tracks = await config.fetch_tracks(
        request=None,
        library_ids=library_ids,
        playlist_length=playlist_length,
        playlist=playlist,
        settings=settings,
    )
    if not source_tracks:
        scheduler_logger.warning(f"⚠️ No tracks found for {config.type_key} refresh")
        return

    # 2. Optional smart filtering (type-specific).
    if config.apply_smart_filter is not None:
        candidate_tracks, filter_metadata = await config.apply_smart_filter(
            source_tracks=source_tracks,
            target_playlist_size=playlist_length,
            request=None,
            nav_client=nav_client,
            ai_client=ai_client,
            settings=settings,
        )
    else:
        candidate_tracks = source_tracks

    # 3. AI curation (type-specific; refresh variant with variety context).
    curated_track_ids, description = await config.curate(
        candidate_tracks=candidate_tracks,
        num_tracks=playlist_length,
        request=None,
        ai_client=ai_client,
        playlist=playlist,
        settings=settings,
    )

    if not curated_track_ids:
        scheduler_logger.warning(f"⚠️ No curated tracks generated for {config.type_key} refresh")
        return

    # 4. Update the existing Navidrome playlist.
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

    # 5. Persist the new content locally.
    track_titles = _titles_for_ids(curated_track_ids, source_tracks)
    await db.update_playlist_content(
        navidrome_playlist_id=playlist.get("navidrome_playlist_id"),
        songs=track_titles,
        description=comment_to_use,
    )
    scheduler_logger.info(f"✅ Successfully refreshed {config.type_key} playlist {playlist.get('navidrome_playlist_id')}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _titles_for_ids(track_ids: List[str], source_tracks: List[Dict[str, Any]]) -> List[str]:
    """Map curated track IDs back to their titles, preserving curated order."""
    track_id_to_title = {track["id"]: track["title"] for track in source_tracks}
    return [track_id_to_title[tid] for tid in track_ids if tid in track_id_to_title]


def _artist_id_for(config: PlaylistTypeConfig, request: Optional[Any], playlist_name: str) -> str:
    """Compute the ``artist_id`` column value used for storage."""
    if config.artist_id_resolver is not None:
        return config.artist_id_resolver(request=request, playlist_name=playlist_name)
    # Types that are not artist-based (genre_mix, rediscover) override this via
    # their own builder if needed; the default uses the request's primary id.
    if request is not None and getattr(request, "artist_ids", None):
        return request.artist_ids[0]
    return config.type_key


def _log_filter_metadata(type_key: str, filter_metadata: Dict[str, Any]) -> None:
    """Log smart-filtering results at a glance."""
    if not filter_metadata.get("filtered"):
        scheduler_logger.info(f"✅ No filtering needed: {filter_metadata.get('source_count')} tracks below threshold")
        return
    sent = filter_metadata.get("sent_count")
    source = filter_metadata.get("source_count")
    scheduler_logger.info(f"🎯 Smart filtering applied for {type_key}: {source} → {sent} tracks")
