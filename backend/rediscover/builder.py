"""Builder and refresh logic for 'Re-Discover' (v2) playlists.

Legacy ``"rediscover"`` playlists (stored with that type) are handled here by
mapping them onto the v2 processor, preserving behaviour for existing rows while
the legacy ``RediscoverWeekly`` class has been removed.
"""
import logging
from typing import Any, Dict

from ..database import DatabaseManager
from ..core.dependencies import get_ai_client
from ..core.server_router import get_server_client
from ..core.scheduler import calculate_next_refresh
from .processor import ReDiscoverV2Processor


scheduler_logger = logging.getLogger("scheduler")

FREQUENCY_NAMES = {
    "daily": "Re-Discover Daily ✨",
    "weekly": "Re-Discover Weekly ✨",
    "monthly": "Re-Discover Monthly ✨",
    "never": "Re-Discover ✨",
}


def _playlist_name_for(frequency: str, is_fallback: bool) -> str:
    name = FREQUENCY_NAMES.get(frequency, "Re-Discover Weekly ✨")
    if is_fallback:
        name += " (Fallback)"
    return name


async def create_rediscover_playlist_v2(
    request, db: DatabaseManager
) -> Dict[str, Any]:
    """Create a Re-Discover Weekly v2.0 playlist in Navidrome."""
    scheduler_logger.info(
        f"🎵 Starting Re-Discover v2.0 playlist creation with length {request.playlist_length}, "
        f"library_ids: {request.library_ids}"
    )
    server_client = get_server_client()
    ai_client = get_ai_client()

    user_id = await db.get_or_create_user_id()
    server_id = server_client.base_url or "unknown_server"

    processor = ReDiscoverV2Processor(server_client, ai_client, db)
    playlist_data = await processor.generate_playlist(user_id, server_id, request.library_ids)
    tracks = playlist_data.get("tracks", [])

    if not tracks:
        scheduler_logger.error("❌ No tracks generated for Re-Discover Weekly v2.0")
        raise ValueError("No tracks found for Re-Discover Weekly v2.0")

    scheduler_logger.info(f"✅ Generated {len(tracks)} tracks for Re-Discover Weekly v2.0")

    ai_description = playlist_data.get("description", "")
    ai_curated = any(track.get("ai_curated", False) for track in tracks)
    if ai_curated:
        track_description = next(
            (track.get("ai_description", "") for track in tracks if track.get("ai_curated", False) and track.get("ai_description")),
            "",
        )
        if track_description:
            ai_description = track_description

    scheduler_logger.info(f"🎵 AI curated: {ai_curated}, description length: {len(ai_description)}")

    frequency = request.refresh_frequency
    playlist_name = _playlist_name_for(frequency, playlist_data.get("is_fallback", False))
    scheduler_logger.info(f"📝 Creating playlist: {playlist_name}")

    track_ids = [track["id"] for track in tracks]
    scheduler_logger.info(f"🎵 Track IDs: {track_ids[:5]}... (total: {len(track_ids)})")

    comment_to_use = ai_description if ai_description else f"Theme: {playlist_data.get('theme', 'Mixed')}"
    scheduler_logger.info(f"💬 Creating Re-Discover v2.0 playlist with comment (length: {len(comment_to_use)})")

    navidrome_playlist_id = await server_client.create_playlist(
        name=playlist_name,
        track_ids=track_ids,
        comment=comment_to_use,
    )
    scheduler_logger.info(f"✅ Navidrome playlist created: {navidrome_playlist_id}")

    track_titles = [track.get("title", "Unknown") for track in tracks]
    scheduler_logger.info(f"📊 Storing {len(track_titles)} track titles in database")

    curation_settings = {
        "playlist_length": len(tracks),
        "library_ids": request.library_ids,
        "refresh_frequency": frequency,
    }
    playlist_record = await db.create_playlist(
        artist_id="rediscover_v2",
        playlist_name=playlist_name,
        songs=track_titles,
        description=ai_description,
        navidrome_playlist_id=navidrome_playlist_id,
        playlist_length=len(tracks),
        library_ids=request.library_ids,
        curation_settings=curation_settings,
        playlist_type="rediscover_weekly_v2",
    )
    scheduler_logger.info(f"💾 Database playlist created: {playlist_record}")

    if frequency != "never":
        scheduler_logger.info(f"⏰ Setting up {frequency} refresh schedule")
        from ..core.scheduler import sync_playlist_job
        from ..core.schedule_spec import spec_from_frequency

        spec = spec_from_frequency(frequency)
        schedule_row = await db.upsert_schedule(
            playlist_type="rediscover_weekly_v2",
            navidrome_playlist_id=navidrome_playlist_id,
            refresh_frequency=frequency,
            next_refresh=calculate_next_refresh(frequency),
            schedule_json=spec.model_dump_json() if spec else None,
        )
        sync_playlist_job(schedule_row)
        scheduler_logger.info(f"✅ Scheduled playlist created")

    return {
        "message": f"Re-Discover Weekly v2.0 playlist created successfully with {len(tracks)} tracks",
        "playlist_id": navidrome_playlist_id,
        "track_count": len(tracks),
        "theme": playlist_data.get("theme", "Mixed"),
        "mode": playlist_data.get("mode", "Unknown"),
        "is_fallback": playlist_data.get("is_fallback", False),
    }


async def refresh_rediscover_playlist(playlist: Dict[str, Any], db: DatabaseManager) -> int:
    """Refresh a Re-Discover Weekly playlist (legacy or v2) using the v2 processor.

    Args:
        playlist: Playlist row from ``get_playlist_by_navidrome_id_with_schedule_info``.
        db: Database manager.

    Returns:
        The number of tracks written to the playlist.

    Raises:
        ValueError: If the processor produced no tracks.
    """
    navidrome_playlist_id = playlist.get("navidrome_playlist_id")
    scheduler_logger.info(f"🔄 Starting refresh for playlist ID: {navidrome_playlist_id}")

    server_client = get_server_client()
    ai_client = get_ai_client()

    settings = playlist.get("curation_settings") or {}
    library_ids = settings.get("library_ids") or []
    original_length = settings.get("playlist_length") or playlist.get("playlist_length", 20)
    scheduler_logger.info(f"🎯 Using original playlist length: {original_length}")

    previous_songs = playlist.get("songs", [])[:10]
    scheduler_logger.info(
        f"🔄 Re-Discover v2.0 refresh context - Previous tracks: {len(previous_songs)}, Library IDs: {library_ids}"
    )

    user_id = await db.get_or_create_user_id()
    server_id = server_client.base_url or "unknown_server"

    processor = ReDiscoverV2Processor(server_client, ai_client, db)
    result = await processor.generate_playlist(user_id, server_id, library_ids if library_ids else None)

    tracks = result.get("tracks", [])
    if not tracks:
        raise ValueError("No tracks generated")

    scheduler_logger.info(f"🎵 Generated {len(tracks)} new tracks for refresh")
    if len(tracks) != original_length:
        scheduler_logger.warning(f"⚠️ Generated {len(tracks)} tracks but user requested {original_length}")
    else:
        scheduler_logger.info(f"✅ Generated exact number of requested tracks: {len(tracks)}")

    first_track = tracks[0]
    ai_description = first_track.get("ai_description", "")
    ai_curated = first_track.get("ai_curated", False)

    track_ids = [track["id"] for track in tracks]
    comment_to_use = ai_description if (ai_description and ai_curated) else "Re-Discover Weekly v2.0 - Automatically refreshed"
    await server_client.update_playlist(
        playlist_id=navidrome_playlist_id,
        track_ids=track_ids,
        comment=comment_to_use,
    )

    track_titles = [track["title"] for track in tracks]
    description_to_store = ai_description if ai_curated else "Algorithmic selection"
    await db.update_playlist_content(
        navidrome_playlist_id=navidrome_playlist_id,
        songs=track_titles,
        description=description_to_store,
    )

    scheduler_logger.info(f"✅ Successfully refreshed playlist {navidrome_playlist_id}")
    return len(track_titles)
